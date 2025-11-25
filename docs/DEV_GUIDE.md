# FiberStack-Lite Developer Guide

**Version:** 1.0  
**Date:** 2025-11-24  
**Status:** Draft (Pending Freeze)

---

## 1. Getting Started

### Prerequisites

Ensure you have the following installed:
- **Python**: 3.11+ (`python3 --version`)
- **Node.js**: 18+ (`node --version`)
- **Docker**: 24+ (`docker --version`)
- **Docker Compose**: 2.20+ (`docker-compose --version`)
- **Git**: 2.40+

### Repository Setup

```bash
# Clone the repository
git clone https://github.com/your-org/FiberStack-Lite.git
cd FiberStack-Lite

# Create virtual environment (for local tooling)
python3 -m venv venv
source venv/bin/activate

# Install dev dependencies
pip install -r requirements-dev.txt
pre-commit install
```

---

## 2. Local Development Environment

We use **Docker Compose** to spin up the entire stack locally.

### Start the Stack

```bash
# Start all services in detached mode
docker-compose -f fiber-deploy/docker-compose.dev.yml up -d

# View logs
docker-compose -f fiber-deploy/docker-compose.dev.yml logs -f
```

### Access Services

| Service | URL | Credentials (Default) |
|---------|-----|-----------------------|
| **Dashboard** | http://localhost:3000 | N/A |
| **API Docs** | http://localhost:8000/docs | N/A |
| **TimescaleDB** | localhost:5432 | user: `postgres`, pass: `postgres` |
| **Elasticsearch** | http://localhost:9200 | N/A |
| **Redis** | localhost:6379 | N/A |

### Stopping the Stack

```bash
# Stop containers
docker-compose -f fiber-deploy/docker-compose.dev.yml down

# Stop and remove volumes (RESET DATA)
docker-compose -f fiber-deploy/docker-compose.dev.yml down -v
```

---

## 3. Development Workflow

### Branching Strategy

- **`main`**: Production-ready code. Always stable.
- **`develop`**: Integration branch.
- **`feature/xyz`**: New features (branch off `develop`).
- **`fix/xyz`**: Bug fixes (branch off `develop`).

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat: add new probe metric`
- `fix: resolve api timeout`
- `docs: update deployment guide`
- `chore: bump dependencies`

### Making Changes

#### Backend (fiber-api / fiber-etl / fiber-probe)

1. **Modify code** in `src/`.
2. **Auto-reload** is enabled in dev container.
3. **Run tests**:
   ```bash
   pytest tests/
   ```

#### Frontend (fiber-dashboard)

1. **Modify code** in `src/`.
2. **Auto-reload** is enabled via React scripts.
3. **Run tests**:
   ```bash
   npm test
   ```

#### Database Migrations

1. **Create migration**:
   ```bash
   alembic revision -m "add_new_table"
   ```
2. **Apply migration**:
   ```bash
   alembic upgrade head
   ```

---

## 4. Coding Standards

### Python (Backend)

- **Style Guide**: PEP 8
- **Formatter**: Black (`line-length = 88`)
- **Linter**: Flake8
- **Type Checking**: Mypy (strict mode)

**Example:**
```python
# Good
def calculate_latency(start_time: float, end_time: float) -> float:
    """Calculates latency in milliseconds."""
    return (end_time - start_time) * 1000

# Bad
def calc(t1, t2):
    return (t2-t1)*1000
```

### JavaScript/TypeScript (Frontend)

- **Style Guide**: Airbnb
- **Formatter**: Prettier
- **Linter**: ESLint

---

## 5. Testing Guidelines

### Unit Tests
- Test individual functions and classes.
- Mock external dependencies (DB, Redis, API).
- **Goal**: >80% code coverage.

### Integration Tests
- Test interactions between modules (e.g., API → DB).
- Use Docker test containers.

### End-to-End (E2E) Tests
- Test full user flows (Probe → API → DB → Dashboard).
- Run before merging to `main`.

---

## 6. Project Structure

```
FiberStack-Lite/
├── docs/               # Architecture documentation
├── fiber-api/          # API Gateway service
├── fiber-dashboard/    # React frontend
├── fiber-db/           # Database schemas & migrations
├── fiber-deploy/       # Docker & deployment configs
├── fiber-etl/          # Data processing pipeline
├── fiber-logging/      # Shared logging library
├── fiber-probe/        # Metrics collection agent
└── tests/              # Cross-service tests
```

---

## 7. Troubleshooting

**Issue: Containers fail to start**
- Check ports: `lsof -i :5432` (ensure ports aren't taken).
- Check logs: `docker-compose logs <service_name>`.

**Issue: Database connection failed**
- Ensure DB container is healthy (`docker ps`).
- Check credentials in `.env`.

**Issue: Changes not reflecting**
- Restart container: `docker-compose restart <service_name>`.
- Rebuild image: `docker-compose build <service_name>`.

---

**Document Status:** Draft - Pending Architecture Freeze  
**Next Step:** Review in [ARCHITECTURE_FREEZE.md](file:///Users/macpro/FiberStack-Lite/docs/ARCHITECTURE_FREEZE.md)
