#!/bin/bash
# FiberStack TimescaleDB Backup Script
# Usage: ./backup-db.sh [full|hourly]
set -euo pipefail

BACKUP_TYPE="${1:-full}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
DATE=$(date +%Y%m%d-%H%M%S)
PGHOST="${PGHOST:-timescaledb}"
PGUSER="${PGUSER:-postgres}"
ENCRYPTION_KEY_FILE="${ENCRYPTION_KEY_FILE:-/run/secrets/backup_key}"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"/{daily,hourly,weekly}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

backup_full() {
    local BACKUP_FILE="$BACKUP_DIR/daily/db-$DATE.tar.gz.gpg"
    local CHECKSUM_FILE="$BACKUP_DIR/daily/db-$DATE.sha256"
    
    log "Starting full backup..."
    
    # Create encrypted backup
    pg_basebackup -h "$PGHOST" -U "$PGUSER" -D - -Ft -z -P 2>/dev/null | \
        gpg --symmetric --cipher-algo AES256 --batch --yes \
            --passphrase-file "$ENCRYPTION_KEY_FILE" \
            -o "$BACKUP_FILE"
    
    # Generate checksum
    sha256sum "$BACKUP_FILE" > "$CHECKSUM_FILE"
    
    # Set secure permissions
    chmod 600 "$BACKUP_FILE" "$CHECKSUM_FILE"
    
    log "Full backup complete: $BACKUP_FILE"
    log "Checksum: $(cat $CHECKSUM_FILE)"
}

backup_hourly() {
    local BACKUP_FILE="$BACKUP_DIR/hourly/db-$DATE.sql.gz.gpg"
    
    log "Starting hourly logical backup..."
    
    # Logical dump with compression and encryption
    pg_dump -h "$PGHOST" -U "$PGUSER" -d "${PGDATABASE:-fiberstack}" -Fc | \
        gzip | \
        gpg --symmetric --cipher-algo AES256 --batch --yes \
            --passphrase-file "$ENCRYPTION_KEY_FILE" \
            -o "$BACKUP_FILE"
    
    chmod 600 "$BACKUP_FILE"
    
    log "Hourly backup complete: $BACKUP_FILE"
}

cleanup_old() {
    log "Cleaning up old backups..."
    
    # Keep only last 24 hourly backups
    find "$BACKUP_DIR/hourly" -name "db-*.gpg" -mmin +1440 -delete 2>/dev/null || true
    
    # Keep only last 7 daily backups
    find "$BACKUP_DIR/daily" -name "db-*.gpg" -mtime +7 -delete 2>/dev/null || true
    find "$BACKUP_DIR/daily" -name "db-*.sha256" -mtime +7 -delete 2>/dev/null || true
    
    log "Cleanup complete"
}

# Main execution
case "$BACKUP_TYPE" in
    full)
        backup_full
        cleanup_old
        ;;
    hourly)
        backup_hourly
        ;;
    *)
        echo "Usage: $0 [full|hourly]"
        exit 1
        ;;
esac

log "Backup process finished successfully"
