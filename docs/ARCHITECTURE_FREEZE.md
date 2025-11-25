# FiberStack-Lite Architecture Freeze

**Version:** 1.0  
**Freeze Date:** 2025-11-24  
**Status:** **LOCKED**

---

## 1. Executive Summary

This document certifies that the architecture for **FiberStack-Lite Phase 1-6** is now **FROZEN**. All development must strictly adhere to the decisions recorded here. Any deviation requires a formal change request and version bump.

**Objective:** Build a distributed network monitoring system for 10-20 nodes across Ghana, Nigeria, and Kenya.

---

## 2. Frozen Decisions

The following architectural choices are locked and cannot be changed without significant refactoring.

| Category | Decision | Rationale | Change Impact |
|----------|----------|-----------|---------------|
| **Dashboard** | **React Web** | Standard web tech, easier hiring, rich ecosystem | High (Rewrite UI) |
| **Database** | **TimescaleDB** | Optimized for time-series, SQL compatibility | Critical (Schema rewrite) |
| **Logs** | **Elasticsearch** | Powerful search, scalable log aggregation | Medium (Adapter change) |
| **Queue** | **Redis** | Simple, fast, already used for cache | Medium (Worker refactor) |
| **API** | **FastAPI (Python)** | Async performance, auto-docs, type safety | High (Rewrite API) |
| **Deployment** | **Docker Compose** | Portable, consistent dev/prod parity | Medium (Ops change) |
| **Regions** | **GH, NG, KE** | Initial target markets | Low (Config change) |

---

## 3. Service Boundaries (Inviolable)

1. **fiber-probe**: MUST ONLY collect and push. NO local storage (except buffer).
2. **fiber-api**: MUST be stateless. NO heavy processing.
3. **fiber-etl**: MUST be the ONLY writer to metrics tables.
4. **fiber-dashboard**: MUST read ONLY from API. NO direct DB access.

---

## 4. Data Model Freeze

- **Primary Key**: UUID for all nodes.
- **Time Precision**: Milliseconds (stored as TIMESTAMPTZ).
- **Retention**: 
  - Raw: 7 days
  - Hourly: 90 days
  - Daily: 1 year

---

## 5. Change Control Process

To modify any "Frozen" item above:

1. **Proposal**: Create an issue describing the limitation of current architecture.
2. **Review**: Must be approved by Lead Architect.
3. **Migration**: Must include a data migration plan.
4. **Version Bump**: Increment System Version (e.g., 1.0 → 1.1).

---

## 6. Sign-Off

**Architect:** Antigravity AI  
**Date:** 2025-11-24  
**Validation:**
- [x] All service contracts reviewed.
- [x] Data model covers all requirements.
- [x] Deployment model is feasible.
- [x] Technology stack is compatible.

**Outcome:** ✅ **APPROVED FOR DEVELOPMENT**
