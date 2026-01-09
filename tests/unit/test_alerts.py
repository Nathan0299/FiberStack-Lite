import pytest
from unittest.mock import AsyncMock, MagicMock
import pytest
from unittest.mock import AsyncMock, MagicMock
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../fiber-etl/src')))

from alerts import AlertEngine, Alert, AlertDispatcher, Severity

# Mock Dispatcher
class MockDispatcher(AlertDispatcher):
    def __init__(self):
        self.dispatched = []
    
    async def dispatch(self, alert: Alert):
        self.dispatched.append(alert)

@pytest.fixture
def redis_mock():
    mock = AsyncMock()
    # Default set returns True (key set)
    mock.set.return_value = True
    mock.get.return_value = "1"
    mock.incr.return_value = 1
    return mock

@pytest.fixture
def engine(redis_mock):
    dispatcher = MockDispatcher()
    return AlertEngine(redis_mock, dispatcher), dispatcher, redis_mock

@pytest.mark.asyncio
async def test_alert_latency_critical(engine):
    eng, disp, redis = engine
    
    metric = {"node_id": "test-1", "latency_ms": 600.0, "packet_loss": 0.0, "uptime_pct": 100.0}
    
    await eng.process(metric)
    
    # 600ms defaults to firing BOTH Warning (>200) and Critical (>500)
    assert len(disp.dispatched) >= 1
    
    # Verify we caught the Critical one
    critical_alerts = [a for a in disp.dispatched if a.severity == Severity.CRITICAL]
    assert len(critical_alerts) == 1
    
    alert = critical_alerts[0]
    assert alert.metric_name == "latency_ms"
    assert alert.value == 600.0
    
    # Check Redis Deduplication call
    # Should be called for each alert
    assert redis.set.call_count >= 1
    key = alert.get_dedup_key()
    
    # Check if ANY of the calls contained the critical key
    calls = [call[0][0] for call in redis.set.call_args_list]
    assert key in calls

@pytest.mark.asyncio
async def test_alert_deduplication(engine):
    eng, disp, redis = engine
    
    metric = {"node_id": "test-dedup", "latency_ms": 300.0, "packet_loss": 0.0, "uptime_pct": 100.0}
    
    # First pass: Redis returns True (Set successful)
    redis.set.return_value = True
    await eng.process(metric)
    assert len(disp.dispatched) == 1
    
    # Second pass: Redis returns False (Key exists, throttling)
    redis.set.return_value = False
    await eng.process(metric)
    
    # Should still satisfy assert len == 1 (no new dispatch)
    assert len(disp.dispatched) == 1

@pytest.mark.asyncio
async def test_no_alert_healthy(engine):
    eng, disp, _ = engine
    metric = {"node_id": "healthy", "latency_ms": 50.0, "packet_loss": 0.0, "uptime_pct": 100.0}
    
    await eng.process(metric)
    assert len(disp.dispatched) == 0
