import asyncpg
import asyncio

class DbAssertionHelper:
    def __init__(self, dsn):
        self.dsn = dsn

    async def get_count(self, table, condition=None):
        conn = await asyncpg.connect(self.dsn)
        try:
            query = f"SELECT COUNT(*) FROM {table}"
            if condition:
                query += f" WHERE {condition}"
            return await conn.fetchval(query)
        finally:
            await conn.close()

    async def wait_for_data(self, table, condition=None, min_count=1, timeout=30):
        for _ in range(timeout):
            count = await self.get_count(table, condition)
            if count >= min_count:
                return count
            await asyncio.sleep(1)
        raise AssertionError(f"Timeout waiting for data in {table} (current: {await self.get_count(table, condition)})")

    async def get_node_status(self, node_id):
        conn = await asyncpg.connect(self.dsn)
        try:
            return await conn.fetchval("SELECT status FROM nodes WHERE node_id = $1", node_id)
        finally:
            await conn.close()
