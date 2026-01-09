import asyncio
import aiohttp
import time
import uuid
import os
import random
from datetime import datetime, timezone

API_URL = "http://localhost:8000/api/ingest"
TOKEN = os.getenv("FEDERATION_TOKEN", "hybrid_dry_run_secret")
TOTAL_REQUESTS = 500
CONCURRENCY = 10

async def send_batch(session, batch_id):
    node_id = f"stress-node-{random.randint(1, 20)}"
    payload = {
        "node_id": node_id,
        "metrics": [{
            "node_id": node_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "country": "GH",
            "region": "Accra",
            "latency_ms": random.uniform(20, 100),
            "packet_loss": 0.0,
            "uptime_pct": 100.0,
            "metadata": {"stress": True, "batch_id": batch_id}
        }]
    }
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "X-Batch-ID": batch_id
    }
    try:
        async with session.post(API_URL, json=payload, headers=headers) as resp:
            return resp.status
    except Exception as e:
        print(f"Error: {e}")
        return 0

async def worker(queue, session):
    count = 0
    while not queue.empty():
        batch_id = await queue.get()
        status = await send_batch(session, batch_id)
        if status == 202:
            count += 1
        queue.task_done()
    return count

async def main():
    print(f"Starting burst injection: {TOTAL_REQUESTS} requests, concurrency {CONCURRENCY}")
    queue = asyncio.Queue()
    for _ in range(TOTAL_REQUESTS):
        queue.put_nowait(str(uuid.uuid4()))
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        tasks = [asyncio.create_task(worker(queue, session)) for _ in range(CONCURRENCY)]
        results = await asyncio.gather(*tasks)
    
    duration = time.time() - start_time
    total_sent = sum(results)
    print(f"Done. Sent {total_sent}/{TOTAL_REQUESTS} in {duration:.2f}s ({total_sent/duration:.2f} req/s)")

if __name__ == "__main__":
    asyncio.run(main())
