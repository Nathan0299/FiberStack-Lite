# Cluster Deployment

This folder contains Docker Compose configurations for the 3-tier cluster topology.

## Structure

| File | Purpose |
|------|---------|
| `central.docker-compose.yml` | Central Aggregator (API, ETL, DB, Grafana) |
| `regional.docker-compose.yml` | Regional Ingest (API relay, Redis buffer) |
| `edge.docker-compose.yml` | Edge Probe only |

## Deployment Order

1. Deploy **Central** first (cloud VPS).
2. Deploy **Regional** in each target region (GH, NG, KE).
3. Deploy **Edge** probes pointing to nearest Regional.

## Environment Variables

| Variable | Central | Regional | Edge |
|----------|---------|----------|------|
| `CENTRAL_API_URL` | - | Required | - |
| `REGIONAL_API_URL` | - | - | Required |
| `FEDERATION_SECRET` | Issues | Validates | Uses |
| `REGION_ID` | - | Required | - |
