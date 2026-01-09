#!/bin/bash
# FiberStack Service Health Check Waiter

TIMEOUT=${1:-60}
INTERVAL=2
ELAPSED=0

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

log "Waiting for services to be healthy (timeout: ${TIMEOUT}s)..."

while [ $ELAPSED -lt $TIMEOUT ]; do
    API_HEALTH=$(curl -sf http://localhost:8000/api/status 2>/dev/null | jq -r '.status' 2>/dev/null || echo "unhealthy")
    DB_READY=$(docker exec fiber-db pg_isready -U postgres 2>/dev/null && echo "ready" || echo "not_ready")
    
    if [ "$API_HEALTH" == "ok" ] && [ "$DB_READY" == "ready" ]; then
        log "All services are healthy! ✓"
        exit 0
    fi
    
    log "Waiting... (API: $API_HEALTH, DB: $DB_READY)"
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

log "ERROR: Services failed to become healthy within ${TIMEOUT}s"
exit 1
