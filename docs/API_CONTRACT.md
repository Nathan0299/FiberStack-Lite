# API Service Contract (fiber-api)

## Responsibility
Receive probe data, validate it, store it via ETL pipeline.

## Inputs
- Probe data (POST /api/push)
- Dashboard queries (/api/metrics)
- ETL callbacks (/api/etl/*)

## Outputs
- Normalized JSON passed to ETL queue
- Aggregated metrics for dashboard

## Endpoints
GET /api/status
POST /api/push
GET /api/metrics
GET /api/nodes
GET /api/etl/status

## What API Will Never Do
- Heavy transformations (ETL's job)
- Direct chart rendering (dashboard's job)
- Raw database writes (ETL handles shaping)
- Probe scheduling or orchestration
