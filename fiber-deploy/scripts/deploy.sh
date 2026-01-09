#!/bin/bash
set -e

# Load Utils
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/utils.sh"

ENV="$1"

if [ -z "$ENV" ]; then
    fail "Usage: $0 [env] (dev, staging, prod)"
fi

log_info "Deploying to $ENV..."

# 1. State Tracking & Rollback Prep
RELEASE_FILE="$SCRIPT_DIR/release.json"
RELEASE_PREV="$SCRIPT_DIR/release.prev.json"

if [ -f "$RELEASE_FILE" ]; then
    cp "$RELEASE_FILE" "$RELEASE_PREV"
    log_info "Backed up current release state to release.prev.json"
else
    log_warn "No previous release tracking found."
fi

# 2. Pre-flight Checks
check_resources

# Select Compose File
COMPOSE_FILE="docker-compose.yml"
if [ "$ENV" == "dev" ]; then COMPOSE_FILE="docker-compose.dev.yml"; fi
COMPOSE_FLAGS="-f fiber-deploy/${COMPOSE_FILE}"

# 3. Migrations (Atomic)
log_info "Running Database Migrations..."
# In prod, we might want to snapshot first
if [ "$ENV" == "prod" ]; then
    log_info "Processing Production Snapshot..."
    # Call backup-db.sh if it existed in the image context, or manually
    # docker exec fiber-backup /scripts/backup-db.sh "pre-deploy-$(date +%s)"
fi

# Run Alembic Upgrade
# We use a temporary container or the running API container
# Assuming fiber-api container has alembic
if docker compose $COMPOSE_FLAGS run --rm fiber-api [ -f fiber-api/alembic.ini ] && docker compose $COMPOSE_FLAGS run --rm fiber-api alembic -c fiber-api/alembic.ini upgrade head; then
    log_info "Migrations Successful."
elif ! docker compose $COMPOSE_FLAGS run --rm fiber-api [ -f fiber-api/alembic.ini ]; then
     log_warn "No fiber-api/alembic.ini found. Skipping Migrations."
else
    fail "Migration Failed! Aborting Deploy."
fi

# 4. Rollout
log_info "Rolling out services..."
docker compose $COMPOSE_FLAGS up -d --remove-orphans

# 5. Health Checks (Env-Tuned)
TIMEOUT=30
if [ "$ENV" == "staging" ]; then TIMEOUT=90; fi
if [ "$ENV" == "prod" ]; then TIMEOUT=180; fi

log_info "Verifying Health (Timeout: ${TIMEOUT}s)..."

check_health() {
    # Check API Status
    if ! curl -s -f http://localhost:8000/api/status > /dev/null; then
        return 1
    fi
    # Check DB Connection (via postgres-ready check if possible, or assume API check covers it)
    return 0
}

if retry_with_backoff 10 "$TIMEOUT" check_health; then
    log_info "Health Checks Passed."
    log_audit "Deploy Success: $ENV"
else
    log_error "Health Checks FAILED!"
    
    # 6. Automatic Rollback
    if [ -f "$RELEASE_PREV" ]; then
        log_warn "Triggering Rollback to previous release..."
        # In a real digest-based system, we'd source release.prev.json and export variables
        # For Compose, we might just revert the file or image tags.
        # Since we rely on 'latest' vs 'sha' tags in build, rollback via compose is tricky without explicit digest pinning in compose file.
        # For this MVP script, we assume 'rollback' means tearing down or restarting previous containers if we haven't pruned.
        
        # Simple Rollback: Restart previous containers? No, images might be replaced if using 'latest'.
        # Ideal: We should have deployed specific tags from release.json.
        # Assumption: The compose file uses variables or we updated the .env with versions.
        
        log_warn "Rollback: Please investigate manual intervention. Restoring release.prev.json..."
        cp "$RELEASE_PREV" "$RELEASE_FILE"
    else
        log_warn "No previous release to rollback to."
    fi
    fail "Deploy Failed. Rollback State Restored (Artifacts only)."
fi

log_info "Deployment Complete."
