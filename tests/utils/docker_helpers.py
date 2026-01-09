import subprocess
import time
from typing import Optional

def verify_db_record_exists(node_id: str, container_name="fiber-db", retries=10, delay=1) -> bool:
    """
    Verifies a metrics record exists in the DB container via docker exec.
    
    Args:
        node_id: The UUID to check for in the metrics table.
        container_name: Name of the DB container (default: fiber-db).
        retries: Number of retry attempts.
        delay: Delay between retries in seconds.
    """
    cmd = [
        "docker", "exec", container_name, 
        "psql", "-U", "postgres", "-d", "fiberstack", 
        "-t", "-c", 
        f"SELECT count(*) FROM metrics WHERE node_id = '{node_id}';"
    ]
    
    for _ in range(retries):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                count = res.stdout.strip()
                if count == "1":
                    return True
        except Exception:
            # Ignoring transient errors during retry loop
            pass
        time.sleep(delay)
    return False


def verify_alert_in_logs(node_id: str, severity: str = "warning", retries: int = 5) -> bool:
    """Check if an alert was fired in ETL logs."""
    cmd = [
        "docker", "logs", "dev-fiber-etl-1", "--tail", "200"
    ]
    for _ in range(retries):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            if f'"node_id": "{node_id}"' in res.stdout and f'"severity": "{severity}"' in res.stdout:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def get_redis_key(key: str, container_name: str = "dev-fiber-redis-1") -> Optional[str]:
    """Get a key from Redis."""
    cmd = ["docker", "exec", container_name, "redis-cli", "GET", key]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return res.stdout.strip() if res.returncode == 0 else None
    except Exception:
        return None
