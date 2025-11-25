# FiberStack Sandbox (Local)

Purpose:
This sandbox is an isolated environment for local development.

What it does:
- Runs TimescaleDB + Elasticsearch locally
- Runs the API, ETL worker, dashboard, and probe in safe mode
- No real-world nodes touched
- No cloud services involved

Start:
./bootstrap.sh

Reset:
../scripts/reset_sandbox.sh


# Environment Structure

env.sandbox
    Base env for all services.
env.api
    API-only variables.
env.etl
    ETL-specific.
env.probe
    Probe-specific.
env.dashboard
    Dashboard-specific.

To apply changes:
docker compose down
docker compose up --build


# Run Sandbox Stack

docker compose -f docker-compose.sandbox.yml up --build

# Stop Stack
docker compose -f docker-compose.sandbox.yml down

# Logs
docker compose -f docker-compose.sandbox.yml logs -f fiber-api
