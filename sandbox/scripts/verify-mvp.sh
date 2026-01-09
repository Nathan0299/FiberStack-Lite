#!/bin/bash
# verify-mvp.sh
# The "Gauntlet" - Full Stack Verification for MVP Freeze

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[MVP-VERIFY]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# 1. Infrastructure Check
log "Checking Infrastructure..."
# Updated for hybrid-dry-run.yml service names
SERVICES=("hybrid-redis" "hybrid-db" "hybrid-api" "hybrid-etl")
for APP in "${SERVICES[@]}"; do
    if ! docker ps --format '{{.Names}}' | grep -q "${APP}"; then
        error "Service ${APP} is NOT running."
    fi
done
log "All Infrastructure Services are UP."

# 2. API Health Check
log "Checking API Health..."
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
if [ "$API_STATUS" != "200" ]; then
    error "API Health Check Failed (HTTP $API_STATUS)"
fi
log "API is Healthy."

# 3. Telemetry Flow Verification
TEST_NODE_ID="mvp-test-$(date +%s)"
log "Using Node ID: $TEST_NODE_ID"

log "Attempting Admin Login..."
LOGIN_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin"}')

ADMIN_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.data.token')

if [ -z "$ADMIN_TOKEN" ] || [ "$ADMIN_TOKEN" == "null" ]; then
    echo "Login Response: $LOGIN_RESPONSE"
    error "Failed to obtain Admin Token"
fi
log "Authenticated as Admin."

# Register Node (via API)
log "Registering Test Node..."
# Added status field
REGISTER_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/nodes" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"node_id\": \"$TEST_NODE_ID\", \"country\": \"GH\", \"region\": \"Accra-Test\", \"lat\": 5.6, \"lng\": -0.1, \"status\": \"registered\"}")

if echo "$REGISTER_RESPONSE" | grep -q "error" || echo "$REGISTER_RESPONSE" | grep -q "missing"; then
   echo "Register Response: $REGISTER_RESPONSE"
   error "Failed to register node"
fi

# Simulate Probe Ingest
log "Injecting Telemetry for $TEST_NODE_ID..."
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
PAYLOAD="{\"node_id\": \"$TEST_NODE_ID\", \"timestamp\": \"$TIMESTAMP\", \"latency_ms\": 42.5, \"uptime_pct\": 99.9, \"packet_loss\": 0.0, \"region\": \"Accra-Test\", \"country\": \"GH\", \"metadata\": {\"env\": \"mvp-test\"}}"

docker exec hybrid-redis redis-cli LPUSH fiber:etl:queue "$PAYLOAD" > /dev/null

log "Waiting for ETL processing (5s)..."
sleep 5

# 4. Data Verification (DB)
log "Verifying Data Persistence..."
COUNT=$(docker exec hybrid-db psql -U postgres -d fiberstack -t -c "SELECT COUNT(*) FROM metrics WHERE node_id = '$TEST_NODE_ID';")
if [ $(echo "$COUNT" | xargs) -eq 0 ]; then
    error "Metric ID $TEST_NODE_ID NOT found in database!"
fi
log "Telemetry persisted successfully."

# 5. Dashboard/Aggregates Verification
NODE_CHECK=$(docker exec hybrid-db psql -U postgres -d fiberstack -t -c "SELECT COUNT(*) FROM nodes WHERE node_id = '$TEST_NODE_ID';")
if [ $(echo "$NODE_CHECK" | xargs) -eq 0 ]; then
    error "Node metadata NOT found in 'nodes' table."
fi
log "Node metadata verified."

# 6. Audit Trail Verification
log "Verifying Audit Trail..."
# Split into two steps for debugging
FOUND_LINE=$(docker exec hybrid-api grep "$TEST_NODE_ID" /tmp/fiber-audit.jsonl || true)

if [ -z "$FOUND_LINE" ]; then
    echo "DEBUG: Content of /tmp/fiber-audit.jsonl:"
    docker exec hybrid-api cat /tmp/fiber-audit.jsonl
    error "Audit Log entry for $TEST_NODE_ID NOT found in file."
fi

if echo "$FOUND_LINE" | grep -q "CREATE_NODE"; then
    log "Audit Trail verified: Found CREATE_NODE."
else
    echo "DEBUG: Found Line: $FOUND_LINE"
    error "Audit Log entry found but action 'CREATE_NODE' mismatch."
fi

log "MVP GAUNTLET PASSED! 🚀 System is ready for freeze."
exit 0
