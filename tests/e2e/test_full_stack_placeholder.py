import pytest
import requests
import uuid
import os
import time
from datetime import datetime, timezone
from tests.utils.docker_helpers import verify_db_record_exists, verify_alert_in_logs, get_redis_key
from tests.utils.api_helpers import (
    push_single_metric, 
    push_batch_metrics, 
    get_aggregated_metrics, 
    API_URL, 
    FEDERATION_SECRET
)

DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "localhost")
DASHBOARD_URL = f"http://{DASHBOARD_HOST}:3000"

@pytest.mark.e2e
def test_dashboard_reachability():
    """Verify Dashboard (Grafana) is up and reachable."""
    try:
        r = requests.get(DASHBOARD_URL)
        # 200 OK or 302 Found (login page) are acceptable
        assert r.status_code in [200, 302], f"Dashboard returned {r.status_code}"
        # Basic check for Grafana HTML signature or Login title
        assert "Grafana" in r.text or "<html" in r.text.lower(), "Dashboard did not return likely Grafana content"
    except requests.exceptions.ConnectionError:
        pytest.fail(f"Dashboard unreachable at {DASHBOARD_URL}")

@pytest.mark.e2e
def test_basic_probe_to_dashboard():
    """
    End-to-End Test: Probe -> API -> DB -> Dashboard.
    """
    # 1. Simulate Probe Push
    node_id = str(uuid.uuid4())
    resp = push_single_metric(node_id=node_id, region="E2E-Basic")
    assert resp.status_code == 202, f"Expected 202 Accepted, got {resp.status_code}: {resp.text}"

    # 2. Verify Persistence
    print(f"\nWaiting for metric {node_id} in DB...")
    # Note: In sandbox, the container is named 'fiber-db'
    persistence_success = verify_db_record_exists(node_id, container_name="fiber-db")
    assert persistence_success, f"Metric {node_id} failed to persist in DB"

