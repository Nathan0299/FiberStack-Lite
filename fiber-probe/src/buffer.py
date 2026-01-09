"""
Day 97: Durable SQLite Buffer
Replaces Redis buffer with local disk-backed FIFO queue to survive host crashes.
"""
import sqlite3
import json
import logging
import os
import time
from typing import List, Dict, Any, Optional

logger = logging.getLogger("fiber-probe.buffer")

class DurableBuffer:
    """
    SQLite-backed FIFO queue for metrics.
    Features:
    - WAL mode for performance/consistency
    - Byte-size quota enforcement
    - FIFO ordering (id ASC)
    - Thread-safe (sqlite3 serialized mode handling)
    """

    def __init__(self, db_path: str, max_size_bytes: int = 100 * 1024 * 1024):
        self.db_path = db_path
        self.max_size = max_size_bytes
        self._init_db()

    def _init_db(self):
        """Initialize DB with WAL mode."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        # Performance tuning
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at REAL DEFAULT (unixepoch())
            )
        """)
        self.conn.commit()
        logger.info(f"Initialized DurableBuffer at {self.db_path}")

    def push(self, metric: Dict[str, Any]) -> bool:
        """Push metric to queue. Returns False if quota exceeded (and drops oldest)."""
        try:
            payload = json.dumps(metric)
            size = len(payload)
            
            # Check quota
            current_size = self._get_size()
            if current_size + size > self.max_size:
                logger.warning(f"Buffer full ({current_size}/{self.max_size} bytes). Dropping oldest.")
                self._drop_oldest()
            
            self.conn.execute("INSERT INTO queue (payload, size_bytes) VALUES (?, ?)", (payload, size))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Buffer push failed: {e}")
            return False

    def pop_batch(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Pop batch of metrics (destructive read)."""
        try:
            cur = self.conn.execute("SELECT id, payload FROM queue ORDER BY id ASC LIMIT ?", (limit,))
            rows = cur.fetchall()
            
            if not rows:
                return []
            
            ids = [r['id'] for r in rows]
            metrics = []
            for r in rows:
                try:
                    metrics.append(json.loads(r['payload']))
                except json.JSONDecodeError:
                    logger.error(f"Corrupt payload in buffer id={r['id']}")
            
            # Delete processed
            placeholders = ','.join('?' * len(ids))
            self.conn.execute(f"DELETE FROM queue WHERE id IN ({placeholders})", ids)
            self.conn.commit()
            
            return metrics
        except Exception as e:
            logger.error(f"Buffer pop failed: {e}")
            return []

    def peek_batch(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Peek batch returning (id, payload) for ACK safety."""
        try:
            cur = self.conn.execute("SELECT id, payload FROM queue ORDER BY id ASC LIMIT ?", (limit,))
            rows = cur.fetchall()
            results = []
            for r in rows:
                try:
                    data = json.loads(r['payload'])
                    results.append({"_id": r['id'], "data": data})
                except json.JSONDecodeError:
                    # Auto-delete corrupt
                    self.conn.execute("DELETE FROM queue WHERE id = ?", (r['id'],))
                    self.conn.commit()
            return results
        except Exception as e:
            logger.error(f"Buffer peek failed: {e}")
            return []

    def acknowledge(self, ids: List[int]):
        """Delete acknowledged metrics."""
        if not ids: return
        try:
            placeholders = ','.join('?' * len(ids))
            self.conn.execute(f"DELETE FROM queue WHERE id IN ({placeholders})", ids)
            self.conn.commit()
        except Exception as e:
            logger.error(f"Buffer ack failed: {e}")

    def depth(self) -> int:
        """Get item count."""
        try:
            return self.conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
        except Exception:
            return 0

    def _get_size(self) -> int:
        """Get total bytes used by payloads."""
        try:
            res = self.conn.execute("SELECT SUM(size_bytes) FROM queue").fetchone()[0]
            return res if res else 0
        except Exception:
            return 0

    def _drop_oldest(self):
        """Eviction policy."""
        try:
            # Drop 10% of oldest items to make space
            self.conn.execute("""
                DELETE FROM queue WHERE id IN (
                    SELECT id FROM queue ORDER BY id ASC LIMIT (SELECT COUNT(*)/10 FROM queue)
                )
            """)
            self.conn.commit()
        except Exception as e:
            logger.error(f"Eviction failed: {e}")

    def close(self):
        self.conn.close()
