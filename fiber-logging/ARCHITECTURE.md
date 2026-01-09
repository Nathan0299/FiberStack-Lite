# Fiber-Logging Architecture

## Component Design

### Overview

Fiber-Logging implements a centralized logging facade that abstracts configuration management and output formatting. It provides a single `get_logger()` function that returns environment-appropriate logger instances.

```
┌─────────────┐
│   Service   │ (fiber-api, fiber-etl, etc.)
└──────┬──────┘
       │ import
       v
┌──────────────────────┐
│ fiber-logging        │
│  get_logger(name, env│
└──────┬───────────────┘
       │
       ├──> Load configs/logging.{env}.json
       │
       └──> Return configured logger
             │
             ├──> Console (dev)
             └──> Elasticsearch (prod, future)
```

## Implementation

### Core Function

**File:** `src/logger.py`

```python
import logging
import logging.config
import json
import os

def get_logger(service: str, env: str = "dev") -> logging.Logger:
    """
    Get a configured logger for a service.
    
    Args:
        service: Service name (e.g., "fiber-api")
        env: Environment ("dev" or "prod")
    
    Returns:
        Configured logger instance
    """
    config_path = f"/app/fiber-logging/configs/logging.{env}.json"
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    logging.config.dictConfig(config)
    
    return logging.getLogger(service)
```

**Design:** Simple, stateless function that loads config and returns logger

## Configuration Management

### Config File Structure

**Format:** Python logging dictConfig schema
**Location:** `/app/fiber-logging/configs/logging.{env}.json`

**Schema:**
```json
{
  "version": 1,
  "disable_existing_loggers": false,
  "formatters": { ... },
  "handlers": { ... },
  "loggers": { ... },
  "root": { ... }
}
```

### Development Config

**File:** `logging.dev.json`

**Characteristics:**
- Human-readable format
- Console output only
- INFO level (verbose)
- Includes timestamps

**Formatter:**
```
%(asctime)s [%(levelname)s] %(name)s: %(message)s
     ↓            ↓            ↓          ↓
  timestamp    severity    service    message
```

**Example Output:**
```
2025-11-25 22:13:43,260 [INFO] fiber-api: Request received from 10.0.0.1
```

### Production Config (Future)

**File:** `logging.prod.json`

**Characteristics:**
- JSON structured format
- Console + Elasticsearch outputs
- WARNING level (less verbose)
- Service/request correlation IDs

**JSON Formatter:**
```json
{
  "timestamp": "2025-11-25T22:13:43.260Z",
  "level": "INFO",
  "service": "fiber-api",
  "message": "Request received",
  "request_id": "abc-123",
  "client_ip": "10.0.0.1"
}
```

## Logging Levels

### Hierarchy

```
CRITICAL  (50) - System failure, immediate action required
ERROR     (40) - Error occurred, functionality impaired
WARNING   (30) - Unexpected event, but system continues
INFO      (20) - General informational messages
DEBUG     (10) - Detailed diagnostic information
```

### Usage Guidelines

| Level | When to Use | Example |
|-------|-------------|---------|
| DEBUG | Development diagnostics | `logger.debug("Parsing JSON", extra={"raw": msg})` |
| INFO | Normal operational events | `logger.info("Metric processed successfully")` |
| WARNING | Recoverable issues | `logger.warning("Queue depth high", extra={"depth": 1000})` |
| ERROR | Errors that need attention | `logger.error("DB connection failed", extra={"error": e})` |
| CRITICAL | System-level failures | `logger.critical("Out of memory, shutting down")` |

## Handler Architecture

### Console Handler

**Purpose:** Output to stdout/stderr
**Use Case:** Development, Docker logs collection

**Configuration:**
```json
{
  "console": {
    "class": "logging.StreamHandler",
    "level": "INFO",
    "formatter": "standard",
    "stream": "ext://sys.stdout"
  }
}
```

**Output Destination:** 
- `docker logs fiber-api` captures console output
- Kubernetes logs collector reads stdout

### Elasticsearch Handler (Future)

**Purpose:** Centralized log aggregation
**Use Case:** Production monitoring, alerting

**Library:** CMRESHandler
```bash
pip install CMRESHandler
```

**Configuration:**
```json
{
  "elasticsearch": {
    "class": "cmreslogging.handlers.CMRESHandler",
    "hosts": [{"host": "elasticsearch", "port": 9200}],
    "auth_type": "NO_AUTH",
    "es_index_name": "fiber-logs",
    "es_doc_type": "_doc",
    "index_name_frequency": "daily",
    "level": "INFO"
  }
}
```

