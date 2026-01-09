# Fiber-DB Architecture

## Schema Design

### Overview

Fiber-DB implements a hybrid relational-timeseries model. Node metadata is stored in a traditional PostgreSQL table (`nodes`) while metrics data uses a TimescaleDB hypertable (`metrics`) for efficient time-based partitioning and querying.

```
┌─────────────────────────────────────────────────┐
│                 TimescaleDB                      │
├───────────────────┬──────────────────────────────┤
│  nodes (relational│  metrics (hypertable)        │
│  -----------       │  -----------------           │
│  node_id PK       │  time                        │
│  node_name        │  node_id FK → nodes          │
│  region           │  latency_ms                  │
│  created_at       │  uptime_pct                  │
│  last_seen_at     │  packet_loss                 │
└──────┬────────────┴────────┬─────────────────────┘
       │                     │
       │                     v
       │           ┌──────────────────────┐
       │           │ Chunked by Time      │
       │           │ (1 week intervals)   │
       │           └──────────────────────┘
       │                     │
       │                     v
       │           ┌──────────────────────┐
       │           │ Continuous Aggregates│
       │           │  - Hourly            │
       │           │  - Daily             │
       │           └──────────────────────┘
       │                     │
       v                     v
     1:N                Compressed
  Relationship         (after 3 days)
```

## TimescaleDB Features

### Hypertables

**Purpose:** Automatic time-based partitioning
**Benefit:** Fast queries on recent data, efficient storage

**Creation:**
```sql
CREATE TABLE metrics (...);

SELECT create_hypertable(
    'metrics',                    -- Table name
    'time',                       -- Time column
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);
```

**Result:** Data automatically partitioned into weekly chunks

### Chunk Management

```
metrics table
├── _timescaledb_internal._hyper_1_1_chunk  (2025-W47)
├── _timescaledb_internal._hyper_1_2_chunk  (2025-W48)
└── _timescaledb_internal._hyper_1_3_chunk  (2025-W49)
```

**Benefits:**
- Queries only scan relevant chunks
- Old chunks can be dropped/compressed independently
- Parallel chunk processing

### Compression

**Strategy:** Columnar compression for old data
**Trigger:** Data older than 3 days

**Configuration:**
```sql
ALTER TABLE metrics SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'node_id',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('metrics', INTERVAL '3 days');
```

**Compression Ratio:** Typically 10:1 to 20:1

**Trade-offs:**
- ✅ 90% storage reduction
- ✅ Faster range scans
- ❌ Cannot UPDATE/DELETE compressed data
- ❌ INSERT into compressed chunks needs decompression

### Continuous Aggregates

**Purpose:** Pre-computed rollups for fast dashboards
**Implementation:** Materialized views with auto-refresh

**Hourly Aggregates:**
```sql
CREATE MATERIALIZED VIEW aggregates_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    node_id,
    AVG(latency_ms) AS avg_latency_ms,
    MAX(latency_ms) AS max_latency_ms,
    MIN(latency_ms) AS min_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
    AVG(uptime_pct) AS avg_uptime_pct,
    AVG(packet_loss) AS avg_packet_loss,
    COUNT(*) AS measurement_count
FROM metrics
GROUP BY bucket, node_id;
```

**Auto-Refresh Policy:**
```sql
SELECT add_continuous_aggregate_policy(
    'aggregates_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);
```

**Benefit:** Dashboard queries use pre-aggregated data instead of scanning millions of rows

## Index Strategy

### Primary Indexes

**Time-based (hypertable default):**
```sql
CREATE INDEX idx_metrics_time ON metrics (time DESC);
```

**Node-based:**
```sql
CREATE INDEX idx_metrics_node_id ON metrics (node_id, time DESC);
```

**Composite:**
```sql
CREATE INDEX idx_metrics_node_time ON metrics (node_id, time DESC)
WHERE time > NOW() - INTERVAL '7 days';
```

**Rationale:** Recent data queries (last 7 days) are most common

### Index Usage

**Query:** Recent metrics for a specific node
```sql
SELECT * FROM metrics
WHERE node_id = 'uuid' AND time > NOW() - INTERVAL '24 hours'
ORDER BY time DESC;
```

**Execution Plan:** Uses `idx_metrics_node_id`, scans only relevant chunk

## Data Lifecycle

### Phase 1: Hot Data (0-3 days)
- **Storage:** Uncompressed, row-oriented
- **Access:** Full CRUD operations
- **Queries:** Sub-millisecond latency

### Phase 2: Warm Data (3-90 days)
- **Storage:** Compressed, columnar
- **Access:** Read-only (SELECT)
- **Queries:** Fast range scans

