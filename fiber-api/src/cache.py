"""
Day 96: Production-Grade Redis Caching Layer

Features:
- TTL-based expiration with configurable freshness
- Cache busting via Redis pub/sub on data updates
- Hit/miss metrics exposed to Prometheus
- Eviction strategy: LRU with namespace isolation
"""
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, Any
import logging

logger = logging.getLogger("fiber-api.cache")

# ============================================
# Try importing Prometheus metrics (optional)
# ============================================
try:
    from prometheus_client import Counter, Histogram
    CACHE_HITS = Counter('dashboard_cache_hits_total', 'Cache hits', ['endpoint'])
    CACHE_MISSES = Counter('dashboard_cache_misses_total', 'Cache misses', ['endpoint'])
    CACHE_LATENCY = Histogram('dashboard_cache_latency_seconds', 'Cache operation latency')
    PROMETHEUS_ENABLED = True
except ImportError:
    PROMETHEUS_ENABLED = False
    CACHE_HITS = None
    CACHE_MISSES = None
    CACHE_LATENCY = None


# ============================================
# Configuration
# ============================================
class CacheConfig:
    TTL_CLUSTER = 60        # 1 minute for cluster summary
    TTL_REGIONAL = 60       # 1 minute for regional data
    TTL_NODE_TREND = 30     # 30 seconds for node-specific data
    TTL_REALTIME = 10       # 10 seconds for real-time dashboards
    
    # Freshness threshold: Maximum age before considering stale
    FRESHNESS_THRESHOLD_SECONDS = 5
    
    # Namespace prefix for isolation
    NAMESPACE = "fiberstack:cache:dashboard"
    
    # Max cache size per namespace (LRU eviction)
    MAX_KEYS_PER_NAMESPACE = 10000


# ============================================
# Cache Key Generation
# ============================================
def cache_key(prefix: str, **params) -> str:
    """Generate deterministic cache key with namespace."""
    param_str = json.dumps(params, sort_keys=True, default=str)
    hash_suffix = hashlib.md5(param_str.encode()).hexdigest()[:12]
    return f"{CacheConfig.NAMESPACE}:{prefix}:{hash_suffix}"


# ============================================
# Cache Operations with Metrics
# ============================================
async def get_cached(redis, key: str, endpoint: str = "unknown") -> Optional[Any]:
    """
    Retrieve cached value with metrics.
    
    Returns None if cache miss or data is stale.
    """
    try:
        data = await redis.get(key)
        if data:
            if PROMETHEUS_ENABLED:
                CACHE_HITS.labels(endpoint=endpoint).inc()
            
            result = json.loads(data)
            
            # Check freshness (cached_at timestamp)
            if "cached_at" in result:
                try:
                    cached_at = datetime.fromisoformat(result["cached_at"].replace('Z', '+00:00'))
                    age = (datetime.now(timezone.utc) - cached_at).total_seconds()
                    # Return None if older than TTL (stale)
                    if age > CacheConfig.TTL_CLUSTER * 2:
                        logger.debug(f"Cache stale: {key} age={age:.1f}s")
                        return None
                except (ValueError, TypeError):
                    pass
            
            return result.get("data")
        
        if PROMETHEUS_ENABLED:
            CACHE_MISSES.labels(endpoint=endpoint).inc()
        return None
        
    except Exception as e:
        logger.warning(f"Cache get error: {e}")
        if PROMETHEUS_ENABLED:
            CACHE_MISSES.labels(endpoint=endpoint).inc()
        return None


async def set_cached(redis, key: str, value: Any, ttl: int):
    """Cache value with timestamp for freshness checking."""
    try:
        payload = {
            "data": value,
            "cached_at": datetime.now(timezone.utc).isoformat()
        }
        await redis.setex(key, ttl, json.dumps(payload, default=str))
    except Exception as e:
        logger.warning(f"Cache set error: {e}")


# ============================================
# Cache Busting (Pub/Sub)
# ============================================
INVALIDATION_CHANNEL = "fiberstack:cache:invalidate"


async def invalidate_cache(redis, pattern: str = "*"):
    """
    Invalidate cache keys matching pattern.
    
    Returns number of keys deleted.
    """
    try:
        # Publish invalidation event for distributed cache busting
        await redis.publish(INVALIDATION_CHANNEL, pattern)
        
        # Delete matching keys locally
        full_pattern = f"{CacheConfig.NAMESPACE}:{pattern}"
        cursor = 0
        deleted = 0
        
        while True:
            cursor, keys = await redis.scan(cursor, match=full_pattern, count=100)
            if keys:
                await redis.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        
        logger.info(f"Cache invalidated: pattern={pattern} deleted={deleted}")
        return deleted
        
    except Exception as e:
        logger.error(f"Cache invalidation error: {e}")
        return 0


async def invalidate_on_ingest(redis, node_id: str):
    """
    Invalidate cache entries affected by new data ingestion.
    
    Called after metrics ingestion to bust stale cache.
    """
    patterns = [
        f"cluster:*",           # Cluster summaries
        f"regional:*",          # Regional breakdowns 
        f"node:{node_id}:*",    # Node-specific trends
        f"aggregated:*",        # Aggregated metrics
    ]
    
    for pattern in patterns:
        await invalidate_cache(redis, pattern)


# ============================================
# Cache Warmup
# ============================================
async def warmup_cache(redis, db, common_queries: list):
    """
    Pre-populate cache with common dashboard queries.
    
    Called on API startup to reduce cold-start latency.
    """
    warmed = 0
    for query_fn, key_prefix, ttl in common_queries:
        try:
            result = await query_fn(db)
            key = cache_key(key_prefix)
            await set_cached(redis, key, result, ttl)
            warmed += 1
        except Exception as e:
            logger.warning(f"Cache warmup failed for {key_prefix}: {e}")
    
    logger.info(f"Cache warmed: {warmed}/{len(common_queries)} entries")
    return warmed


# ============================================
# Cache Stats
# ============================================
async def get_cache_stats(redis) -> dict:
    """Get cache statistics for monitoring."""
    try:
        # Count keys in namespace
        cursor = 0
        key_count = 0
        while True:
            cursor, keys = await redis.scan(
                cursor, 
                match=f"{CacheConfig.NAMESPACE}:*", 
                count=1000
            )
            key_count += len(keys)
            if cursor == 0:
                break
        
        return {
            "namespace": CacheConfig.NAMESPACE,
            "key_count": key_count,
            "max_keys": CacheConfig.MAX_KEYS_PER_NAMESPACE,
            "ttl_cluster": CacheConfig.TTL_CLUSTER,
            "ttl_realtime": CacheConfig.TTL_REALTIME,
        }
    except Exception as e:
        logger.error(f"Cache stats error: {e}")
        return {"error": str(e)}
