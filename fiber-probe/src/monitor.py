import asyncio
import time
import logging
import psutil
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger("fiber-probe")

class StatsTracker:
    """
    Singleton-style operational counters for the probe transport.
    Monotonic counters reset on process restart.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StatsTracker, cls).__new__(cls)
            cls._instance.reset()
        return cls._instance
    
    def reset(self):
        self.push_ok = 0
        self.push_err = 0
    
    def inc_success(self):
        self.push_ok += 1
        
    def inc_error(self):
        self.push_err += 1
        
    def get_snapshot(self) -> Dict[str, int]:
        return {
            "push_ok": self.push_ok,
            "push_err": self.push_err
        }

class SystemMonitor:
    """
    Background task to monitor system resources and probe health.
    Pushes a 'health' metric every 60s.
    """
    def __init__(self, client, node_id: str, interval_s: int = 60):
        self.client = client
        self.node_id = node_id
        self.interval = interval_s
        self.stats = StatsTracker()
        self._running = False

    async def start(self):
        self._running = True
        logger.info(f"System Monitor started (Interval: {self.interval}s)")
        
        while self._running:
            try:
                await asyncio.sleep(self.interval)
                await self._collect_and_push()
            except asyncio.CancelledError:
                logger.info("System Monitor stopped")
                break
            except Exception as e:
                logger.error(f"System Monitor failed: {e}")
                # Resilience: Don't crash the loop
                await asyncio.sleep(10) 

    async def _collect_and_push(self):
        # 1. Collect Resources
        cpu_pct = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        
        # 2. Snapshot Transport Stats
        transport_stats = self.stats.get_snapshot()
        
        # 3. Construct Payload
        # Note: 'latency_ms' is None to avoid skewing aggregation
        metric = {
            "node_id": self.node_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latency_ms": None, 
            "uptime_pct": 100.0, # Self-reported uptime is always 100% if we are running
            "packet_loss": 0.0,
            "country": "XX", # Default, overridden by client/config usually
            "region": "health",
            "metadata": {
                "type": "health",
                "cpu_pct": cpu_pct,
                "mem_pct": mem.percent,
                "push_ok": transport_stats["push_ok"],
                "push_err": transport_stats["push_err"]
            }
        }
        
        # 4. Push directly via client
        # We assume client handle_backoff/etc are handled inside push_batch if we used that,
        # but here we might want a direct push. 
        # However, to reuse logic, we can just put it in the queue or call push_batch.
        # Since client.py likely has a method to push, let's look at client.py.
        # We will use client.push_batch([metric]) to reuse auth/backoff logic.
        
        try:
            # We wrap in a list as push_batch expects a batch
            success = await self.client.push_batch([metric])
            if success:
                logger.debug("Health metric pushed")
            else:
                logger.warning("Failed to push health metric")
        except Exception as e:
            logger.error(f"Health push loop error: {e}")
