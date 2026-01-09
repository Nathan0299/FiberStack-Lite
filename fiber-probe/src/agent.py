"""
Fiber-Probe Agent (Day 81 — Low-Resource Optimized)

Features:
- LEAN_MODE: Reduced metadata, batching
- Systemd watchdog integration
- Windowed circuit breaker
- Memory backpressure
- Prometheus metrics
"""

import asyncio
import aiohttp
import psutil
import time
import uuid
import os
import ssl
import gc
from collections import deque
from datetime import datetime, timezone

import sys
import uuid
# Day 87: Unified logging
sys.path.insert(0, '/Users/macpro/FiberStack-Lite')
try:
    from fiber_shared.log_lib import get_logger, generate_trace_id, set_trace_id
    logger = get_logger("fiber-probe")
except ImportError:
    sys.path.insert(0, '/app/fiber-logging/src')
    from logger import get_logger
    logger = get_logger("fiber-probe", env=os.getenv("ENV", "dev"))
    def generate_trace_id(): return str(uuid.uuid4())[:8]
    def set_trace_id(t): pass
try:
    from profiler import ResourceProfiler, start_metrics_server, PAYLOAD_SIZE
    PROFILER_ENABLED = True
except ImportError:
    PROFILER_ENABLED = False

# Optional: Systemd notifier
try:
    import sdnotify
    NOTIFIER = sdnotify.SystemdNotifier()
except ImportError:
    NOTIFIER = None

logger = get_logger("fiber-probe", env=os.getenv("ENV", "dev"))

# === CONFIGURATION ===
API_URL = os.getenv("API_URL", "http://localhost:8000/api/push")
NODE_ID = os.getenv("NODE_ID", str(uuid.uuid4()))
COUNTRY = os.getenv("COUNTRY", "GH")
REGION = os.getenv("REGION", "Accra")

# Timing
INTERVAL = int(os.getenv("INTERVAL", "60"))
WATCHDOG_USEC = int(os.getenv("WATCHDOG_USEC", "0"))
HEARTBEAT_INTERVAL = (WATCHDOG_USEC / 2_000_000) if WATCHDOG_USEC else INTERVAL

# Lean Mode
LEAN_MODE = os.getenv("LEAN_MODE", "false").lower() == "true"
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))

# Retry & Circuit Breaker
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_BACKOFF_BASE = float(os.getenv("RETRY_BACKOFF_BASE", "2.0"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))
CIRCUIT_WINDOW_SEC = 30
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_PAUSE_SEC = 60
CIRCUIT_SUCCESS_RESET = 3

# Backpressure
MEMORY_LIMIT_BYTES = int(os.getenv("MEMORY_LIMIT_BYTES", "0"))  # cgroup limit
BACKPRESSURE_THRESHOLD = 0.80  # 80%

# Connection Pool Hysteresis
POOL_HYSTERESIS_SEC = 60


class CircuitBreaker:
    """Windowed circuit breaker with success reset."""
    
    def __init__(self):
        self.failures = deque(maxlen=100)
        self.consecutive_successes = 0
        self.paused_until = 0
    
    def record(self, success: bool):
        now = time.time()
        self.failures.append((now, not success))
        
        if success:
            self.consecutive_successes += 1
            if self.consecutive_successes >= CIRCUIT_SUCCESS_RESET:
                self.paused_until = 0
        else:
            self.consecutive_successes = 0
            recent_failures = sum(1 for t, f in self.failures if f and now - t < CIRCUIT_WINDOW_SEC)
            if recent_failures >= CIRCUIT_FAILURE_THRESHOLD:
                self.paused_until = now + CIRCUIT_PAUSE_SEC
                logger.warning(f"Circuit breaker OPEN for {CIRCUIT_PAUSE_SEC}s")
    
    def is_open(self) -> bool:
        return time.time() < self.paused_until


