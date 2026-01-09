import asyncio
import json
import os
import logging
import asyncpg
import redis.asyncio as redis
from datetime import datetime
from .normalizer import normalize_metric, validate_metric
from .event_logger import get_event_logger
import time as time_module
import sys
import uuid

# Day 87: Unified logging
sys.path.insert(0, '/Users/macpro/FiberStack-Lite')
try:
    from fiber_shared.log_lib import set_trace_id, get_trace_id, generate_trace_id, get_instrumented_logger, start_span
    logger = get_instrumented_logger("fiber-etl")
except ImportError:
    sys.path.insert(0, '/app/fiber-logging/src')
    from logger import get_logger
    logger = get_logger("fiber-etl", env=os.getenv("ENV", "dev"))
    def set_trace_id(t): pass
    def get_trace_id(): return "unknown"
    def generate_trace_id(): return str(uuid.uuid4())[:8]
    class start_span:
        def __init__(self, n): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")
DB_NAME = os.getenv("DB_NAME", "fiberstack")
QUEUE_KEY = "fiber:etl:queue"
BATCH_SIZE = int(os.getenv("ETL_BATCH_SIZE", "100"))
DEDUP_TTL_SEC = int(os.getenv("DEDUP_TTL_SEC", "180"))
NODE_CACHE_REFRESH_SEC = 3600

# Feature Flags
USE_COPY = os.getenv("ETL_USE_COPY", "true").lower() == "true"
DEDUP_ENABLED = os.getenv("ETL_DEDUP_ENABLED", "true").lower() == "true"
NODE_CACHE_ENABLED = os.getenv("ETL_NODE_CACHE_ENABLED", "true").lower() == "true"

from .metrics import ETLMetrics
from datetime import timezone

# Singleton Metrics
etl_metrics = ETLMetrics()

# Load Lua Script
with open(os.path.join(os.path.dirname(__file__), 'scripts', 'batch_pop.lua'), 'r') as f:
    BATCH_POP_LUA = f.read()

async def get_db_connection():
    return await asyncpg.connect(
        user=DB_USER, password=DB_PASS, database=DB_NAME, host=DB_HOST
    )

async def dedupe_batch(redis_client, batch):
    """Pre-dedup batch using Redis SET NX."""
    if not DEDUP_ENABLED or not batch:
        return batch
    
    pipe = redis_client.pipeline()
    for m in batch:
        # Key: node_id + minute-granularity timestamp (approx dedup)
        # Using full timestamp might be too fine if probes vary ms
        # Assuming ISO string, first 16 chars is YYYY-MM-DDTHH:MM
        ts_key = m['timestamp'][:19] if len(m['timestamp']) >= 19 else m['timestamp']
        key = f"dedup:{m['node_id']}:{ts_key}"
        pipe.set(key, "1", nx=True, ex=DEDUP_TTL_SEC)
    
    results = await pipe.execute()
    
    cleaned = []
    duplicates = 0
    for m, is_new in zip(batch, results):
        if is_new:
            cleaned.append(m)
        else:
            duplicates += 1
            etl_metrics.record_duplicate()
    
    if duplicates > 0:
        logger.debug(f"Deduped {duplicates} metrics from batch")
    
    return cleaned

async def ensure_nodes_cached(redis_client, conn, batch):
    """Ensure nodes exist using Redis-backed cache."""
    if not batch:
        return

    node_ids = {m['node_id'] for m in batch}
    
    if NODE_CACHE_ENABLED:
        # Check centralized Redis cache
        # SMISMEMBER is O(N) where N is number of members
        # Redis 6.2+
        try:
            cached_status = await redis_client.smismember("cache:nodes", *node_ids)
            new_nodes = {node_id for node_id, is_cached in zip(node_ids, cached_status) if not is_cached}
        except Exception:
            # Fallback for older Redis or failure
            cached = await redis_client.smembers("cache:nodes")
            new_nodes = node_ids - cached
    else:
        new_nodes = node_ids

    if not new_nodes:
        return

    # Fetch node metadata from batch for inserts
    # We take the first occurrence of each new node
    nodes_to_insert = {}
    for m in batch:
        if m['node_id'] in new_nodes and m['node_id'] not in nodes_to_insert:
            nodes_to_insert[m['node_id']] = m

    if not nodes_to_insert:
        return

    # Upsert new nodes into DB
    try:
        await conn.executemany("""
            INSERT INTO nodes (node_id, node_name, country, region)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (node_id) DO UPDATE 
            SET last_seen_at = NOW()
        """, [
            (
                m['node_id'], 
                f"probe-{m['node_id'][:8]}", 
                m.get('country', 'XX'), 
                m.get('region', 'Unknown')
            ) 
            for m in nodes_to_insert.values()
        ])
        
        # Update cache
        if NODE_CACHE_ENABLED and new_nodes:
            await redis_client.sadd("cache:nodes", *new_nodes)
            
    except Exception as e:
        logger.error(f"Failed to upsert nodes: {e}")
        # Don't crash batch, might just be metadata failure