@pytest.mark.e2e
class TestProbeFederation:
    """Test suite for probe federation (batch ingestion)."""

    def test_batch_ingest_success(self):
        """Test successful batch ingestion with valid auth."""
        node_id = f"test-node-{uuid.uuid4().hex[:8]}"
        metrics = [
            {
                "node_id": node_id,
                "country": "US",
                "region": "Virginia",
                "latency_ms": 45.0,
                "uptime_pct": 100.0,
                "packet_loss": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]
        
        resp = push_batch_metrics(node_id, metrics)
        assert resp.status_code == 202
        assert "accepted" in resp.json()["status"]

    def test_batch_ingest_invalid_auth(self):
        """Test batch ingestion fails with invalid auth."""
        resp = requests.post(
            f"{API_URL}/ingest",
            json={"node_id": "test", "metrics": []},
            headers={"Authorization": "Bearer invalid_token", "X-Batch-ID": str(uuid.uuid4())}
        )
        assert resp.status_code == 401

    def test_batch_ingest_missing_batch_id(self):
        """Test batch ingestion fails without X-Batch-ID header."""
        resp = requests.post(
            f"{API_URL}/ingest",
            json={"node_id": "test", "metrics": []},
            headers={"Authorization": f"Bearer {FEDERATION_SECRET}"}
        )
        assert resp.status_code == 400

    def test_batch_idempotency(self):
        """Test same batch_id is idempotent (processed once)."""
        node_id = f"test-node-{uuid.uuid4().hex[:8]}"
        batch_id = str(uuid.uuid4())
        metrics = [{
            "node_id": node_id,
            "country": "US",
            "region": "Test",
            "latency_ms": 50.0,
            "uptime_pct": 100.0,
            "packet_loss": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }]
        
        # First request
        resp1 = push_batch_metrics(node_id, metrics, batch_id=batch_id)
        assert resp1.status_code == 202
        
        # Second request with same batch_id
        resp2 = push_batch_metrics(node_id, metrics, batch_id=batch_id)
        assert resp2.status_code == 202
        assert "already processed" in resp2.json().get("message", "").lower()

@pytest.mark.e2e
class TestAlertTriggers:
    """Test suite for alert triggering."""

    def test_latency_warning_alert(self):
        """Test latency > 200ms triggers WARNING alert."""
        node_id = f"alert-test-{uuid.uuid4().hex[:8]}"
        
        # Push metric with high latency
        resp = push_single_metric(
            node_id=node_id,
            latency_ms=250.0,  # > ALERT_LATENCY_WARN (200)
            packet_loss=0.0
        )
        assert resp.status_code == 202
        
        # Wait for ETL to process and check logs
        # Higher cooldown might be needed for ETL to pick it up and process
        time.sleep(5)
        assert verify_alert_in_logs(node_id, severity="warning"), \
            f"Expected WARNING alert for node {node_id}"

    def test_latency_critical_alert(self):
        """Test latency > 500ms triggers CRITICAL alert."""
        node_id = f"alert-crit-{uuid.uuid4().hex[:8]}"
        
        resp = push_single_metric(
            node_id=node_id,
            latency_ms=600.0,  # > ALERT_LATENCY_CRIT (500)
            packet_loss=0.0
        )
        assert resp.status_code == 202
        
        time.sleep(5)
        assert verify_alert_in_logs(node_id, severity="critical"), \
            f"Expected CRITICAL alert for node {node_id}"

    def test_packet_loss_warning_alert(self):
        """Test packet_loss > 1% triggers WARNING alert."""
        node_id = f"loss-test-{uuid.uuid4().hex[:8]}"
        
        resp = push_single_metric(
            node_id=node_id,
            latency_ms=50.0,
            packet_loss=2.0  # > ALERT_LOSS_WARN (1.0)
        )
        assert resp.status_code == 202
        
        time.sleep(5)
        assert verify_alert_in_logs(node_id, severity="warning"), \
            f"Expected WARNING alert for packet loss on {node_id}"

    def test_alert_deduplication(self):
        """Test alerts are deduplicated (same alert not fired within cooldown)."""
        node_id = f"dedup-test-{uuid.uuid4().hex[:8]}"
        
        # Push first metric
        resp = push_single_metric(node_id=node_id, latency_ms=250.0)
        assert resp.status_code == 202
        time.sleep(5)
        
        # Check Redis for dedup key
        # The key pattern from alerts.py is f"alert:throttle:{self.node_id}:{self.metric_name}:{self.severity.value}"
        dedup_key = f"alert:throttle:{node_id}:latency_ms:warning"
        key_value = get_redis_key(dedup_key)
        assert key_value == "1", f"Alert deduplication key {dedup_key} should be set in Redis"

@pytest.mark.e2e
class TestAggregatedMetrics:
    """Test suite for aggregated metrics endpoint."""

    def test_aggregation_by_region(self):
        """Test aggregation grouped by region."""
        # Push some metrics first
        node_id = f"agg-test-{uuid.uuid4().hex[:8]}"
        region = f"Region-{uuid.uuid4().hex[:4]}"
        push_single_metric(node_id=node_id, latency_ms=100.0, region=region)
        push_single_metric(node_id=node_id, latency_ms=200.0, region=region) 
        
        time.sleep(5)  # Wait for ETL
        
        resp = get_aggregated_metrics(dimension="region")
        assert resp.status_code == 200
        
        data = resp.json()["data"]
        assert isinstance(data, list)
        
        # Find our region in the results
        # Dimension format is "region/country"
        region_data = next((d for d in data if region in d.get("dimension", "")), None)
        assert region_data is not None, f"Region {region} not found in aggregated results"
        assert region_data["reporting_count"] >= 2

    def test_aggregation_by_node(self):
        """Test aggregation grouped by node."""
        node_id = f"node-agg-{uuid.uuid4().hex[:8]}"
        push_single_metric(node_id=node_id, latency_ms=150.0)
        time.sleep(5)
        
        resp = get_aggregated_metrics(dimension="node")
        assert resp.status_code == 200
        
        data = resp.json()["data"]
        assert isinstance(data, list)
        node_data = next((d for d in data if node_id == d.get("dimension")), None)
        assert node_data is not None

    def test_aggregation_calculates_p95(self):
        """Test that p95 latency is calculated correctly."""
        # Push metrics with known latencies
        node_id = f"p95-test-{uuid.uuid4().hex[:8]}"
        latencies = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        
        for lat in latencies:
            push_single_metric(node_id=node_id, latency_ms=float(lat), region="P95Test")
        
        time.sleep(6)  # Wait for ETL
        
        resp = get_aggregated_metrics(dimension="node")
        assert resp.status_code == 200
        
        data = resp.json()["data"]
        node_data = next((d for d in data if node_id == d.get("dimension", "")), None)
        
        assert node_data is not None
        # p95 of [10-100] should be ~95
        assert node_data["p95_latency"] >= 90, f"p95 ({node_data['p95_latency']}) should be >= 90"

    def test_aggregation_invalid_dimension(self):
        """Test aggregation fails with invalid dimension."""
        resp = requests.get(f"{API_URL}/metrics/aggregated", params={"dimension": "invalid"})
        assert resp.status_code == 422  # Validation error (regex check)
