"""
Day 77: Prometheus Metrics for Probe Failover

Exports metrics for observability:
- Failover events
- Buffer overflow
- Active target state
"""

from prometheus_client import Counter, Gauge


# Failover Events
FAILOVER_EVENT_COUNTER = Counter(
    'fiber_failover_events_total',
    'Total failover events between targets',
    ['from_target', 'to_target', 'node_id']
)

FAILOVER_FAILURE_COUNTER = Counter(
    'fiber_failover_push_failures_total',
    'Failed push attempts that may trigger failover',
    ['node_id', 'target']
)

# Buffer Metrics
BUFFER_OVERFLOW_COUNTER = Counter(
    'fiber_buffer_overflow_total',
    'Buffer overflow events (rejected metrics)',
    ['node_id']
)

BUFFER_DEPTH_GAUGE = Gauge(
    'fiber_buffer_depth',
    'Current buffer depth',
    ['node_id']
)

# Active Target State
ACTIVE_TARGET_GAUGE = Gauge(
    'fiber_active_target_priority',
    'Priority of currently active target (1=primary, 2+=secondary)',
    ['node_id']
)

# Push Latency
PUSH_LATENCY_HISTOGRAM = None  # Optional: Add if needed

# Connection State
CONNECTION_STATE_GAUGE = Gauge(
    'fiber_connection_state',
    'Connection state per target (1=healthy, 0=circuit open)',
    ['node_id', 'target']
)