async def process_batch(redis_client, db_pool, batch_pop_script, alert_engine=None, analytics_engine=None):
    """Process a batch of messages."""
    
    # 1. Atomic Batch Pop
    try:
        raw_messages = await batch_pop_script(keys=[QUEUE_KEY], args=[BATCH_SIZE])
    except Exception as e:
        logger.error(f"Redis batch pop failed: {e}")
        return 0
    
    if not raw_messages:
        return 0

    # Day 87: Trace Propagation
    # Inherit trace context from first message in batch (heuristic)
    try:
        first_payload = json.loads(raw_messages[0])
        trace_id = first_payload.get("_meta", {}).get("trace_id") or generate_trace_id()
        set_trace_id(trace_id)
        parent_span = first_payload.get("_meta", {}).get("span_id")
        # Start ETL span linked to API parent
        span = start_span("etl_process_batch", parent=parent_span)
        span.__enter__() # Manual enter/exit due to async func structure if widely scoped
    except Exception:
        set_trace_id(generate_trace_id())
        span = start_span("etl_process_batch")
        span.__enter__()

    event_logger = get_event_logger()
    batch_id = event_logger.start_batch()
    etl_metrics.start_batch()


    valid_metrics = []
    
    # 2. Parse & Validate
    for msg in raw_messages:
        try:
            raw_data = json.loads(msg)
            data = normalize_metric(raw_data)
            if validate_metric(data):
                valid_metrics.append(data)
            else:
                etl_metrics.record_row(success=False)
        except Exception:
            etl_metrics.record_row(success=False)
            
    if not valid_metrics:
        return len(raw_messages)

    # 3. Dedup
    cleaned_metrics = await dedupe_batch(redis_client, valid_metrics)
    if not cleaned_metrics:
        # All duplicates
        return len(raw_messages)

    # 4. Process in DB Transaction
    processed_count = 0
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            
            # 5. Pipeline Alerts & Analytics (Hooks)
            if alert_engine or analytics_engine:
                for data in cleaned_metrics:
                    try:
                        if alert_engine:
                            await alert_engine.process(data)
                        if analytics_engine:
                            # Note: Computed analytics inserts still single-row for now
                            # optimizing core metrics first
                            computed = await analytics_engine.compute(data)
                            if computed:
                                await conn.execute("""
                                    INSERT INTO metrics_aggregated (
                                        time, node_id, latency_avg_window, latency_std_window,
                                        packet_loss_spike, anomaly_score, metadata
                                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                                """,
                                datetime.fromisoformat(data['timestamp']), data['node_id'],
                                computed.latency_avg_window, computed.latency_std_window,
                                computed.packet_loss_spike, computed.anomaly_score,
                                json.dumps({"source": "etl-analytics"})
                                )
                    except Exception as e:
                        logger.warning(f"Engine hook failed: {e}")

            # 6. Ensure Nodes (Cached)
            await ensure_nodes_cached(redis_client, conn, cleaned_metrics)
            
            # 7. Bulk Insert Metrics
            # 7. Bulk Insert Metrics (Hardened with Audit)
            if USE_COPY:
                try:
                    records = [
                        (
                            datetime.fromisoformat(m['timestamp'].replace("Z", "+00:00")),
                            m['node_id'],
                            float(m['latency_ms']),
                            float(m['uptime_pct']),
                            float(m['packet_loss']),
                            json.dumps(m['metadata'])
                        ) for m in cleaned_metrics
                    ]
                    
                    await conn.copy_records_to_table(
                        'metrics',
                        records=records,
                        columns=['time', 'node_id', 'latency_ms', 'uptime_pct', 'packet_loss', 'metadata']
                    )
                    processed_count = len(records)
                    
                except asyncpg.UniqueViolationError:
                    # Day 97: Fallback to Row-by-Row for Audit
                    logger.warning("Batch contains duplicates! Falling back to audit mode.")
                    processed_count = 0
                    for m in cleaned_metrics:
                        try:
                            # Use ON CONFLICT DO NOTHING and check result
                            status = await conn.execute("""
                                INSERT INTO metrics (time, node_id, latency_ms, uptime_pct, packet_loss, metadata)
                                VALUES ($1, $2, $3, $4, $5, $6)
                                ON CONFLICT (time, node_id) DO NOTHING
                            """, 
                            datetime.fromisoformat(m['timestamp'].replace("Z", "+00:00")),
                            m['node_id'], float(m['latency_ms']), float(m['uptime_pct']), float(m['packet_loss']), json.dumps(m['metadata'])
                            )
                            
                            if status == "INSERT 0 1":
                                processed_count += 1
                            else:
                                # Duplicate detected -> Audit
                                etl_metrics.record_duplicate() # Prometheus
                                await conn.execute("""
                                    INSERT INTO metric_conflicts (time, node_id, payload, ingest_region)
                                    VALUES ($1, $2, $3, $4)
                                """,
                                datetime.fromisoformat(m['timestamp'].replace("Z", "+00:00")),
                                m['node_id'], json.dumps(m), m.get('_meta', {}).get('source_region', 'unknown')
                                )
                                logger.info(f"Audited conflict for node {m['node_id']}")
                                
                        except Exception as inner_e:
                            logger.error(f"Row insert failed: {inner_e}")
                            etl_metrics.record_row(success=False)

                except Exception as e:
                    logger.error(f"COPY/Audit batch failed: {e}")
                    for _ in cleaned_metrics:
                        etl_metrics.record_row(success=False)
            else:
                # Legacy executemany (safe fallback)
                try:
                    await conn.executemany("""
                        INSERT INTO metrics (
                            time, node_id, latency_ms, uptime_pct, packet_loss, metadata
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT DO NOTHING
                    """, [
                        (
                            m['timestamp'], m['node_id'], m['latency_ms'], 
                            m['uptime_pct'], m['packet_loss'], json.dumps(m['metadata'])
                        )
                        for m in cleaned_metrics
                    ])
                    processed_count = len(cleaned_metrics)
                    for _ in cleaned_metrics:
                        etl_metrics.record_row(success=True)
                except Exception as e:
                     logger.error(f"executemany batch failed: {e}")
                     for _ in cleaned_metrics:
                        etl_metrics.record_row(success=False)

    etl_metrics.set_active_probes(len({m['node_id'] for m in cleaned_metrics}))
    
    # 8. Logs & Status
    summary = etl_metrics.get_summary()
    if summary["rows_processed"] > 0 or summary["duplicate_count"] > 0:
        logger.info(json.dumps({
            "event": "ETL_BATCH_COMPLETE",
            "batch_id": batch_id,
            "metrics": summary
        }))
    
    # Update Status
    try:
        await redis_client.hset(
            "fiber:etl:status",
            mapping={
                "last_processed_ts": datetime.now(timezone.utc).isoformat(),
                "last_batch_size": summary["rows_processed"],
                "error_rate": summary["error_rate"]
            }
        )
    except Exception:
        pass

    span.__exit__(None, None, None)
    return len(raw_messages)

