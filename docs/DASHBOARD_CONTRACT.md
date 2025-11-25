# Dashboard Service Contract (fiber-dashboard)

## Responsibility
Visualize metrics and display infra health.

## Inputs
- Metrics query response from fiber-api (/api/metrics)
- Node lists (/api/nodes)
- Map rendering resources

## Outputs
- Web UI
- Charts for latency, uptime, packet loss

## Endpoints Consumed
GET /api/metrics
GET /api/nodes
GET /api/status

## What Dashboard Will Never Do
- Store data
- Process raw metrics
- Modify ETL or API logic
- Push probe data
