#!/bin/bash
set -e

echo "=== FiberStack Diagnostics ==="

# Detect running API container
if docker ps --format '{{.Names}}' | grep -q "^fs-api-sandbox$"; then
    CONTAINER="fs-api-sandbox"
elif docker ps --format '{{.Names}}' | grep -q "^fiber-api$"; then
    CONTAINER="fiber-api"
else
    echo "❌ Error: No running API container found (checked 'fs-api-sandbox' and 'fiber-api')"
    exit 1
fi

echo "Executing internal checks inside container: $CONTAINER"

# Pipe the python script into the container to execute it
cat sandbox/dev/diagnostics/check_network.py | docker exec -i $CONTAINER python -

echo "=== All Checks Passed ==="
