"""
Day 77: Failover Controller with Stickiness

Implements priority-based failover with:
- Per-target timeouts
- Exponential backoff with jitter
- Monotonic clock for stickiness
- Prometheus metrics export
- Rollback-safe FanOutController alternative
"""

import asyncio
import logging
import random
import time
from typing import List, Dict, Any, Tuple, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger("fiber-probe.failover")

# Import metrics (will fail gracefully if not available)
try:
    from metrics import (
        FAILOVER_EVENT_COUNTER,
        FAILOVER_FAILURE_COUNTER,
        ACTIVE_TARGET_GAUGE,
        CONNECTION_STATE_GAUGE
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    logger.warning("Prometheus metrics not available")


class BaseController(ABC):
    """Abstract base for push controllers."""
    
    @abstractmethod
    async def push(self, session, batch: List[Dict], node_id: str) -> Tuple[bool, Optional[str]]:
        """Push metrics. Returns (success, active_target_name)."""
        pass
    
    @abstractmethod
    def get_active_target(self) -> Optional[str]:
        """Get currently active target name."""
        pass


class FailoverController(BaseController):
    """
    Priority-based failover controller with stickiness.
    
    Features:
    - Tries targets in priority order
    - Per-target timeout (prevents hangs)
    - Exponential backoff with jitter
    - Stickiness: 120s minimum on secondary before returning
    - Promotion threshold: 5 consecutive successes
    - Uses monotonic clock (immune to system time changes)
    """
    
    # Configuration
    STICKINESS_SEC = 120
    PROMOTION_THRESHOLD = 5
    DEMOTION_THRESHOLD = 3
    TIMEOUT_SEC = 10
    INITIAL_BACKOFF = 1.0
    MAX_BACKOFF = 60.0
    
    def __init__(self, clients: List, node_id: str = "unknown"):
        """
        Initialize failover controller.
        
        Args:
            clients: List of FederationClient instances
            node_id: Probe node ID for metrics labeling
        """
        # Sort by priority (lower = higher priority)
        self.clients = sorted(clients, key=lambda c: getattr(c, 'priority', 99))
        self.node_id = node_id
        
        # State
        self.active_index = 0
        self.cooldown_until = 0.0  # Monotonic time
        self.consecutive_successes = 0
        self.consecutive_failures = 0
        self.backoff_sec = self.INITIAL_BACKOFF
        
        logger.info(f"FailoverController initialized with {len(clients)} targets")
        for i, c in enumerate(self.clients):
            logger.info(f"  [{i}] {c.name} (priority: {getattr(c, 'priority', 99)})")
    
    async def push(self, session, batch: List[Dict], node_id: str) -> Tuple[bool, Optional[str]]:
        """
        Push metrics with failover logic.
        
        Returns:
            Tuple of (success, active_target_name)
        """
        if not self.clients:
            logger.error("No targets configured")
            return False, None
        
        active = self.clients[self.active_index]
        
        # Try active target with timeout
        success = await self._try_push(session, active, batch, node_id)
        
        if success:
            self._record_success()
            self._update_metrics()
            return True, active.name
        
        # Active failed, try fallback
        self._record_failure(active.name)
        return await self._try_fallback(session, batch, node_id)
    
    async def _try_push(self, session, client, batch: List[Dict], node_id: str) -> bool:
        """Attempt push with timeout."""
        try:
            return await asyncio.wait_for(
                client.push_batch(session, batch, node_id),
                timeout=self.TIMEOUT_SEC
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout on {client.name} after {self.TIMEOUT_SEC}s",
                extra={"target": client.name, "timeout": self.TIMEOUT_SEC}
            )
            return False
        except Exception as e:
            logger.error(f"Push error on {client.name}: {e}")
            return False
    
    async def _try_fallback(self, session, batch: List[Dict], node_id: str) -> Tuple[bool, Optional[str]]:
        """Try fallback targets with exponential backoff."""
        # Apply backoff with jitter
        jitter = random.uniform(0.5, 1.5)
        delay = self.backoff_sec * jitter
        logger.debug(f"Backoff: {delay:.2f}s before trying fallback")
        await asyncio.sleep(delay)
        
        # Increase backoff for next failure
        self.backoff_sec = min(self.backoff_sec * 2, self.MAX_BACKOFF)
        
        # Try each fallback target in priority order
        for i, client in enumerate(self.clients):
            if i == self.active_index:
                continue  # Skip current active
            
            success = await self._try_push(session, client, batch, node_id)
            
            if success:
                self._failover_to(i)
                self._update_metrics()
                return True, client.name
        
        logger.error("All targets failed")
        return False, None
    
    def _record_success(self):
        """Record successful push."""
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        self.backoff_sec = self.INITIAL_BACKOFF  # Reset backoff
        
        # Check if we can promote back to primary
        if self.active_index > 0 and self._can_promote():
            self._promote_to_primary()
    
    def _record_failure(self, target_name: str):
        """Record failed push."""
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        
        if METRICS_AVAILABLE:
            FAILOVER_FAILURE_COUNTER.labels(
                node_id=self.node_id,
                target=target_name
            ).inc()
    
    def _failover_to(self, new_index: int):
        """Switch to a new target."""
        old_name = self.clients[self.active_index].name
        new_name = self.clients[new_index].name
        
        self.active_index = new_index
        self.cooldown_until = time.monotonic() + self.STICKINESS_SEC
        self.consecutive_successes = 0
        self.backoff_sec = self.INITIAL_BACKOFF
        
        logger.warning(
            f"FAILOVER: {old_name} → {new_name}",
            extra={
                "event": "failover",
                "from_target": old_name,
                "to_target": new_name,
                "stickiness_until": self.cooldown_until
            }
        )
        
        if METRICS_AVAILABLE:
            FAILOVER_EVENT_COUNTER.labels(
                from_target=old_name,
                to_target=new_name,
                node_id=self.node_id
            ).inc()
    
    def _can_promote(self) -> bool:
        """Check if promotion back to primary is allowed."""
        return (
            self.consecutive_successes >= self.PROMOTION_THRESHOLD and
            time.monotonic() > self.cooldown_until
        )
    
    def _promote_to_primary(self):
        """Promote back to primary target."""
        old_name = self.clients[self.active_index].name
        self.active_index = 0
        new_name = self.clients[0].name
        self.consecutive_successes = 0
        
        logger.info(
            f"PROMOTION: {old_name} → {new_name}",
            extra={
                "event": "promotion",
                "from_target": old_name,
                "to_target": new_name
            }
        )
        
        if METRICS_AVAILABLE:
            FAILOVER_EVENT_COUNTER.labels(
                from_target=old_name,
                to_target=new_name,
                node_id=self.node_id
            ).inc()
    
    def _update_metrics(self):
        """Update Prometheus gauges."""
        if not METRICS_AVAILABLE:
            return
        
        # Active target priority
        active = self.clients[self.active_index]
        ACTIVE_TARGET_GAUGE.labels(node_id=self.node_id).set(
            getattr(active, 'priority', self.active_index + 1)
        )
        
        # Connection states
        for client in self.clients:
            is_healthy = not getattr(client, 'circuit_open', False)
            CONNECTION_STATE_GAUGE.labels(
                node_id=self.node_id,
                target=client.name
            ).set(1 if is_healthy else 0)
    
    def get_active_target(self) -> Optional[str]:
        """Get currently active target name."""
        if self.clients:
            return self.clients[self.active_index].name
        return None


class FanOutController(BaseController):
    """
    Legacy fan-out controller (sends to ALL targets).
    
    Used as fallback when FAILOVER_ENABLED=false.
    """
    
    def __init__(self, clients: List, node_id: str = "unknown"):
        self.clients = clients
        self.node_id = node_id
        logger.info(f"FanOutController initialized with {len(clients)} targets (legacy mode)")
    
    async def push(self, session, batch: List[Dict], node_id: str) -> Tuple[bool, Optional[str]]:
        """Push to all targets (fan-out)."""
        if not self.clients:
            return False, None
        
        tasks = [client.push_batch(session, batch, node_id) for client in self.clients]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r is True)
        any_success = success_count > 0
        
        logger.debug(f"Fan-out: {success_count}/{len(self.clients)} targets succeeded")
        
        # Return first target name for compatibility
        return any_success, self.clients[0].name if any_success else None
    
    def get_active_target(self) -> Optional[str]:
        """In fan-out mode, return 'fan-out' as the active target."""
        return "fan-out"
