# ETL Service Contract (fiber-etl)

## Responsibility
Normalize, transform, and load all incoming metric data.

## Inputs
- Normalized payload from fiber-api (internal message queue or function call)
- Schema definitions from fiber-db

## Outputs
- Inserts into TimescaleDB
- Indexing documents into Elasticsearch

## Operations
transform()  → cleanup and validation  
load_timescale()  → metrics table  
load_elastic()  → logs/index  

## What ETL Will Never Do
- Serve public API endpoints
- Accept external traffic
- Render dashboards
- Trigger probe operations
