import asyncio
import aiohttp
import psutil
import time
import uuid
import os
import logging
import random
import yaml
from datetime import datetime, timezone
import sys

# Add logging path
sys.path.insert(0, '/app/fiber-logging/src')
# Fallback if local
if os.path.exists('../fiber-logging/src'):
    sys.path.insert(0, '../fiber-logging/src')

try:
    from logger import get_logger
except ImportError:
    # Fallback basic logger
    logging.basicConfig(level=logging.INFO)
    def get_logger(name, env): return logging.getLogger(name)

from client import FederationClient

# Initialize logging
ENV = os.getenv("ENV", "dev")
logger = get_logger("fiber-probe", env=ENV)

# Defaults
DEFAULT_CONFIG_PATH = "../configs/federation.yaml"
NODE_ID = os.getenv("NODE_ID", str(uuid.uuid4()))

def load_config(path: str) -> dict:
    """Load federation config from YAML or return defaults."""
    config = {
        "federation": {
            "node_id": NODE_ID,
            "targets": []
        }
    }
    
    # Try to load YAML
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                # Expand env vars in YAML? For MVP, simple load.
                # Ideally we'd use a parser that expands ${VAR}
                # Here we just rely on the structure.
                loaded = yaml.safe_load(f)
                if loaded:
                    config = loaded
            logger.info(f"Loaded config from {path}")
        except Exception as e:
            logger.error(f"Failed to load config {path}: {e}")
    else:
        logger.warning(f"Config {path} not found, using legacy ENV vars")
        # Legacy fallback
        api_url = os.getenv("API_URL")
        if api_url:
             config["federation"]["targets"].append({
                 "name": "legacy-env",
                 "url": api_url,
                 "enabled": True,
                 "auth": {"type": "bearer", "token_env": "FEDERATION_TOKEN_CLOUD"}
             })

    return config

async def measure_latency(host="8.8.8.8"):
    await asyncio.sleep(random.uniform(0.02, 0.1))
    return random.uniform(20.0, 150.0)

async def measure_packet_loss(host="8.8.8.8"):
    if random.random() > 0.95:
        return random.uniform(1.0, 5.0)
    return 0.0

def get_system_uptime():
    cpu_load = psutil.cpu_percent()
    return max(0.0, 100.0 - (cpu_load / 10.0))

async def collect_metrics(node_id, country, region):
    latency = await measure_latency()
    packet_loss = await measure_packet_loss()
    uptime = get_system_uptime()
    
    return {
        "node_id": node_id,
        "country": country,
        "region": region,
        "latency_ms": round(latency, 2),
        "uptime_pct": round(uptime, 2),
        "packet_loss": round(packet_loss, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent
        }
    }

def expand_env_vars(url: str) -> str:
    """Simple env var expansion for URLs."""
    if not url: return ""
    import re
    # Replace ${VAR} with os.getenv('VAR')
    return re.sub(r'\$\{([^}]+)\}', lambda m: os.getenv(m.group(1), ''), url)


