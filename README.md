# FiberStack-Lite

![Status](https://img.shields.io/badge/Status-Active_Development-green)
![Version](https://img.shields.io/badge/Version-0.1.0-blue)
![Architecture](https://img.shields.io/badge/Architecture-Frozen-red)

**Distributed Network Infrastructure Monitoring System for Africa**

FiberStack-Lite is a lightweight, scalable monitoring solution designed to track network performance (latency, uptime, packet loss) across geographically distributed nodes.

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+

### Run Locally
```bash
# Clone repo
git clone https://github.com/your-org/FiberStack-Lite.git
cd FiberStack-Lite

# Start development stack
docker-compose -f fiber-deploy/docker-compose.dev.yml up -d
```

Access the dashboard at `http://localhost:3000`.

---

## 📚 Documentation

The project architecture is strictly defined in the `docs/` directory:

- **[System Blueprint](docs/SYSTEM_BLUEPRINT.md)**: High-level architecture and module overview.
- **[Data Model](docs/DATA_MODEL.md)**: Database schemas (TimescaleDB) and data structures.
- **[Deployment Model](docs/DEPLOYMENT_MODEL.md)**: Infrastructure, topology, and scaling.
- **[Developer Guide](docs/DEV_GUIDE.md)**: Setup, workflow, and coding standards.
- **[Architecture Freeze](docs/ARCHITECTURE_FREEZE.md)**: Locked decisions and constraints.

---

## 🏗 Architecture

FiberStack-Lite consists of 6 microservices:

1. **fiber-probe**: Edge agent collecting metrics.
2. **fiber-api**: FastAPI gateway for data ingestion and queries.
3. **fiber-etl**: Async pipeline for data transformation.
4. **fiber-db**: TimescaleDB + Elasticsearch storage layer.
5. **fiber-dashboard**: React-based visualization UI.
6. **fiber-logging**: Centralized logging service.

---

## 🗺 Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| **Phase 1** | Architecture & Foundation | ✅ Complete |
| **Phase 2** | Core Services (API, DB, Probe) | 🚧 Planned |
| **Phase 3** | Sandbox & Testing | 📅 Planned |
| **Phase 4** | Dashboard & Visualization | 📅 Planned |
| **Phase 5** | Deployment & Containerization | 📅 Planned |
| **Phase 6** | MVP Validation | 📅 Planned |
| **Phase 7** | Public Launch | 📅 Planned |

---

## 📄 License

Proprietary - Internal Use Only
