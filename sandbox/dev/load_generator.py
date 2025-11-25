import asyncio
import aiohttp
import random
import time
import uuid
import logging
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("load_gen")

API_URL = "http://localhost:8000/api/push"
NUM_PROBES = 5
DURATION_SECONDS = 60
INTERVAL_SECONDS = 1.0

async def simulate_probe(session, probe_id, region):
    """Simulate a single probe sending data."""
    logger.info(f"Probe {probe_id[:8]} started in {region}")
    
    end_time = time.time() + DURATION_SECONDS
    count = 0
    
    while time.time() < end_time:
        # Simulate metrics
        latency = random.uniform(20, 150)
        packet_loss = 0.0 if random.random() > 0.95 else random.uniform(0.1, 2.0)
        uptime = 100.0
        
        payload = {
            "node_id": probe_id,
            "country": "GH",
            "region": region,
            "latency_ms": round(latency, 2),
            "uptime_pct": uptime,
            "packet_loss": round(packet_loss, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {"simulated": True}
        }
        
        try:
            async with session.post(API_URL, json=payload) as resp:
                if resp.status == 202:
                    count += 1
                else:
                    logger.warning(f"Probe {probe_id[:8]} failed: {resp.status}")
        except Exception as e:
            logger.error(f"Probe {probe_id[:8]} error: {e}")
            
        await asyncio.sleep(INTERVAL_SECONDS + random.uniform(-0.1, 0.1))
        
    logger.info(f"Probe {probe_id[:8]} finished. Sent {count} metrics.")
    return count

async def main():
    logger.info(f"Starting Load Generator: {NUM_PROBES} probes for {DURATION_SECONDS}s")
    
    probes = [
        (str(uuid.uuid4()), "Accra"),
        (str(uuid.uuid4()), "Kumasi"),
        (str(uuid.uuid4()), "Lagos"),
        (str(uuid.uuid4()), "Abuja"),
        (str(uuid.uuid4()), "Nairobi")
    ]
    
    async with aiohttp.ClientSession() as session:
        tasks = [simulate_probe(session, pid, region) for pid, region in probes]
        results = await asyncio.gather(*tasks)
        
    total_sent = sum(results)
    logger.info(f"Load Test Complete. Total Metrics Sent: {total_sent}")

if __name__ == "__main__":
    asyncio.run(main())
