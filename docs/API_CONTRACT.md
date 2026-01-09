# API Service Contract (fiber-api)

## Responsibility
Receive probe data, validate it, store it via ETL pipeline.

## Inputs
- Probe data (POST /api/push)
- Dashboard queries (/api/metrics)
- Federation batches (POST /api/ingest)

## Outputs
- Normalized JSON passed to ETL queue
- Aggregated metrics for dashboard

---

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/status` | System health check |
| POST | `/api/push` | Single metric ingestion |
| POST | `/api/ingest` | Federation batch ingestion |
| GET | `/api/metrics` | Query stored metrics |
| GET | `/api/metrics/aggregated` | Analytics aggregation |
| GET | `/api/metrics/cluster` | Cluster-wide stats |
| GET | `/api/nodes` | List registered nodes |

---

## Error Responses

| Code | Condition | Response Body |
|------|-----------|---------------|
| `400` | Malformed batch / invalid JSON | `{"status":"error","code":"MALFORMED_BATCH"}` |
| `401` | Invalid or missing token | `{"status":"error","code":"INVALID_TOKEN"}` |
| `409` | Duplicate `X-Batch-ID` | `{"status":"accepted","message":"Already processed"}` |
| `413` | Batch exceeds 10MB | `{"status":"error","code":"PAYLOAD_TOO_LARGE"}` |
| `429` | Rate limit exceeded | `{"status":"error","code":"RATE_LIMITED"}` |

---

## Rate Limits

| Endpoint | Limit | Window | Header |
|----------|-------|--------|--------|
| `/api/push` | 100 req | 1 min | `X-RateLimit-Remaining` |
| `/api/ingest` | 50 req | 1 min | `X-RateLimit-Remaining` |
| `/api/metrics/*` | 200 req | 1 min | `X-RateLimit-Remaining` |

---

## Payload Constraints

| Field | Max Size |
|-------|----------|
| Single metric | 4 KB |
| Batch payload | 10 MB |
| Metrics per batch | 1000 |

---

## POST /api/ingest

**Purpose:** Batch ingestion from Regional hubs.

**Headers:**
- `Authorization: Bearer <token>` (Required)
- `X-Batch-ID: <uuid>` (Required, idempotency key)
- `X-Region-ID: <region>` (Optional, e.g., `gh-accra`)

**Request:**
```json
{
  "node_id": "region-hub-01",
  "metrics": [
    {
      "node_id": "probe-gh-01",
      "country": "GH",
      "region": "Accra",
      "latency_ms": 45.0,
      "uptime_pct": 100,
      "packet_loss": 0.0,
      "timestamp": "2025-12-30T12:00:00Z"
    }
  ]
}
```

**Response:** `202 Accepted`
```json
{
  "status": "accepted",
  "message": "Queued 5 metrics",
  "data": {"batch_id": "...", "source_region": "gh-accra"}
}
```

---

## GET /api/metrics/cluster

**Purpose:** Cluster-wide fleet metrics with regional breakdown.

**Query Params:**
- `start_time` (optional, UTC)
- `end_time` (optional, UTC)
- `top_n` (1-20, default 5)

**Response:**
```json
{
  "status": "ok",
  "data": {
    "time_range": {"start": "...", "end": "..."},
    "fleet_summary": {
      "total_nodes": 18,
      "avg_latency_ms": 35.2,
      "avg_uptime_pct": 99.8
    },
    "regional_breakdown": [
      {"region": "gh-accra", "nodes": 5, "avg_latency": 32.0}
    ],
    "top_problematic_nodes": [
      {"node_id": "...", "score": 8.5, "avg_latency": 120.0}
    ]
  }
}
```

---

## Logging Contract

All services must adhere to the **FiberStack Logging Standard** (`fiber-logging` module):

| Environment | Format | Level |
|-------------|--------|-------|
| Production | **JSON** | WARNING+ |
| Staging | **JSON** | INFO+ |
| Development | **Text** (Colorized) | DEBUG+ |

---

## What API Will Never Do
- Heavy transformations (ETL's job)
- Direct chart rendering (dashboard's job)
- Raw database writes (ETL handles shaping)
- Probe scheduling or orchestration
