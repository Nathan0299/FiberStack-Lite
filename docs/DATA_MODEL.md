# FiberStack-Lite Data Model

**Version:** 1.0  
**Date:** 2025-11-24  
**Status:** Draft (Pending Freeze)

---

## Overview

FiberStack-Lite uses a hybrid data storage approach:
- **TimescaleDB** (PostgreSQL extension): Time-series metrics and metadata
- **Elasticsearch**: Log aggregation and full-text search
- **Redis**: Message queue and caching layer

This document defines all schemas, relationships, indexes, and data retention policies.

---

## TimescaleDB Schema

### Database: `fiberstack`

**PostgreSQL Version:** 15+  
**TimescaleDB Version:** 2.11+

### Extensions

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS postgis; -- For geographic data (future)
CREATE EXTENSION IF NOT EXISTS pg_stat_statements; -- For query monitoring
```

---

## Tables

### 1. `nodes` (Metadata Table)

Stores information about all probe nodes in the network.

```sql
CREATE TABLE nodes (
    -- Primary Key
    node_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Node Identification
    node_name VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    
    -- Geographic Information
    country CHAR(2) NOT NULL, -- ISO 3166-1 alpha-2 (GH, NG, KE)
    region VARCHAR(100) NOT NULL, -- Ghana, Nigeria, Kenya
    city VARCHAR(100),
    latitude DECIMAL(9,6), -- -90 to 90
    longitude DECIMAL(9,6), -- -180 to 180
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    last_seen_at TIMESTAMPTZ,
    
    -- Metadata
    probe_version VARCHAR(50),
    hardware_info JSONB, -- CPU, RAM, OS details
    tags JSONB, -- Custom tags for filtering
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_nodes_country ON nodes(country);
CREATE INDEX idx_nodes_region ON nodes(region);
CREATE INDEX idx_nodes_active ON nodes(is_active) WHERE is_active = true;
CREATE INDEX idx_nodes_last_seen ON nodes(last_seen_at DESC);

-- Constraints
ALTER TABLE nodes ADD CONSTRAINT check_latitude 
    CHECK (latitude BETWEEN -90 AND 90);
ALTER TABLE nodes ADD CONSTRAINT check_longitude 
    CHECK (longitude BETWEEN -180 AND 180);
ALTER TABLE nodes ADD CONSTRAINT check_country_code 
    CHECK (country ~ '^[A-Z]{2}$');

-- Comments
COMMENT ON TABLE nodes IS 'Metadata for all probe nodes in the FiberStack network';
COMMENT ON COLUMN nodes.node_id IS 'Unique identifier for the node (UUID)';
COMMENT ON COLUMN nodes.hardware_info IS 'JSON object with CPU, RAM, OS details';
COMMENT ON COLUMN nodes.tags IS 'JSON array of custom tags for filtering/grouping';
```

**Example Row:**
```json
{
  "node_id": "550e8400-e29b-41d4-a716-446655440000",
  "node_name": "probe-gh-accra-01",
  "display_name": "Accra Data Center 1",
  "country": "GH",
  "region": "Ghana",
  "city": "Accra",
  "latitude": 5.6037,
  "longitude": -0.1870,
  "is_active": true,
  "last_seen_at": "2025-11-24T16:00:00Z",
  "probe_version": "0.1.0",
  "hardware_info": {
    "cpu": "2 cores",
    "ram": "4GB",
    "os": "Ubuntu 22.04"
  },
  "tags": ["tier1", "datacenter", "priority"],
  "created_at": "2025-11-01T10:00:00Z",
  "updated_at": "2025-11-24T16:00:00Z"
}
```

---

### 2. `metrics` (Hypertable - Time-Series Data)

Stores raw metric data from probes.

```sql
CREATE TABLE metrics (
    -- Time dimension (required for hypertable)
    time TIMESTAMPTZ NOT NULL,
    
    -- Node reference
    node_id UUID NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    
    -- Metrics
    latency_ms DECIMAL(10,2), -- Milliseconds, 2 decimal places
    uptime_pct DECIMAL(5,2), -- Percentage 0-100, 2 decimal places
    packet_loss DECIMAL(5,2), -- Percentage 0-100, 2 decimal places
    
    -- Additional context
    target_host VARCHAR(255), -- Which host was probed (e.g., google.com)
    probe_type VARCHAR(50), -- 'ping', 'http', 'tcp', etc.
    
    -- Metadata (flexible schema for future metrics)
    metadata JSONB,
    
    -- Constraints
    CONSTRAINT check_latency CHECK (latency_ms >= 0 AND latency_ms < 10000),
    CONSTRAINT check_uptime CHECK (uptime_pct >= 0 AND uptime_pct <= 100),
    CONSTRAINT check_packet_loss CHECK (packet_loss >= 0 AND packet_loss <= 100)
);

-- Convert to hypertable (partitioned by time)
SELECT create_hypertable('metrics', 'time', chunk_time_interval => INTERVAL '1 week');

-- Indexes
CREATE INDEX idx_metrics_node_time ON metrics (node_id, time DESC);
CREATE INDEX idx_metrics_time ON metrics (time DESC);
CREATE INDEX idx_metrics_metadata ON metrics USING GIN (metadata);

-- Compression (for older data)
ALTER TABLE metrics SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'node_id'
);

