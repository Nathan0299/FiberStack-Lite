# Database Contract (fiber-db)

## Responsibility
Provide storage models for metrics and logs.

## Inputs
- ETL writes
- Dashboard read queries
- API data lookups (nodes, metadata)

## Outputs
- Timescale metrics (SELECT)
- Elasticsearch index responses

## Schema Guarantee
Tables:
- metrics_raw
- metrics_agg
- nodes
- etl_logs

Elastic indexes:
- infra_logs

## What DB Will Never Do
- Accept direct writes from probes or API
- Accept unvalidated payloads
- Implement business logic
