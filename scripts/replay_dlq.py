#!/usr/bin/env python3
"""
Day 87: DLQ Replay Script
Drains dead-letter queue logs into Elasticsearch with backoff and quarantine.
"""
import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("dlq-replay")

# Configuration
DLQ_DIR = Path(os.getenv("DLQ_DIR", "/var/lib/fiber/dlq"))
ES_URL = os.getenv("ELASTIC_URL", "http://localhost:9200")
BATCH_SIZE = int(os.getenv("REPLAY_BATCH_SIZE", "100"))
DELAY_MS = int(os.getenv("REPLAY_DELAY_MS", "100"))
RETENTION_DAYS = int(os.getenv("DLQ_RETENTION_DAYS", "7"))

# Prometheus metrics (optional)
try:
    from prometheus_client import Counter, start_http_server
    REPLAY_SUCCESS = Counter('dlq_replay_events_total', 'Events replayed', ['status'])
    start_http_server(9101)
except ImportError:
    REPLAY_SUCCESS = None

def es_health_ok() -> bool:
    """Check Elasticsearch cluster health."""
    try:
        import requests
        resp = requests.get(f"{ES_URL}/_cluster/health", timeout=5)
        return resp.status_code == 200 and resp.json().get("status") in ("green", "yellow")
    except Exception:
        return False

def bulk_with_backoff(batch: list, es_client) -> int:
    """Bulk index with exponential backoff."""
    from elasticsearch import helpers
    
    for attempt in range(5):
        if not es_health_ok():
            wait = 2 ** attempt
            logger.warning(f"ES unhealthy, waiting {wait}s...")
            time.sleep(wait)
            continue
        
        try:
            success, _ = helpers.bulk(
                es_client, batch,
                raise_on_error=False,
                request_timeout=30
            )
            if REPLAY_SUCCESS:
                REPLAY_SUCCESS.labels(status="success").inc(success)
            return success
        except Exception as e:
            logger.error(f"Bulk failed: {e}")
            time.sleep(2 ** attempt)
    
    if REPLAY_SUCCESS:
        REPLAY_SUCCESS.labels(status="failed").inc(len(batch))
    return 0

def replay_file(file: Path, es_client):
    """Replay a single DLQ file with quarantine for bad lines."""
    quarantine = file.with_suffix(".quarantine")
    batch = []
    replayed = 0
    quarantined = 0
    
    logger.info(f"Replaying {file.name}...")
    
    with open(file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            try:
                doc = json.loads(line.strip())
                batch.append({
                    "_index": doc.get("_index", "fiber-logs-replay"),
                    "_source": doc.get("_source", doc)
                })
                
                if len(batch) >= BATCH_SIZE:
                    replayed += bulk_with_backoff(batch, es_client)
                    batch = []
                    time.sleep(DELAY_MS / 1000)
                    
            except json.JSONDecodeError as e:
                logger.warning(f"Quarantining line {line_num}: {e}")
                with open(quarantine, 'a') as q:
                    q.write(line)
                quarantined += 1
    
    # Final batch
    if batch:
        replayed += bulk_with_backoff(batch, es_client)
    
    logger.info(f"Replayed {replayed}, quarantined {quarantined}")
    
    # Delete original if successful
    if quarantined == 0:
        file.unlink()
        logger.info(f"Deleted {file.name}")

def cleanup_old_files():
    """Delete DLQ files older than retention period."""
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    for file in DLQ_DIR.glob("logs-*.ndjson"):
        # Parse date from filename: logs-2026-01-03.ndjson
        try:
            date_str = file.stem.replace("logs-", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            if file_date < cutoff:
                file.unlink()
                logger.info(f"Cleaned up old DLQ file: {file.name}")
        except ValueError:
            continue

def main():
    from elasticsearch import Elasticsearch
    
    if not DLQ_DIR.exists():
        logger.info(f"DLQ directory {DLQ_DIR} does not exist")
        return
    
    es = Elasticsearch(ES_URL, request_timeout=30)
    
    if not es.ping():
        logger.error("Cannot connect to Elasticsearch")
        sys.exit(1)
    
    # Cleanup old files first
    cleanup_old_files()
    
    # Replay in chronological order
    files = sorted(DLQ_DIR.glob("logs-*.ndjson"))
    if not files:
        logger.info("No DLQ files to replay")
        return
    
    logger.info(f"Found {len(files)} DLQ files to replay")
    
    for file in files:
        replay_file(file, es)
    
    logger.info("Replay complete")

if __name__ == "__main__":
    main()
