import asyncio
import asyncpg
import os
import sys

# Centralized logging (entrypoint pattern)
sys.path.insert(0, '/app/fiber-logging/src')
try:
    from logger import get_logger
    logger = get_logger("fiber-etl", env=os.getenv("ENV", "dev"))
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("fiber-etl")

# Configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")
DB_NAME = os.getenv("DB_NAME", "fiberstack")
async def apply_schema():
    logger.info(f"Connecting to {DB_HOST}/{DB_NAME}...")
    try:
        conn = await asyncpg.connect(
            user=DB_USER, password=DB_PASS, database=DB_NAME, host=DB_HOST
        )
        
        logger.info("Creating table metrics_aggregated...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS metrics_aggregated (
                time TIMESTAMPTZ NOT NULL,
                node_id UUID NOT NULL,
                latency_avg_window DECIMAL(10,2),
                latency_std_window DECIMAL(10,2),
                packet_loss_spike BOOLEAN DEFAULT FALSE,
                anomaly_score DECIMAL(5,4), -- 0.0 to 1.0
                metadata JSONB
            );
        """)
        
        logger.info("Converting to hypertable...")
        # Check if already hypertable
        is_hyper = await conn.fetchval("""
            SELECT 1 FROM timescaledb_information.hypertables 
            WHERE hypertable_name = 'metrics_aggregated'
        """)
        
        if not is_hyper:
            await conn.execute("""
                SELECT create_hypertable('metrics_aggregated', 'time', chunk_time_interval => INTERVAL '1 week', if_not_exists => TRUE);
            """)
        
        logger.info("Creating indexes...")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_agg_node_time ON metrics_aggregated (node_id, time DESC);
        """)
        
        logger.info("Schema applied successfully.")
        await conn.close()
        
    except Exception as e:
        logger.error(f"Failed to apply schema: {e}")
        exit(1)

if __name__ == "__main__":
    asyncio.run(apply_schema())
