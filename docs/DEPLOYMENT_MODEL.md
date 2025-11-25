# FiberStack-Lite Deployment Model

**Version:** 1.0  
**Date:** 2025-11-24  
**Status:** Draft (Pending Freeze)

---

## Overview

This document defines how FiberStack-Lite is deployed across different environments (Development, Staging, Production). It covers infrastructure requirements, service topology, scaling strategies, and environment-specific configurations.

**Key Principles:**
- **Containerization**: All services are Dockerized for consistency.
- **Infrastructure as Code**: Deployments are defined in `docker-compose.yml` (MVP) and Terraform (Future).
- **Separation of Concerns**: Stateful services (DB) are separated from stateless services (API, ETL).
- **Observability**: Monitoring and logging are built-in from day one.

---

## Infrastructure Requirements

### 1. Hardware Specifications

| Component | Development (Local) | Staging (Single Node) | Production (MVP - 10-20 Probes) |
|-----------|---------------------|-----------------------|---------------------------------|
| **CPU** | 4+ Cores | 2 vCPU | 4 vCPU (API/ETL) + 2 vCPU (DB) |
| **RAM** | 8 GB+ | 4 GB | 8 GB (API/ETL) + 8 GB (DB) |
| **Storage** | 20 GB SSD | 40 GB SSD | 100 GB SSD (NVMe preferred) |
| **Network** | Localhost | Public IP + DNS | Load Balancer + Private VPC |

### 2. External Dependencies

- **Docker Engine**: v24.0+
- **Docker Compose**: v2.20+
- **Domain Name**: `fiberstack.io` (example) with DNS records managed via Cloudflare.
- **SSL Certificates**: Let's Encrypt (via Certbot or Traefik).

---

## Service Topology

### 1. Development Environment (Local)

**Goal**: Rapid iteration, full stack on one machine.

```mermaid
graph TD
    User[Developer] -->|localhost:3000| Dashboard[fiber-dashboard<br/>(Dev Server)]
    User -->|localhost:8000| API[fiber-api<br/>(FastAPI Reload)]
    
    subgraph Docker Network
        API -->|Read/Write| DB[(TimescaleDB)]
        API -->|Push| Redis[Redis Queue]
        
        ETL[fiber-etl<br/>(Worker)] -->|Pop| Redis
        ETL -->|Write| DB
        ETL -->|Index| ES[(Elasticsearch)]
        
        API -.->|Log| ES
        ETL -.->|Log| ES
    end
```

**Configuration:**
- **File**: `fiber-deploy/docker-compose.dev.yml`
- **Volumes**: Local bind mounts for code (hot reloading).
- **Ports**: Exposed to host (3000, 8000, 5432, 6379).

### 2. Production Environment (MVP)

**Goal**: Stability, security, and basic scalability for 10-20 probes.

```mermaid
graph TD
    Internet((Internet)) -->|HTTPS/443| LB[Nginx / Load Balancer]
    
    subgraph "Private Network (VPC)"
        LB -->|/api| API1[fiber-api-1]
        LB -->|/api| API2[fiber-api-2]
        LB -->|/| Static[fiber-dashboard<br/>(Nginx Static)]
        
        API1 & API2 --> Redis[Redis Cache/Queue]
        
        subgraph "Async Workers"
            ETL1[fiber-etl-1]
            ETL2[fiber-etl-2]
        end
        
        Redis --> ETL1 & ETL2
        
        subgraph "Data Layer"
            DB[(TimescaleDB)]
            ES[(Elasticsearch)]
        end
        
        API1 & API2 --> DB
        ETL1 & ETL2 --> DB & ES
    end
```

**Configuration:**
- **File**: `fiber-deploy/docker-compose.prod.yml`
- **Volumes**: Named Docker volumes for persistence (no bind mounts).
- **Network**: Internal bridge network, only LB ports exposed.
- **Restart Policy**: `always` or `on-failure`.

---

## Environment Configuration

Configuration is managed via `.env` files and environment variables.

### Key Environment Variables

| Variable | Description | Example (Dev) | Example (Prod) |
|----------|-------------|---------------|----------------|
| `ENV` | Environment Name | `dev` | `prod` |
| `DB_HOST` | Database Hostname | `localhost` | `db-primary` |
| `DB_PASS` | Database Password | `postgres` | `(secret)` |
| `REDIS_URL` | Redis Connection | `redis://localhost:6379/0` | `redis://redis-prod:6379/0` |
| `ELASTIC_URL` | Elasticsearch URL | `http://localhost:9200` | `http://es-prod:9200` |
| `API_KEY_SECRET` | Secret for signing keys | `dev-secret` | `(strong-secret)` |
| `CORS_ORIGINS` | Allowed CORS origins | `http://localhost:3000` | `https://dashboard.fiberstack.io` |

### Secrets Management

- **Development**: `.env` file (git-ignored).
- **Production**: Docker Secrets or injected environment variables from CI/CD pipeline.

---

## Scaling Strategy

### Phase 1 (MVP - 20 Probes)
- **Vertical Scaling**: Single node is sufficient.
- **Bottleneck**: Likely none at this scale.

### Phase 2 (100+ Probes)
- **API Layer**: Scale horizontally (add more `fiber-api` containers).
- **ETL Layer**: Add more `fiber-etl` workers to consume Redis queue faster.
- **Database**: Optimize TimescaleDB config (memory tuning).

### Phase 3 (1000+ Probes - Future)
- **Database**: Read replicas for dashboard queries.
- **Ingestion**: Dedicated ingestion nodes.
- **Load Balancing**: Cloud Load Balancer (AWS ALB / Cloudflare).

---

## Deployment Workflow

### CI/CD Pipeline (GitHub Actions - Planned)

1. **Build Stage**
   - Lint code (flake8, eslint).
   - Run unit tests.
   - Build Docker images.

2. **Publish Stage**
   - Tag images (`fiber-api:v1.0.0`).
   - Push to Container Registry (GHCR / Docker Hub).

3. **Deploy Stage**
   - SSH into production server.
   - `docker-compose pull`.
   - `docker-compose up -d`.
   - Run database migrations (`alembic upgrade head`).

---

## Monitoring & Maintenance

### Health Checks

- **API**: `GET /api/status` (checks DB & Redis connectivity).
- **ETL**: Monitor queue depth in Redis.
- **Probe**: `last_seen_at` timestamp in DB.

### Logging

- All services log to `stdout`/`stderr` (JSON format).
- Docker logging driver sends logs to Elasticsearch (via Filebeat or direct).
- **Retention**: 30 days.

### Backup Strategy

- **Database**: Daily `pg_dump` to S3 bucket.
- **Config**: Git repository.
- **Recovery**: Restore from latest S3 dump + replay logs (if WAL archiving enabled).

---

## References

- [System Blueprint](file:///Users/macpro/FiberStack-Lite/docs/SYSTEM_BLUEPRINT.md)
- [Data Model](file:///Users/macpro/FiberStack-Lite/docs/DATA_MODEL.md)

---

**Document Status:** Draft - Pending Architecture Freeze  
**Next Step:** Review in [ARCHITECTURE_FREEZE.md](file:///Users/macpro/FiberStack-Lite/docs/ARCHITECTURE_FREEZE.md)
