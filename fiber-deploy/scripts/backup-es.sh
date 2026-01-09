#!/bin/bash
# FiberStack Elasticsearch Backup Script
# Usage: ./backup-es.sh [snapshot|cleanup]
set -euo pipefail

ACTION="${1:-snapshot}"
ES_HOST="${ES_HOST:-elasticsearch:9200}"
REPO_NAME="fiber_backup"
DATE=$(date +%Y%m%d-%H%M%S)
SNAPSHOT_NAME="snapshot-$DATE"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

ensure_repository() {
    log "Ensuring snapshot repository exists..."
    
    # Check if repository exists
    if ! curl -sf "$ES_HOST/_snapshot/$REPO_NAME" >/dev/null 2>&1; then
        log "Creating snapshot repository..."
        curl -sf -X PUT "$ES_HOST/_snapshot/$REPO_NAME" \
            -H 'Content-Type: application/json' \
            -d '{
                "type": "fs",
                "settings": {
                    "location": "/backups/elasticsearch",
                    "compress": true
                }
            }' || {
                log "ERROR: Failed to create repository"
                exit 1
            }
    fi
    
    log "Repository ready"
}

create_snapshot() {
    log "Creating snapshot: $SNAPSHOT_NAME"
    
    # Create snapshot and wait for completion
    RESPONSE=$(curl -sf -X PUT "$ES_HOST/_snapshot/$REPO_NAME/$SNAPSHOT_NAME?wait_for_completion=true" \
        -H 'Content-Type: application/json' \
        -d '{
            "indices": "fiber-logs-*,fiber-metrics-*",
            "include_global_state": false,
            "metadata": {
                "created_by": "backup-es.sh",
                "created_at": "'"$(date -Iseconds)"'"
            }
        }' 2>/dev/null)
    
    # Verify status
    STATUS=$(echo "$RESPONSE" | jq -r '.snapshot.state // "UNKNOWN"')
    
    if [ "$STATUS" = "SUCCESS" ]; then
        log "Snapshot created successfully: $SNAPSHOT_NAME"
        SHARDS=$(echo "$RESPONSE" | jq -r '.snapshot.shards.successful // 0')
        log "Shards backed up: $SHARDS"
    else
        log "ERROR: Snapshot failed with status: $STATUS"
        log "Response: $RESPONSE"
        exit 1
    fi
}

cleanup_old_snapshots() {
    log "Cleaning up old snapshots (>7 days)..."
    
    CUTOFF=$(date -d '7 days ago' +%s 2>/dev/null || date -v-7d +%s)
    CUTOFF_MS=$((CUTOFF * 1000))
    
    # Get all snapshots and delete old ones
    curl -sf "$ES_HOST/_snapshot/$REPO_NAME/_all" 2>/dev/null | \
        jq -r ".snapshots[] | select(.start_time_in_millis < $CUTOFF_MS) | .snapshot" | \
        while read -r SNAPSHOT; do
            log "Deleting old snapshot: $SNAPSHOT"
            curl -sf -X DELETE "$ES_HOST/_snapshot/$REPO_NAME/$SNAPSHOT" >/dev/null
        done
    
    log "Cleanup complete"
}

list_snapshots() {
    log "Available snapshots:"
    curl -sf "$ES_HOST/_snapshot/$REPO_NAME/_all" 2>/dev/null | \
        jq -r '.snapshots[] | "  \(.snapshot) - \(.state) - \(.start_time)"' || \
        echo "  No snapshots found or Elasticsearch unavailable"
}

# Main execution
case "$ACTION" in
    snapshot)
        ensure_repository
        create_snapshot
        ;;
    cleanup)
        cleanup_old_snapshots
        ;;
    list)
        list_snapshots
        ;;
    *)
        echo "Usage: $0 [snapshot|cleanup|list]"
        exit 1
        ;;
esac

log "Elasticsearch backup process finished"
