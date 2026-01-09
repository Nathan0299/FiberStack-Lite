#!/bin/bash
# FiberStack Log Rotation Script
# Usage: ./rotate-logs.sh
set -euo pipefail

LOG_DIR="${LOG_DIR:-/var/log/fiberstack}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

alert() {
    local MSG="$1"
    log "ALERT: $MSG"
    [ -n "$SLACK_WEBHOOK" ] && \
    curl -sf -X POST "$SLACK_WEBHOOK" \
        -H 'Content-Type: application/json' \
        -d "{\"text\":\"⚠️ Log rotation: $MSG\"}" >/dev/null 2>&1 || true
}

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Compress logs older than 1 day
COMPRESSED=0
for f in $(find "$LOG_DIR" -name "*.json" -mtime +1 2>/dev/null); do
    if gzip "$f" 2>/dev/null; then
        ((COMPRESSED++))
        chmod 640 "${f}.gz"
    else
        alert "Failed to compress $f"
    fi
done

# Delete archives older than retention period
DELETED=$(find "$LOG_DIR" -name "*.gz" -mtime +$RETENTION_DAYS -delete -print 2>/dev/null | wc -l)

# Verify disk usage
USAGE=$(df "$LOG_DIR" 2>/dev/null | tail -1 | awk '{print $5}' | tr -d '%' || echo "0")
if [ "$USAGE" -gt 85 ]; then
    alert "Disk usage at $USAGE% - logs may not be rotating properly"
fi

# Set secure permissions on remaining files
find "$LOG_DIR" -type f \( -name "*.json" -o -name "*.gz" \) -exec chmod 640 {} \; 2>/dev/null || true

log "Rotation complete: Compressed=$COMPRESSED, Deleted=$DELETED, Disk=$USAGE%"
