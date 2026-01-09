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

| Component | Development (Local) | Staging (Single Node) | Production (MVP - 20 Probes) | High Performance (1000+ Probes) |
|-----------|---------------------|-----------------------|------------------------------|---------------------------------|
| **CPU** | 4+ Cores | 2 vCPU | 4 vCPU (API/ETL) + 2 vCPU (DB) | 16 vCPU (Cluster) |
| **RAM** | 8 GB+ | 4 GB | 8 GB (API/ETL) + 8 GB (DB) | 32 GB (Cluster) |
| **Storage** | 20 GB SSD | 40 GB SSD | 100 GB SSD (NVMe preferred) | 1 TB NVMe (3000+ IOPS) |
| **Network** | Localhost | Public IP + DNS | 1 Gbps NIC | 10 Gbps NIC (Private VPC) |

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

### 3. Cloud Deployment Profiles

**AWS Native (Recommended)**
- **Compute**: ECS Fargate (API, ETL) + EC2 (Probes if needed).
- **Database**: RDS Aurora PostgreSQL (TimescaleDB support).
- **Cache**: ElastiCache (Redis).
- **Logs**: CloudWatch + Elastic Service (OpenSearch).

**Kubernetes (K8s)**
- **Ingress**: Nginx Ingress Controller + CertManager.
- **Scaling**: HPA on CPU (>70%).
- **Secrets**: K8s Secrets or HashiCorp Vault sidecar.

### 4. Hybrid Deployment (Federation)

The "Data Plane" is distributed across multiple regions while the "Control Plane" remains centralized.

**Topology:**
- **Control Plane (Central)**: `fiber-api`, `fiber-etl`, `fiber-db`, `grafana` hosted in Main Region (e.g., AWS us-east-1).
- **Data Plane (Edge)**: `fiber-probe` instances running in remote regions (Accra, Lagos, Nairobi).

**Connectivity:**
- Probes connect OUTBOUND to Central API via HTTPS (`POST /api/ingest`).
- No inbound ports required on Probes (NAT-friendly).
- Authentication via `FEDERATION_SECRET` (Bearer Token).

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
| `FEDERATION_SECRET` | Probe Authentication | `sandbox_secret` | `(strong-secret)` |
| `ALERT_WEBHOOK_URL` | Alert Notification | `http://localhost...` | `https://slack.com/...` |
| `GF_AUTH_ANONYMOUS_ENABLED` | Grafana Anon Auth | `true` | `false` |
| `RATE_LIMIT_GLOBAL_MAX` | Global System Cap | `200` | `5000` |
| `RATE_LIMIT_INGEST_RATE` | Per-Probe Ingest | `1.0` | `1000.0` |
| `RATE_LIMIT_INGEST_BURST` | Per-Probe Burst | `10` | `2000` |

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

### Verification Strategy ("Airtight")

All verification scripts MUST run **inside the network** (e.g., via `docker exec`) to ensure true connectivity matching service DNS resolution. Host-based verification is unreliable due to network differences.

- **Tools**: `check_network.py` (Container-native diagnostics).
- **Method**: `cat script.py | docker exec -i fiber-api python -`

### Performance Thresholds (Verification Gates)

| Metric | Target | Verification Tool |
|--------|--------|-------------------|
| **API Ingest Latency** | < 100ms p95 | Locust / Prometheus |
| **Dashboard LCP** | < 2.5s | Lighthouse / Chrome DevTools |
| **Ingest Capacity** | > 1000 events/sec | `test_1k_concurrent_probes` |
| **Recovery Time** | < 5s (Redis Outage) | `test_fail_closed_redis_outage` |

### Automated Verification
Run the regression suite before any production deployment:
```bash
pytest tests/e2e/test_e2e_hardened.py -v
```

### Logging

#### Docker Logging Driver
All services use the `json-file` driver with rotation:
```yaml
x-logging: &default-logging
  driver: "json-file"
  options:
    max-size: "50m"
    max-file: "5"
    mode: "non-blocking"
```

#### Log Rotation
```bash
# Manual rotation
docker exec fiber-backup /scripts/rotate-logs.sh

# Automated (cron)
0 0 * * * /scripts/rotate-logs.sh
```

#### Log Aggregation
```bash
# Combine container logs (concurrent-safe)
docker exec fiber-backup /scripts/aggregate-logs.sh
```

#### Filebeat Shipping (Optional)
For centralized logging to Elasticsearch:
```bash
# Config: configs/filebeat.yml
# Health check: scripts/check-shipping.sh
```

- **Retention**: 30 days (ILM policy in Elasticsearch)
- **Permissions**: `chmod 640` on all log files

### Backup Strategy

#### TimescaleDB Backups

| Type | Schedule | Retention | Script |
|------|----------|-----------|--------|
| Hourly logical | `0 * * * *` | 24 hours | `backup-db.sh hourly` |
| Daily full | `0 2 * * *` | 7 days | `backup-db.sh full` |
| Weekly full | `0 3 * * 0` | 4 weeks | Offsite to S3 |

**Backup Command:**
```bash
# Manual backup
docker exec fiber-backup /scripts/backup-db.sh full

# Automated (via cron in fiber-backup container)
0 2 * * * /scripts/backup-db.sh full
0 * * * * /scripts/backup-db.sh hourly
```

**Features:**
- AES256 encryption with GPG
- SHA256 checksum verification
- Automatic cleanup of old backups
- Offsite replication support

#### Elasticsearch Backups (Optional)

```bash
# Create snapshot
docker exec fiber-backup /scripts/backup-es.sh snapshot

# List snapshots
docker exec fiber-backup /scripts/backup-es.sh list

# Cleanup old snapshots
docker exec fiber-backup /scripts/backup-es.sh cleanup
```

