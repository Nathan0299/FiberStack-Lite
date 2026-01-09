from fastapi import APIRouter, Request, HTTPException, Depends, Query, Response, BackgroundTasks
from .models import ProbeMetric, APIResponse, Node, AggregatedMetric, BatchPayload
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import logging
import json
import uuid

# Day 78: Auth imports
from .auth import (
    LoginRequest, verify_credentials,
    get_user_role, get_role_permissions, require_auth, require_permission,
    ADMIN_USERS, OPERATOR_USERS, PERMISSIONS, log_role_config
)
from . import auth
from .audit import audit_log, verify_audit_chain, get_audit_stats

# Day 96: Aggregation & Caching
from .cache import get_cached, set_cached, cache_key, CacheConfig, invalidate_on_ingest
from .aggregate_service import (
    select_aggregate, check_aggregate_health, query_with_fallback,
    get_circuit_breaker_status, AggregationConfig
)

router = APIRouter()
logger = logging.getLogger("fiber-api")

# Log role config on module load
log_role_config()


async def get_redis(request: Request):
    return request.app.state.redis


async def get_db(request: Request):
    return request.app.state.db


@router.get("/status", response_model=APIResponse)
async def get_status(request: Request, redis=Depends(get_redis)):
    """
    Deep System Status (ETL Health, Redis, DB).
    Requires authentication.

    
    ETL States:
    - Healthy: Heartbeat lag <= 30s
    - Degraded: Heartbeat lag <= 60s
    - Down: Heartbeat lag > 60s (or missing)
    """
    status_data = {
        "api": "ok", 
        "redis": "unknown",
        "etl": {"state": "unknown", "lag_s": None}
    }
    
    # 1. Redis Check
    try:
        await redis.ping()
        status_data["redis"] = "ok"
    except Exception as e:
        status_data["redis"] = "error"
        logger.error(f"Redis health check failed: {e}")
        return APIResponse(status="degraded", data=status_data)

    # 2. ETL Health Check (State Machine)
    try:
        etl_status = await redis.hgetall("fiber:etl:status")
        if not etl_status:
            status_data["etl"]["state"] = "down"
            status_data["etl"]["message"] = "No status data found"
        else:
            last_hb_str = etl_status.get("last_heartbeat_ts")
            processed_count = etl_status.get("processed_count", 0)
            
            if last_hb_str:
                last_hb = datetime.fromisoformat(last_hb_str)
                now = datetime.now(timezone.utc)
                lag = (now - last_hb).total_seconds()
                
                status_data["etl"]["lag_s"] = round(lag, 1)
                status_data["etl"]["processed"] = int(processed_count)
                
                if lag <= 30:
                    status_data["etl"]["state"] = "healthy"
                elif lag <= 60:
                     status_data["etl"]["state"] = "degraded"
                else:
                     status_data["etl"]["state"] = "down"
            else:
                 status_data["etl"]["state"] = "down"
                 status_data["etl"]["message"] = "No heartbeat timestamp"
                 
    except Exception as e:
        status_data["etl"]["state"] = "error"
        status_data["etl"]["message"] = str(e)
        logger.error(f"ETL status check failed: {e}")

    return APIResponse(status="ok", data=status_data)





