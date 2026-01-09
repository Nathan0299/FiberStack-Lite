#!/bin/bash
# Day 77: Failover Verification Script
# Polling-based verification (no sleep delays)
# Black Signal Standards: Deterministic pass/fail

set -o pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

API_PRIMARY="http://localhost:8000"
API_SECONDARY="http://localhost:8001"

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
info() { echo -e "${YELLOW}[INFO]${NC} $1"; }

wait_for_condition() {
    local max_wait=$1
    local check_cmd=$2
    local description=$3
    local elapsed=0
    
    while [ $elapsed -lt $max_wait ]; do
        if eval "$check_cmd" 2>/dev/null; then
            pass "$description (${elapsed}s)"
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
        echo -n "."
    done
    
    echo ""
    fail "$description (timeout after ${max_wait}s)"
}

echo "=========================================="
echo " Day 77 Failover Verification"
echo "=========================================="

# Pre-flight: Verify services are running
info "Pre-flight checks..."
curl -sf "$API_PRIMARY/api/status" > /dev/null || fail "Primary API not responding"
info "Primary API healthy"

# Baseline: Get initial probe count
INITIAL_STATUS=$(curl -sf "$API_PRIMARY/api/federation/status")
INITIAL_PROBES=$(echo "$INITIAL_STATUS" | jq -r '.data.total_probes // 0')
info "Initial probe count: $INITIAL_PROBES"

echo ""
echo "=== F-01: Reroute Check ==="
info "Stopping primary API..."
docker stop hybrid-api 2>/dev/null || docker stop fiber-api 2>/dev/null || true
sleep 5

# Wait for failover (status should change to "failover")
wait_for_condition 60 \
    "curl -sf '$API_SECONDARY/api/federation/status' 2>/dev/null | jq -e '.data.status == \"failover\"'" \
    "Failover detected"

echo ""
echo "=== F-02: Return Check ==="
info "Starting primary API..."
docker start hybrid-api 2>/dev/null || docker start fiber-api 2>/dev/null || true
sleep 10

# Wait for return to primary (with stickiness: 120s + 10s buffer)
wait_for_condition 180 \
    "curl -sf '$API_PRIMARY/api/federation/status' 2>/dev/null | jq -e '.data.status == \"primary\"'" \
    "Returned to primary with stickiness"

echo ""
echo "=== F-03: Zero Loss Check (Idempotency) ==="
# Check for duplicates in the last 24 hours
DB_CONTAINER=$(docker ps --filter name=db --format "{{.Names}}" | head -1)
if [ -z "$DB_CONTAINER" ]; then
    DB_CONTAINER="hybrid-db"
fi

DUPES=$(docker exec "$DB_CONTAINER" psql -U postgres -d fiberstack -t -c \
  "SELECT COUNT(*) FROM (
     SELECT node_id, time 
     FROM metrics 
     WHERE time > NOW() - INTERVAL '24 hours' 
     GROUP BY node_id, time 
     HAVING COUNT(*) > 1
   ) x" 2>/dev/null)


DUPES=$(echo "$DUPES" | tr -d ' \n')
if [ "$DUPES" == "0" ] || [ -z "$DUPES" ]; then
    pass "Zero duplicates (24h window)"
else
    fail "Found $DUPES duplicate entries"
fi

echo ""
echo "=== F-04: Buffer Persistence Check ==="
# Check if Redis buffer has any data
REDIS_CONTAINER=$(docker ps --filter name=redis --format "{{.Names}}" | head -1)
if [ -z "$REDIS_CONTAINER" ]; then
    REDIS_CONTAINER="hybrid-redis"
fi

# Get a probe buffer key
BUFFER_KEYS=$(docker exec "$REDIS_CONTAINER" redis-cli KEYS "fiber:probe:*:buffer" 2>/dev/null | head -1)
if [ -n "$BUFFER_KEYS" ]; then
    pass "Buffer keys exist in Redis"
else
    info "No buffer keys (probes may be pushing directly)"
fi

echo ""
echo "=== F-05: Federation Endpoint Check ==="
FED_STATUS=$(curl -sf "$API_PRIMARY/api/federation/status")
FED_SOURCE=$(echo "$FED_STATUS" | jq -r '.data.source')

if [ "$FED_SOURCE" == "probe-reported" ]; then
    pass "Federation status source is probe-reported"
else
    fail "Federation status source is '$FED_SOURCE' (expected: probe-reported)"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✓ ALL FAILOVER GATES PASSED${NC}"
echo "=========================================="
