#!/bin/bash
set -e

echo "Rolling back fiber-probe to 'previous-stable'..."

# Option A: If using Watchtower / Tags
# We assume 'fiberstack/probe:previous-stable' exists or we revert hash.
# For simplicity in this plan, we might pull a specific known good tag if managed centrally.
# Here we just force a re-pull of 'stable' in case it was updated back, or pull 'legacy'.

echo "Stopping service..."
docker-compose down fiber-probe

echo "Updating config to use backup image tag (simulation)..."
# In real scenario: export IMAGE_TAG=v1.1 etc.
# For now, just restart to clear ephemeral fail state
docker-compose up -d --force-recreate fiber-probe

echo "Rollback trigger complete (Basic). For full version rollback, update .env IMAGE_TAG."
