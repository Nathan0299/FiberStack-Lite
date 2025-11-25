import asyncio
import json
import os
import logging
import asyncpg
import redis.asyncio as redis
from datetime import datetime
# from fiber_logging.configurator import init_logging
import sys
sys.path.insert(0, '/app/fiber-logging/src')
from logger import get_logger

# Initialize logging
logger = get_logger("fiber-etl", env=os.getenv("ENV", "dev"))

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")
DB_NAME = os.getenv("DB_NAME", "fiberstack")
QUEUE_KEY = "fiber:etl:queue"
BATCH_SIZE = 100

async def get_db_connection():
    return await asyncpg.connect(
        user=DB_USER, password=DB_PASS, database=DB_NAME, host=DB_HOST
    )

async def ensure_node_exists(conn, node_id, country, region):
    """Ensure node exists in metadata table."""
    # In a real system, we might cache this check
    await conn.execute("""
        INSERT INTO nodes (node_id, node_name, country, region)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (node_id) DO UPDATE 
        SET last_seen_at = NOW()
    """, node_id, f"probe-{node_id[:8]}", country, region)

async def process_batch(redis_client, db_pool):
    """Process a batch of messages from Redis."""
    # Pop multiple items (simulated with loop for MVP, ideally use pipelining or Lua)
    messages = []
    for _ in range(BATCH_SIZE):
        msg = await redis_client.lpop(QUEUE_KEY)
        if not msg:
            break
        messages.append(msg)
    
    if not messages:
        return 0

    logger.info(f"Processing batch of {len(messages)} metrics")
    
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            for msg in messages:
                try:
                    data = json.loads(msg)
                    
                    # 1. Ensure node exists
                    await ensure_node_exists(conn, data['node_id'], data['country'], data['region'])
                    
                    # 2. Insert metric
                    await conn.execute("""
                        INSERT INTO metrics (
                            time, node_id, latency_ms, uptime_pct, packet_loss, metadata
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                    """, 
                    datetime.fromisoformat(data['timestamp']),
                    data['node_id'],
                    data['latency_ms'],
                    data['uptime_pct'],
                    data['packet_loss'],
                    json.dumps(data.get('metadata', {}))
                    )
                except Exception as e:
                    logger.error(f"Failed to process message: {e}", extra={"msg": msg})
                    # In prod, send to Dead Letter Queue (DLQ)
    
    return len(messages)

async def main():
    logger.info("Starting Fiber-ETL Worker")
    
    # Connect to Redis
    redis_client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    
    # Create DB pool
    db_pool = await asyncpg.create_pool(
        user=DB_USER, password=DB_PASS, database=DB_NAME, host=DB_HOST
    )
    
    try:
        while True:
            processed = await process_batch(redis_client, db_pool)
            if processed == 0:
                await asyncio.sleep(1) # Wait if queue is empty
    except Exception as e:
        logger.critical(f"ETL Worker crashed: {e}")
    finally:
        await redis_client.close()
        await db_pool.close()

if __name__ == "__main__":
    asyncio.run(main())
