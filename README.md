# FiberStack-Lite

[![status](https://img.shields.io/badge/status-alpha-yellow)]() [![license](https://img.shields.io/badge/license-MIT-blue)]()

Lightweight, modular infrastructure stack for building and testing **digital sovereignty systems**.  
Provides core services (DB, cache, messaging, API gateway) with minimal overhead.

---

## Table of Contents
- [Project Overview](#project-overview)
- [Status](#status)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Quickstart (Dev)](#quickstart-dev)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
  - [Docker Compose (Default)](#docker-compose-default)
- [Environment Variables](#environment-variables)
- [Testing](#testing)
- [Contributing](#contributing)
- [Roadmap](#roadmap)
- [License](#license)
- [Contact](#contact)

---

## Project Overview
FiberStack-Lite is a **sovereign infra starter kit**:  
- Easy to spin up locally or on a small VPS  
- Combines **Postgres, Redis, FastAPI, Nginx gateway, and optional MQTT**  
- Designed for learning, prototyping, and running **minimal but powerful digital services**

---

## Status
**Alpha** — works for dev experiments.  
Pending: scaling tests, multi-node setup, monitoring layer.

---

## Key Features
- Postgres database with migrations baked in
- Redis for cache & queues
- FastAPI backend service
- Optional MQTT for messaging
- Nginx as API gateway / reverse proxy
- Docker Compose orchestration

---

## Tech Stack
- **Backend**: Python (FastAPI)
- **Database**: PostgreSQL
- **Cache/Queue**: Redis
- **Messaging**: MQTT (optional)
- **Gateway**: Nginx
- **Containerization**: Docker / Docker Compose

---

## Architecture
Client (Browser/Mobile)
↕
Nginx Gateway
↕
FastAPI Backend
↕
PostgreSQL + Redis
↕
(MQTT Broker)

Security:
- Minimal exposed services  
- Configurable `.env` for secrets  
- Modular design → swap components easily  

---

## Quickstart (Dev)

> Prerequisites: `python3.11`, `docker`, and `docker compose` installed.

### 1. Clone the repository
```bash
git clone git@github.com:Nathan0299/FiberStack-Lite.git
cd FiberStack-Lite


```
## Backend Setup
cd backend                # Move into backend folder
python -m venv venv       # Create virtual environment
source venv/bin/activate  # Activate environment
pip install -r requirements.txt   # Install dependencies
uvicorn app.main:app --reload     # Run dev server

## Frontend Setup
cd frontend
npm install
npm run dev

## Docker Compose (Default)
docker compose up --build


## Environment Variables
POSTGRES_USER=admin
POSTGRES_PASSWORD=secret
POSTGRES_DB=fiberstack
REDIS_URL=redis://redis:6379/0
SECRET_KEY=your_secret_key_here
MQTT_BROKER_URL=broker

## Testing
Backend:
pytest

## Database migration test:
alembic upgrade head

## Contributing
Pull requests are welcome.
For major changes, open an issue first to discuss what you’d like to change.

## Roadmap
 Add Prometheus + Grafana monitoring
 Kubernetes Helm charts
 Multi-node deployment guide
 Hardened security configs

## License
MIT License. See LICENSE for details.

## Contact
Project lead: Nathaniel Lamptey
📧 Email: [nathaniellamptey17@gmail.com]
🌍 GitHub: @Nathan0299
