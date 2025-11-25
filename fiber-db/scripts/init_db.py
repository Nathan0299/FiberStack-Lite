import os
import time
import asyncio
import asyncpg
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_db")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "postgres")
DB_NAME = os.getenv("DB_NAME", "fiberstack")

async def wait_for_db():
    """Wait for TimescaleDB to be ready."""
    logger.info(f"Waiting for Database at {DB_HOST}...")
    for i in range(30):
        try:
            conn = await asyncpg.connect(
                user=DB_USER, password=DB_PASS, database=DB_NAME, host=DB_HOST
            )
            await conn.close()
            logger.info("Database is ready!")
            return True
        except Exception:
            pass
        time.sleep(2)
    logger.error("Database failed to start.")
    return False

async def apply_schema():
    """Apply schema.sql to the database."""
    schema_path = os.path.join(os.path.dirname(__file__), "../schemas/schema.sql")
    
    with open(schema_path, "r") as f:
        schema_sql = f.read()

    try:
        conn = await asyncpg.connect(
            user=DB_USER, password=DB_PASS, database=DB_NAME, host=DB_HOST
        )
        await conn.execute(schema_sql)
        await conn.close()
        logger.info("Schema applied successfully!")
    except Exception as e:
        logger.error(f"Failed to apply schema: {e}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    if loop.run_until_complete(wait_for_db()):
        loop.run_until_complete(apply_schema())
