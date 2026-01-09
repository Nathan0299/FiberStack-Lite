# Release Notes - v1.0.0 (MVP) 🚀

**Date**: January 1, 2026
**Status**: Stable / Freeze
**Codename**: "Black Signal"

## Executive Summary
FiberStack-Lite v1.0.0 is a production-ready, hybrid-cloud network observability platform. It allows operators to visualize network latency, packet loss, and uptime across distributed nodes with a "Tier 1" investigative dashboard.

## Key Capabilities

### 1. Unified Observability
*   **Investigative Map**: Geospatial visualization of all probes. Click-to-inspect functionality for deep dives.
*   **Vital Signs Panel**: Slide-over details panel showing r/t latency, loss, and 10-minute sparkline history.
*   **Strict UX Contract**: Visual states (`HEALTHY`, `DEGRADED`, `STALE`, `DOWN`) are strictly defined by SLA thresholds.

### 2. Hybrid & Multi-Region
*   **Federated Ingest**: Supports telemetry from Cloud (AWS/GCP) and Edge (On-Prem) probes via `fiber-probe` containers.
*   **Global Aggregation**: `fiber-etl` normalizes and aggregates metrics across all regions into a single pane of glass.

### 3. Security & Compliance
*   **RBAC**: Role-Based Access Control (Admin, Operator, Viewer) enforced at API and UI levels.
*   **Audit Trail**: Tamper-evident, hash-chained audit logs for all privileged actions (Node Creation, Deletion).
*   **Zero Trust**: No anonymous access to operational data.

### 4. Operational Legibility
*   **Structured Logging**: Backend emits JSON-structured events for automated analysis.
*   **Traceability**: End-to-end request tracing via `X-Request-ID`.
*   **Resilience**: Validated failover and self-healing for ETL consumers.

## verification "The Gauntlet"
The system has passed the `verify-mvp.sh` validation suite:
- [x] Infrastructure Health (All containers Healthy)
- [x] API Security (Auth & RBAC)
- [x] End-to-End Data Flow (Probe -> Redis -> ETL -> DB)
- [x] Data Integrity & Persistence
- [x] Audit Log Verification

## Known Limitations (v1.0.0)
*   **History**: Sparklines limited to last 100 points in UI (performance optimization).
*   **Alerts**: Email/Slack notifications are mocked (logs only).

## Usage
*   **Start**: `docker compose -f fiber-deploy/docker-compose.dev.yml up -d`
*   **Dashboard**: `http://localhost:4000` (Command-Grade UI)
*   **API**: `http://localhost:8000`

> [!IMPORTANT]
> **Security**: Authentication requires `JWT_SECRET` and `FEDERATION_SECRET` environment variables. See `DEV_GUIDE.md` for configuration.
