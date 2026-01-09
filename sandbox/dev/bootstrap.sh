#!/bin/bash
set -e

echo "🚀 Starting FiberStack Sandbox..."
echo "================================="

cd "$(dirname "$0")"

# Clean up old containers
echo "🧹 Cleaning up old containers..."
docker compose -f docker-compose.sandbox.yml down -v 2>/dev/null || true

# Start stack with build
echo "🔨 Building and starting services..."
docker compose -f docker-compose.sandbox.yml up -d --build

# Wait for health checks
echo ""
echo "⏳ Waiting for services to be healthy..."

wait_for_healthy() {
    local container=$1
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "not_found")
        
        if [ "$status" = "healthy" ]; then
            echo "   ✅ $container is healthy"
            return 0
        elif [ "$status" = "not_found" ]; then
            echo "   ⚠️  $container not found, checking if running..."
            if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
                echo "   ✅ $container is running (no healthcheck)"
                return 0
            fi
        fi
        
        attempt=$((attempt + 1))
        echo "   ⏳ Waiting for $container... ($attempt/$max_attempts)"
        sleep 2
    done
    
    echo "   ❌ $container failed to become healthy"
    return 1
}

wait_for_healthy "fs-redis-sandbox"
wait_for_healthy "fs-timescale-sandbox"
wait_for_healthy "fs-api-sandbox"

# Check if ETL is running
echo ""
echo "🔍 Checking ETL worker..."
sleep 3
if docker ps --format '{{.Names}}' | grep -q "fs-etl-sandbox"; then
    echo "   ✅ ETL worker is running"
else
    echo "   ❌ ETL worker failed to start"
    docker logs fs-etl-sandbox --tail 20
    exit 1
fi

# Final API health check
echo ""
echo "🔍 Final API health check..."
API_STATUS=$(curl -s http://localhost:8000/api/status 2>/dev/null || echo '{"status":"error"}')
echo "   API Response: $API_STATUS"

echo ""
echo "================================="
echo "✅ FiberStack Sandbox Ready!"
echo "================================="
echo ""
echo "Endpoints:"
echo "   API:      http://localhost:8000"
echo "   API Docs: http://localhost:8000/docs"
echo "   Redis:    localhost:6380"
echo "   Postgres: localhost:5433"
echo ""
echo "To generate load:"
echo "   python load_generator.py"
echo ""
echo "To check ETL logs:"
echo "   docker logs fs-etl-sandbox -f"
echo ""
