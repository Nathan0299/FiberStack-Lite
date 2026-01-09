"""E2E Test API Helpers."""
import os
import requests
import uuid
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional

API_HOST = os.getenv("API_HOST", "localhost")
API_URL = f"http://{API_HOST}:8000/api"
FEDERATION_SECRET = os.getenv("FEDERATION_SECRET", "sandbox_secret")


def push_single_metric(
    node_id: str,
    latency_ms: float = 50.0,
    packet_loss: float = 0.0,
    uptime_pct: float = 100.0,
    country: str = "US",
    region: str = "Test"
) -> requests.Response:
    """Push a single metric via legacy /push endpoint."""
    payload = {
        "node_id": node_id,
        "country": country,
        "region": region,
        "latency_ms": latency_ms,
        "uptime_pct": uptime_pct,
        "packet_loss": packet_loss,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    return requests.post(f"{API_URL}/push", json=payload)


def push_batch_metrics(
    node_id: str,
    metrics: List[Dict],
    batch_id: Optional[str] = None
) -> requests.Response:
    """Push a batch of metrics via /ingest (federation) endpoint."""
    batch_id = batch_id or str(uuid.uuid4())
    payload = {
        "node_id": node_id,
        "metrics": metrics
    }
    headers = {
        "Authorization": f"Bearer {FEDERATION_SECRET}",
        "X-Batch-ID": batch_id,
        "Content-Type": "application/json"
    }
    return requests.post(f"{API_URL}/ingest", json=payload, headers=headers)


def get_aggregated_metrics(dimension: str = "region") -> requests.Response:
    """Fetch aggregated metrics."""
    return requests.get(f"{API_URL}/metrics/aggregated", params={"dimension": dimension})


def get_api_status() -> requests.Response:
    """Get API/ETL status."""
    return requests.get(f"{API_URL}/status")
