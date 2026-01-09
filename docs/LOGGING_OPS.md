# Day 87: Logging Operations Runbook

## Overview
This document covers operational procedures for the FiberStack logging pipeline.

## Architecture
```
Probe → API → Redis → ETL → ES
         ↑                   ↑
      Filebeat ─────────────┘
```

## Trace ID Flow
| Service | Action |
|---------|--------|
| Probe | Generates 8-char base62 `trace_id`, sends via `X-Trace-ID` header |
| API | Reads `X-Trace-ID` (or generates), echoes back, adds to `_meta` |
| ETL | Inherits `trace_id` from `_meta`, creates child spans |

---

## Common Scenarios

### ES Down
1. **Symptoms**: `log_dropped_total` increasing, DLQ files growing
2. **Action**:
   ```bash
   # Check ES health
   curl http://localhost:9200/_cluster/health
   
   # Monitor DLQ size
   du -sh /var/lib/fiber/dlq/
   ```
3. **Recovery**: Once ES is healthy, run replay:
   ```bash
   python3 scripts/replay_dlq.py
   ```

### ES Recovery (Post-Outage)
1. **Throttle replay** to avoid overwhelming ES:
   ```bash
   export REPLAY_BATCH_SIZE=50
   export REPLAY_DELAY_MS=200
   python3 scripts/replay_dlq.py
   ```
2. **Monitor**: Check `dlq_replay_events_total` in Grafana

### DLQ Full (>100MB)
1. **Extend retention** during outage:
   ```bash
   export DLQ_RETENTION_DAYS=30
   ```
2. **Scale ES** if outage is prolonged
3. Oldest files auto-deleted after retention period

### High Cardinality Alert
1. **Reduce sampling**:
   ```bash
   export LOG_SAMPLE_RATE=0.1  # 10%
   ```
2. **Restart services** to pick up new rate

### Quarantine Review
Bad log lines are saved to `*.quarantine` files:
```bash
cat /var/lib/fiber/dlq/*.quarantine
# Fix and re-queue manually if needed
```

---

## ILM Management

### Check Policy Status
```bash
curl "http://localhost:9200/_ilm/explain/fiber-logs-*" | jq
```

### Force Rollover
```bash
curl -X POST "http://localhost:9200/fiber-logs-*/_rollover"
```

---

## Alerting Thresholds

| Alert | Threshold | Action |
|-------|-----------|--------|
| LogsDropped | >10/sec for 2m | Check sampling, increase ES capacity |
| DLQFilling | >50MB | Scale ES, extend retention |
| ESIngestionSlow | p99 >5s | Scale ES, check disk I/O |
| MissingTraceRatio | >10% for 5m | Check probe/API trace propagation |
| LogSurge | >1000/sec for 2m | Check for log loops, reduce verbosity |
| ReplayFailures | >0 | Check ES health, review quarantine |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | INFO | Logging verbosity |
| `LOG_FORMAT` | json | `json` or `human` |
| `LOG_SAMPLE_RATE` | 1.0 | Sampling rate (0.0-1.0) |
| `SERVICE_NAME` | fiber | Service identifier in logs |
| `DLQ_DIR` | /var/lib/fiber/dlq | Dead-letter queue path |
| `DLQ_RETENTION_DAYS` | 7 | Days to keep DLQ files |
| `REPLAY_BATCH_SIZE` | 100 | Bulk size during replay |
| `REPLAY_DELAY_MS` | 100 | Delay between batches |
