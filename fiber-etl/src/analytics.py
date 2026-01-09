import os
import logging
import json
import statistics
import redis.asyncio as redis
from typing import Optional, List
from pydantic import BaseModel, Field

logger = logging.getLogger("fiber-etl-analytics")

# Configuration
WINDOW_SIZE = 20 # Keep last 20
COMPUTE_MIN_SAMPLES = 5 # Need at least 5 to calculate stddev safely
LOSS_SPIKE_THRESHOLD = 1.0 # % (Standard Black Signal limit)

class ComputedMetric(BaseModel):
    latency_avg_window: Optional[float] = None
    latency_std_window: Optional[float] = None
    packet_loss_spike: bool = False
    anomaly_score: float = 0.0

class AnalyticsEngine:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.window_size = WINDOW_SIZE

    async def compute(self, metric: dict) -> ComputedMetric:
        """
        Compute analytics for a single metric point.
        Stateful: updates Redis (sliding window of latency).
        """
        node_id = metric.get("node_id")
        latency = metric.get("latency_ms")
        loss = metric.get("packet_loss", 0.0)

        if not node_id or latency is None:
            return ComputedMetric() # Empty result

        # 1. Update State (Rolling Latency Window)
        key = f"state:latency:{node_id}"
        async with self.redis.pipeline() as pipe:
            # Push new value to head (Left)
            pipe.lpush(key, latency)
            # Trim to window size
            pipe.ltrim(key, 0, self.window_size - 1)
            # Fetch all values
            pipe.lrange(key, 0, -1)
            results = await pipe.execute()
        
        # results[2] is the lrange output (list of strings)
        raw_samples = results[2]
        samples = [float(x) for x in raw_samples]
        
        # 2. Compute Statistics
        cm = ComputedMetric()
        cm.packet_loss_spike = (loss > LOSS_SPIKE_THRESHOLD)

        if len(samples) >= COMPUTE_MIN_SAMPLES:
            mean = statistics.mean(samples)
            stdev = statistics.stdev(samples)
            cm.latency_avg_window = round(mean, 2)
            cm.latency_std_window = round(stdev, 2)
            
            # 3. Anomaly Scoring (Z-Score)
            if stdev > 0.001: # Avoid div by zero
                z_score = abs(latency - mean) / stdev
                cm.anomaly_score = self._normalize_z_score(z_score)
            else:
                # Variance 0 -> If value diff from mean (unlikely if var 0), spike?
                cm.anomaly_score = 1.0 if abs(latency - mean) > 1 else 0.0
        else:
            # Insufficient data -> Score 0
            cm.anomaly_score = 0.0

        return cm

    def _normalize_z_score(self, z: float) -> float:
        """
        Map Z-Score to 0.0 - 1.0 range.
        < 1.5 sigma -> 0.0 (Noise)
        > 3.0 sigma -> 1.0 (Critical)
        Linear ramp in between.
        """
        if z < 1.5:
            return 0.0
        if z >= 3.0:
            return 1.0
        # 1.5 to 3.0 range (width 1.5)
        return round((z - 1.5) / 1.5, 4)