@router.post("/ingest", response_model=APIResponse)
async def ingest_batch(
    request: Request,
    redis=Depends(get_redis)
):
    """
    Ingest a batch of metrics from a probe (Federation).
    
    Headers:
    - Authorization: Bearer <token> (JWT or legacy secret)
    - X-Batch-ID: UUIDv4 (Required for Idempotency)
    - X-Region-ID: Region identifier (Optional, highest precedence)
    - X-Fiber-Signature: HMAC-SHA256 signature (Optional but recommended)
    - X-Fiber-Timestamp: ISO8601 timestamp (Required with signature)
    - X-Fiber-Nonce: UUID nonce (Required with signature)
    """
    import os
    import jwt
    import hmac
    import hashlib
    
    # Get raw body FIRST for HMAC verification
    raw_body = await request.body()
    body_str = raw_body.decode('utf-8')
    
    # Config-driven settings
    legacy_secret = os.getenv("FEDERATION_SECRET", "default_secret_change_me")
    jwt_public_key = os.getenv("JWT_PUBLIC_KEY", "")
    queue_key = os.getenv("ETL_QUEUE_KEY", "fiber:etl:queue")
    allowed_regions = os.getenv("ALLOWED_REGIONS", "gh-accra,ng-lagos,ke-nairobi").split(",")
    node_role = os.getenv("NODE_ROLE", "central")
    validation_mode = os.getenv("REGION_VALIDATION", "strict")
    
    # 1. Auth Check (Defense in Depth)
    # Layer 1: HMAC Signature (Integrity & Anti-Replay)
    signature = request.headers.get("X-Fiber-Signature")
    timestamp = request.headers.get("X-Fiber-Timestamp")
    nonce = request.headers.get("X-Fiber-Nonce")
    batch_id = request.headers.get("X-Batch-ID")
    
    if signature and timestamp and nonce and batch_id:
        # Verify Timestamp Freshness (5 min window)
        try:
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if abs((now - ts).total_seconds()) > 300:
                raise HTTPException(status_code=401, detail="Request timestamp too old")
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid timestamp format")

        # Verify Nonce (Anti-Replay)
        nonce_key = f"nonce:{nonce}"
        if await redis.exists(nonce_key):
             raise HTTPException(status_code=401, detail="Nonce replay detected")
        await redis.setex(nonce_key, 600, "1")

        # Verify Signature using RAW BODY (byte-perfect match)
        secret = os.getenv("FEDERATION_SECRET", "default_secret_change_me")
        body_hash = hashlib.sha256(raw_body).hexdigest()
        message = f"{batch_id}:{timestamp}:{nonce}:{body_hash}"
        
        expected_sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        
        # Constant time compare
        if not hmac.compare_digest(signature, expected_sig):
            logger.warning(f"Signature mismatch for batch {batch_id}")
            raise HTTPException(status_code=401, detail="Invalid HMAC signature")
        
        logger.info(f"Verified HMAC for batch {batch_id}")
    
    # Parse body into Pydantic model AFTER HMAC verification
    try:
        body_dict = json.loads(body_str)
        batch = BatchPayload(**body_dict)
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid payload: {e}")

    # Layer 2: Legacy/JWT (Identity)
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        # If HMAC present/valid, maybe allow? 
        # Policy: Require Identity too.
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    token = auth_header.split(" ")[1]
    jwt_claims = None
    
    # Try JWT first (RS256)
    if jwt_public_key and "." in token:
        try:
            jwt_claims = jwt.decode(
                token,
                key=jwt_public_key,
                algorithms=["RS256"],
                audience="fiber-api"
            )
            logger.info(f"JWT auth: sub={jwt_claims.get('sub')}, kid={jwt.get_unverified_header(token).get('kid')}")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="JWT expired")
        except jwt.InvalidTokenError as e:
            # Fall through to legacy check
            jwt_claims = None
    
    # Legacy Bearer fallback (Phase 4 transition)
    if not jwt_claims:
        if token != legacy_secret:
            raise HTTPException(status_code=401, detail="Invalid Federation Token")

    # 2. Idempotency Check (Redundant with Nonce but keeps Batch semantics)
    idempotency_key = f"idempotency:batch:{batch_id}"
    if await redis.exists(idempotency_key):
        return APIResponse(status="accepted", message="Batch already processed (Idempotent)")
    
    await redis.setex(idempotency_key, 600, "1")

    # 3. Region Extraction (Canonical Precedence)
    # Priority 1: X-Region-ID header
    source_region = request.headers.get("X-Region-ID")
    
    # Priority 2: Derive from first metric
    if not source_region and batch.metrics:
        first_metric = batch.metrics[0]
        country = (first_metric.country or "xx").lower()
        region = (first_metric.region or "unknown").lower().replace(" ", "-")
        source_region = f"{country}-{region}"
    
    # Priority 3: Fallback
    if not source_region:
        source_region = "unknown"

    # 4. Region Validation (Strict at Central)
    if source_region not in allowed_regions and source_region != "unknown":
        if validation_mode == "strict" and node_role == "central":
            # Increment rejection counter
            await redis.incr("fiber:metrics:ingest_rejection_count")
            logger.warning(f"Rejected batch {batch_id}: unknown region '{source_region}'")
            raise HTTPException(
                status_code=400, 
                detail={
                    "status": "error",
                    "code": "INVALID_REGION",
                    "message": f"Unknown region: {source_region}",
                    "batch_id": batch_id
                }
            )
        else:
            logger.warning(f"Accepted batch {batch_id} with unknown region '{source_region}' (lenient mode)")

    # 5. Enqueue Metrics with Metadata Enrichment
    try:
        pipeline = redis.pipeline()
        count = 0
        ingested_at = datetime.now(timezone.utc).isoformat()
        
        for metric in batch.metrics:
            if metric.node_id != batch.node_id:
                logger.warning(f"Metric node_id {metric.node_id} mismatch with batch {batch.node_id}")
                continue
                
            payload = metric.model_dump(mode='json')
            # Versioned _meta schema
            payload["_meta"] = {
                "schema_version": 1,
                "ingested_at": ingested_at,
                "ingested_by": node_role,
                "source_region": source_region
            }
            pipeline.rpush(queue_key, json.dumps(payload))
            count += 1
        
        await pipeline.execute()
        
        logger.info(f"Ingested batch {batch_id} from {batch.node_id} ({source_region}): {count} metrics")
        
        return APIResponse(
            status="accepted", 
            message=f"Queued {count} metrics",
            data={"batch_id": batch_id, "source_region": source_region}
        )
    except Exception as e:
        logger.error(f"Failed to ingest batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail="Ingestion failed")


@router.get("/metrics", response_model=APIResponse)
async def get_metrics(
    node_id: Optional[str] = Query(None, description="Filter by node UUID"),
    start_time: Optional[datetime] = Query(None, description="Start time (UTC)"),
    end_time: Optional[datetime] = Query(None, description="End time (UTC)"),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db=Depends(get_db)
):
    """
    Query stored metrics from TimescaleDB.
    
    **Ordering**: Results are ordered by time DESC (most recent first).
    
    **Timezone**: All times should be in UTC (Z suffix recommended).
    """
    try:
        # Build parameterized query with qualified column names
        query = """
            SELECT m.node_id, n.country, n.region,
                   m.latency_ms, m.uptime_pct, m.packet_loss, 
                   m.time, m.metadata
            FROM metrics m
            LEFT JOIN nodes n ON m.node_id = n.node_id
            WHERE 1=1
        """
        params = []
        param_idx = 1
        
        if node_id:
            query += f" AND m.node_id = ${param_idx}"
            params.append(node_id)
            param_idx += 1
        
        if start_time:
            query += f" AND m.time >= ${param_idx}"
            params.append(start_time)
            param_idx += 1
        
        if end_time:
            query += f" AND m.time <= ${param_idx}"
            params.append(end_time)
            param_idx += 1
        
        query += f" ORDER BY m.time DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
        params.extend([limit, offset])
        
        async with db.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        metrics = [
            {
                "node_id": str(r["node_id"]),
                "country": r["country"] or "XX",
                "region": r["region"] or "Unknown",
                "latency_ms": float(r["latency_ms"]),
                "uptime_pct": float(r["uptime_pct"]),
                "packet_loss": float(r["packet_loss"]),
                "time": r["time"].isoformat().replace("+00:00", "Z"),
                "metadata": r["metadata"]
            }
            for r in rows
        ]
        
        return APIResponse(
            status="ok",
            data={
                "count": len(metrics),
                "limit": limit,
                "offset": offset,
                "order": "time DESC",
                "metrics": metrics
            }
        )
    except Exception as e:
        logger.error(f"Failed to query metrics: {e}")
        raise HTTPException(status_code=500, detail="Database query failed")


# --- Node Management (Day 43) ---

@router.get("/nodes", response_model=APIResponse)
@require_permission("monitor:nodes")
async def get_nodes(request: Request, db=Depends(get_db)):
    """Fetch all active (non-deleted) nodes."""
    try:
        # Fetch nodes joined with latest metric timestamp
        query = """
            SELECT n.node_id, n.status, n.country, n.region, n.lat, n.lng,
                   MAX(m.time) as last_seen
            FROM nodes n
            LEFT JOIN metrics m ON n.node_id = m.node_id
            WHERE n.status != 'deleted'
            GROUP BY n.node_id
            ORDER BY n.country, n.region
        """
        async with db.acquire() as conn:
            rows = await conn.fetch(query)

        nodes = [
            {
                "node_id": str(r["node_id"]),
                "status": r["status"],
                "country": r["country"],
                "region": r["region"],
                "lat": float(r["lat"]) if r["lat"] is not None else 0.0,
                "lng": float(r["lng"]) if r["lng"] is not None else 0.0,
                "last_seen": r["last_seen"].isoformat().replace("+00:00", "Z") if r["last_seen"] else None
            }
            for r in rows
        ]
        
        return APIResponse(status="ok", data=nodes)
    except Exception as e:
        logger.error(f"Failed to fetch nodes: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch nodes")



@router.post("/nodes", response_model=APIResponse, status_code=201)
@require_permission("write:node:create")
async def create_node(node: Node, request: Request, db=Depends(get_db)):
    """Register a new node (Metadata Shell). Requires OPERATOR or ADMIN."""
    try:
        # Enforce lifecycle start state
        if node.status != "registered":
            raise HTTPException(status_code=400, detail="New nodes must start as 'registered'")

        async with db.acquire() as conn:
            # Check existence
            existing = await conn.fetchval("SELECT 1 FROM nodes WHERE node_id = $1", node.node_id)
            if existing:
                raise HTTPException(status_code=409, detail="Node ID already exists")

            await conn.execute(
                """
                INSERT INTO nodes (node_id, status, country, region, lat, lng)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                node.node_id, node.status, node.country, node.region, node.lat, node.lng
            )
        
        # Audit log
        audit_log(request.state.user, "CREATE_NODE", node.node_id, {
            "country": node.country,
            "region": node.region
        })
        
        logger.info(f"Registered new node: {node.node_id}")
        return APIResponse(status="created", message="Node registered successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create node: {e}")
        raise HTTPException(status_code=500, detail="Failed to create node")



@router.delete("/nodes/{node_id}", response_model=APIResponse)
@require_permission("write:node:delete")
async def delete_node(node_id: str, request: Request, db=Depends(get_db)):
    """Soft delete a node (status='deleted'). Requires ADMIN only."""
    try:
        async with db.acquire() as conn:
            result = await conn.execute(
                "UPDATE nodes SET status = 'deleted' WHERE node_id = $1", 
                node_id
            )
            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail="Node not found")
        
        # Audit log (critical action)
        audit_log(request.state.user, "DELETE_NODE", node_id)
        
        logger.info(f"Soft deleted node: {node_id}")
        return APIResponse(status="ok", message="Node deleted")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete node: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete node")


# --- Analytics (Day 45) ---

@router.get("/metrics/aggregated", response_model=APIResponse)
async def get_aggregated_metrics(
    request: Request,
    dimension: str = Query(..., regex="^(region|node)$", description="Grouping dimension: 'region' or 'node'"),
    start_time: Optional[datetime] = Query(None, description="Start (UTC). Default: 24h ago"),
    end_time: Optional[datetime] = Query(None, description="End (UTC). Default: Now"),
    interval: Optional[str] = Query(None, regex="^(1m|5m|1h|1d|auto)$", description="Aggregation interval"),
    prefer_freshness: bool = Query(False, description="Force raw metrics for real-time"),
    db=Depends(get_db)
):
    """
    Get aggregated fleet statistics with intelligent source selection.
    
    Day 96 Optimization:
    - Uses pre-computed continuous aggregates when possible
    - Redis caching with 60s TTL for dashboard queries
    - Automatic fallback to raw metrics if aggregates are stale
    
    Parameters:
    - interval=auto: Automatically selects best aggregate based on window
    - prefer_freshness=true: Forces raw metrics for windows < 10 min
    """
    try:
        redis = request.app.state.redis
        
        # Defaults
        now = datetime.now(timezone.utc)
        if not end_time:
            end_time = now
        if not start_time:
            start_time = now - timedelta(hours=24)

        # Make naive datetimes aware
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        # Calculate window size
        window_seconds = int((end_time - start_time).total_seconds())
        
        # Check cache first
        key = cache_key("aggregated", dim=dimension, start=start_time.isoformat(), end=end_time.isoformat())
        cached = await get_cached(redis, key, endpoint="aggregated")
        if cached:
            return APIResponse(status="ok", data=cached, meta={"source": "cache"})
        
        # Select aggregate table
        table, check_health = select_aggregate(window_seconds, dimension, prefer_freshness)
        source = table
        
        # Health check for aggregates
        if check_health and table != "metrics":
            healthy = await check_aggregate_health(db, table)
            if not healthy:
                table = "metrics"
                source = "metrics (fallback)"
        
        # Build query based on selected table
        if table == "metrics":
            # Raw metrics query (original logic)
            group_col = "n.region" if dimension == "region" else "m.node_id"
            select_dim = "n.region || '/' || n.country" if dimension == "region" else "m.node_id"
            
            query = f"""
                SELECT 
                    {select_dim} as dim_key,
                    AVG(m.latency_ms) as avg_lat,
                    MIN(m.latency_ms) as min_lat,
                    MAX(m.latency_ms) as max_lat,
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY m.latency_ms) as p95_lat,
                    AVG(m.packet_loss) as avg_loss,
                    COUNT(*) as total_count,
                    COUNT(*) FILTER (WHERE m.uptime_pct < 100) as downtime_count
                FROM metrics m
                LEFT JOIN nodes n ON m.node_id = n.node_id
                WHERE m.time >= $1 AND m.time <= $2
                GROUP BY {group_col}{", n.country" if dimension == "region" else ""}
            """
            async with db.acquire() as conn:
                rows = await conn.fetch(query, start_time, end_time)
                
        elif table in ("aggregates_1m", "aggregates_5m_node", "aggregates_hourly"):
            # Per-node aggregate query
            query = f"""
                SELECT 
                    a.node_id as dim_key,
                    AVG(a.avg_latency) as avg_lat,
                    MIN(a.min_latency) as min_lat,
                    MAX(a.max_latency) as max_lat,
                    AVG(a.avg_latency) * 1.5 as p95_lat,  -- Approximation from avg
                    AVG(a.avg_loss) as avg_loss,
                    SUM(a.samples) as total_count,
                    SUM(CASE WHEN a.avg_uptime < 100 THEN a.samples ELSE 0 END) as downtime_count
                FROM {table} a
                WHERE a.bucket >= $1 AND a.bucket <= $2
                GROUP BY a.node_id
            """
            async with db.acquire() as conn:
                rows = await conn.fetch(query, start_time, end_time)
                
        elif table == "aggregates_5m_region":
            # Per-region aggregate query
            query = """
                SELECT 
                    a.region as dim_key,
                    AVG(a.avg_latency) as avg_lat,
                    MIN(a.avg_latency) as min_lat,  -- Approximate from bucket avgs
                    MAX(a.avg_latency) as max_lat,
                    AVG(a.avg_latency) * 1.5 as p95_lat,
                    AVG(a.avg_loss) as avg_loss,
                    SUM(a.samples) as total_count,
                    SUM(CASE WHEN a.avg_uptime < 100 THEN a.samples ELSE 0 END) as downtime_count
                FROM aggregates_5m_region a
                WHERE a.time >= $1 AND a.time <= $2
                GROUP BY a.region
            """
            async with db.acquire() as conn:
                rows = await conn.fetch(query, start_time, end_time)
        else:
            # Daily aggregate
            query = """
                SELECT 
                    a.node_id as dim_key,
                    AVG(a.avg_latency_ms) as avg_lat,
                    MIN(a.min_latency_ms) as min_lat,
                    MAX(a.max_latency_ms) as max_lat,
                    AVG(a.avg_latency_ms) * 1.5 as p95_lat,
                    AVG(a.avg_packet_loss) as avg_loss,
                    SUM(a.sample_count) as total_count,
                    SUM(CASE WHEN a.avg_uptime_pct < 100 THEN a.sample_count ELSE 0 END) as downtime_count
                FROM aggregates_daily a
                WHERE a.time >= $1 AND a.time <= $2
                GROUP BY a.node_id
            """
            async with db.acquire() as conn:
                rows = await conn.fetch(query, start_time, end_time)

        # Format response
        data = []
        for r in rows:
            total = r["total_count"] or 0
            downtime = r["downtime_count"] or 0
            avail = 100.0 * (1.0 - (downtime / total)) if total > 0 else 0.0

            data.append({
                "dimension": str(r["dim_key"]) if r["dim_key"] else "Unknown",
                "avg_latency": float(r["avg_lat"] or 0),
                "min_latency": float(r["min_lat"] or 0),
                "max_latency": float(r["max_lat"] or 0),
                "p95_latency": float(r["p95_lat"] or 0),
                "avg_packet_loss": float(r["avg_loss"] or 0),
                "reporting_count": int(total),
                "downtime_intervals": int(downtime),
                "availability_pct": float(avail)
            })

        # Cache result
        ttl = CacheConfig.TTL_REALTIME if window_seconds < 600 else CacheConfig.TTL_CLUSTER
        await set_cached(redis, key, data, ttl)
        
        return APIResponse(status="ok", data=data, meta={"source": source, "window_seconds": window_seconds})

    except Exception as e:
        logger.error(f"Failed to aggregate metrics: {e}")
        raise HTTPException(status_code=500, detail="Aggregation failed")


# --- Cluster Analytics (Day 64) ---

@router.get("/metrics/cluster", response_model=APIResponse)
async def get_cluster_metrics(
    request: Request,
    start_time: Optional[datetime] = Query(None, description="Start (UTC). Default: 24h ago"),
    end_time: Optional[datetime] = Query(None, description="End (UTC). Default: Now"),
    top_n: int = Query(5, ge=1, le=20, description="Number of problematic nodes"),
    db=Depends(get_db)
):
    """
    Cluster-wide fleet metrics with regional breakdown and top problematic nodes.
    
    Day 96 Optimization:
    - Redis caching for dashboard performance
    - Uses pre-computed aggregates for efficient queries
    """
    try:
        redis = request.app.state.redis
        
        now = datetime.now(timezone.utc)
        if not end_time:
            end_time = now
        if not start_time:
            start_time = now - timedelta(hours=24)

        # Ensure timezone-aware
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        # Enforce 7-day max window
        max_window = timedelta(days=7)
        if (end_time - start_time) > max_window:
            raise HTTPException(
                status_code=400,
                detail={"code": "WINDOW_TOO_LARGE", "message": "Max query window is 7 days"}
            )

        window_seconds = int((end_time - start_time).total_seconds())
        
        # Check Cache
        key = cache_key("cluster", start=start_time.isoformat(), end=end_time.isoformat(), top=top_n)
        cached = await get_cached(redis, key, endpoint="cluster")
        if cached:
            return APIResponse(status="ok", data=cached, meta={"source": "cache"})

        # Select Aggregate
        # For cluster metrics, we usually want >= 5m aggregate unless window is tiny
        table, check_health = select_aggregate(window_seconds, dimension="node", prefer_freshness=False)
        source = table
        
        # Health check
        if check_health and table != "metrics":
            healthy = await check_aggregate_health(db, table)
            if not healthy:
                table = "metrics"
                source = "metrics (fallback)"

        async with db.acquire() as conn:
            # 1. Fleet Summary
            if table == "metrics":
                fleet_query = """
                    SELECT 
                        COUNT(DISTINCT node_id) as total_nodes,
                        AVG(latency_ms) as avg_latency,
                        AVG(uptime_pct) as avg_uptime,
                        AVG(packet_loss) as avg_loss
                    FROM metrics
                    WHERE time >= $1 AND time <= $2
                """
            else:
                fleet_query = f"""
                    SELECT 
                        COUNT(DISTINCT node_id) as total_nodes,
                        AVG(avg_latency) as avg_latency,
                        AVG(avg_uptime) as avg_uptime,
                        AVG(avg_loss) as avg_loss
                    FROM {table}
                    WHERE bucket >= $1 AND bucket <= $2
                """
            fleet_row = await conn.fetchrow(fleet_query, start_time, end_time)

            # 2. Regional Breakdown
            if table == "metrics":
                regional_query = """
                    SELECT 
                        LOWER(n.country) || '-' || LOWER(REPLACE(n.region, ' ', '-')) as region_key,
                        COUNT(DISTINCT m.node_id) as nodes,
                        AVG(m.latency_ms) as avg_latency,
                        AVG(m.uptime_pct) as avg_uptime
                    FROM metrics m
                    JOIN nodes n ON m.node_id = n.node_id
                    WHERE m.time >= $1 AND m.time <= $2
                    GROUP BY n.country, n.region
                """
                regional_rows = await conn.fetch(regional_query, start_time, end_time)
            else:
                # Use Per-Node Aggregate + Join for accuracy
                regional_query = f"""
                    SELECT 
                        LOWER(n.country) || '-' || LOWER(REPLACE(n.region, ' ', '-')) as region_key,
                        COUNT(DISTINCT a.node_id) as nodes,
                        AVG(a.avg_latency) as avg_latency,
                        AVG(a.avg_uptime) as avg_uptime
                    FROM {table} a
                    JOIN nodes n ON a.node_id = n.node_id
                    WHERE a.bucket >= $1 AND a.bucket <= $2
                    GROUP BY n.country, n.region
                """
                regional_rows = await conn.fetch(regional_query, start_time, end_time)

            # 3. Top-N Problematic Nodes
            if table == "metrics":
                problematic_query = f"""
                    SELECT 
                        m.node_id,
                        LOWER(n.country) || '-' || LOWER(REPLACE(n.region, ' ', '-')) as region_key,
                        AVG(m.latency_ms) as avg_lat,
                        AVG(m.packet_loss) as avg_loss,
                        AVG(m.uptime_pct) as avg_uptime,
                        (AVG(m.latency_ms)/50.0 + AVG(m.packet_loss)*10.0 + (100.0-AVG(m.uptime_pct))*2.0) as score
                    FROM metrics m
                    JOIN nodes n ON m.node_id = n.node_id
                    WHERE m.time >= $1 AND m.time <= $2
                    GROUP BY m.node_id, n.country, n.region
                    ORDER BY score DESC
                    LIMIT $3
                """
            else:
                 problematic_query = f"""
                    SELECT 
                        a.node_id,
                        LOWER(n.country) || '-' || LOWER(REPLACE(n.region, ' ', '-')) as region_key,
                        AVG(a.avg_latency) as avg_lat,
                        AVG(a.avg_loss) as avg_loss,
                        AVG(a.avg_uptime) as avg_uptime,
                        (AVG(a.avg_latency)/50.0 + AVG(a.avg_loss)*10.0 + (100.0-AVG(a.avg_uptime))*2.0) as score
                    FROM {table} a
                    JOIN nodes n ON a.node_id = n.node_id
                    WHERE a.bucket >= $1 AND a.bucket <= $2
                    GROUP BY a.node_id, n.country, n.region
                    ORDER BY score DESC
                    LIMIT $3
                """
            problematic_rows = await conn.fetch(problematic_query, start_time, end_time, top_n)

        # Build response
        response = {
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "fleet_summary": {
                "total_nodes": int(fleet_row["total_nodes"] or 0),
                "avg_latency_ms": round(float(fleet_row["avg_latency"] or 0), 2),
                "avg_uptime_pct": round(float(fleet_row["avg_uptime"] or 0), 2),
                "avg_loss_pct": round(float(fleet_row["avg_loss"] or 0), 3)
            },
            "regional_breakdown": [
                {
                    "region": r["region_key"] or "unknown",
                    "nodes": int(r["nodes"]),
                    "avg_latency": round(float(r["avg_latency"] or 0), 2),
                    "avg_uptime": round(float(r["avg_uptime"] or 0), 2)
                }
                for r in regional_rows
            ],
            "top_problematic_nodes": [
                {
                    "node_id": str(r["node_id"]),
                    "region": r["region_key"] or "unknown",
                    "score": round(float(r["score"] or 0), 2),
                    "avg_latency": round(float(r["avg_lat"] or 0), 2),
                    "avg_loss": round(float(r["avg_loss"] or 0), 3)
                }
                for r in problematic_rows
            ]
        }

        # Cache result
        await set_cached(redis, key, response, CacheConfig.TTL_CLUSTER)

        return APIResponse(status="ok", data=response, meta={"source": source})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cluster metrics: {e}")
        raise HTTPException(status_code=500, detail="Cluster metrics query failed")


# =============================================================================
# Day 77: Federation Status Endpoints
# Probe-reported state for failover visibility
# =============================================================================

from pydantic import BaseModel

class ProbeHeartbeat(BaseModel):
    """Probe federation state heartbeat."""
    node_id: str
    active_target: str
    timestamp: Optional[str] = None


PROBE_STATE_TTL = 60  # seconds


@router.post("/probe/heartbeat", response_model=APIResponse)
async def probe_heartbeat(heartbeat: ProbeHeartbeat, redis=Depends(get_redis)):
    """
    Receive probe federation state heartbeat.
    
    Probes emit their active target periodically.
    This is the source of truth for which aggregator is receiving metrics.
    """
    try:
        key = f"fiber:probe:state:{heartbeat.node_id}"
        state_data = {
            "node_id": heartbeat.node_id,
            "active_target": heartbeat.active_target,
            "last_seen": heartbeat.timestamp or datetime.now(timezone.utc).isoformat()
        }
        await redis.setex(key, PROBE_STATE_TTL, json.dumps(state_data))
        
        logger.debug(
            f"Probe heartbeat: {heartbeat.node_id} -> {heartbeat.active_target}",
            extra={"node_id": heartbeat.node_id, "target": heartbeat.active_target}
        )
        
        return APIResponse(status="ok", data={"received": True})
        
    except Exception as e:
        logger.error(f"Probe heartbeat failed: {e}")
        raise HTTPException(status_code=500, detail="Heartbeat storage failed")


@router.get("/federation/status", response_model=APIResponse)
async def federation_status(redis=Depends(get_redis)):
    """
    Get authoritative federation status from probe-reported data.
    
    Returns:
    - source: Always "probe-reported" (probes are the authority)
    - total_probes: Active probe count
    - targets: Count per target (e.g., {"central": 3, "regional": 1})
    - status: "primary" | "failover" | "degraded" | "unknown"
    - probe_details: Per-probe state with last_seen timestamps
    """
    try:
        # Get all probe state keys
        keys = await redis.keys("fiber:probe:state:*")
        states = []
        
        for key in keys:
            data = await redis.get(key)
            if data:
                try:
                    states.append(json.loads(data))
                except json.JSONDecodeError:
                    continue
        
        # Count probes per target
        target_counts = {}
        for s in states:
            t = s.get("active_target", "unknown")
            target_counts[t] = target_counts.get(t, 0) + 1
        
        total = len(states)
        
        # Compute overall status
        status = _compute_federation_status(target_counts, total)
        
        response = {
            "source": "probe-reported",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_probes": total,
            "targets": target_counts,
            "status": status,
            "probe_details": states
        }
        
        return APIResponse(status="ok", data=response)
        
    except Exception as e:
        logger.error(f"Federation status failed: {e}")
        raise HTTPException(status_code=500, detail="Federation status query failed")


def _compute_federation_status(counts: dict, total: int) -> str:
    """
    Compute overall federation status.
    
    - unknown: No probes reporting
    - primary: All probes on primary (central)
    - failover: All probes on secondary
    - degraded: Mixed state (some on primary, some on secondary)
    """
    if total == 0:
        return "unknown"
    
    primary_count = counts.get("central", 0) + counts.get("legacy-env", 0)
    
    if primary_count == total:
        return "primary"
    elif primary_count == 0:
        return "failover"
    else:
        return "degraded"



# =============================================================================
# Day 78/85: Authentication Endpoints
# =============================================================================

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    role: str

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/auth/login", response_model=AuthResponse)
async def login(login_req: LoginRequest, request: Request, redis=Depends(get_redis)):
    """Authenticate and issue Dual Tokens."""
    # Rate Limit: 5/min per IP
    ip = request.client.host
    limit_key = f"limit:auth:{ip}"
    current = await redis.incr(limit_key)
    if current == 1: await redis.expire(limit_key, 60)
    
    if current > 5:
        logger.warning(f"Auth Rate Limit exceeded for {ip}")
        raise HTTPException(status_code=429, detail="Too many login attempts")

    if not verify_credentials(login_req.username, login_req.password):
        audit_log({"username": login_req.username}, "LOGIN_FAILED", "auth")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    tokens = auth.issue_tokens(login_req.username)
    
    audit_log({"username": login_req.username, "role": tokens["role"]}, "LOGIN_SUCCESS", "auth")
    return AuthResponse(**tokens)

@router.post("/auth/refresh", response_model=AuthResponse)
async def refresh_token(req: RefreshRequest, redis=Depends(get_redis)):
    """Rotate Refresh Token (Revoke Old, Issue New)."""
    try:
        tokens = await auth.rotate_refresh_token(req.refresh_token, redis)
        return AuthResponse(**tokens)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Refresh failed: {e}")
        raise HTTPException(status_code=401, detail="Refresh failed")

@router.post("/auth/logout")
async def logout(request: Request, redis=Depends(get_redis)):
    """Revoke Current Access Token."""
    user = getattr(request.state, 'user', None)
    if user and user.get("jti"):
        # Revoke Access Token
        exp = user.get("exp")
        ttl = max(0, exp - int(datetime.now(timezone.utc).timestamp()))
        await auth.revoke_jti(redis, user["jti"], ttl)
        return {"message": "Logged out"}
    return {"message": "Already logged out"}

# --- Secure Push ---
@router.post("/push", response_model=APIResponse, status_code=202)
@require_auth
async def push_metrics(
    payload: BatchPayload, 
    response: Response,
    request: Request,
    background_tasks: BackgroundTasks,
    redis=Depends(get_redis)
):
    from .limiter import check_rate_limit # Late import
    # print("DEBUG: Calling check_rate_limit") 
    await check_rate_limit(request)

    """
    Ingest a batch of metrics from a probe.
    Protected by JWT and Rate Limit.
    """
    try:
        # Enqueue all metrics in batch
        # We use a pipeline or just loop for now (redis is fast)
        async with redis.pipeline(transaction=True) as pipe:
            for metric in payload.metrics:
                # Ensure node_id is consistent if missing in metric (though model requires it)
                if not metric.node_id: 
                    metric.node_id = payload.node_id
                pipe.lpush("fiber:etl:queue", metric.json())
            await pipe.execute()
            
        return APIResponse(status="accepted", data={"queued": len(payload.metrics)})
    except Exception as e:
        logger.error(f"Push failed: {e}")
        response.status_code = 503
        return APIResponse(status="error", data={"detail": str(e)})


@router.get("/status/ratelimit", response_model=APIResponse)
@require_auth
async def ratelimit_status(request: Request):
    """
    Diagnostic: View Rate Limit Config & Mode.
    Headers tell the real story of remaining tokens.
    """
    from . import limiter  # Late import to avoid circular dependency
    return APIResponse(status="ok", data={
         "policy": limiter.limiter.state,
         "rate_per_sec": config.RATE_LIMIT_INGEST_RATE / 60.0,
         "burst": config.RATE_LIMIT_INGEST_BURST
    })



@router.get("/auth/me", response_model=APIResponse)
@require_auth
async def get_current_user(request: Request):
    """
    Get current authenticated user info.
    
    Returns username, role, and permissions.
    """
    user = request.state.user
    return APIResponse(status="ok", data={
        "authenticated": True,
        "username": user.get("username"),
        "role": user.get("role"),
        "permissions": get_role_permissions(user.get("role"))
    })


@router.get("/auth/roles", response_model=APIResponse)
@require_permission("admin:roles")
async def get_role_config(request: Request):
    """
    Admin-only: View role configuration.
    
    For observability of environment-controlled role assignments.
    """
    audit_log(request.state.user, "VIEW_ROLES", "auth")
    
    return APIResponse(status="ok", data={
        "admin_users": ADMIN_USERS,
        "operator_users": OPERATOR_USERS,
        "permissions_by_role": {
            role: [p for p, roles in PERMISSIONS.items() if role in roles]
            for role in ['VIEWER', 'OPERATOR', 'ADMIN']
        }
    })


@router.get("/auth/audit/verify", response_model=APIResponse)
@require_permission("admin:audit")
async def verify_audit(request: Request):
    """
    Admin-only: Verify audit log hash chain integrity.
    
    Returns whether the audit log is tamper-evident.
    """
    is_valid, break_line = verify_audit_chain()
    stats = get_audit_stats()
    
    return APIResponse(status="ok", data={
        "chain_valid": is_valid,
        "break_at_line": break_line,
        "audit_stats": stats
    })
