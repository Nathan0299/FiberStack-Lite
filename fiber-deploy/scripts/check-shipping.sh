#!/bin/bash
# FiberStack Filebeat Shipping Health Check
# Usage: ./check-shipping.sh
set -euo pipefail

FILEBEAT_HOST="${FILEBEAT_HOST:-localhost}"
FILEBEAT_PORT="${FILEBEAT_PORT:-5066}"
SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"
MIN_EVENTS="${MIN_EVENTS:-1}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

alert() {
    local MSG="$1"
    log "ALERT: $MSG"
    [ -n "$SLACK_WEBHOOK" ] && \
    curl -sf -X POST "$SLACK_WEBHOOK" \
        -H 'Content-Type: application/json' \
        -d "{\"text\":\"⚠️ Filebeat: $MSG\"}" >/dev/null 2>&1 || true
}

# Check Filebeat health endpoint
STATS=$(curl -sf "http://${FILEBEAT_HOST}:${FILEBEAT_PORT}/stats" 2>/dev/null) || {
    alert "Filebeat not responding on port $FILEBEAT_PORT"
    exit 1
}

# Parse metrics
ACKED=$(echo "$STATS" | jq -r '.libbeat.output.events.acked // 0')
FAILED=$(echo "$STATS" | jq -r '.libbeat.output.events.failed // 0')
DROPPED=$(echo "$STATS" | jq -r '.libbeat.output.events.dropped // 0')

log "Filebeat stats: acked=$ACKED, failed=$FAILED, dropped=$DROPPED"

# Alert on shipping failures
if [ "$FAILED" -gt 0 ]; then
    alert "Shipping failures detected: $FAILED events failed"
fi

if [ "$DROPPED" -gt 0 ]; then
    alert "Events dropped: $DROPPED events lost"
fi

# Check if any events are flowing
if [ "$ACKED" -lt "$MIN_EVENTS" ]; then
    log "WARNING: Low event throughput (acked=$ACKED)"
fi

log "Shipping health check complete"
