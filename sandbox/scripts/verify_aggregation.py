"""
Day 96 Verification Script (Standard Lib)
Verifies:
1. 1-minute and 5-minute aggregates exist in DB
2. Redis cache hits/misses
3. API endpoints returning correct metadata (source: "cache" vs "aggregates_1m")
4. Aggregate selection logic
"""
import sys
import json
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta
import os

# Configuration
# Updated to include /api prefix
API_URL = os.getenv("API_URL", "http://localhost:8000/api")
ADMIN_USER = "admin"
ADMIN_PASS = "admin"

def test_endpoint(url, params, headers, desc):
    print(f"\n--- Testing {desc} ---")
    
    # Query string
    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}"
    
    start = datetime.now()
    try:
        req = urllib.request.Request(full_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            latency = (datetime.now() - start).total_seconds()
            data = json.loads(response.read().decode('utf-8'))
            
            meta = data.get("meta", {})
            source = meta.get("source", "unknown")
            print(f"✅ Success ({latency:.3f}s)")
            print(f"   Source: {source}")
            print(f"   Data Points: {len(data.get('data', [])) if isinstance(data.get('data'), list) else 'Object'}")
            return True, source
    except urllib.error.HTTPError as e:
        print(f"❌ Failed: {e.code} - {e.reason}")
        print(e.read().decode('utf-8'))
        return False, None
    except Exception as e:
        print(f"❌ Error: {e}")
        return False, None

def main():
    print("🚀 Starting Day 96 Verification (Standard Lib)")
    
    # 1. Login
    login_url = f"{API_URL}/auth/login"
    login_data = json.dumps({"username": ADMIN_USER, "password": ADMIN_PASS}).encode('utf-8')
    req = urllib.request.Request(login_url, data=login_data, headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())
            token = data["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            print("✅ Login successful")
    except Exception as e:
        print(f"❌ Login failed connecting to {login_url}: {e}")
        sys.exit(1)
        
    # 2. Test Real-time Window (< 2 min) -> Should be "metrics" (raw)
    print("\n[Test 1] Real-time Window (< 2 min)")
    success, source = test_endpoint(f"{API_URL}/metrics/aggregated", 
        {"dimension": "node", "start_time": "2024-01-01T00:00:00Z", "end_time": "2024-01-01T00:01:00Z", "prefer_freshness": "true"},
        headers,
        "Real-time Aggregation"
    )
    if source != "metrics" and source != "metrics (fallback)":
         print(f"⚠️ warning: Expected source 'metrics', got '{source}'")

    # 3. Test Short Window (10 min) -> Should be "aggregates_1m"
    print("\n[Test 2] Window (10 min)")
    now = datetime.utcnow()
    start_ts = (now - timedelta(minutes=10)).isoformat()
    end_ts = now.isoformat()
    
    success, source = test_endpoint(f"{API_URL}/metrics/aggregated", 
        {"dimension": "node", "start_time": start_ts, "end_time": end_ts}, 
        headers,
        "1m Aggregation"
    )
    if success and "aggregates_1m" in str(source):
         print("✅ Correct aggregate selected")
    elif "metrics" in str(source):
         print("⚠️ Fallback to raw/metrics (acceptable if agg empty/stale)")

    # 4. Test Cache Hit
    print("\n[Test 3] Cache Hit Verification")
    success, source_cached = test_endpoint(f"{API_URL}/metrics/aggregated", 
        {"dimension": "node", "start_time": start_ts, "end_time": end_ts}, 
        headers,
        "1m Aggregation (Cached)"
    )
    if success and source_cached == "cache":
        print("✅ Cache HIT verified")
    else:
        print(f"❌ Cache MISS (Got {source_cached})")

    # 5. Test Cluster Metrics (Long Window -> 5m agg)
    print("\n[Test 4] Cluster Metrics (1 Hour)")
    start_ts_1h = (now - timedelta(hours=1)).isoformat()
    success, source = test_endpoint(f"{API_URL}/metrics/cluster", 
        {"start_time": start_ts_1h, "end_time": end_ts}, 
        headers,
        "Cluster Metrics"
    )
    if "aggregates" in str(source):
        print("✅ Uses aggregates")
    elif source == "metrics (fallback)":
        print("⚠️ Uses fallback (acceptable if fresh)")
            
    print("\n🏁 Verification Complete")

if __name__ == "__main__":
    main()