#### Recovery Procedures (DR Playbook)

> [!IMPORTANT]
> **RTO Target**: < 15 minutes (Database), < 60 minutes (Full Cluster)
> **RPO Target**: < 1 hour (Standard), < 5 minutes (WAL Archiving enabled)

**1. Database Restore (Gold Standard)**
Use the `verify_backup.py` logic manually if automated scripts fail.

**Scenario A: Full Disaster (Clean Slate)**
1.  **Stop Ingestion**: `docker stop fiber-api fiber-etl` (Prevent split-brain).
2.  **Provision New DB**: Start empty `fiber-db` container.
3.  **Restore Schema & Data**:
    ```bash
    # Restore from latest hourly dump
    gunzip -c db-latest.tar.gz | docker exec -i fiber-db psql -U postgres -d fiberstack
    ```
4.  **Verify Integrity**:
    ```sql
    SELECT count(*) FROM metrics;
    SELECT count(*) FROM nodes;
    -- Verify Hypertable chunks
    SELECT * FROM timescaledb_information.chunks;
    ```
5.  **Re-enable Services**: `docker start fiber-api fiber-etl`.

**Scenario B: Partial Corruption (Dropped Table/Chunk)**
1.  **Identify Point-in-Time**: Find WAL position before error.
2.  **PITR Recovery** (Requires WAL Archiving):
    - Recover to a *new* temporary instance.
    - Export missing data: `COPY (SELECT * FROM metrics ...) TO STDOUT`.
    - Import to Prod: `COPY metrics FROM STDIN`.

**2. Elasticsearch Recovery**
If the Search Index is corrupted or desynced from DB.

1.  **Snapshot Restore**:
    ```bash
    curl -X POST "es:9200/_snapshot/my_backup/snapshot_1/_restore"
    ```
2.  **Rehydration (Reindex from DB)**:
    If snapshots are stale, re-run ETL on historical data.
    - Set ETL into "Replay Mode".
    - `fiber-etl` reads DB -> Pushes to ES.
    - Throughput: ~5k events/sec (estimated).

---

### Automated Verification
Run the "Brutal" Verification Suite weekly to ensure backups are valid.
```bash
# Simulates full destruction and restore in Sandbox
python3 sandbox/scripts/verify_backup.py
```
**Pass Criteria:**
- Row Counts match baseline.
- Latency Checksum matches.
- Schema Constraints (Indexes) valid.


---

## Operator Doctrine

### What Operators MAY Change

| Setting | Location | Notes |
|---------|----------|-------|
| `FEDERATION_SECRET` | `.env` | Required before first deploy |
| `DB_PASS` | `.env` | Required before first deploy |
| Port mappings | `docker-compose.yml` | Host ports only |
| GF_* environment | `docker-compose.yml` | Grafana settings |
| Backup retention | `backup-db.sh` | Days in `DAILY_RETENTION` |

### What Operators MUST NOT Touch

| Item | Reason |
|------|--------|
| Service names in `docker-compose.yml` | Breaks internal DNS |
| Redis key prefixes (`fiber:*`) | Breaks ETL processing |
| ETL queue keys | Data will be lost |
| Database schema | Use migrations only |
| Network name `fiber-net` | Breaks service discovery |

> [!CAUTION]
> Modifying protected items voids data consistency and support guarantees.

---

## Local Cluster Setup

```bash
# Clone and configure
cd FiberStack-Lite/fiber-deploy
cp env.example .env
# Edit .env: Set FEDERATION_SECRET and DB_PASS

# Start services
docker-compose up -d

# Verify health (blocks until ready)
./scripts/wait-for-services.sh 60

# Inject test data
python3 sandbox/dev/load_generator.py
```

---

## Cloud Deployment

### Secrets Handling

| Secret | Source | Injection |
|--------|--------|-----------|
| `FEDERATION_SECRET` | AWS SSM / Vault | ENV via ECS task def |
| `DB_PASS` | AWS Secrets Manager | Sidecar injection |
| `JWT_PUBLIC_KEY` | Parameter Store | Mounted file |

### TLS Termination

- **Load Balancer**: ALB with ACM certificate
- **Internal**: Plaintext (VPC isolation) or mTLS (Phase 6)
- **Probes → Central**: HTTPS required

### Failure Simulation (Required Before Prod)

| Scenario | How to Test | Expected Behavior |
|----------|-------------|-------------------|
| Central outage | `docker stop fiber-api fiber-etl` | Regional buffers (check Redis `LLEN`) |
| Regional outage | `docker stop regional-api` | Probes fallback to Central |
| DB outage | `docker stop fiber-db` | ETL retries with DLQ |
| Network partition | `iptables -A OUTPUT -d central-ip -j DROP` | 24h buffer, replay on restore |

### Observability

| Signal | Destination | Endpoint |
|--------|-------------|----------|
| Logs | Elasticsearch | Via Filebeat |
| Metrics | Prometheus | `:9090/metrics` (future) |
| Health | API | `/api/status` |
| Alerts | Slack | `SLACK_WEBHOOK` |

---

## References

- [System Blueprint](file:///Users/macpro/FiberStack-Lite/docs/SYSTEM_BLUEPRINT.md)
- [Architecture Freeze](file:///Users/macpro/FiberStack-Lite/docs/ARCHITECTURE_FREEZE.md)
- [API Contract](file:///Users/macpro/FiberStack-Lite/docs/API_CONTRACT.md)
- [Data Model](file:///Users/macpro/FiberStack-Lite/docs/DATA_MODEL.md)

---

**Document Status:** v1.1 (Day 75 Black Signal)  
**Freeze Date:** 2025-12-30