async def heartbeat_loop(redis_client):
    logger.info("Starting Heartbeat Loop")
    while True:
        try:
            await redis_client.hset(
                "fiber:etl:status",
                "last_heartbeat_ts",
                datetime.now(timezone.utc).isoformat()
            )
        except Exception:
            pass
        await asyncio.sleep(10)

async def main():
    logger.info("Starting Fiber-ETL Worker (Optimized)")
    
    # Redis
    redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    batch_pop_script = redis_client.register_script(BATCH_POP_LUA)
    
    # DB Pool (Tuned)
    db_pool = await asyncpg.create_pool(
        user=DB_USER, password=DB_PASS, database=DB_NAME, host=DB_HOST,
        min_size=int(os.getenv("DB_POOL_MIN", "5")),
        max_size=int(os.getenv("DB_POOL_MAX", "20")),
        max_queries=50000,
        max_inactive_connection_lifetime=300.0
    )
    
    # Engines
    from .alerts import AlertEngine, WebhookDispatcher, LogDispatcher
    
    webhook_url = os.getenv("ALERT_WEBHOOK_URL")
    dispatcher = WebhookDispatcher(webhook_url) if webhook_url else LogDispatcher()
    
    alert_engine = AlertEngine(redis_client, dispatcher=dispatcher)
    from .analytics import AnalyticsEngine
    analytics_engine = AnalyticsEngine(redis_client)
    
    heartbeat_task = asyncio.create_task(heartbeat_loop(redis_client))
    
    try:
        while True:
            processed = await process_batch(redis_client, db_pool, batch_pop_script, alert_engine, analytics_engine)
            if processed == 0:
                await asyncio.sleep(0.1) # Small sleep if empty
            # Else loop immediately to drain queue
    except Exception as e:
        logger.critical(f"ETL Worker crashed: {e}")
    finally:
        heartbeat_task.cancel()
        await redis_client.close()
        await db_pool.close()

if __name__ == "__main__":
    asyncio.run(main())
