import requests
import redis
import psycopg2
import sys
import os

def check(name, func):
    try:
        func()
        print(f"✅ {name}: PASS")
    except Exception as e:
        print(f"❌ {name}: FAIL - {e}")
        # Build resilience: Don't exit immediately, let other checks run? 
        # For now, simplistic exit is fine, or we can collect failures.
        # Let's collect failures to see full picture.
        return False
    return True

def check_open_network():
    env = os.getenv("ENV", "dev")
    print(f"   Detected ENV: {env}")

    # Hostname mapping based on environment
    if env == "sandbox":
        timescale_host = "timescale"
        es_host = "elasticsearch"
        dashboard_host = "fiber-dashboard" # Service name in sandbox compose
    else:
        # Standard fiber-deploy compose
        timescale_host = "timescaledb"
        es_host = None # Not in standard compose yet
        dashboard_host = "fiber-dashboard"

    success = True

    # 1. API itself
    print("   Checking API (localhost:8000)...")
    if not check("API", lambda: requests.get("http://localhost:8000/api/status").raise_for_status()): success = False
    
    # 2. Redis
    print("   Checking Redis (redis:6379)...")
    r = redis.Redis(host="redis", port=6379, db=0)
    if not check("Redis", lambda: r.ping() or True): success = False

    # 3. TimescaleDB
    print(f"   Checking TimescaleDB ({timescale_host}:5432)...")
    def check_db():
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "fiberstack"), 
            user=os.getenv("DB_USER", "postgres"), 
            password=os.getenv("DB_PASS", "postgres"), 
            host=timescale_host
        )
        conn.close()
    if not check("TimescaleDB", check_db): success = False

    # 4. Elasticsearch (Conditional)
    if es_host:
        print(f"   Checking Elasticsearch ({es_host}:9200)...")
        if not check("Elasticsearch", lambda: requests.get(f"http://{es_host}:9200/_cluster/health").raise_for_status()): success = False
    else:
        print("   Skipping Elasticsearch (not configured for this env)")

    # 5. Dashboard
    print(f"   Checking Dashboard ({dashboard_host}:3000)...")
    if not check("Dashboard", lambda: requests.get(f"http://{dashboard_host}:3000").raise_for_status()): success = False

    if not success:
        print("\n❌ SOME CHECKS FAILED")
        sys.exit(1)

if __name__ == "__main__":
    print("\nStarting Internal Connectivity Checks...")
    check("Network Connectivity", check_open_network)
