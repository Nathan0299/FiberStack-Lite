import requests
import json
from datetime import datetime

def main():
    sample = {
        "node_id": "SANDBOX-TEST",
        "country": "Sandbox",
        "region": "Local",
        "latency_ms": 15.4,
        "uptime_pct": 99.9,
        "packet_loss": 0.0,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    try:
        r = requests.post("http://localhost:8081/api/push", json=sample)
        print("Probe Push:", r.status_code, r.text)
    except Exception as e:
        print("Probe Push: FAILED", e)

if __name__ == "__main__":
    main()
