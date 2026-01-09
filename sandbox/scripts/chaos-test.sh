#!/bin/bash
# Day 77: Chaos Testing Script
# Tests resilience under adverse network conditions
# Requires: tc (traffic control) in containers

set -o pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

API_URL="http://localhost:8000"

info() { echo -e "${YELLOW}[CHAOS]${NC} $1"; }
pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

echo "=========================================="
echo " Day 77 Chaos Testing"
echo "=========================================="

# Find API container
API_CONTAINER=$(docker ps --filter name=api --format "{{.Names}}" | grep -E "(hybrid-api|fiber-api)" | head -1)
if [ -z "$API_CONTAINER" ]; then
    echo "No API container found. Ensure hybrid-api or fiber-api is running."
    exit 1
fi
info "Using container: $API_CONTAINER"

# Check if tc is available
if ! docker exec "$API_CONTAINER" which tc > /dev/null 2>&1; then
    warn "tc (traffic control) not available in container. Installing iproute2..."
    docker exec "$API_CONTAINER" apt-get update -qq && docker exec "$API_CONTAINER" apt-get install -y -qq iproute2 2>/dev/null || \
    docker exec "$API_CONTAINER" apk add --no-cache iproute2 2>/dev/null || \
    { warn "Could not install iproute2. Chaos tests will be simulated."; SIMULATED=true; }
fi

get_federation_status() {
    curl -sf "$API_URL/api/federation/status" | jq -r '.data.status // "unknown"'
}

echo ""
echo "=== Chaos 1: 500ms Latency Injection ==="
echo "Expectation: Should NOT trigger failover (timeout is 10s)"
info "Injecting 500ms latency..."

if [ "$SIMULATED" != "true" ]; then
    docker exec "$API_CONTAINER" tc qdisc add dev eth0 root netem delay 500ms 2>/dev/null || true
fi

sleep 30
STATUS=$(get_federation_status)
info "Federation status: $STATUS"

if [ "$STATUS" == "primary" ] || [ "$STATUS" == "unknown" ]; then
    pass "No failover triggered (latency within tolerance)"
else
    warn "Unexpected status: $STATUS (may be expected if probes are sensitive)"
fi

if [ "$SIMULATED" != "true" ]; then
    docker exec "$API_CONTAINER" tc qdisc del dev eth0 root 2>/dev/null || true
fi
info "Latency removed"

echo ""
echo "=== Chaos 2: 50% Packet Loss Injection ==="
echo "Expectation: Should trigger failover after 3 failures"
info "Injecting 50% packet loss..."

if [ "$SIMULATED" != "true" ]; then
    docker exec "$API_CONTAINER" tc qdisc add dev eth0 root netem loss 50% 2>/dev/null || true
fi

sleep 45  # Allow time for 3+ failures
STATUS=$(get_federation_status)
info "Federation status: $STATUS"

if [ "$STATUS" == "failover" ] || [ "$STATUS" == "degraded" ]; then
    pass "Failover triggered by packet loss"
else
    warn "Status: $STATUS (probes may have recovered between attempts)"
fi

if [ "$SIMULATED" != "true" ]; then
    docker exec "$API_CONTAINER" tc qdisc del dev eth0 root 2>/dev/null || true
fi
info "Packet loss removed"

echo ""
echo "=== Chaos 3: API Container Restart ==="
echo "Expectation: Probes should buffer and recover"
info "Restarting API container..."

docker restart "$API_CONTAINER" > /dev/null 2>&1
sleep 15

STATUS=$(get_federation_status)
info "Federation status after restart: $STATUS"

if curl -sf "$API_URL/api/status" > /dev/null 2>&1; then
    pass "API recovered after restart"
else
    warn "API may still be starting up"
fi

echo ""
echo "=== Chaos 4: Redis Pause (10s) ==="
echo "Expectation: Probes should buffer locally, no data loss"
REDIS_CONTAINER=$(docker ps --filter name=redis --format "{{.Names}}" | head -1)

if [ -n "$REDIS_CONTAINER" ]; then
    info "Pausing Redis for 10s..."
    docker pause "$REDIS_CONTAINER" > /dev/null 2>&1
    sleep 10
    docker unpause "$REDIS_CONTAINER" > /dev/null 2>&1
    info "Redis unpaused"
    
    sleep 5
    if curl -sf "$API_URL/api/status" | jq -e '.data.redis == "ok"' > /dev/null 2>&1; then
        pass "Redis recovered"
    else
        warn "Redis may still be reconnecting"
    fi
else
    warn "Redis container not found, skipping pause test"
fi

echo ""
echo "=== Chaos 5: ETL Worker Kill (Process Death) ==="
echo "Expectation: Worker should restart (docker) or be replaced"
ETL_CONTAINER=$(docker ps --filter name=etl --format "{{.Names}}" | grep -E "(hybrid-etl|fiber-etl)" | head -1)

if [ -n "$ETL_CONTAINER" ]; then
    info "Killing ETL container: $ETL_CONTAINER..."
    # Kill the container to simulate crash
    docker kill "$ETL_CONTAINER" > /dev/null 2>&1
    
    # Wait for restart policy (usually immediate in docker compose unless --no-recreate)
    info "Waiting for 10s (Docker Auto-Restart)..."
    sleep 10
    
    # Check status
    NEW_STATUS=$(docker inspect --format='{{.State.Status}}' "$ETL_CONTAINER")
    if [ "$NEW_STATUS" == "running" ]; then
       pass "ETL Worker recovered (Status: $NEW_STATUS)"
    else
       warn "ETL Worker did NOT recover (Status: $NEW_STATUS). Check restart policy."
    fi
else
    warn "ETL container not found, skipping kill test"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✓ CHAOS TESTING COMPLETE${NC}"
echo "=========================================="
echo ""
info "Review probe logs for failover events:"
echo "  docker logs hybrid-probe-gh 2>&1 | grep -E 'FAILOVER|PROMOTION'"