class ConnectionPoolManager:
    """Dynamic connection pool with hysteresis."""
    
    def __init__(self):
        self.size = 1
        self.last_resize = 0
    
    def get_size(self, queue_depth: int) -> int:
        now = time.monotonic()
        if now - self.last_resize < POOL_HYSTERESIS_SEC:
            return self.size
        
        if queue_depth == 0:
            new_size = 1
        elif queue_depth <= 50:
            new_size = 2
        elif queue_depth <= 200:
            new_size = 3
        else:
            new_size = 4
        
        if new_size != self.size:
            logger.info(f"Pool resized: {self.size} -> {new_size}")
            self.size = new_size
            self.last_resize = now
        
        return self.size


# Global state
circuit_breaker = CircuitBreaker()
pool_manager = ConnectionPoolManager()
profiler = None
batch_buffer = []
original_batch_size = BATCH_SIZE
original_interval = INTERVAL


def notify_watchdog(status: str = None):
    """Send systemd watchdog notifications."""
    if NOTIFIER:
        NOTIFIER.notify("WATCHDOG=1")
        if status:
            NOTIFIER.notify(f"STATUS={status}")


def check_backpressure():
    """Check memory and apply backpressure if needed."""
    global BATCH_SIZE, INTERVAL
    
    if not MEMORY_LIMIT_BYTES:
        return False
    
    rss = psutil.Process().memory_info().rss
    usage_pct = rss / MEMORY_LIMIT_BYTES
    
    if usage_pct >= BACKPRESSURE_THRESHOLD:
        BATCH_SIZE = max(1, original_batch_size // 2)
        INTERVAL = original_interval * 2
        logger.warning(f"Backpressure active: RSS={rss/1e6:.1f}MB ({usage_pct*100:.0f}%)")
        if profiler:
            profiler.set_backpressure(True)
        return True
    else:
        BATCH_SIZE = original_batch_size
        INTERVAL = original_interval
        if profiler:
            profiler.set_backpressure(False)
        return False


async def collect_metrics():
    """Collect metrics with LEAN_MODE support."""
    # Simulated metrics
    latency = 20.0 + (time.time() % 130)
    packet_loss = 0.0 if (int(time.time()) % 20) else 1.5
    uptime = 100.0 - (psutil.cpu_percent() / 10.0)
    
    trace_id = generate_trace_id()
    
    payload = {
        "node_id": NODE_ID,
        "country": COUNTRY,
        "region": REGION,
        "latency_ms": round(latency, 2),
        "uptime_pct": round(max(0, uptime), 2),
        "packet_loss": round(packet_loss, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "_meta": {"trace_id": trace_id}
    }
    
    if not LEAN_MODE:
        payload["metadata"] = {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent
        }
    
    return payload



# === AUTH & TLS ===
PROBE_USER = os.getenv("PROBE_USER", "admin")
PROBE_SECRET = os.getenv("PROBE_SECRET", "admin")
API_SSL_CA = os.getenv("API_SSL_CA")

class AuthClient:
    """Handles Dual-Token Auth: Login, Refresh, Rotation."""
    def __init__(self):
        self.access_token = None
        self.refresh_token = None
        self.access_exp = 0
        self.base_url = API_URL.replace("/push", "") # strict assumption for now
        self.ssl_ctx = self._create_ssl_ctx()

    def _create_ssl_ctx(self):
        if not API_SSL_CA: return None # Use default (system CAs or None)
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=API_SSL_CA)
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx

    def get_headers(self):
        if not self.access_token: return {}
        return {"Authorization": f"Bearer {self.access_token}"}

    async def login(self, session):
        """Initial Login."""
        try:
            url = f"{self.base_url}/auth/login"
            payload = {"username": PROBE_USER, "password": PROBE_SECRET}
            async with session.post(url, json=payload, ssl=self.ssl_ctx) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._update_tokens(data)
                    logger.info("Logged in successfully")
                    return True
                logger.error(f"Login failed: {resp.status}")
        except Exception as e:
            logger.error(f"Login error: {e}")
        return False

    async def refresh(self, session):
        """Rotate Refresh Token."""
        if not self.refresh_token: return await self.login(session)
        
        try:
            url = f"{self.base_url}/auth/refresh"
            payload = {"refresh_token": self.refresh_token}
            async with session.post(url, json=payload, ssl=self.ssl_ctx) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._update_tokens(data)
                    if profiler: profiler.record_token_refresh(success=True)
                    logger.info("Token refreshed successfully")
                    return True
                elif resp.status == 401:
                    logger.warning("Refresh token expired/revoked. Re-logging in.")
                    if profiler: profiler.record_token_refresh(success=False)
                    return await self.login(session)
        except Exception as e:
             logger.error(f"Refresh error: {e}")
        return False

    def _update_tokens(self, data):
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        # Set expiry (subtract buffer)
        self.access_exp = time.time() + data.get("expires_in", 900)

    def needs_refresh(self):
        # Rotate at 80% TTL (approx 3 mins buffer for 15m token)
        return time.time() > (self.access_exp - 300)

auth_client = AuthClient()


async def send_metrics(session, metrics_batch):
    """Send metrics with circuit breaker and TLS error tracking."""
    if circuit_breaker.is_open():
        return False
    
    # 1. Proactive Refresh
    if auth_client.needs_refresh():
        await auth_client.refresh(session)
        
    payload = metrics_batch if len(metrics_batch) > 1 else metrics_batch[0]
    payload_size = len(str(payload).encode())
    
    if profiler: profiler.record_payload(payload_size)
    
    for attempt in range(MAX_RETRIES):
        try:
            headers = auth_client.get_headers()
            # Day 87: Unified Trace Propagation
            try:
                # payload can be list or dict
                item = payload[0] if isinstance(payload, list) else payload
                trace_id = item.get("_meta", {}).get("trace_id")
                if trace_id:
                     headers["X-Trace-ID"] = trace_id
            except Exception:
                pass
                
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            
            async with session.post(API_URL, json=payload, headers=headers, timeout=timeout, ssl=auth_client.ssl_ctx) as response:
                if response.status == 202:
                    circuit_breaker.record(True)
                    logger.info(f"Sent {len(metrics_batch)} metrics ({payload_size}B)")
                    return True
                
                if response.status == 401:
                    logger.warning("401 Unauthorized - Forcing Refresh")
                    if await auth_client.refresh(session):
                        continue # Retry with new token
                
                circuit_breaker.record(False)
                logger.warning(f"HTTP {response.status} on attempt {attempt + 1}")
                
        except ssl.SSLCertVerificationError as e:
            reason = 'cert_expired' if 'expired' in str(e).lower() else 'chain_invalid'
            if profiler: profiler.record_tls_error(reason)
            logger.error(f"TLS error: {reason}")
            circuit_breaker.record(False)
            
        except ssl.SSLError as e:
            reason = 'hostname_mismatch' if 'hostname' in str(e).lower() else 'ssl_unknown'
            if profiler: profiler.record_tls_error(reason)
            circuit_breaker.record(False)
            
        except asyncio.TimeoutError:
            logger.warning(f"Timeout on attempt {attempt + 1}")
            circuit_breaker.record(False)
            
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            circuit_breaker.record(False)
        
        if profiler: profiler.record_retry()
        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(RETRY_BACKOFF_BASE ** attempt)
    
    return False


async def main():
    global profiler, batch_buffer
    
    if NOTIFIER:
        NOTIFIER.notify("READY=1")
        NOTIFIER.notify(f"MAINPID={os.getpid()}")
    
    if PROFILER_ENABLED:
        start_metrics_server()
        profiler = ResourceProfiler(NODE_ID, LEAN_MODE)
    
    logger.info(f"Probe starting: {NODE_ID} ({COUNTRY}/{REGION})")
    
    connector = aiohttp.TCPConnector(limit=pool_manager.size)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Initial Login
        await auth_client.login(session)
        
        cycle = 0
        while True:
            cycle += 1
            start = time.time()
            notify_watchdog(f"Cycle {cycle}")
            check_backpressure()
            
            try:
                metrics = await collect_metrics()
                batch_buffer.append(metrics)
                if len(batch_buffer) >= BATCH_SIZE:
                    await send_metrics(session, batch_buffer)
                    batch_buffer = []
            except Exception as e:
                logger.error(f"Cycle failed: {e}")
            
            if profiler:
                profiler.collect()
                profiler.set_circuit_status(circuit_breaker.is_open())
            
            elapsed = time.time() - start
            await asyncio.sleep(max(0, INTERVAL - elapsed))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Probe stopping...")
