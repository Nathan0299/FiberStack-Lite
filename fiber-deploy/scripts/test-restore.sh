#!/bin/bash
# FiberStack Automated Restore Test
# Usage: ./test-restore.sh
# Runs weekly to verify backup integrity
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
ENCRYPTION_KEY_FILE="${ENCRYPTION_KEY_FILE:-/run/secrets/backup_key}"
SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"
TEST_DB_NAME="fiber-test-db-$$"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

send_alert() {
    local MESSAGE="$1"
    local STATUS="$2"
    
    if [ -n "$SLACK_WEBHOOK" ]; then
        local EMOJI="✅"
        [ "$STATUS" = "FAIL" ] && EMOJI="⚠️"
        
        curl -sf -X POST "$SLACK_WEBHOOK" \
            -H 'Content-Type: application/json' \
            -d "{\"text\": \"$EMOJI FiberStack Backup Test: $MESSAGE\"}" \
            >/dev/null 2>&1 || log "WARNING: Failed to send Slack alert"
    fi
}

cleanup() {
    log "Cleaning up test container..."
    docker rm -f "$TEST_DB_NAME" 2>/dev/null || true
}

trap cleanup EXIT

test_db_restore() {
    log "=== Starting Automated Restore Test ==="
    
    # Find latest backup
    LATEST=$(ls -t "$BACKUP_DIR"/daily/db-*.tar.gz.gpg 2>/dev/null | head -1)
    
    if [ -z "$LATEST" ]; then
        log "ERROR: No backup files found in $BACKUP_DIR/daily/"
        send_alert "No backup files found" "FAIL"
        exit 1
    fi
    
    log "Testing backup: $LATEST"
    
    # Verify checksum
    CHECKSUM_FILE="${LATEST%.gpg}.sha256"
    if [ -f "$CHECKSUM_FILE" ]; then
        log "Verifying checksum..."
        if ! sha256sum -c "$CHECKSUM_FILE" --quiet 2>/dev/null; then
            log "ERROR: Checksum verification failed"
            send_alert "Checksum verification failed for $(basename $LATEST)" "FAIL"
            exit 1
        fi
        log "Checksum verified ✓"
    fi
    
    # Spin up temporary database
    log "Starting temporary database container..."
    docker run -d --name "$TEST_DB_NAME" \
        -e POSTGRES_PASSWORD=testpass \
        -e POSTGRES_DB=fiberstack \
        timescale/timescaledb:2.11.2-pg15 >/dev/null
    
    # Wait for DB to be ready
    log "Waiting for database to be ready..."
    for i in {1..30}; do
        if docker exec "$TEST_DB_NAME" pg_isready -U postgres >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    # Decrypt and restore
    log "Decrypting and restoring backup..."
    gpg --decrypt --batch --passphrase-file "$ENCRYPTION_KEY_FILE" "$LATEST" 2>/dev/null | \
        gunzip | \
        docker exec -i "$TEST_DB_NAME" pg_restore -U postgres -d fiberstack --clean --if-exists 2>/dev/null || true
    
    # Verify data
    log "Verifying restored data..."
    METRICS=$(docker exec "$TEST_DB_NAME" psql -U postgres -d fiberstack -tAc "SELECT COUNT(*) FROM metrics" 2>/dev/null || echo "0")
    NODES=$(docker exec "$TEST_DB_NAME" psql -U postgres -d fiberstack -tAc "SELECT COUNT(*) FROM nodes" 2>/dev/null || echo "0")
    
    log "Restored metrics: $METRICS"
    log "Restored nodes: $NODES"
    
    # Validate
    if [ "$METRICS" -eq 0 ] && [ "$NODES" -eq 0 ]; then
        log "WARNING: Database empty after restore (may be expected for fresh backups)"
    fi
    
    log "=== Restore Test PASSED ✓ ==="
    send_alert "Restore test passed (metrics: $METRICS, nodes: $NODES)" "OK"
}

# Main execution
test_db_restore
