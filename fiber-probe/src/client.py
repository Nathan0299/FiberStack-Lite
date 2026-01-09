import asyncio
import aiohttp
import logging
import uuid
import time
from datetime import datetime, timezone
import uuid
from typing import List, Dict, Any
from monitor import StatsTracker, SystemMonitor

logger = logging.getLogger("fiber-probe.client")

class FederationClient:
    """
    Handles robust metric pushing to an upstream target.
    Features:
    - Bearer Auth
    - Batching (Payload construction)
    - Idempotency (X-Batch-ID)
    - Exponential Backoff & Retry
    - Circuit Breaker (Basic)
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.url = config["url"]
        self.auth_token = self._resolve_token(config.get("auth", {}))
        # DEBUG: Log the resolved token (masked)
        token_len = len(self.auth_token)
        logger.info(f"Resolved auth token for {name}: {'Found' if token_len > 0 else 'EMPTY'} (Length: {token_len})")
        
        # Resilience settings
        self.retry_policy = config.get("retry", {})
        self.max_attempts = self.retry_policy.get("max_attempts", 3)
        self.base_delay = self.retry_policy.get("base_delay_ms", 500) / 1000.0
        self.max_delay = self.retry_policy.get("max_delay_ms", 10000) / 1000.0
        
        # Observability state
        self.consecutive_failures = 0
        self.circuit_open = False
        self.circuit_reset_time = 0

        # Day 54: Self-Monitoring
        # We derive node_id from config or generate one. 
        # Note: In real usage, node_id usually comes from higher up, but client needs it for SystemMonitor.
        # We'll assume the caller passes node_id in config or we generate a temp one (monitor won't allow None)
        self.node_id = config.get("node_id", "unknown-node") 
        self.stats = StatsTracker() 
        self.monitor = SystemMonitor(self, self.node_id)
        self._monitor_task = None
    
    async def start(self):
        """Start background tasks."""
        self._monitor_task = asyncio.create_task(self.monitor.start())

    async def stop(self):
        """Stop background tasks."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    def _resolve_token(self, auth_config: Dict) -> str:
        """Resolve auth token from env var."""
        if auth_config.get("type") == "bearer":
            import os
            env_var = auth_config.get("token_env")
            if env_var:
                return os.getenv(env_var, "")
        return ""

    def _calculate_signature(self, batch_id: str, timestamp: str, nonce: str, payload_str: str) -> str:
        """Calculate HMAC-SHA256 signature."""
        import hmac
        import hashlib
        import os
        
        secret = os.getenv("FEDERATION_SECRET")
        if not secret:
            raise ValueError("CRITICAL: FEDERATION_SECRET not found in environment")
        # Canonical String: Method + Path + Timestamp + Nonce + BodyHash
        # Since client knows path from URL, we'll just sign key fields + body
        body_hash = hashlib.sha256(payload_str.encode()).hexdigest()
        message = f"{batch_id}:{timestamp}:{nonce}:{body_hash}"
        
        signature = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature

    async def push_batch(self, session: aiohttp.ClientSession, batch: List[Dict], node_id: str) -> bool:
        """
        Push a batch of metrics with retry logic and HMAC signing.
        Returns True if successful, False otherwise.
        """
        import json
        
        if self._is_circuit_open():
            logger.warning(f"Circuit open for target {self.name}, skipping push.")
            return False

        if not batch:
            return True

        batch_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        nonce = str(uuid.uuid4())
        
        # Prepare payload
        payload_dict = {
            "node_id": node_id,
            "metrics": batch
        }
        # Canonical serialization (no spaces, sorted keys)
        payload_str = json.dumps(payload_dict, separators=(',', ':'), sort_keys=True)
        
        # Calculate Signature
        signature = self._calculate_signature(batch_id, timestamp, nonce, payload_str)
        
        headers = {
            "Content-Type": "application/json",
            "X-Batch-ID": batch_id,
            "X-Fiber-Timestamp": timestamp,
            "X-Fiber-Nonce": nonce,
            "X-Fiber-Signature": signature
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        for attempt in range(1, self.max_attempts + 1):
            try:
                # Use data=payload_str to ensure byte-perfect signing match
                async with session.post(self.url, data=payload_str, headers=headers, timeout=10) as resp:
                    if resp.status in (200, 201, 202):
                        self._record_success(len(batch), batch_id)
                        return True
                    
                    # Unrecoverable errors (400, 401, 403, 422)
                    if 400 <= resp.status < 500 and resp.status != 408:
                        text = await resp.text()
                        logger.error(
                            f"Target {self.name} rejected batch {batch_id} (HTTP {resp.status}): {text[:100]}", 
                            extra={"target": self.name, "status": resp.status}
                        )
                        return False
                    
                    # Server errors (5xx) -> Retry
                    logger.warning(f"Target {self.name} failed (HTTP {resp.status}), attempt {attempt}/{self.max_attempts}")

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"Target {self.name} network error: {e}, attempt {attempt}/{self.max_attempts}")
            except Exception as e:
                logger.error(f"Target {self.name} unexpected error: {e}")
                return False

            # Backoff before next retry
            if attempt < self.max_attempts:
                delay = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
                await asyncio.sleep(delay)

        self._record_failure()
        return False

    def _record_success(self, count: int, batch_id: str):
        """Reset failure counters and log success."""
        self.consecutive_failures = 0
        self.stats.inc_success()
        if self.circuit_open:
            logger.info(f"Target {self.name} circuit closed (recovered).")
            self.circuit_open = False
            
        logger.info(
            f"Pushed {count} metrics to {self.name}", 
            extra={"target": self.name, "batch_id": batch_id, "count": count}
        )

    def _record_failure(self):
        """Increment failure counters and trip circuit if needed."""
        self.consecutive_failures += 1
        self.stats.inc_error() # Day 54: Monotonic Counter
        threshold = 5 
        if self.consecutive_failures >= threshold:
            reset_ms = 30000 
            self.circuit_open = True
            self.circuit_reset_time = time.time() + (reset_ms / 1000.0)
            logger.error(f"Target {self.name} circuit tripped! Too many failures ({self.consecutive_failures}).")

    def _is_circuit_open(self) -> bool:
        if not self.circuit_open:
            return False
        
        # Check if reset timeout passed
        if time.time() > self.circuit_reset_time:
             # Half-open: allow one request implicitly by saying it's closed?
             # For simplicity, just auto-close on time expiry for next attempt
             # Ideally we'd have a HALF_OPEN state, but for MVP Auto-Reset is fine.
             self.circuit_open = False
             self.consecutive_failures = 0
             return False
        
        return True
