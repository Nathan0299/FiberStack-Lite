# Fiber-Logging

**Centralized Logging Library for FiberStack-Lite**

## Overview

Fiber-Logging provides a unified logging interface across all FiberStack services. It implements structured logging with environment-aware configuration, supporting both console output (development) and Elasticsearch integration (production).

## Quick Start

### Installation

```python
# Add to requirements.txt
python-json-logger==2.0.7

# Install
pip install python-json-logger
```

### Usage

```python
import sys
sys.path.insert(0, '/app/fiber-logging/src')
from logger import get_logger

logger = get_logger("my-service", env="dev")
logger.info("Application started")
logger.error("Failed to process request", extra={"request_id": "123"})
```

## Configuration

### Environment-Based Config

Logging configurations are loaded from JSON files:
- **Development:** `configs/logging.dev.json`
- **Production:** `configs/logging.prod.json`

### Development Config (`logging.dev.json`)

```json
{
  "version": 1,
  "disable_existing_loggers": false,
  "formatters": {
    "standard": {
      "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    }
  },
  "handlers": {
    "console": {
      "class": "logging.StreamHandler",
      "level": "INFO",
      "formatter": "standard",
      "stream": "ext://sys.stdout"
    }
  },
  "root": {
    "level": "INFO",
    "handlers": ["console"]
  }
}
```

**Output:**
```
2025-11-25 22:13:43,260 [INFO] fiber-etl: Processing batch of 60 metrics
```

### Production Config (Future)

```json
{
  "handlers": {
    "console": { "class": "logging.StreamHandler" },
    "elasticsearch": {
      "class": "CMRESHandler",
      "hosts": [{"host": "elasticsearch", "port": 9200}],
      "auth_type": "NO_AUTH",
      "es_index_name": "fiber-logs"
    }
  },
  "root": {
    "level": "INFO",
    "handlers": ["console", "elasticsearch"]
  }
}
```

## API

### `get_logger(service: str, env: str = "dev") -> logging.Logger`

**Parameters:**
- `service`: Service name (e.g., "fiber-api", "fiber-etl")
- `env`: Environment ("dev" or "prod")

**Returns:** Configured logger instance

**Example:**
```python
logger = get_logger("fiber-api", env="dev")
```

### Logging Methods

```python
# Info level
logger.info("Request received", extra={"method": "POST", "path": "/api/push"})

# Warning level
logger.warning("Queue depth high", extra={"depth": 1000})

# Error level
logger.error("Failed to connect to database", extra={"error": str(e)})

# Debug level
logger.debug("Parsing message", extra={"message": msg})
```

## Structured Logging

### Extra Context

```python
logger.info("Metric processed", extra={
    "node_id": "uuid",
    "latency_ms": 45.2,
    "processing_time_ms": 12.5
})
```

**Output (with JSON formatter):**
```json
{
  "timestamp": "2025-11-25T22:13:43.260Z",
  "level": "INFO",
  "service": "fiber-etl",
  "message": "Metric processed",
  "node_id": "uuid",
  "latency_ms": 45.2,
  "processing_time_ms": 12.5
}
```

## Integration

### Import Pattern (Current)

Due to directory structure with hyphens, using sys.path injection:

```python
import sys
sys.path.insert(0, '/app/fiber-logging/src')
from logger import get_logger

logger = get_logger("service-name", env=os.getenv("ENV", "dev"))
```

### Future: Proper Package

```python
# After renaming fiber-logging → fiber_logging
from fiber_logging import get_logger
```

## Project Structure

```
fiber-logging/
├── src/
│   ├── __init__.py
│   └── logger.py          # get_logger() function
├── configs/
│   ├── logging.dev.json   # Development config
│   └── logging.prod.json  # Production config (future)
├── README.md
└── ARCHITECTURE.md
```

## Performance

- **Overhead:** <1ms per log entry
- **Memory:** Negligible (<1MB)
- **I/O Impact:** Async writes (non-blocking)

## Best Practices

### Use Appropriate Levels

```python
logger.debug("Variable value: ", extra={"var": value})  # Verbose debugging
logger.info("Request completed")                        # Normal events
logger.warning("High memory usage")                     # Potential issues
logger.error("Database connection failed")              # Errors
logger.critical("System shutting down")                 # Critical failures
```

### Include Context

```python
# Bad
logger.error("Failed")

# Good
logger.error("Failed to insert metric", extra={
    "node_id": node_id,
    "error": str(e),
    "attempt": retry_count
})
```

### Don't Log Sensitive Data

```python
# Bad
logger.info("User logged in", extra={"password": pwd})

# Good
logger.info("User logged in", extra={"username": user})
```

## Elasticsearch Integration (Future)

### Setup

```bash
pip install CMRESHandler
```

### Configuration

```json
{
  "handlers": {
    "elasticsearch": {
      "class": "cmreslogging.handlers.CMRESHandler",
      "hosts": [{"host": "es:9200"}],
      "index_name_frequency": "daily",
      "es_index_name": "fiber-logs"
    }
  }
}
```

### Kibana Queries

```
# Filter by service
service:"fiber-api" AND level:"ERROR"

# Time range
@timestamp:[now-1h TO now]

# Latency > 100ms
latency_ms:>100
```

## Testing

```python
# tests/test_logging.py
import logging
from logger import get_logger

def test_get_logger():
    logger = get_logger("test-service")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test-service"

def test_log_with_context(caplog):
    logger = get_logger("test-service")
    logger.info("Test message", extra={"key": "value"})
    assert "Test message" in caplog.text
```

## Related Documentation

- [CONFIG.md](CONFIG.md) - Configuration details
- [ARCHITECTURE.md](ARCHITECTURE.md) - Design decisions

## License

MIT License - FiberStack-Lite © 2025
