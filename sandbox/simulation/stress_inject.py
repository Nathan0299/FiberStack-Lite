#!/usr/bin/env python3
"""
Day 70: Stress Injection Script

Injects synthetic metrics to test alert triggering and dashboard updates.

Usage:
    python stress_inject.py --mode high_latency --node probe-accra-01 --duration 300
    python stress_inject.py --mode dual_spike
    python stress_inject.py --mode dedup_test
"""

import argparse
import requests
import time
import uuid
import json
import os
import random
from datetime import datetime, timezone

API_URL = os.getenv("API_URL", "http://localhost:8000")
TOKEN = os.getenv("FEDERATION_TOKEN", os.getenv("FEDERATION_SECRET", "sandbox_secret"))

def send_batch(node_id: str, country: str, region: str, latency: float, loss: float, uptime: float = 99.0):
    """Send a batch of metrics to the API."""
    batch_id = str(uuid.uuid4())
    payload = {
        "node_id": node_id,
        "metrics": [{
            "node_id": node_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "country": country,
            "region": region,
            "latency_ms": latency,
            "packet_loss": loss,
            "uptime_pct": uptime,
            "metadata": {"stress_injection": True, "batch_id": batch_id}
        }]
    }
    
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "X-Batch-ID": batch_id,
        "X-Region-ID": f"{country.lower()}-{region.lower()}"
    }
    
    try:
        resp = requests.post(f"{API_URL}/api/ingest", json=payload, headers=headers, timeout=10)
        print(f"[{datetime.now().isoformat()}] {node_id}: latency={latency}ms, loss={loss}% -> {resp.status_code}")
        return resp.status_code == 202
    except Exception as e:
        print(f"[ERROR] {node_id}: {e}")
        return False

def run_high_latency(node_id: str, country: str, region: str, duration: int):
    """Inject high latency metrics."""
    print(f"=== HIGH LATENCY: {node_id} for {duration}s ===")
    end_time = time.time() + duration
    while time.time() < end_time:
        latency = random.uniform(150, 200)
        send_batch(node_id, country, region, latency, 0.1)
        time.sleep(15)

def run_packet_loss(node_id: str, country: str, region: str, duration: int):
    """Inject packet loss metrics."""
    print(f"=== PACKET LOSS: {node_id} for {duration}s ===")
    end_time = time.time() + duration
    while time.time() < end_time:
        loss = random.uniform(2.5, 5.0)
        send_batch(node_id, country, region, 40, loss)
        time.sleep(15)

def run_dual_spike(duration: int = 300):
    """Compound: Dual region spike (GH latency + NG loss)."""
    print(f"=== DUAL SPIKE: GH + NG for {duration}s ===")
    end_time = time.time() + duration
    while time.time() < end_time:
        # GH: high latency
        send_batch("probe-accra-01", "GH", "Accra", random.uniform(170, 200), 0.1)
        # NG: high loss
        send_batch("probe-lagos-01", "NG", "Lagos", 40, random.uniform(2.5, 4.0))
        time.sleep(15)

def run_dedup_test():
    """Inject same spike twice within 3 minutes."""
    print("=== DEDUP TEST: Same spike at T=0 and T=3min ===")
    # First spike
    for _ in range(3):
        send_batch("probe-accra-01", "GH", "Accra", 180, 0.1)
        time.sleep(15)
    
    print("Waiting 3 minutes...")
    time.sleep(180)
    
    # Second spike (should not trigger new notification)
    for _ in range(3):
        send_batch("probe-accra-01", "GH", "Accra", 180, 0.1)
        time.sleep(15)
    
    print("Check: Only 1 Slack notification should exist")

def run_partial_failure(duration: int = 360):
    """Probe sends heartbeat only (no latency/loss values)."""
    print(f"=== PARTIAL FAILURE: KE heartbeat only for {duration}s ===")
    print("(Simulated by not sending metrics - Node Down should fire)")
    print(f"Stop probe-ke and wait {duration}s...")
    time.sleep(duration)
    print("Check: Node Down alert should fire for probe-nairobi-01")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stress Injection")
    parser.add_argument("--mode", choices=["high_latency", "packet_loss", "dual_spike", "dedup_test", "partial_failure"], required=True)
    parser.add_argument("--node", default="probe-accra-01")
    parser.add_argument("--country", default="GH")
    parser.add_argument("--region", default="Accra")
    parser.add_argument("--duration", type=int, default=300)
    
    args = parser.parse_args()
    
    if args.mode == "high_latency":
        run_high_latency(args.node, args.country, args.region, args.duration)
    elif args.mode == "packet_loss":
        run_packet_loss(args.node, args.country, args.region, args.duration)
    elif args.mode == "dual_spike":
        run_dual_spike(args.duration)
    elif args.mode == "dedup_test":
        run_dedup_test()
    elif args.mode == "partial_failure":
        run_partial_failure(args.duration)
    
    print("=== STRESS INJECTION COMPLETE ===")
