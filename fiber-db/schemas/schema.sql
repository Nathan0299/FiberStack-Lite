-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Table: nodes
CREATE TABLE IF NOT EXISTS nodes (
    node_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_name VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    country CHAR(2) NOT NULL,
    region VARCHAR(100) NOT NULL,
    city VARCHAR(100),
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
    is_active BOOLEAN DEFAULT true,
    last_seen_at TIMESTAMPTZ,
    probe_version VARCHAR(50),
    hardware_info JSONB,
    tags JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nodes_country ON nodes(country);
CREATE INDEX IF NOT EXISTS idx_nodes_region ON nodes(region);
CREATE INDEX IF NOT EXISTS idx_nodes_active ON nodes(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_nodes_last_seen ON nodes(last_seen_at DESC);

-- Table: metrics
CREATE TABLE IF NOT EXISTS metrics (
    time TIMESTAMPTZ NOT NULL,
    node_id UUID NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    latency_ms DECIMAL(10,2),
    uptime_pct DECIMAL(5,2),
    packet_loss DECIMAL(5,2),
    target_host VARCHAR(255),
    probe_type VARCHAR(50),
    metadata JSONB
);

-- Convert to hypertable
SELECT create_hypertable('metrics', 'time', chunk_time_interval => INTERVAL '1 week', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_metrics_node_time ON metrics (node_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_time ON metrics (time DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_metadata ON metrics USING GIN (metadata);

-- Compression policy
ALTER TABLE metrics SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'node_id'
);

SELECT add_compression_policy('metrics', INTERVAL '3 days', if_not_exists => TRUE);

-- Continuous Aggregate: Hourly
CREATE MATERIALIZED VIEW IF NOT EXISTS aggregates_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS time,
    node_id,
    AVG(latency_ms) AS avg_latency_ms,
    MIN(latency_ms) AS min_latency_ms,
    MAX(latency_ms) AS max_latency_ms,
    AVG(uptime_pct) AS avg_uptime_pct,
    AVG(packet_loss) AS avg_packet_loss,
    COUNT(*) AS sample_count
FROM metrics
GROUP BY time_bucket('1 hour', time), node_id;

SELECT add_continuous_aggregate_policy('aggregates_hourly',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '0 hours',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);

-- Continuous Aggregate: Daily
CREATE MATERIALIZED VIEW IF NOT EXISTS aggregates_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS time,
    node_id,
    AVG(latency_ms) AS avg_latency_ms,
    MIN(latency_ms) AS min_latency_ms,
    MAX(latency_ms) AS max_latency_ms,
    AVG(uptime_pct) AS avg_uptime_pct,
    AVG(packet_loss) AS avg_packet_loss,
    COUNT(*) AS sample_count
FROM metrics
GROUP BY time_bucket('1 day', time), node_id;

SELECT add_continuous_aggregate_policy('aggregates_daily',
    start_offset => INTERVAL '2 days',
    end_offset => INTERVAL '0 days',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE);