-- Automatic compression policy (compress data older than 3 days)
SELECT add_compression_policy('metrics', INTERVAL '3 days');

-- Comments
COMMENT ON TABLE metrics IS 'Raw time-series metrics from probe nodes';
COMMENT ON COLUMN metrics.time IS 'Timestamp when the metric was collected (UTC)';
COMMENT ON COLUMN metrics.latency_ms IS 'Round-trip latency in milliseconds';
COMMENT ON COLUMN metrics.uptime_pct IS 'Service uptime percentage (0-100)';
COMMENT ON COLUMN metrics.packet_loss IS 'Packet loss percentage (0-100)';
COMMENT ON COLUMN metrics.metadata IS 'Additional metric-specific data (JSON)';
```

**Example Row:**
```json
{
  "time": "2025-11-24T16:35:00Z",
  "node_id": "550e8400-e29b-41d4-a716-446655440000",
  "latency_ms": 45.23,
  "uptime_pct": 99.95,
  "packet_loss": 0.12,
  "target_host": "google.com",
  "probe_type": "http",
  "metadata": {
    "http_status": 200,
    "response_size": 1024,
    "tls_version": "1.3"
  }
}
```

---

### 3. `aggregates_hourly` (Continuous Aggregate)

Pre-computed hourly aggregations for faster dashboard queries.

```sql
CREATE MATERIALIZED VIEW aggregates_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS time,
    node_id,
    
    -- Latency aggregates
    AVG(latency_ms) AS avg_latency_ms,
    MIN(latency_ms) AS min_latency_ms,
    MAX(latency_ms) AS max_latency_ms,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms) AS p50_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) AS p99_latency_ms,
    
    -- Uptime aggregates
    AVG(uptime_pct) AS avg_uptime_pct,
    MIN(uptime_pct) AS min_uptime_pct,
    
    -- Packet loss aggregates
    AVG(packet_loss) AS avg_packet_loss,
    MAX(packet_loss) AS max_packet_loss,
    
    -- Sample count
    COUNT(*) AS sample_count
FROM metrics
GROUP BY time_bucket('1 hour', time), node_id;

-- Index on continuous aggregate
CREATE INDEX idx_agg_hourly_node_time ON aggregates_hourly (node_id, time DESC);

-- Refresh policy (refresh every hour, covering last 2 hours)
SELECT add_continuous_aggregate_policy('aggregates_hourly',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '0 hours',
    schedule_interval => INTERVAL '1 hour');

