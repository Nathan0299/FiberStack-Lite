import time
from typing import Dict, Any

class ETLMetrics:
    """
    Singleton-style metrics collector for ETL batches.
    """
    def __init__(self):
        self._start_time = 0
        self.rows_processed = 0
        self.rows_failed = 0
        self.active_probes = 0
        self.duplicate_count = 0

    def start_batch(self):
        self._start_time = time.time()
        self.rows_processed = 0
        self.rows_failed = 0
        self.active_probes = 0
        self.duplicate_count = 0

    def record_row(self, success: bool = True):
        if success:
            self.rows_processed += 1
        else:
            self.rows_failed += 1
            
    def record_duplicate(self):
        self.duplicate_count += 1
        
    def set_active_probes(self, count: int):
        self.active_probes = count

    def get_summary(self) -> Dict[str, Any]:
        duration_ms = int((time.time() - self._start_time) * 1000)
        return {
            "duration_ms": duration_ms,
            "rows_processed": self.rows_processed,
            "rows_failed": self.rows_failed,
            "duplicate_count": self.duplicate_count,
            "active_probes": self.active_probes,
            "error_rate": self._calculate_error_rate()
        }

    def _calculate_error_rate(self) -> float:
        total = self.rows_processed + self.rows_failed
        if total == 0:
            return 0.0
        return round(self.rows_failed / total, 4)
