"""
Day 96: Aggregate Service with Fallback & Circuit Breaker

Features:
- Automatic aggregate selection based on query window
- Fallback to raw metrics if aggregates are stale/failing
- Circuit breaker for aggregate failures (5 failures → open)
- Health monitoring integration
- Auto-rollback if fallback rate exceeds threshold
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional, List, Any
import logging

logger = logging.getLogger("fiber-api.aggregate")

# ============================================
# Try importing Prometheus metrics (optional)
# ============================================
try:
    from prometheus_client import Counter, Gauge
    AGGREGATE_QUERIES = Counter('aggregate_queries_total', 'Aggregate queries', ['table', 'status'])
    AGGREGATE_FALLBACKS = Counter('aggregate_fallback_total', 'Fallback to raw metrics')
    AGGREGATE_HEALTH = Gauge('aggregate_health_status', 'Aggregate health (1=healthy)', ['view_name'])
    CIRCUIT_BREAKER_OPEN = Gauge('aggregate_circuit_breaker_open', 'Circuit breaker state', ['view_name'])
    PROMETHEUS_ENABLED = True
except ImportError:
    PROMETHEUS_ENABLED = False
    AGGREGATE_QUERIES = None
    AGGREGATE_FALLBACKS = None
    AGGREGATE_HEALTH = None
    CIRCUIT_BREAKER_OPEN = None


# ============================================
# Configuration
# ============================================
class AggregationConfig:
    # Feature flag: Set to False to disable aggregates entirely
    USE_AGGREGATES = os.getenv("USE_AGGREGATES", "true").lower() == "true"
    
    # Rollback threshold: If fallback rate exceeds this, auto-disable
    AUTO_ROLLBACK_THRESHOLD = 0.3  # 30% fallback rate
    
    # Rollback cooldown: How long to wait before re-enabling
    ROLLBACK_COOLDOWN_SECONDS = 300  # 5 minutes
    
    # Query timeout for aggregates
    QUERY_TIMEOUT_SECONDS = 5.0
    
    # Max lag before considering aggregate stale
    MAX_LAG_SECONDS = {
        "aggregates_1m": 120,           # 2 min max lag
        "aggregates_5m_node": 600,      # 10 min max lag
        "aggregates_5m_region": 600,    # 10 min max lag
        "aggregates_hourly": 7200,      # 2 hour max lag
        "aggregates_daily": 86400,      # 1 day max lag
    }


# ============================================
# Circuit Breaker
# ============================================
class CircuitBreaker:
    """
    Circuit breaker pattern for aggregate queries.
    
    States:
    - CLOSED: Normal operation, queries go through
    - OPEN: Too many failures, all queries fall back
    - HALF_OPEN: Testing if aggregate recovered
    """
    
    def __init__(self, name: str, failure_threshold: int = 5, reset_timeout: int = 60):
        self.name = name
        self.failures = 0
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.last_failure: Optional[datetime] = None
        self.is_open = False
    
    def record_failure(self):
        """Record a query failure."""
        self.failures += 1
        self.last_failure = datetime.now(timezone.utc)
        
        if self.failures >= self.failure_threshold:
            self.is_open = True
            logger.warning(f"Circuit breaker OPEN: {self.name} after {self.failures} failures")
            
            if PROMETHEUS_ENABLED:
                CIRCUIT_BREAKER_OPEN.labels(view_name=self.name).set(1)
    
    def record_success(self):
        """Record a successful query."""
        if self.failures > 0 or self.is_open:
            logger.info(f"Circuit breaker reset: {self.name}")
        
        self.failures = 0
        self.is_open = False
        
        if PROMETHEUS_ENABLED:
            CIRCUIT_BREAKER_OPEN.labels(view_name=self.name).set(0)
    
    def can_proceed(self) -> bool:
        """Check if queries should proceed or fall back."""
        if not self.is_open:
            return True
        
        # Check if reset timeout has passed (half-open state)
        if self.last_failure:
            elapsed = (datetime.now(timezone.utc) - self.last_failure).total_seconds()
            if elapsed > self.reset_timeout:
                logger.info(f"Circuit breaker HALF-OPEN: {self.name} (testing)")
                return True  # Allow one test query
        
        return False
    
    def get_state(self) -> str:
        if not self.is_open:
            return "CLOSED"
        if self.last_failure:
            elapsed = (datetime.now(timezone.utc) - self.last_failure).total_seconds()
            if elapsed > self.reset_timeout:
                return "HALF_OPEN"
        return "OPEN"


# Per-aggregate circuit breakers
CIRCUIT_BREAKERS = {
    "aggregates_1m": CircuitBreaker("aggregates_1m"),
    "aggregates_5m_node": CircuitBreaker("aggregates_5m_node"),
    "aggregates_5m_region": CircuitBreaker("aggregates_5m_region"),
    "aggregates_hourly": CircuitBreaker("aggregates_hourly"),
    "aggregates_daily": CircuitBreaker("aggregates_daily"),
}


# ============================================
# Aggregate Selection Logic
# ============================================
def select_aggregate(
    window_seconds: int, 
    dimension: str = "node",
    prefer_freshness: bool = False
) -> Tuple[str, bool]:
    """
    Select optimal aggregate table based on query window.
    
    Args:
        window_seconds: Query time window in seconds
        dimension: "node" or "region" for grouping
        prefer_freshness: If True, prefer raw metrics for small windows
    
    Returns:
        Tuple of (table_name, requires_health_check)
    
    Selection Rules:
    - < 2 min: Raw metrics (real-time)
    - 2-15 min: aggregates_1m
    - 15 min - 2 hours: aggregates_5m_* 
    - 2 - 48 hours: aggregates_hourly
    - > 48 hours: aggregates_daily
    """
    # Feature flag check
    if not AggregationConfig.USE_AGGREGATES:
        return "metrics", False
    
    # Force raw for very fresh data
    if prefer_freshness and window_seconds < 600:
        return "metrics", False
    
    # Select based on window size
    if window_seconds < 120:  # < 2 min: Always raw
        return "metrics", False
    
    elif window_seconds < 900:  # 2-15 min: 1m aggregate
        table = "aggregates_1m"
    
    elif window_seconds < 7200:  # 15 min - 2 hours: 5m aggregate
        table = "aggregates_5m_region" if dimension == "region" else "aggregates_5m_node"
    
    elif window_seconds < 172800:  # 2-48 hours: hourly
        table = "aggregates_hourly"
    
    else:  # > 48 hours: daily
        table = "aggregates_daily"
    
    # Check circuit breaker
    cb = CIRCUIT_BREAKERS.get(table)
    if cb and not cb.can_proceed():
        if PROMETHEUS_ENABLED:
            AGGREGATE_FALLBACKS.inc()
        logger.debug(f"Circuit breaker blocking {table}, falling back to raw")
        return "metrics", False
    
    return table, True


# ============================================
# Aggregate Health Check
# ============================================
async def check_aggregate_health(db, view_name: str) -> bool:
    """
    Check if aggregate is fresh enough to use.
    
    Uses TimescaleDB internal stats to determine if aggregate
    has refreshed within acceptable lag window.
    
    Returns True if healthy, False if stale/failed.
    """
    # Query TimescaleDB continuous aggregate stats
    query = """
        SELECT 
            view_name,
            materialization_hypertable_name
        FROM timescaledb_information.continuous_aggregates
        WHERE hypertable_name = $1
    """
    
    try:
        async with db.acquire() as conn:
            row = await conn.fetchrow(query, view_name)
            
            if not row:
                # View doesn't exist
                if PROMETHEUS_ENABLED:
                    AGGREGATE_HEALTH.labels(view_name=view_name).set(0)
                return False
            
            # Check latest bucket in the aggregate
            mat_table = row["materialization_hypertable_name"]
            if mat_table:
                latest_query = f"""
                    SELECT MAX(bucket) as latest_bucket
                    FROM {view_name}
                """
                latest_row = await conn.fetchrow(latest_query)
                
                if latest_row and latest_row["latest_bucket"]:
                    latest = latest_row["latest_bucket"]
                    if latest.tzinfo is None:
                        latest = latest.replace(tzinfo=timezone.utc)
                    
                    lag = (datetime.now(timezone.utc) - latest).total_seconds()
                    max_lag = AggregationConfig.MAX_LAG_SECONDS.get(view_name, 3600)
                    
                    is_healthy = lag < max_lag
                    
                    if PROMETHEUS_ENABLED:
                        AGGREGATE_HEALTH.labels(view_name=view_name).set(1 if is_healthy else 0)
                    
                    if not is_healthy:
                        logger.warning(f"Aggregate stale: {view_name} lag={lag:.0f}s (max={max_lag}s)")
                    
                    return is_healthy
            
            # Couldn't determine health, assume healthy
            if PROMETHEUS_ENABLED:
                AGGREGATE_HEALTH.labels(view_name=view_name).set(1)
            return True
            
    except Exception as e:
        logger.error(f"Health check failed for {view_name}: {e}")
        if PROMETHEUS_ENABLED:
            AGGREGATE_HEALTH.labels(view_name=view_name).set(0)
        return False


# ============================================
# Query with Fallback
# ============================================
async def query_with_fallback(
    db,
    aggregate_query: str,
    raw_query: str,
    params: tuple,
    table_name: str
) -> List[Any]:
    """
    Execute query against aggregate with automatic fallback to raw metrics.
    
    Features:
    - Timeout protection (5 seconds)
    - Circuit breaker integration
    - Automatic fallback on failure
    
    Args:
        db: Database connection pool
        aggregate_query: Query using aggregate table
        raw_query: Fallback query using raw metrics table
        params: Query parameters
        table_name: Name of aggregate table (for metrics)
    
    Returns:
        Query results as list of records
    """
    cb = CIRCUIT_BREAKERS.get(table_name)
    
    # Try aggregate query first
    try:
        async with db.acquire() as conn:
            result = await asyncio.wait_for(
                conn.fetch(aggregate_query, *params),
                timeout=AggregationConfig.QUERY_TIMEOUT_SECONDS
            )
        
        # Success: Reset circuit breaker
        if cb:
            cb.record_success()
        
        if PROMETHEUS_ENABLED:
            AGGREGATE_QUERIES.labels(table=table_name, status="success").inc()
        
        return result
        
    except asyncio.TimeoutError:
        logger.warning(f"Aggregate query timeout: {table_name}")
        if cb:
            cb.record_failure()
        if PROMETHEUS_ENABLED:
            AGGREGATE_QUERIES.labels(table=table_name, status="timeout").inc()
            AGGREGATE_FALLBACKS.inc()
        
    except Exception as e:
        logger.warning(f"Aggregate query failed: {table_name} - {e}")
        if cb:
            cb.record_failure()
        if PROMETHEUS_ENABLED:
            AGGREGATE_QUERIES.labels(table=table_name, status="error").inc()
            AGGREGATE_FALLBACKS.inc()
    
    # Fallback to raw metrics
    logger.info(f"Falling back to raw metrics from {table_name}")
    try:
        async with db.acquire() as conn:
            return await conn.fetch(raw_query, *params)
    except Exception as e:
        logger.error(f"Fallback query also failed: {e}")
        raise


# ============================================
# Auto-Rollback Check
# ============================================
async def check_auto_rollback(redis) -> bool:
    """
    Check if aggregates should be auto-disabled due to high fallback rate.
    
    Uses Redis to track fallback rate across instances.
    """
    try:
        # Check if already disabled
        disabled = await redis.get("aggregation:disabled")
        if disabled:
            return True
        
        # In production, this would check Prometheus metrics
        # For now, just check circuit breaker states
        open_count = sum(1 for cb in CIRCUIT_BREAKERS.values() if cb.is_open)
        
        if open_count >= 3:  # 3+ circuit breakers open
            await redis.setex(
                "aggregation:disabled", 
                AggregationConfig.ROLLBACK_COOLDOWN_SECONDS, 
                "1"
            )
            logger.critical(f"AUTO-ROLLBACK: Aggregates disabled ({open_count} circuit breakers open)")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Auto-rollback check failed: {e}")
        return False


# ============================================
# Get Circuit Breaker Status
# ============================================
def get_circuit_breaker_status() -> dict:
    """Get status of all circuit breakers for monitoring."""
    return {
        name: {
            "state": cb.get_state(),
            "failures": cb.failures,
            "threshold": cb.failure_threshold,
            "last_failure": cb.last_failure.isoformat() if cb.last_failure else None,
        }
        for name, cb in CIRCUIT_BREAKERS.items()
    }