-- Comments
COMMENT ON MATERIALIZED VIEW aggregates_hourly IS 'Hourly aggregated metrics for improved query performance';
```

---

### 4. `aggregates_daily` (Continuous Aggregate)

Daily aggregations for long-term trend analysis.

```sql
CREATE MATERIALIZED VIEW aggregates_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS time,
    node_id,
    
    -- Daily statistics
    AVG(latency_ms) AS avg_latency_ms,
    MIN(latency_ms) AS min_latency_ms,
    MAX(latency_ms) AS max_latency_ms,
    AVG(uptime_pct) AS avg_uptime_pct,
    AVG(packet_loss) AS avg_packet_loss,
    COUNT(*) AS sample_count,
    
    -- Availability calculation (samples with uptime > 95%)
    COUNT(*) FILTER (WHERE uptime_pct > 95.0) AS high_availability_count,
    (COUNT(*) FILTER (WHERE uptime_pct > 95.0)::DECIMAL / COUNT(*) * 100) AS availability_pct
FROM metrics
GROUP BY time_bucket('1 day', time), node_id;

-- Index
CREATE INDEX idx_agg_daily_node_time ON aggregates_daily (node_id, time DESC);

-- Refresh policy (refresh daily at 1 AM)
SELECT add_continuous_aggregate_policy('aggregates_daily',
    start_offset => INTERVAL '2 days',
    end_offset => INTERVAL '0 days',
    schedule_interval => INTERVAL '1 day');
```

---

### 5. `alerts` (Future - Phase 3+)

Tracks alert events and their status.

```sql
CREATE TABLE alerts (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL REFERENCES nodes(node_id),
    
    -- Alert details
    alert_type VARCHAR(50) NOT NULL, -- 'high_latency', 'low_uptime', 'packet_loss'
    severity VARCHAR(20) NOT NULL, -- 'info', 'warning', 'critical'
    message TEXT NOT NULL,
    
    -- Timing
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    
    -- Context
    metric_value DECIMAL(10,2),
    threshold_value DECIMAL(10,2),
    metadata JSONB,
    
    -- Status
    status VARCHAR(20) DEFAULT 'open' -- 'open', 'acknowledged', 'resolved'
);

CREATE INDEX idx_alerts_node ON alerts(node_id);
CREATE INDEX idx_alerts_status ON alerts(status) WHERE status != 'resolved';
CREATE INDEX idx_alerts_triggered ON alerts(triggered_at DESC);
```

---

## Data Retention Policies

### Automatic Data Retention

```sql
-- Raw metrics: Keep for 7 days
SELECT add_retention_policy('metrics', INTERVAL '7 days');

-- Hourly aggregates: Keep for 90 days
SELECT add_retention_policy('aggregates_hourly', INTERVAL '90 days');

