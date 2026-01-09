"""Event-oriented logging to Elasticsearch."""
import os
import time
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional
from elasticsearch import Elasticsearch, helpers
from elasticsearch import exceptions as es_exceptions

logger = logging.getLogger("fiber-etl.events")

ES_URL = os.getenv("ELASTIC_URL", "http://localhost:9200")
ES_INDEX_PREFIX = os.getenv("ES_INDEX_PREFIX", "fiber-events")
ES_ENABLED = os.getenv("ES_ENABLED", "true").lower() == "true"
ES_BULK_SIZE = int(os.getenv("ES_BULK_SIZE", "50"))


class EventLogger:
    """Event logger with bulk indexing and graceful degradation."""
    
    def __init__(self, url: str = ES_URL, enabled: bool = ES_ENABLED):
        self.enabled = enabled
        self.client: Optional[Elasticsearch] = None
        self._buffer: List[Dict] = []
        self._batch_id: Optional[str] = None
        
        if not enabled:
            logger.info("Elasticsearch disabled")
            return
        
        try:
            self.client = Elasticsearch(url, request_timeout=5)
            if self.client.ping():
                logger.info(f"Connected to Elasticsearch")
                self._ensure_template()
            else:
                self._disable("ping failed")
        except Exception as e:
            self._disable(str(e))
    
    def _disable(self, reason: str):
        logger.warning(f"ES disabled: {reason}")
        self.enabled = False
    
    def _ensure_template(self):
        """Create index template with proper mappings."""
        name = f"{ES_INDEX_PREFIX}-template"
        if self.client.indices.exists_index_template(name=name):
            return
        
        self.client.indices.put_index_template(
            name=name,
            body={
                "index_patterns": [f"{ES_INDEX_PREFIX}-*"],
                "template": {
                    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                    "mappings": {
                        "properties": {
                            "@timestamp": {"type": "date"},
                            "service": {"type": "keyword"},
                            "event_type": {"type": "keyword"},
                            "level": {"type": "keyword"},
                            "node_id": {"type": "keyword"},
                            "country": {"type": "keyword"},
                            "region": {"type": "keyword"},
                            "status": {"type": "keyword"},
                            "batch_id": {"type": "keyword"},
                            "processing_ms": {"type": "integer"},
                            "count": {"type": "integer"},
                            "message": {"type": "text"},
                            "summary": {"type": "flattened"}
                        }
                    }
                }
            }
        )
        logger.info(f"Created ES template: {name}")
    
    def _index_name(self) -> str:
        now = datetime.now(tz=None)
        return f"{ES_INDEX_PREFIX}-{now.year}.{now.month:02d}"
    
    def start_batch(self) -> str:
        """Start a new batch, return batch_id."""
        self._batch_id = str(uuid.uuid4())[:8]
        self._buffer = []
        self.log_event("batch_started", level="debug")
        return self._batch_id
    
    def log_event(self, event_type: str, level: str = "info", **kwargs):
        """Buffer an event for bulk indexing."""
        if not self.enabled:
            return
        
        event = {
            "_index": self._index_name(),
            "_source": {
                "@timestamp": datetime.now(tz=None).isoformat(),
                "service": "fiber-etl",
                "event_type": event_type,
                "level": level,
                "batch_id": self._batch_id,
                **kwargs
            }
        }
        self._buffer.append(event)
        
        # Auto-flush if buffer full
        if len(self._buffer) >= ES_BULK_SIZE:
            self.flush()
    
    def flush(self) -> int:
        """Bulk index all buffered events.
        
        INVARIANT: Event loss is acceptable under worker crash conditions.
        Best-effort delivery only. Use atexit for graceful shutdown.
        """
        if not self.enabled or not self._buffer:
            return 0
        
        try:
            start = time.time()
            success, _ = helpers.bulk(
                self.client,
                self._buffer,
                raise_on_error=False,
                request_timeout=10
            )
            elapsed_ms = int((time.time() - start) * 1000)
            
            # Detect slow ES (> 2 seconds is concerning)
            if elapsed_ms > 2000:
                logger.warning(f"ES bulk slow: {elapsed_ms}ms for {len(self._buffer)} events")
            
            count = len(self._buffer)
            self._buffer = []
            return success
        except es_exceptions.ConnectionError:
            self._disable("connection lost")
            return 0
        except Exception as e:
            logger.error(f"Bulk index failed: {e}")
            self._buffer = []
            return 0
    
    def close(self):
        """Close ES connection and reset singleton."""
        global _logger
        self.flush()
        if self.client:
            self.client.close()
        self.enabled = False
        self.client = None
        _logger = None


# Singleton
_logger: Optional[EventLogger] = None

def get_event_logger() -> EventLogger:
    global _logger
    if _logger is None:
        _logger = EventLogger()
        # Register flush on exit for graceful shutdown (defensive)
        import atexit
        def safe_flush():
            try:
                if _logger:
                    _logger.flush()
            except Exception:
                pass  # Suppress shutdown errors
        atexit.register(safe_flush)
    return _logger
