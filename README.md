# FiberStack-Lite

![Status](https://img.shields.io/badge/Status-MVP_Frozen-red)
![Version](https://img.shields.io/badge/Version-v1.0.0--mvp-blue)
![Architecture](https://img.shields.io/badge/Architecture-Frozen-red)
![Freeze Date](https://img.shields.io/badge/Freeze_Date-2026--01--09-orange)

**Distributed Network Infrastructure Monitoring System for Africa**

FiberStack-Lite is a lightweight, scalable monitoring solution designed to track network performance (latency, uptime, packet loss) across geographically distributed nodes.

---

## 🚀 Quick Start (MVP Dry Run)

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+

### Run Locally (Hybrid Simulation)
```bash
# Clone repo
git clone https://github.com/Nathan0299/FiberStack-Lite.git
cd FiberStack-Lite

# Start MVP Stack (Black Signal Verified)
docker-compose -f fiber-deploy/docker-compose.dev.yml up -d
```

- **Dashboard**: `http://localhost:4000` (Command-Grade UI)
- **API Docs**: `http://localhost:8000/docs`

---

## 📚 Documentation

The project architecture is strictly defined in the `docs/` directory:

- **[System Blueprint](docs/SYSTEM_BLUEPRINT.md)**: High-level architecture and module overview.
- **[Data Model](docs/DATA_MODEL.md)**: Database schemas (TimescaleDB) and data structures.
- **[Deployment Model](docs/DEPLOYMENT_MODEL.md)**: Infrastructure, topology, and scaling.
- **[Developer Guide](docs/DEV_GUIDE.md)**: Setup, workflow, and coding standards.
- **[Architecture Freeze](docs/ARCHITECTURE_FREEZE.md)**: Locked decisions and constraints.
- **[Release Notes](docs/RELEASE_NOTES.md)**: v1.0.0 Capabilities.

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
| **Phase 2** | Core Services (API, DB, Probe) | ✅ Complete |
| **Phase 3** | Sandbox & Testing | ✅ Complete |
| **Phase 4** | Dashboard & Visualization | ✅ Complete |
| **Phase 5** | Deployment & Containerization | ✅ Complete |
| **Phase 6** | MVP Validation | ✅ Complete |
| **Phase 7** | Public Launch | 🚧 Next |

---

## 📄 License

MIT License

## 📧 Contact

Project lead: Nathaniel Lamptey  
Email: nathaniellamptey17@gmail.com  
GitHub: @Nathan0299
