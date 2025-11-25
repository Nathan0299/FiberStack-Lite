# Probe Service Contract (fiber-probe)

## Responsibility
Collect local metrics and push them to fiber-api.

## Inputs
- Local system metrics (latency, packet loss, uptime)
- Configuration file (probe.yaml)

## Outputs
- HTTP POST request to /api/push
- JSON payload

## API Interaction
POST /api/push
Content-Type: application/json

Payload:
{
  "node_id": "<string>",
  "country": "<string>",
  "region": "<string>",
  "latency_ms": <float>,
  "uptime_pct": <float>,
  "packet_loss": <float>,
  "timestamp": "<ISO8601>"
}

## What Probe Will Never Do
- Direct database writes
- Query metrics
- Serve any HTTP endpoints
- Run scheduled dashboards
