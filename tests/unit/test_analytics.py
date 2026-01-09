import pytest
from unittest.mock import AsyncMock, MagicMock
import pytest
from unittest.mock import AsyncMock, MagicMock
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../fiber-etl/src')))

from analytics import AnalyticsEngine, ComputedMetric

@pytest.fixture
def redis_mock():
    mock = AsyncMock()
    
    # 1. The pipeline object itself (Synchronous methods)
    pipeline = MagicMock()
    
    # 2. Sync methods return self for chaining
    pipeline.lpush.return_value = pipeline
    pipeline.ltrim.return_value = pipeline
    pipeline.lrange.return_value = pipeline
    
    # 3. Async methods (execute is obtained via property access, needs to be AsyncMock)
    # But wait, methods on MagicMock are MagicMocks. We need .execute to be awaitable.
    execute_mock = AsyncMock()
    pipeline.execute = execute_mock
    
    # 4. Async Context Manager
    async def enter(*args, **kwargs): return pipeline
    async def exit(*args, **kwargs): return None
    pipeline.__aenter__ = AsyncMock(side_effect=enter)
    pipeline.__aexit__ = AsyncMock(side_effect=exit)
    
    # 5. client.pipeline() is a SYNC call returning the pipeline
    mock.pipeline = MagicMock(return_value=pipeline)
    
    return mock

@pytest.fixture
def engine(redis_mock):
    return AnalyticsEngine(redis_mock), redis_mock

@pytest.mark.asyncio
async def test_insufficient_data(engine):
    eng, redis = engine
    # Access the pipeline object returned by mock.pipeline()
    pipeline = redis.pipeline.return_value
    # Set return value on the attached execute AsyncMock
    pipeline.execute.return_value = [1, True, ["10.0", "12.0"]]
    
    cm = await eng.compute({"node_id": "test", "latency_ms": 11.0})
    
    assert cm.anomaly_score == 0.0
    assert cm.latency_avg_window is None

@pytest.mark.asyncio
async def test_normal_flow(engine):
    eng, redis = engine
    pipeline = redis.pipeline.return_value
    pipeline.execute.return_value = [
        1, True, ["10.0", "11.0", "10.5", "10.0", "11.0", "10.5", "10.0", "11.0", "10.0", "11.0"]
    ]
    
    cm = await eng.compute({"node_id": "test", "latency_ms": 10.5})
    
    assert cm.latency_avg_window == 10.5
    assert cm.anomaly_score == 0.0

@pytest.mark.asyncio
async def test_high_spike(engine):
    eng, redis = engine
    pipeline = redis.pipeline.return_value
    
    # Stable history ~10ms
    history = ["10.0"] * 10
    
    # Logic pushes then reads. We simulate the read returning history + new value.
    spike_history = ["100.0"] + history[:-1]
    
    pipeline.execute.return_value = [1, True, spike_history]

    cm = await eng.compute({"node_id": "test", "latency_ms": 100.0})
    
    assert cm.anomaly_score > 0.5
    assert cm.anomaly_score <= 1.0

@pytest.mark.asyncio
async def test_loss_spike(engine):
    eng, redis = engine
    pipeline = redis.pipeline.return_value
    pipeline.execute.return_value = [1, True, []]
    
    cm = await eng.compute({"node_id": "test", "latency_ms": 10.0, "packet_loss": 5.0})
    
    assert cm.packet_loss_spike is True
