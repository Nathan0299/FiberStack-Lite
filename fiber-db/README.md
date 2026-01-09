# Fiber-DB

**TimescaleDB Schema & Database Management**

## Overview

Fiber-DB provides the database layer for FiberStack-Lite, implementing a TimescaleDB schema optimized for time-series network metrics. It includes hypertables for efficient time-based partitioning, continuous aggregates for pre-computed rollups, and compression policies for storage optimization.

## Quick Start

### Local Development

```bash
# Start TimescaleDB (via Docker Compose)
docker-compose -f fiber-deploy/docker-compose.dev.yml up-d timescaledb

# Connect
psql -h localhost -p 5432 -U postgres -d fiberstack

# Verify schema
\dt
\d metrics
```

### Docker Standalone

```bash
docker run -d \
  -p 5432:5432 \
  -e POSTGRES_DB=fiberstack \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -v $(pwd)/fiber-db/schemas:/docker-entrypoint-initdb.d \
  timescale/timescaledb:latest-pg15
```

## Database Schema

### Tables

**nodes** - Node metadata registry
```sql
CREATE TABLE nodes (
    node_id UUID PRIMARY KEY,
    node_name VARCHAR(255) NOT NULL,
    country CHAR(2),
    region VARCHAR(100),
    city VARCHAR(100),
    geolocation POINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW()
);
```

**metrics** - Time-series hypertable
```sql
CREATE TABLE metrics (
    time TIMESTAMPTZ NOT NULL,
    node_id UUID NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    latency_ms DECIMAL(10,2),
    uptime_pct DECIMAL(5,2),
    packet_loss DECIMAL(5,2),
    target_host VARCHAR(255),
    probe_type VARCHAR(50),
    metadata JSONB
);

SELECT create_hypertable('metrics', 'time', chunk_time_interval => INTERVAL '1 week');
```

### Indexes

```sql
CREATE INDEX idx_metrics_node_id ON metrics (node_id, time DESC);
CREATE INDEX idx_metrics_time ON metrics (time DESC);
CREATE INDEX idx_nodes_region ON nodes (region);
```

### Continuous Aggregates

**Hourly Rollups:**
```sql
CREATE MATERIALIZED VIEW aggregates_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    node_id,
    AVG(latency_ms) AS avg_latency_ms,
    MAX(latency_ms) AS max_latency_ms,
    AVG(uptime_pct) AS avg_uptime_pct,
    AVG(packet_loss) AS avg_packet_loss,
    COUNT(*) AS measurement_count
FROM metrics
GROUP BY bucket, node_id;
```

**Daily Rollups:**
```sql
CREATE MATERIALIZED VIEW aggregates_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    node_id,
    AVG(latency_ms) AS avg_latency_ms,
    /* ... */
FROM metrics
GROUP BY bucket, node_id;
```

### Compression

```sql
-- Compress data older than 3 days
ALTER TABLE metrics SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'node_id'
);

SELECT add_compression_policy('metrics', INTERVAL '3 days');
```

### Retention

```sql
-- Keep raw data for 90 days
SELECT add_retention_policy('metrics', INTERVAL '90 days');

-- Keep aggregates for 1 year
SELECT add_retention_policy('aggregates_hourly', INTERVAL '1 year');
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_DB` | `fiberstack` | Database name |
| `POSTGRES_USER` | `postgres` | Database user |
| `POSTGRES_PASSWORD` | `postgres` | User password |
| `POSTGRES_PORT` | `5432` | Port to listen on |

## Initialization

### Auto-Init (Docker)

Files in `schemas/` are automatically executed:
1. `schema.sql` - Creates tables, hypertables, aggregates
2. Additional `.sql` files (alphabetically)

### Manual Init

```bash
psql -h localhost -U postgres -d fiberstack -f fiber-db/schemas/schema.sql
```

## Data Model

### Relationships

```
┌───────────┐
│   nodes   │
│ (metadata)│
└─────┬─────┘
      │ 1:N
      v
┌───────────┐      Aggregate      ┌────────────────────┐
│  metrics  │ ──────────────────> │ aggregates_hourly  │
│(hypertable)│      time_bucket   │ aggregates_daily   │
└───────────┘                      └────────────────────┘
```

## Performance

- **Insert Rate:** 5,000+ rows/sec
- **Query Latency:** <10ms (indexed queries)
- **Compression:** 10:1 ratio for older data
- **Storage:** ~1KB per metric (uncompressed)

## Queries

### Recent Metrics

```sql
SELECT time, node_id, latency_ms, uptime_pct
FROM metrics
WHERE time > NOW() - INTERVAL '1 hour'
ORDER BY time DESC
LIMIT 100;
```

### Node Average (Last 24h)

```sql
SELECT
    n.node_name,
    n.region,
    AVG(m.latency_ms) AS avg_latency,
    AVG(m.uptime_pct) AS avg_uptime
FROM metrics m
JOIN nodes n ON m.node_id = n.node_id
WHERE m.time > NOW() - INTERVAL '24 hours'
GROUP BY n.node_name, n.region;
```

### Using Continuous Aggregates

```sql
SELECT
    bucket,
    n.region,
    avg_latency_ms,
    avg_uptime_pct
FROM aggregates_hourly ah
JOIN nodes n ON ah.node_id = n.node_id
WHERE bucket > NOW() - INTERVAL '7 days';
```

## Project Structure

```
fiber-db/
├── schemas/
│   └── schema.sql         # Main schema definition
├── scripts/
│   ├── init_db.py         # Python initialization (optional)
│   └── init_es.py         # Elasticsearch setup (future)
├── README.md
└── ARCHITECTURE.md
```

## Testing

```bash
# Verify hypertable
SELECT * FROM timescaledb_information.hypertables;

# Check compression
SELECT * FROM timescaledb_information.compression_settings;

# Count metrics
SELECT COUNT(*) FROM metrics;

# Verify aggregates
SELECT * FROM aggregates_hourly ORDER BY bucket DESC LIMIT 10;
```

## Backup & Recovery

### Backup

```bash
# Full database
pg_dump -h localhost -U postgres fiberstack > backup.sql

# Schema only
pg_dump -h localhost -U postgres --schema-only fiberstack > schema_backup.sql
```

### Restore

```bash
psql -h localhost -U postgres -d fiberstack < backup.sql
```

## Monitoring

### Key Metrics
- Table size: `SELECT pg_size_pretty(pg_total_relation_size('metrics'));`
- Row count: `SELECT COUNT(*) FROM metrics;`
- Compression ratio: Check `timescaledb_information.compression_settings`

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - Schema design details
- [DB_CONTRACT.md](../docs/DB_CONTRACT.md) - Service contract
- [DATA_MODEL.md](../docs/DATA_MODEL.md) - Data model specification

## License

MIT License - FiberStack-Lite © 2025
