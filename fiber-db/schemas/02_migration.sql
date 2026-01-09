-- Day 96 Migration: 1m and 5m continuous aggregates (No Toolkit)

-- 1-Minute Aggregate (Already applied? IF NOT EXISTS handles it)
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

SELECT add_retention_policy('aggregates_1m', INTERVAL '1 day', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_agg_1m_node_time ON aggregates_1m(node_id, bucket DESC);

-- 5-Minute Aggregate (Trends)
-- Removed percentile_agg due to missing toolkit
CREATE MATERIALIZED VIEW IF NOT EXISTS aggregates_5m_node
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT
    time_bucket('5 minutes', time) AS bucket,
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

SELECT add_continuous_aggregate_policy('aggregates_5m_node',
    start_offset => INTERVAL '20 minutes',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE);

SELECT add_retention_policy('aggregates_5m_node', INTERVAL '7 days', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_agg_5m_node_time ON aggregates_5m_node(node_id, bucket DESC);

-- Aggregate Health View
CREATE OR REPLACE VIEW aggregate_health AS
SELECT
    hypertable_name as view_name,
    materialization_hypertable_name,
    CASE 
        WHEN materialized_only = false THEN 'realtime_enabled'
        ELSE 'materialized_only'
    END AS mode
FROM timescaledb_information.continuous_aggregates;