-- Daily aggregates: Keep for 1 year
SELECT add_retention_policy('aggregates_daily', INTERVAL '365 days');
```

**Retention Summary:**

| Data Type | Retention | Storage Estimate (20 probes) |
|-----------|-----------|------------------------------|
| Raw metrics (1-min intervals) | 7 days | ~2 GB |
| Hourly aggregates | 90 days | ~500 MB |
| Daily aggregates | 1 year | ~50 MB |
| Node metadata | Forever | <1 MB |

---

## Elasticsearch Schemas

### Index: `fiber-logs-*`

Stores application logs from all services.

**Index Template:**
```json
{
  "index_patterns": ["fiber-logs-*"],
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 1,
      "index.lifecycle.name": "fiber-logs-policy",
      "index.lifecycle.rollover_alias": "fiber-logs"
    },
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "service": { "type": "keyword" },
        "level": { "type": "keyword" },
        "message": { "type": "text" },
        "logger": { "type": "keyword" },
        "request_id": { "type": "keyword" },
        "node_id": { "type": "keyword" },
        "user_id": { "type": "keyword" },
        "exception": {
          "properties": {
            "type": { "type": "keyword" },
            "message": { "type": "text" },
            "stacktrace": { "type": "text" }
          }
        },
        "context": { "type": "object" }
      }
    }
  }
}
```

**Example Document:**
```json
{
  "@timestamp": "2025-11-24T16:35:00Z",
  "service": "fiber-api",
  "level": "INFO",
  "message": "Metrics received from probe",
  "logger": "api.routes.push",
  "request_id": "req-123456",
  "node_id": "550e8400-e29b-41d4-a716-446655440000",
  "context": {
    "latency_ms": 45.23,
    "endpoint": "/api/push"
  }
}
```

**Retention:** 30 days (ILM policy)

---

### Index: `fiber-events-*`

Stores system events (node up/down, alerts, etc.).

**Index Template:**
```json
{
  "index_patterns": ["fiber-events-*"],
  "template": {
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "event_type": { "type": "keyword" },
        "node_id": { "type": "keyword" },
        "severity": { "type": "keyword" },
        "message": { "type": "text" },
        "metadata": { "type": "object" }
      }
    }
  }
}
```

**Retention:** 90 days

---

## Redis Data Structures

### 1. Message Queue (Redis Streams)

**Stream:** `fiber:etl:queue`

```
XADD fiber:etl:queue * payload '{"node_id":"...", "metrics":{...}}'
```

**Consumer Group:** `etl-workers`

### 2. Cache Keys

**Pattern:** `cache:metrics:{node_id}:{timerange_hash}`

```redis
# Example
cache:metrics:550e8400-e29b-41d4-a716-446655440000:1h-20251124
-> JSON serialized metrics array
TTL: 60 seconds
```

### 3. Rate Limiting

**Pattern:** `ratelimit:{api_key}:{minute}`

```redis
# Example
ratelimit:probe_key_12345:202511241635
-> Counter (incremented on each request)
TTL: 60 seconds
```

---

## API Data Models (JSON Schemas)

### POST /api/push - Request Payload

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["node_id", "country", "region", "timestamp"],
  "properties": {
    "node_id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique identifier for the probe node"
    },
    "country": {
      "type": "string",
      "pattern": "^[A-Z]{2}$",
      "description": "ISO 3166-1 alpha-2 country code"
    },
    "region": {
      "type": "string",
      "description": "Human-readable region name"
    },
    "latency_ms": {
      "type": "number",
      "minimum": 0,
      "maximum": 10000,
      "description": "Round-trip latency in milliseconds"
    },
    "uptime_pct": {
      "type": "number",
      "minimum": 0,
      "maximum": 100,
      "description": "Uptime percentage"
    },
    "packet_loss": {
      "type": "number",
      "minimum": 0,
      "maximum": 100,
      "description": "Packet loss percentage"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 timestamp (UTC)"
    },
    "metadata": {
      "type": "object",
      "description": "Additional metric-specific data"
    }
  }
}
```

### GET /api/metrics - Response

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "node_id": { "type": "string", "format": "uuid" },
    "node_name": { "type": "string" },
    "timeframe": {
      "type": "object",
      "properties": {
        "start": { "type": "string", "format": "date-time" },
        "end": { "type": "string", "format": "date-time" }
      }
    },
    "aggregation": {
      "type": "string",
      "enum": ["raw", "hourly", "daily"]
    },
    "data": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "time": { "type": "string", "format": "date-time" },
          "latency_ms": { "type": "number" },
          "uptime_pct": { "type": "number" },
          "packet_loss": { "type": "number" }
        }
      }
    },
    "summary": {
      "type": "object",
      "properties": {
        "avg_latency": { "type": "number" },
        "avg_uptime": { "type": "number" },
        "avg_packet_loss": { "type": "number" },
        "sample_count": { "type": "integer" }
      }
    }
  }
}
```

---

## Database Migration Strategy

### Tool: Alembic (Python)

**Directory Structure:**
```
fiber-db/
├── migrations/
│   ├── versions/
│   │   ├── 001_initial_schema.py
│   │   ├── 002_add_alerts_table.py
│   │   └── ...
│   ├── env.py
│   └── alembic.ini
└── schemas/
    └── schema.sql (reference SQL)