**Index Pattern:** `fiber-logs-2025.11.25`
**Document Structure:**
```json
{
  "@timestamp": "2025-11-25T22:13:43.260Z",
  "level": "INFO",
  "logger_name": "fiber-api",
  "message": "Request received",
  "extra_field": "value"
}
```

## Structured Logging

### Extra Fields

**Pattern:**
```python
logger.info("message", extra={"key": "value", ...})
```

**Benefits:**
- Searchable fields in Elasticsearch
- Easier debugging
- Metrics extraction

**Example:**
```python
logger.error("Failed to insert metric", extra={
    "node_id": "uuid-123",
    "latency_ms": 45.2,
    "error_type": "ConnectionError",
    "retry_count": 3,
    "timestamp": datetime.now().isoformat()
})
```

**Elasticsearch Query:**
```
error_type:"ConnectionError" AND retry_count:>2
```

## Performance Considerations

### Logging Overhead

**Measurement:**
- Console logging: ~0.5ms per call
- Elasticsearch logging: ~2ms per call (network I/O)
- Total overhead: <1% CPU with moderate logging

### Optimization Strategies

**1. Level Filtering:**
```python
# Don't do expensive operations if not logging
if logger.isEnabledFor(logging.DEBUG):
    logger.debug(f"Complex data: {json.dumps(large_object)}")
```

**2. Lazy Formatting:**
```python
# Good (string formatting only if logged)
logger.info("Value: %s", expensive_call())

# Bad (always calls expensive_call())
logger.info(f"Value: {expensive_call()}")
```

**3. Async Handlers (Future):**
```python
# Queue logs in memory, write async
queue_handler = logging.handlers.QueueHandler(queue)
```

## Integration Patterns

### Current Pattern (Workaround)

Due to `fiber-logging` directory name (hyphen not valid in Python imports):

```python
import sys
sys.path.insert(0, '/app/fiber-logging/src')
from logger import get_logger
```

**Executed in:**
- fiber-api/src/main.py
- fiber-etl/src/worker.py
- fiber-probe/src/agent.py

### Recommended Pattern (Future)

**Rename:** `fiber-logging` → `fiber_logging`

**Then use:**
```python
from fiber_logging import get_logger
```

### Package Installation (Future)

```bash
# Install as editable package
pip install -e ./fiber_logging
```

**Then use:**
```python
from fiber_logging import get_logger
```

## Testing Strategy

### Unit Tests

```python
import logging
from logger import get_logger

def test_logger_creation():
    logger = get_logger("test-service", env="dev")
    assert isinstance(logger, logging.Logger)

def test_logger_level():
    logger = get_logger("test-service", env="dev")
    assert logger.level == logging.INFO

def test_log_output(caplog):
    logger = get_logger("test-service", env="dev")
    logger.info("Test message")
    assert "Test message" in caplog.text
```

### Integration Tests

```python
def test_structured_logging():
    logger = get_logger("test-service")
    logger.info("Event occurred", extra={"key": "value"})
    # Verify JSON structure if using JSON formatter
```

## Monitoring & Observability

### Log Aggregation (Future)

**Elasticsearch + Kibana:**
1. All services → Elasticsearch handler
2. Logs indexed to `fiber-logs-*`
3. Kibana dashboards:
   - Error rate by service
   - Response time distribution
   - Request volume over time

### Alerts (Future)

**Elasticsearch Watcher:**
```json
{
  "trigger": {
    "schedule": { "interval": "5m" }
  },
  "input": {
    "search": {
      "request": {
        "indices": ["fiber-logs-*"],
        "body": {
          "query": {
            "bool": {
              "must": [
                { "term": { "level": "ERROR" }},
                { "range": { "@timestamp": { "gte": "now-5m" }}}
              ]
            }
          }
        }
      }
    }
  },
  "condition": {
    "compare": { "ctx.payload.hits.total": { "gt": 10 }}
  },
  "actions": {
    "notify_slack": { ... }
  }
}
```

**Alert:** If >10 errors in 5 minutes, notify Slack

## Related Files

- [logger.py](src/logger.py) - Core implementation
- [logging.dev.json](configs/logging.dev.json) - Development config
- [CONFIG.md](CONFIG.md) - Configuration reference