async def main():
    logger.info(f"Starting Fiber-Probe {NODE_ID}")
    
    # Load Config
    config_path = os.getenv("CONFIG_PATH", DEFAULT_CONFIG_PATH)
    config = load_config(config_path)
    
    fed_config = config.get("federation", {})
    resolved_node_id = expand_env_vars(fed_config.get("node_id", NODE_ID))
    
    # Initialize Clients
    clients = []
    defaults = fed_config.get("defaults", {})
    
    for target_conf in fed_config.get("targets", []):
        if not target_conf.get("enabled", True):
            continue
            
        # Merge defaults (simplistic)
        final_conf = {**defaults, **target_conf}
        # Expand URL
        final_conf["url"] = expand_env_vars(final_conf["url"])
        
        client = FederationClient(final_conf["name"], final_conf)
        clients.append(client)
        logger.info(f"Initialized target: {client.name} -> {client.url}")

    if not clients:
        logger.warning("No targets configured! Probe will run but not push anywhere.")

    # Day 77: Initialize Failover Controller
    failover_enabled = os.getenv("FAILOVER_ENABLED", "true").lower() == "true"
    
    if failover_enabled:
        try:
            from failover import FailoverController
            controller = FailoverController(clients, node_id=resolved_node_id)
            logger.info("FailoverController enabled (priority-based failover)")
        except ImportError:
            from failover import FanOutController
            controller = FanOutController(clients, node_id=resolved_node_id)
            logger.warning("FailoverController import failed, using FanOutController")
    else:
        try:
            from failover import FanOutController
            controller = FanOutController(clients, node_id=resolved_node_id)
            logger.info("FanOutController enabled (legacy fan-out mode)")
        except ImportError:
            controller = None
            logger.warning("No controller available, using direct push")

    # Main Loop
    country = os.getenv("COUNTRY", "GH")
    region = os.getenv("REGION", "Accra")
    interval = int(os.getenv("PROBE_INTERVAL", os.getenv("INTERVAL", "30")))
    heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL", "60"))
    last_heartbeat = 0

    # Day 97: Durable Buffer
    from buffer import DurableBuffer
    BUFFER_PATH = os.getenv("BUFFER_PATH", "/data/buffer.db")
    buffer = DurableBuffer(BUFFER_PATH)

    async def producer():
        while True:
            start = time.time()
            try:
                metric = await collect_metrics(resolved_node_id, country, region)
                if not buffer.push(metric):
                    logger.warning("Buffer full! Dropped metric.")
            except Exception as e:
                logger.error(f"Producer error: {e}")
            
            # Sleep
            elapsed = time.time() - start
            await asyncio.sleep(max(0, interval - elapsed))

    async def consumer(session):
        while True:
            try:
                # Peek batch
                batch_items = buffer.peek_batch(50)
                if not batch_items:
                    await asyncio.sleep(1)
                    continue
                
                # Extract payloads
                payloads = [item["data"] for item in batch_items]
                ids = [item["_id"] for item in batch_items]
                
                # Push
                if controller:
                    success, active = await controller.push(session, payloads, resolved_node_id)
                else:
                    success = False # Should have controller
                
                if success:
                    buffer.acknowledge(ids)
                    logger.debug(f"Consumer: Acked {len(ids)} metrics")
                else:
                    logger.warning("Consumer: Push failed, retrying...")
                    await asyncio.sleep(5) # Backoff
            except Exception as e:
                logger.error(f"Consumer error: {e}")
                await asyncio.sleep(5)

            # Heartbeat (simplified location)
            if time.time() - last_heartbeat[0] > heartbeat_interval:
                await emit_federation_heartbeat(
                    session, resolved_node_id, 
                    controller.get_active_target() if controller else "unknown"
                )
                last_heartbeat[0] = time.time()

    # Run Loops
    last_heartbeat = [0]
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(
            producer(),
            consumer(session)
        )


async def emit_federation_heartbeat(session: aiohttp.ClientSession, node_id: str, active_target: str):
    """Emit current federation state as a heartbeat to the API."""
    api_base = os.getenv("API_URL", "http://localhost:8000")
    # Strip /ingest or other paths if present
    if "/api/" in api_base:
        api_base = api_base.split("/api/")[0]
    
    heartbeat_url = f"{api_base}/api/probe/heartbeat"
    
    payload = {
        "node_id": node_id,
        "active_target": active_target,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        async with session.post(heartbeat_url, json=payload, timeout=5) as resp:
            if resp.status == 200:
                logger.debug(f"Heartbeat sent: active_target={active_target}")
            else:
                logger.warning(f"Heartbeat failed: HTTP {resp.status}")
    except Exception as e:
        logger.debug(f"Heartbeat failed (endpoint may not exist): {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Probe stopping...")

