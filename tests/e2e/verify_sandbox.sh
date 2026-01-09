#!/bin/bash
set -e

API_URL="http://localhost:8000"
MAX_RETRIES=30

echo "🔍 Starting Sandbox Verification..."

# 1. Wait for API Liveness
echo -n "Waiting for API..."
for i in $(seq 1 $MAX_RETRIES); do
    if curl -s "$API_URL/health" | grep -q "ok"; then
        echo " UP!"
        break
    fi
    echo -n "."
    sleep 2
done

# 2. Hybrid Setup: Register Nodes (Simulate Administration/Provisioning)
# Note: Nodes may already exist if probes started pushing before this script runs
echo "Registering Sandbox Nodes..."
curl -s -X POST "$API_URL/api/nodes" \
  -H "Content-Type: application/json" \
  -d '{"node_id": "us-east-1", "status": "registered", "country": "US", "region": "Virginia", "lat": 38.0, "lng": -77.0}' | grep -E "(created|already exists|Conflict)" || true
curl -s -X POST "$API_URL/api/nodes" \
  -H "Content-Type: application/json" \
  -d '{"node_id": "eu-west-1", "status": "registered", "country": "IE", "region": "Dublin", "lat": 53.0, "lng": -6.0}' | grep -E "(created|already exists|Conflict)" || true
curl -s -X POST "$API_URL/api/nodes" \
  -H "Content-Type: application/json" \
  -d '{"node_id": "asia-south-1", "status": "registered", "country": "IN", "region": "Mumbai", "lat": 19.0, "lng": 72.0}' | grep -E "(created|already exists|Conflict)" || true

# 2.5 Wait for Data Flow
echo "Generated Traffic: Waiting 30s for probes to push metrics..."
sleep 30

# 3. Check Active Nodes
echo -n "Checking Registered Nodes (Expect 3)..."
NODE_COUNT=$(curl -s "$API_URL/api/nodes" | grep -o "node_id" | wc -l)
echo " Found: $NODE_COUNT"
if [ "$NODE_COUNT" -lt 3 ]; then
    echo "❌ FAIL: Expected at least 3 nodes"
    exit 1
fi

# 4. Check Metrics Flow
echo -n "Checking Metrics Flow..."
METRIC_COUNT=$(curl -s "$API_URL/api/metrics?limit=10" | grep -o "latency_ms" | wc -l)
echo " Recent Limit Count: $METRIC_COUNT"
if [ "$METRIC_COUNT" -eq 0 ]; then
    echo "❌ FAIL: No metrics found in API"
    exit 1
fi

# 5. Deep ETL Health Check
echo -n "Checking ETL Health Status..."
ETL_STATE=$(curl -s "$API_URL/api/status" | grep -o '"state":"[^"]*"' | cut -d'"' -f4)
echo " State: $ETL_STATE"
if [ "$ETL_STATE" != "healthy" ]; then
    echo "❌ FAIL: ETL is not reporting 'healthy' (Found: $ETL_STATE)"
    # Allow 'degraded' for now if just starting up? No, contract says healthy.
    exit 1
fi

# 6. Negative Data Validation (via docker exec psql)
echo -n "Running Negative Data Validation (SQL)..."
# Check for latency=0 artifacts
ZERO_LATENCY=$(docker compose -f sandbox/dev/docker-compose.sandbox.yml exec fiber-db psql -U postgres -d fiberstack -t -c "SELECT count(*) FROM metrics WHERE latency_ms = 0;")
ZERO_LATENCY=$(echo $ZERO_LATENCY | xargs) # trim
if [ "$ZERO_LATENCY" != "0" ]; then
    echo "❌ FAIL: Found $ZERO_LATENCY metrics with latency_ms=0 (Polluted Data)"
    exit 1
fi
echo " PASS (Clean Data)"

echo "✅ SANDBOX VERIFICATION PASSED (CORRECTNESS ESTABLISHED)"
exit 0