### Phase 3: Cold Data (90+ days)
- **Storage:** Dropped (retention policy)
- **Backup:** Archive to S3/Glacier (future)

### Retention Policy

```sql
SELECT add_retention_policy('metrics', INTERVAL '90 days');
```

**Effect:** Automatically drops chunks older than 90 days

## Query Optimization Patterns

### Use Continuous Aggregates

**Bad:**
```sql
-- Scans 1M+ rows
SELECT AVG(latency_ms)
FROM metrics
WHERE time > NOW() - INTERVAL '30 days';
```

**Good:**
```sql
-- Scans ~720 pre-aggregated rows (30 days × 24 hours)
SELECT AVG(avg_latency_ms)
FROM aggregates_hourly
WHERE bucket > NOW() - INTERVAL '30 days';
```

### Time-based Filtering

**Bad:**
```sql
-- Full table scan
SELECT * FROM metrics
WHERE latency_ms > 100;
```

**Good:**
```sql
-- Chunk-pruned scan
SELECT * FROM metrics
WHERE time > NOW() - INTERVAL '1 hour'
  AND latency_ms > 100;
```

### EXPLAIN ANALYZE

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM metrics
WHERE node_id = 'uuid' AND time > NOW() - INTERVAL '24 hours';
```

**Look for:**
- `Chunks excluded during startup: X` (good!)
- `Index Scan` (efficient)
- Avoid `Seq Scan` (table scan)

## Scaling Considerations

### Write Scalability

**Current:** Single writer (ETL worker)
**Future:** Multiple ETL workers → Same table (TimescaleDB handles it)

**Bottlenecks:**
- Network I/O to database
- Index maintenance overhead

**Mitigation:**
- Batch inserts (current: 100 rows/transaction)
- Connection pooling (asyncpg pool)

### Read Scalability

**Current:** Direct queries to primary
**Future:** Read replicas for dashboard queries

**TimescaleDB supports:**
- Streaming replication (PostgreSQL native)
- Continuous aggregate on replica

### Storage Scalability

**Projection:**
- 5 probes × 60 metrics/hour × 24 hours = 7,200 metrics/day
- 1KB per metric → ~7MB/day uncompressed
- With compression: ~700KB/day
- 90-day retention: ~63MB total

**For 1000 probes:**
- ~1.4GB/day compressed
- ~126GB for 90 days
- Manageable on single server

## Backup Strategy

### Continuous Archiving (WAL)

```sql
-- Enable WAL archiving
archive_mode = on
archive_command = 'cp %p /backup/wal/%f'
```

**Benefit:** Point-in-time recovery

### Logical Backups

```bash
# Daily cron job
pg_dump-h localhost -U postgres fiberstack | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Hypertable-specific Backups

```sql
-- Export old chunks to S3 before dropping
COPY (
    SELECT * FROM _timescaledb_internal._hyper_1_1_chunk
) TO PROGRAM 'gzip > /s3mount/chunk_1_1.csv.gz' CSV HEADER;
```

## Monitoring Queries

### Database Size

```sql
SELECT pg_size_pretty(pg_database_size('fiberstack'));
```

### Table Sizes

```sql
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC;
```

### Chunk Information

```sql
SELECT
    chunk_name,
    range_start,
    range_end,
    pg_size_pretty(total_bytes) AS size,
    is_compressed
FROM timescaledb_information.chunks
WHERE hypertable_name = 'metrics'
ORDER BY range_start DESC
LIMIT 10;
```

### Compression Stats

```sql
SELECT
    chunk_name,
    before_compression_total_bytes,
    after_compression_total_bytes,
    ROUND((1 - (after_compression_total_bytes::numeric / before_compression_total_bytes)) * 100, 2) AS compression_ratio
FROM timescaledb_information.compressed_chunk_stats
WHERE hypertable_name = 'metrics';
```

## Migration Strategy

### Adding Columns

```sql
-- Safe: Adds column without rewriting table
ALTER TABLE metrics ADD COLUMN throughput_mbps DECIMAL(10,2);
```

### Modifying Aggregates

```sql
-- Refresh aggregate after schema change
CALL refresh_continuous_aggregate('aggregates_hourly', NULL, NULL);
```

### Changing Chunk Interval

```sql
-- For new data only (doesn't affect existing chunks)
SELECT set_chunk_time_interval('metrics', INTERVAL '1 day');
```

## Related Files

- [schema.sql](schemas/schema.sql) - Full schema definition
- [init_db.py](scripts/init_db.py) - Initialization script
- [DB_CONTRACT.md](../docs/DB_CONTRACT.md) - Service boundaries
- [DATA_MODEL.md](../docs/DATA_MODEL.md) - Conceptual data model
