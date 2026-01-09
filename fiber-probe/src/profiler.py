"""
Fiber-Probe Resource Profiler

Long-run profiling with Prometheus metrics export.
Tracks: RSS, GC, FDs, threads, TLS errors, retries.
"""

import asyncio
import gc
import os
import psutil
import time
from collections import deque
from prometheus_client import start_http_server, Gauge, Counter, Histogram, Info

# === PROMETHEUS METRICS ===
METRICS_PORT = int(os.getenv("METRICS_PORT", "9100"))

# Memory
MEMORY_RSS = Gauge('probe_memory_rss_bytes', 'Resident Set Size in bytes')
MEMORY_VMS = Gauge('probe_memory_vms_bytes', 'Virtual Memory Size in bytes')
GC_COLLECTIONS = Counter('probe_gc_collections_total', 'GC collections', ['generation'])

# CPU
CPU_PERCENT = Gauge('probe_cpu_percent', 'CPU usage percentage')
CPU_USER_TIME = Gauge('probe_cpu_user_seconds', 'CPU user time in seconds')
CPU_SYSTEM_TIME = Gauge('probe_cpu_system_seconds', 'CPU system time in seconds')

# File Descriptors
FD_COUNT = Gauge('probe_open_fds', 'Number of open file descriptors')

# Threads
THREAD_COUNT = Gauge('probe_threads', 'Number of threads')
ASYNCIO_TASKS = Gauge('probe_asyncio_tasks', 'Number of asyncio tasks')

# Network
PAYLOAD_SIZE = Histogram('probe_payload_bytes', 'Payload size in bytes', buckets=[100, 200, 400, 600, 800, 1000, 2000])
RETRIES_TOTAL = Counter('probe_retries_total', 'Total retry attempts')
TLS_ERRORS = Counter('probe_tls_errors_total', 'TLS errors by reason', ['reason'])

# Circuit Breaker
CIRCUIT_OPEN = Gauge('probe_circuit_breaker_open', '1 if circuit breaker is open')

# Backpressure
BACKPRESSURE_ACTIVE = Gauge('probe_backpressure_active', '1 if backpressure is active')

# Info
PROBE_INFO = Info('probe', 'Probe information')


class ResourceProfiler:
    """Collects and exports resource metrics."""
    
    def __init__(self, node_id: str, lean_mode: bool = False):
        self.node_id = node_id
        self.lean_mode = lean_mode
        self.process = psutil.Process()
        self._gc_baseline = self._get_gc_stats()
        
        PROBE_INFO.info({
            'node_id': node_id,
            'lean_mode': str(lean_mode),
            'pid': str(os.getpid())
        })
    
    def _get_gc_stats(self):
        """Get current GC collection counts."""
        return [s['collections'] for s in gc.get_stats()]
    
    def collect(self):
        """Collect all resource metrics."""
        # Memory
        mem = self.process.memory_info()
        MEMORY_RSS.set(mem.rss)
        MEMORY_VMS.set(mem.vms)
        
        # GC
        current_gc = self._get_gc_stats()
        for gen, (current, baseline) in enumerate(zip(current_gc, self._gc_baseline)):
            delta = current - baseline
            if delta > 0:
                GC_COLLECTIONS.labels(generation=str(gen)).inc(delta)
        self._gc_baseline = current_gc
        
        # CPU
        cpu_times = self.process.cpu_times()
        CPU_PERCENT.set(self.process.cpu_percent())
        CPU_USER_TIME.set(cpu_times.user)
        CPU_SYSTEM_TIME.set(cpu_times.system)
        
        # FDs
        try:
            FD_COUNT.set(self.process.num_fds())
        except Exception:
            FD_COUNT.set(len(self.process.open_files()))
        
        # Threads
        THREAD_COUNT.set(self.process.num_threads())
        
        # Asyncio tasks
        try:
            loop = asyncio.get_running_loop()
            ASYNCIO_TASKS.set(len(asyncio.all_tasks(loop)))
        except RuntimeError:
            pass
    
    def record_payload(self, size_bytes: int):
        """Record payload size."""
        PAYLOAD_SIZE.observe(size_bytes)
    
    def record_retry(self):
        """Record a retry attempt."""
        RETRIES_TOTAL.inc()
    
    def record_tls_error(self, reason: str):
        """Record TLS error with labeled reason."""
        TLS_ERRORS.labels(reason=reason).inc()
    
    def set_circuit_status(self, is_open: bool):
        """Set circuit breaker status."""
        CIRCUIT_OPEN.set(1 if is_open else 0)
    
    def set_backpressure(self, active: bool):
        """Set backpressure status."""
        BACKPRESSURE_ACTIVE.set(1 if active else 0)
    
    def get_memory_percent(self, cgroup_limit_bytes: int = None):
        """Get memory usage as percentage of limit."""
        rss = self.process.memory_info().rss
        if cgroup_limit_bytes:
            return (rss / cgroup_limit_bytes) * 100
        # Fallback to system memory
        return self.process.memory_percent()


def start_metrics_server():
    """Start Prometheus metrics HTTP server."""
    start_http_server(METRICS_PORT)
    print(f"Prometheus metrics available at http://0.0.0.0:{METRICS_PORT}/metrics")


if __name__ == "__main__":
    # Standalone profiler for testing
    import time
    
    start_metrics_server()
    profiler = ResourceProfiler("test-node", lean_mode=False)
    
    print("Profiler running. Collecting metrics every 5s...")
    while True:
        profiler.collect()
        time.sleep(5)
