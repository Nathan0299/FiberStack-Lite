#!/bin/bash
# verify-rollback.sh
# Validates System Reversibility (Gap #2)

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[ROLLBACK-TEST]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

COMPOSE_FILE="sandbox/simulation/hybrid-dry-run.yml"

# 1. Image Pinning Check
log "Checking for Image Pinning..."
if grep -q ":latest" "$COMPOSE_FILE"; then
    error "Violation: Found ':latest' tag in $COMPOSE_FILE. Must use specific versions for MVP."
fi
log "Image Pinning Verified (No :latest tags)."

# 2. Config Reversion Drill (The "Bad Deploy")
log "Starting Config Reversion Drill..."

# Snapshot current config (Not needed for Override method, but keeping logic clean)
# cp "$COMPOSE_FILE" "${COMPOSE_FILE}.bak"

# Apply Bad Config (Break DB Crash)
log "Applying BROKEN config (Simulating bad deploy via override)..."
# We simulate a "Bad Commit" by merging the broken config (in older compose this is what happens if you changed the file)
# But here we just use -f override.

# Restart Stack (Deploy Broken)
log "Deploying Broken Stack..."
# Note: We must include the base file AND the broken file
docker compose -f "$COMPOSE_FILE" -f sandbox/simulation/broken-override.yml up -d --remove-orphans || true

# Health Check (Expect FAIL)
log "Verifying Failure..."
sleep 15
DB_STATUS=$(docker inspect --format='{{.State.Health.Status}}' hybrid-db 2>/dev/null || echo "dead")
DB_STATE=$(docker inspect --format='{{.State.Status}}' hybrid-db 2>/dev/null || echo "dead")

if [ "$DB_STATUS" == "healthy" ]; then
    error "Simulation Failed: DB stayed healthy despite /bin/false entrypoint!"
fi
log "System successfully FAILED (Status: $DB_STATE / Health: $DB_STATUS)."

# Rollback
log "Executing Rollback (Reverting to clean compose file)..."
# Just redeploy without the override

# Deploy Good Stack
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# Health Check (Expect PASS)
log "Verifying Recovery..."
DB_RECOVERED=""

log "System successfully FAILED (as expected)."

# Rollback
log "Executing Rollback..."
mv "${COMPOSE_FILE}.bak" "$COMPOSE_FILE"
rm -f "${COMPOSE_FILE}.tmp"

# Deploy Good Stack
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# Health Check (Expect PASS)
log "Verifying Recovery..."
sleep 10
# Wait loop 
for i in {1..12}; do
    if [ "$DB_RECOVERED" == "healthy" ]; then
        break
    fi
    sleep 5
    DB_RECOVERED=$(docker inspect --format='{{.State.Health.Status}}' hybrid-db 2>/dev/null || echo "dead")
done

if [ "$DB_RECOVERED" != "healthy" ]; then
     error "Rollback Failed: System did not recover to healthy state."
fi

log "Rollback Verified: System recovered automatically after config revert."
exit 0
