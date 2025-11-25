import asyncio
import aiohttp
import asyncpg
import json
import uuid
import os
import time
from datetime import datetime, timezone

# Configuration
API_URL = "http://localhost:8000/api/push"
DB_DSN = "postgresql://postgres:postgres@localhost:5432/fiberstack"

async def send_mock_metric(session, node_id):
    """Send a single mock metric to the API."""
    payload = {
        "node_id": node_id,
        "country": "GH",
        "region": "Test Region",
        "latency_ms": 50.5,
        "uptime_pct": 99.9,
        "packet_loss": 0.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {"test": True}
    }
    async with session.post(API_URL, json=payload) as resp:
        return resp.status

async def verify_db_insertion(node_id):
    """Check if the metric arrived in TimescaleDB."""
    # Wait up to 10 seconds for ETL to process
    for _ in range(10):
        try:
            conn = await asyncpg.connect(DB_DSN)
            row = await conn.fetchrow(
                "SELECT * FROM metrics WHERE node_id = $1", node_id
            )
            await conn.close()
            if row:
                return True
        except Exception as e:
            print(f"DB Connect failed: {e}")
        
        await asyncio.sleep(1)
    return False

async def main():
    print("Starting End-to-End Data Flow Test...")
    
    node_id = str(uuid.uuid4())
    print(f"Generated Test Node ID: {node_id}")
    
    async with aiohttp.ClientSession() as session:
        # 1. Send Metric
        print("Sending metric to API...")
        try:
            status = await send_mock_metric(session, node_id)
            if status == 202:
                print("✅ API accepted metric (202 Accepted)")
            else:
                print(f"❌ API failed: {status}")
                return
        except Exception as e:
            print(f"❌ API connection failed: {e}")
            print("Make sure Docker stack is running!")
            return

        # 2. Verify DB
        print("Verifying Database insertion (waiting for ETL)...")
        if await verify_db_insertion(node_id):
            print("✅ Metric found in TimescaleDB!")
            print("🎉 End-to-End Flow SUCCESS!")
        else:
            print("❌ Metric NOT found in DB after 10s.")
            print("Check fiber-etl logs.")

if __name__ == "__main__":
    asyncio.run(main())
