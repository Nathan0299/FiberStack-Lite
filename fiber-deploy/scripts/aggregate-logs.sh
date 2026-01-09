#!/bin/bash
# FiberStack Concurrent-Safe Log Aggregation
# Usage: ./aggregate-logs.sh
set -euo pipefail

LOCK_FILE="/tmp/aggregate-logs.lock"
LOG_DIR="${LOG_DIR:-/var/log/fiberstack}"
OUTPUT_DIR="${LOG_DIR}/aggregated"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Prevent concurrent runs using flock
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    log "Another aggregation in progress, skipping"
    exit 0
fi

OUTPUT="$OUTPUT_DIR/combined-$(date +%Y%m%d-%H%M%S).json"
TEMP=$(mktemp)
trap "rm -f $TEMP" EXIT

log "Starting log aggregation..."

# Aggregate Docker container logs
cd /Users/macpro/FiberStack-Lite/fiber-deploy 2>/dev/null || cd .
docker-compose logs --no-color --timestamps 2>/dev/null | \
    grep -E '^\{' | \
    jq -cs 'sort_by(.timestamp // .time) | unique_by((.timestamp // .time) + (.message // ""))' > "$TEMP" 2>/dev/null || \
    echo "[]" > "$TEMP"

# Atomic move
mv "$TEMP" "$OUTPUT"
chmod 640 "$OUTPUT"

# Get stats
ENTRIES=$(jq 'length' "$OUTPUT" 2>/dev/null || echo "0")
log "Aggregation complete: $OUTPUT ($ENTRIES entries)"

# Cleanup old aggregated files (keep last 7)
ls -t "$OUTPUT_DIR"/combined-*.json 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null || true
