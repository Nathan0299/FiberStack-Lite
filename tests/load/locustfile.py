from locust import HttpUser, task, between
import uuid
import random
from datetime import datetime, timezone
import requests
from gevent.lock import BoundedSemaphore

SHARED_TOKEN = None
TOKEN_LOCK = BoundedSemaphore()

class FiberUser(HttpUser):
    wait_time = between(0.01, 0.1)  # High throughput

    def on_start(self):
        global SHARED_TOKEN
        if not SHARED_TOKEN:
            with TOKEN_LOCK:
                if not SHARED_TOKEN:
                    try:
                        resp = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
                        if resp.status_code == 200:
                            SHARED_TOKEN = resp.json()["access_token"]
                            print("Logged in successfully (Singleton)")
                        else:
                            print(f"Login Failed: {resp.status_code}")
                    except Exception as e:
                        print(f"Login Error: {e}")
        
        if SHARED_TOKEN:
            self.client.headers.update({"Authorization": f"Bearer {SHARED_TOKEN}"})

    @task
    def push_metric(self):
        node_id = f"load-{uuid.uuid4().hex[:8]}"
        payload = {
            "node_id": node_id,
            "region": "LoadTest",
            "country": "US",
            "latency_ms": random.uniform(10, 500),
            "packet_loss": random.choice([0.0, 0.1, 1.5]),
            "uptime_pct": 99.9,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.client.post("/api/push", json=payload)
