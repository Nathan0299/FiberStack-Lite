#!/bin/bash
set -e

# Load Utils
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/utils.sh"

ENV="$1"
CLEAN_FLAG="$2"

if [ -z "$ENV" ]; then
    fail "Usage: $0 [env] [--clean]"
fi

log_info "Tearing down $ENV..."

# 1. Audit
log_audit "Teardown Initiated for $ENV (Clean: ${CLEAN_FLAG:-false})"

# 2. Command Prep
COMPOSE_FILE="docker-compose.yml"
if [ "$ENV" == "dev" ]; then COMPOSE_FILE="docker-compose.dev.yml"; fi
COMPOSE_FLAGS="-f fiber-deploy/${COMPOSE_FILE}"

CMD="docker compose $COMPOSE_FLAGS down"

# 3. Clean Handling
if [ "$CLEAN_FLAG" == "--clean" ]; then
    confirm_destructive "$ENV" "Remove ALL Volumes and Orphans? Data will be lost."
    CMD="$CMD --volumes --remove-orphans"
fi

# 4. Execute
eval "$CMD"

log_info "Teardown Complete."
