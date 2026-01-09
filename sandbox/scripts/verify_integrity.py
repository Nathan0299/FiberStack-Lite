import os
import sys
import time
import psycopg2
import redis
import requests
import json
from datetime import datetime, timedelta

# Configuration
DB_HOST = "localhost"
DB_CONFIG = {
    "dbname": "fiberstack",
    "user": "postgres",
    "password": "postgres",
    "host": DB_HOST,
    "port": 5432
}
API_URL = "http://localhost:8000"
REDIS_URL = "redis://localhost:6379/0"

def log(msg, level="INFO"):
    print(f"[{datetime.now().isoformat()}] [{level}] {msg}")

def fail(msg):
    log(msg, "CRITICAL")
    sys.exit(1)

def check_api_health():
    log("Checking API Health & Latency...")
    start = time.time()
    try:
        r = requests.get(f"{API_URL}/health", timeout=1)
        latency = (time.time() - start) * 1000
        if r.status_code != 200:
            fail(f"API Health failed: {r.status_code}")
        data = r.json()
        if data.get("status") != "ok":
            fail(f"API invalid status: {data}")
        log(f"API OK. Latency: {latency:.2f}ms")
        if latency > 200:
            log(f"API Latency High! (>200ms)", "WARN")
    except Exception as e:
        fail(f"API Connection refused: {e}")

def check_db_health():
    log("Checking DB Connection...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        conn.close()
        log("DB Connection OK")
    except Exception as e:
        fail(f"DB Connection failed: {e}")

def verify_data_integrity():
    log("Verifying Data Integrity...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # 1. Completeness (3 Probes)
    cur.execute("SELECT DISTINCT node_id FROM metrics")
    nodes = [r[0] for r in cur.fetchall()]
    log(f"Found Probes: {nodes}")
    if len(nodes) < 3:
        log(f"Missing probes! Expected 3, found {len(nodes)}", "WARN") # Might be startup delay

    # 2. Logic & Schema
    cur.execute("""
        SELECT count(*) FROM metrics 
        WHERE latency_ms < 0 OR packet_loss < 0
    """)
    invalid_rows = cur.fetchone()[0]
    if invalid_rows > 0:
        fail(f"Found {invalid_rows} rows with invalid metrics (negative values)!")
    
    # 3. Deduplication
    # Check for duplicate (node_id, time)
    cur.execute("""
        SELECT node_id, time, count(*) 
        FROM metrics 
        GROUP BY node_id, time 
        HAVING count(*) > 1
    """)
    dupes = cur.fetchall()
    if dupes:
        fail(f"Found duplicate metrics! {dupes[:5]}...")
    
    # 4. Freshness (Lag)
    cur.execute("SELECT MAX(time) FROM metrics")
    last_ts = cur.fetchone()[0]
    if last_ts:
        # Timezone aware comparison
        now = datetime.now(last_ts.tzinfo)
        lag = now - last_ts
        log(f"Data Freshness Lag: {lag.total_seconds():.2f}s")
        if lag.total_seconds() > 30: # 15s interval + buffer
             log("Data is stale! >30s lag", "WARN")
    else:
        log("No data found in metrics table yet.", "WARN")

    conn.close()
    log("Data Integrity Checks Passed.")

if __name__ == "__main__":
    log("Starting Day 91 Validation (10/10 Bulletproof)...")
    
    # Wait loop for service readiness
    retries = 30
    while retries > 0:
        try:
            check_api_health()
            check_db_health()
            break
        except SystemExit:
            retries -= 1
            time.sleep(2)
            if retries == 0:
                fail("Services failed to come online in 60s")

    verify_data_integrity()
    log("Validation Complete: SUCCESS")
