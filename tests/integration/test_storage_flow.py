import pytest
import httpx
import uuid
import os
from datetime import datetime, timezone
from tests.utils.docker_helpers import verify_db_record_exists

API_URL = f"http://{os.getenv('API_HOST', 'localhost')}:8000/api"

@pytest.mark.asyncio
async def test_e2e_storage_flow(probe_token):
    """Test full pipeline: API -> Redis -> ETL -> DB using shared helper."""
    # 1. Prepare Data
    node_id = str(uuid.uuid4())
    payload = {
        "node_id": node_id,
        "country": "TE",
        "region": "Refactored",
        "latency_ms": 123.45,
        "uptime_pct": 99.9,
        "packet_loss": 0.01,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # 2. Push to API (Async with Auth)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/push", 
            json=payload,
            headers={"Authorization": f"Bearer {probe_token}"}
        )
    
    assert response.status_code == 202, f"Expected 202 Accepted, got {response.status_code}: {response.text}"
    
    # 3. Verify DB (Sync helper remains)
    print(f"\nWaiting for metric {node_id} to appear in DB...")
    # This helper checks DB via docker exec so it works from outside
    found = verify_db_record_exists(node_id)
    assert found, f"Metric {node_id} not found in DB after retries (Check ETL logs)"
