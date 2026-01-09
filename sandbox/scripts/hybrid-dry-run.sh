#!/bin/bash
set -e

# Configuration
HYBRID_COMPOSE="fiber-deploy/docker-compose.hybrid.yml"
ARTIFACTS_DIR="artifacts"
mkdir -p "$ARTIFACTS_DIR"

log() {
    echo "[INFO] $(date +'%Y-%m-%d %H:%M:%S') - $1"
}

audit() {
    echo "[AUDIT] $(date +'%Y-%m-%d %H:%M:%S') | User: $(whoami) | Action: $1"
}

# 1. Cleanup
log "Step 1: Cleanup Environment"
docker compose -f "$HYBRID_COMPOSE" down --volumes --remove-orphans || true
rm -f fiber-db/schemas/hybrid_init.sql

# 2. Setup Resources (Create DBs)
log "Step 2: Initialize Hybrid Databases"
# We start just the DB first to create databases
docker compose -f "$HYBRID_COMPOSE" up -d fiber-db
log "Waiting for DB to be healthy..."
# Portable wait loop (max 60s)
for i in {1..30}; do
    if docker inspect --format "{{.State.Health.Status}}" fiber-db | grep -q "healthy"; then
        log "DB is healthy."
        break
    fi
    if [ "$i" -eq 30 ]; then
        log "ERROR: DB failed to become healthy in 60s."
        exit 1
    fi
    sleep 2
done

# Create databases explicitly
docker exec fiber-db psql -U postgres -c "CREATE DATABASE fiber_cloud;" || true
docker exec fiber-db psql -U postgres -c "CREATE DATABASE fiber_local;" || true

# Apply Base Schema (schema.sql)
log "Applying Base Schema to fiber_cloud..."
docker exec fiber-db psql -U postgres -d fiber_cloud -f /docker-entrypoint-initdb.d/schema.sql

log "Applying Base Schema to fiber_local..."
docker exec fiber-db psql -U postgres -d fiber_local -f /docker-entrypoint-initdb.d/schema.sql

# 3. Migrations
log "Step 3: Run Schema Migrations (Alembic)"
# We need to run migrations against both DBs.
# We can use a temporary container or exec into API if available.
# Let's start the rest of the stack first so API containers are up, which have alembic installed.
docker compose -f "$HYBRID_COMPOSE" up -d --wait

# Run against Cloud DB
log "Migrating fiber_cloud..."
docker exec -e DB_NAME=fiber_cloud fiber-api-cloud alembic -c fiber-api/alembic.ini upgrade head

# Run against Local DB
log "Migrating fiber_local..."
docker exec -e DB_NAME=fiber_local fiber-api-local alembic -c fiber-api/alembic.ini upgrade head

# 4. Resource Baseline
log "Step 4: Capture Resource Baseline"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" > "$ARTIFACTS_DIR/hybrid_resource_usage.txt"
cat "$ARTIFACTS_DIR/hybrid_resource_usage.txt"

# 5. Verification
log "Step 5: Run Deep Verification"
# Install dependencies if needed (assuming user env has them or we use a container)
# We'll run python script locally. It connects to localhost ports.
python3 sandbox/scripts/verify_hybrid.py

# 6. Teardown
log "Step 6: Teardown"
docker compose -f "$HYBRID_COMPOSE" down --volumes --remove-orphans
audit "Hybrid Dry Run Complete"

log "=== HYBRID DRY RUN SUCCESS ==="
