#!/bin/bash
# FiberStack TimescaleDB Restore Script
# Usage: ./restore-db.sh <backup_file>
set -euo pipefail

BACKUP_FILE="${1:-}"
PGHOST="${PGHOST:-timescaledb}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-fiberstack}"
ENCRYPTION_KEY_FILE="${ENCRYPTION_KEY_FILE:-/run/secrets/backup_key}"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file.tar.gz.gpg>"
    echo "Available backups:"
    ls -la /backups/daily/*.gpg 2>/dev/null || echo "  No daily backups found"
    exit 1
fi

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

verify_checksum() {
    local CHECKSUM_FILE="${BACKUP_FILE%.gpg}.sha256"
    
    if [ -f "$CHECKSUM_FILE" ]; then
        log "Verifying checksum..."
        if sha256sum -c "$CHECKSUM_FILE" --quiet; then
            log "Checksum verified ✓"
        else
            log "ERROR: Checksum mismatch! Backup may be corrupted."
            exit 1
        fi
    else
        log "WARNING: No checksum file found, skipping verification"
    fi
}

restore_full() {
    log "Starting database restore from: $BACKUP_FILE"
    
    # Verify checksum first
    verify_checksum
    
    # Decrypt and restore
    log "Decrypting and restoring..."
    gpg --decrypt --batch --passphrase-file "$ENCRYPTION_KEY_FILE" "$BACKUP_FILE" | \
        gunzip | \
        pg_restore -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" --clean --if-exists
    
    log "Restore complete"
}

restore_logical() {
    log "Starting logical restore from: $BACKUP_FILE"
    
    gpg --decrypt --batch --passphrase-file "$ENCRYPTION_KEY_FILE" "$BACKUP_FILE" | \
        gunzip | \
        pg_restore -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" --clean --if-exists
    
    log "Logical restore complete"
}

verify_restore() {
    log "Verifying restore..."
    
    local METRICS=$(psql -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" -tAc "SELECT COUNT(*) FROM metrics" 2>/dev/null || echo "0")
    local NODES=$(psql -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" -tAc "SELECT COUNT(*) FROM nodes" 2>/dev/null || echo "0")
    
    log "Metrics: $METRICS rows"
    log "Nodes: $NODES rows"
    
    if [ "$METRICS" -gt 0 ] || [ "$NODES" -gt 0 ]; then
        log "Restore verification: SUCCESS ✓"
    else
        log "WARNING: Database appears empty after restore"
    fi
}

# Main execution
if [[ "$BACKUP_FILE" == *.sql.gz.gpg ]]; then
    restore_logical
else
    restore_full
fi

verify_restore

log "Restore process finished"