```

### Migration Workflow

1. **Development**: Create migration via `alembic revision -m "description"`
2. **Review**: Code review migration SQL
3. **Testing**: Apply to staging database
4. **Production**: Apply with downtime window (or online schema change for large tables)

### Rollback Strategy

- All migrations must have `upgrade()` and `downgrade()` functions
- Test rollback on staging before production deployment
- Keep backup before major schema changes

---

## Indexing Strategy

### Query Patterns & Indexes

| Query Pattern | Index Used | Performance Target |
|--------------|-----------|-------------------|
| Get metrics for node in time range | `idx_metrics_node_time` | <50ms |
| Recent metrics across all nodes | `idx_metrics_time` | <100ms |
| Hourly aggregates for dashboard | `idx_agg_hourly_node_time` | <20ms |
| Search logs by request ID | Elasticsearch | <200ms |
| Active nodes list | `idx_nodes_active` | <10ms |

### Index Maintenance

```sql
-- Reindex weekly (cron job)
REINDEX INDEX CONCURRENTLY idx_metrics_node_time;

-- Analyze statistics (daily)
ANALYZE metrics;
ANALYZE aggregates_hourly;
```

---

## Performance Considerations

### Query Optimization

**Bad Query** (full table scan):
```sql
SELECT * FROM metrics WHERE latency_ms > 100;
```

**Good Query** (uses indexes):
```sql
SELECT * FROM metrics 
WHERE node_id = '550e8400-e29b-41d4-a716-446655440000' 
  AND time >= NOW() - INTERVAL '1 hour'
  AND latency_ms > 100;
```

### Batch Operations

**ETL Batch Insert** (use COPY for bulk inserts):
```python
# Instead of individual INSERTs:
# for row in rows: session.add(row)

# Use COPY (100x faster):
conn.copy_from(csv_file, 'metrics', columns=[...])
```

---

## Database Backups

### Strategy

- **Continuous Archiving**: WAL archiving to S3/GCS (every 5 minutes)
- **Full Backups**: Daily at 2 AM UTC (pg_dump)
- **Retention**: 7 daily, 4 weekly, 12 monthly

### Restore Procedure

```bash
# Point-in-time recovery
pg_restore --clean --if-exists -d fiberstack backup_file.dump
```

---

## Security

### Access Control

```sql
-- Read-only user for dashboard queries
CREATE ROLE dashboard_reader WITH LOGIN PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE fiberstack TO dashboard_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dashboard_reader;

-- ETL writer (INSERT only)
CREATE ROLE etl_writer WITH LOGIN PASSWORD 'secure_password';
GRANT INSERT ON metrics TO etl_writer;
GRANT SELECT ON nodes TO etl_writer;
```

### Encryption

- **At Rest**: Encrypted volumes (LUKS or cloud provider encryption)
- **In Transit**: SSL/TLS for all database connections
- **Credentials**: Stored in secrets manager (not in code)

---

## References

- [TimescaleDB Documentation](https://docs.timescale.com/)
- [PostgreSQL Best Practices](https://wiki.postgresql.org/wiki/Performance_Optimization)
- [Elasticsearch Mapping](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html)
- [System Blueprint](file:///Users/macpro/FiberStack-Lite/docs/SYSTEM_BLUEPRINT.md)

---

**Document Status:** Draft - Pending Architecture Freeze  
**Next Step:** Review in [ARCHITECTURE_FREEZE.md](file:///Users/macpro/FiberStack-Lite/docs/ARCHITECTURE_FREEZE.md)
