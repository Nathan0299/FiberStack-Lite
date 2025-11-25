import asyncio
import aiohttp
import psutil
import time
import uuid
import os
import logging
import random
from datetime import datetime, timezone
# from fiber_logging.configurator import init_logging
import sys
sys.path.insert(0, '/app/fiber-logging/src')
from logger import get_logger

# Initialize logging
logger = get_logger("fiber-probe", env=os.getenv("ENV", "dev"))

# Configuration
API_URL = os.getenv("API_URL", "http://localhost:8000/api/push")
NODE_ID = os.getenv("NODE_ID", str(uuid.uuid4()))
COUNTRY = os.getenv("COUNTRY", "GH")
REGION = os.getenv("REGION", "Accra")
INTERVAL = int(os.getenv("INTERVAL", "60"))

async def measure_latency(host="8.8.8.8"):
    """Measure latency to a target host (simulated for MVP)."""
    # In a real implementation, use ICMP ping or TCP connect
    # Simulating latency between 20ms and 150ms
    await asyncio.sleep(random.uniform(0.02, 0.1))
    return random.uniform(20.0, 150.0)

async def measure_packet_loss(host="8.8.8.8"):
    """Measure packet loss (simulated for MVP)."""
    # Simulating occasional packet loss
    if random.random() > 0.95:
        return random.uniform(1.0, 5.0)
    return 0.0

def get_system_uptime():
    """Get system uptime percentage (simulated based on CPU load)."""
    # In reality, uptime is usually 100% for the OS, but service availability varies
    # We'll use inverse of CPU load as a proxy for 'health' for now
    cpu_load = psutil.cpu_percent()
    return max(0.0, 100.0 - (cpu_load / 10.0)) # Fake logic for demo

async def collect_metrics():
    """Collect all metrics."""
    latency = await measure_latency()
    packet_loss = await measure_packet_loss()
    uptime = get_system_uptime()
    
    return {
        "node_id": NODE_ID,
        "country": COUNTRY,
        "region": REGION,
        "latency_ms": round(latency, 2),
        "uptime_pct": round(uptime, 2),
        "packet_loss": round(packet_loss, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent
        }
    }

async def send_metrics(session, metrics):
    """Send metrics to API."""
    try:
        async with session.post(API_URL, json=metrics) as response:
            if response.status == 202:
                logger.info(f"Metrics sent successfully: {metrics['latency_ms']}ms")
            else:
                logger.warning(f"Failed to send metrics: {response.status}")
    except Exception as e:
        logger.error(f"Error sending metrics: {e}")

async def main():
    logger.info(f"Starting Fiber-Probe {NODE_ID} ({COUNTRY}/{REGION})")
    
    async with aiohttp.ClientSession() as session:
        while True:
            start_time = time.time()
            
            try:
                metrics = await collect_metrics()
                await send_metrics(session, metrics)
            except Exception as e:
                logger.error(f"Collection cycle failed: {e}")
            
            # Sleep for remainder of interval
            elapsed = time.time() - start_time
            sleep_time = max(0, INTERVAL - elapsed)
            await asyncio.sleep(sleep_time)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Probe stopping...")
