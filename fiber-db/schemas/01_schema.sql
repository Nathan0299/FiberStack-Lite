-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Table: nodes
CREATE TABLE IF NOT EXISTS nodes (
    node_id VARCHAR(50) PRIMARY KEY, -- Changed to VARCHAR to match API UUID string expectation or keep UUID if API sends valid UUIDs. API sends string. UUID type in PG handles it if format valid.
    -- Removing unused columns or making nullable
    node_name VARCHAR(255),
    display_name VARCHAR(255),
    
    -- API Fields
    status VARCHAR(20) DEFAULT 'registered', -- Replaces is_active
    country CHAR(2) NOT NULL,
    region VARCHAR(100) NOT NULL,
    lat DECIMAL(9,6), -- Renamed from latitude
    lng DECIMAL(9,6), -- Renamed from longitude
    
    last_seen_at TIMESTAMPTZ,
    probe_version VARCHAR(50),
    hardware_info JSONB,
    tags JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nodes_country ON nodes(country);
CREATE INDEX IF NOT EXISTS idx_nodes_region ON nodes(region);
CREATE INDEX IF NOT EXISTS idx_nodes_active ON nodes(status) WHERE status != 'deleted';
CREATE INDEX IF NOT EXISTS idx_nodes_last_seen ON nodes(last_seen_at DESC);

-- Table: metrics
CREATE TABLE IF NOT EXISTS metrics (
    time TIMESTAMPTZ NOT NULL,
    node_id VARCHAR(50) NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
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
    start_offset => NULL,
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE);

-- Day 46: Aggregated Analytics Table
CREATE TABLE IF NOT EXISTS metrics_aggregated (
    time TIMESTAMPTZ NOT NULL,
    node_id VARCHAR(50) NOT NULL,
    latency_avg_window DECIMAL(10,2),
    latency_std_window DECIMAL(10,2),
    packet_loss_spike BOOLEAN DEFAULT FALSE,
    anomaly_score DECIMAL(5,4), -- 0.0 to 1.0
    metadata JSONB
);

-- Hypertable for analytics
SELECT create_hypertable('metrics_aggregated', 'time', chunk_time_interval => INTERVAL '1 week', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_metrics_agg_node_time ON metrics_aggregated (node_id, time DESC);

-- Day 67: Per-Region 5-Minute Continuous Aggregate
-- Region Authority: nodes.country + nodes.region (canonical)
CREATE MATERIALIZED VIEW IF NOT EXISTS aggregates_5m_region
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', m.time) AS time,
    LOWER(n.country) || '-' || LOWER(REPLACE(n.region, ' ', '-')) AS region,
    AVG(m.latency_ms) AS avg_latency,
    STDDEV(m.latency_ms) AS std_latency,
    AVG(m.packet_loss) AS avg_loss,
    AVG(m.uptime_pct) AS avg_uptime,
    COUNT(*) AS samples
FROM metrics m
JOIN nodes n ON m.node_id = n.node_id
GROUP BY 1, 2;

SELECT add_continuous_aggregate_policy('aggregates_5m_region',
    start_offset => INTERVAL '15 minutes',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_agg_5m_region_time ON aggregates_5m_region(region, time DESC);

-- ============================================
-- Day 96: 1-Minute Per-Node Aggregate (Real-time Dashboard)
-- ============================================
-- Purpose: Real-time dashboard (last 10 min)
-- Freshness: 30 second refresh cycle
-- Late-arrival: 5 minute re-computation window

CREATE MATERIALIZED VIEW IF NOT EXISTS aggregates_1m
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT
    time_bucket('1 minute', time) AS bucket,
    node_id,
    AVG(latency_ms) AS avg_latency,
    MIN(latency_ms) AS min_latency,
    MAX(latency_ms) AS max_latency,
    AVG(uptime_pct) AS avg_uptime,
    AVG(packet_loss) AS avg_loss,
    COUNT(*) AS samples
FROM metrics
GROUP BY 1, 2
WITH NO DATA;

SELECT add_continuous_aggregate_policy('aggregates_1m',
    start_offset => INTERVAL '5 minutes',
    end_offset => INTERVAL '30 seconds',
    schedule_interval => INTERVAL '30 seconds',
    if_not_exists => TRUE);

-- Retention: Keep only 24 hours of 1-minute data
SELECT add_retention_policy('aggregates_1m', INTERVAL '1 day', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_agg_1m_node_time ON aggregates_1m(node_id, bucket DESC);

-- ============================================
-- Day 96: 5-Minute Per-Node Aggregate (Trends)
-- ============================================
-- Purpose: Short-term trends (1-6 hour queries)
-- Uses percentile_agg for statistical analysis

CREATE MATERIALIZED VIEW IF NOT EXISTS aggregates_5m_node
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT
    time_bucket('5 minutes', time) AS bucket,
    node_id,
    AVG(latency_ms) AS avg_latency,
    MIN(latency_ms) AS min_latency,
    MAX(latency_ms) AS max_latency,
    percentile_agg(latency_ms) AS latency_pctl,
    AVG(uptime_pct) AS avg_uptime,
    AVG(packet_loss) AS avg_loss,
    COUNT(*) AS samples
FROM metrics
GROUP BY 1, 2
WITH NO DATA;

SELECT add_continuous_aggregate_policy('aggregates_5m_node',
    start_offset => INTERVAL '20 minutes',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE);

-- Retention: Keep 7 days of 5-minute data
SELECT add_retention_policy('aggregates_5m_node', INTERVAL '7 days', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_agg_5m_node_time ON aggregates_5m_node(node_id, bucket DESC);

-- ============================================
-- Day 96: Aggregate Health Monitoring View
-- ============================================
CREATE OR REPLACE VIEW aggregate_health AS
SELECT
    hypertable_name as view_name,
    materialization_hypertable_name,
    CASE 
        WHEN materialized_only = false THEN 'realtime_enabled'
        ELSE 'materialized_only'
    END AS mode
FROM timescaledb_information.continuous_aggregates;
-- Day 97: Data Integrity & Auditing

-- 1. Ensure unique metrics per node/time (Partition-prudent: time first)
CREATE UNIQUE INDEX IF NOT EXISTS idx_metrics_unique 
ON metrics (time, node_id);

-- 2. Audit Table for Conflicts (Silent Drops)
CREATE TABLE IF NOT EXISTS metric_conflicts (
    id SERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    node_id VARCHAR(50) NOT NULL,
    payload JSONB,
    conflict_at TIMESTAMPTZ DEFAULT NOW(),
    ingest_region VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_conflicts_time ON metric_conflicts(time DESC);
