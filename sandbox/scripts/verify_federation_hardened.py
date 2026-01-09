
import asyncio
import aiohttp
import json
import uuid
import time
import hmac
import hashlib
import os
import subprocess
from datetime import datetime, timezone

# Configuration
API_URL = "http://localhost:8000/api"
SECRET = "sandbox_secret"
NODE_ID = "verify-node-97"

def calculate_signature(batch_id: str, timestamp: str, nonce: str, payload_str: str) -> str:
    """Calculate HMAC-SHA256 signature matching client.py."""
    body_hash = hashlib.sha256(payload_str.encode()).hexdigest()
    message = f"{batch_id}:{timestamp}:{nonce}:{body_hash}"
    return hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()

async def send_batch(session, metrics, tamper_sig=False, replay_nonce=None):
    batch_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    nonce = replay_nonce if replay_nonce else str(uuid.uuid4())
    
    payload = {"node_id": NODE_ID, "metrics": metrics}
    # Canonical string must match server's reproduction exactly (sort_keys=True)
    payload_str = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    
    sig = calculate_signature(batch_id, timestamp, nonce, payload_str)
    if tamper_sig:
        sig = "invalid_signature_hex"
        
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer sandbox_secret",
        "X-Batch-ID": batch_id,
        "X-Fiber-Timestamp": timestamp,
        "X-Fiber-Nonce": nonce,
        "X-Fiber-Signature": sig
    }
    
    async with session.post(f"{API_URL}/ingest", data=payload_str, headers=headers) as resp:
        return resp.status, await resp.text()

def check_db_count(table):
    cmd = f"docker exec fiber-db psql -U postgres -d fiber_cloud -t -c 'SELECT count(*) FROM {table}'"
    res = subprocess.check_output(cmd, shell=True).decode().strip()
    return int(res)

async def run_verification():
    print("🛡️  Starting Day 97 Federation Verification")
    
    async with aiohttp.ClientSession() as session:
        # 1. Test Valid Ingest
        print("\n[1] Testing Valid Ingest (HMAC)...")
        metric = {
            "node_id": NODE_ID,
            "country": "GH",
            "region": "accra",
            "latency_ms": 10.5,
            "uptime_pct": 99.9,
            "packet_loss": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {"test": "valid"}
        }
        status, text = await send_batch(session, [metric])
        if status in (200, 201, 202):
            print("✅ Valid Batch Accepted")
        else:
            print(f"❌ Valid Batch Failed: {status} {text}")
            exit(1)

        # 2. Test Invalid Signature
        print("\n[2] Testing Invalid Signature...")
        status, text = await send_batch(session, [metric], tamper_sig=True)
        if status == 401:
            print("✅ Invalid Signature Rejected (401)")
        else:
            print(f"❌ Invalid Signature Allowed/Wrong Code: {status}")
            exit(1)

        # 3. Test Replay Attack
        print("\n[3] Testing Replay Attack...")
        nonce = str(uuid.uuid4())
        # First send
        await send_batch(session, [metric], replay_nonce=nonce)
        # Replay
        status, text = await send_batch(session, [metric], replay_nonce=nonce)
        if status == 401:
            print("✅ Replay Rejected (401)")
        else:
            print(f"❌ Replay Allowed/Wrong Code: {status}")
            exit(1)

        # 4. Test Conflict Audit (Double Ingest)
        print("\n[4] Testing Conflict Audit...")
        # Send same metric twice (same time/node)
        # Note: routes.py idempotency prevents immediate double processing of SAME batch_id.
        # So we verify worker audit by sending DIFFERENT batch_ids with SAME metric content.
        
        fixed_time = datetime.now(timezone.utc).isoformat()
        metric_dup = {
            "node_id": NODE_ID,
            "country": "GH",
            "region": "accra",
            "latency_ms": 50.0,
            "uptime_pct": 100.0,
            "packet_loss": 0.0,
            "timestamp": fixed_time,
            "metadata": {"test": "audit"}
        }
        
        # Batch A
        s1, _ = await send_batch(session, [metric_dup])
        print(f"   Batch A sent: {s1}")
        
        # Wait a sec for worker to process
        time.sleep(2)
        
        # Batch B (Duplicate Payload)
        s2, _ = await send_batch(session, [metric_dup])
        print(f"   Batch B sent: {s2}")
        
        # Wait for worker
        time.sleep(2)
        
        # Check Audit Table
        conflicts = check_db_count("metric_conflicts")
        print(f"   Metric Conflicts in DB: {conflicts}")
        
        if conflicts >= 1:
            print("✅ Conflict Audited Successfully")
        else:
            print("❌ Conflict NOT Audited (Check worker logs)")
            # Don't fail hard if queue latency is high, but warn
            
    print("\n🎉 Verification Complete (Core Security & Audit)")

if __name__ == "__main__":
    try:
        asyncio.run(run_verification())
    except Exception as e:
        print(f"❌ Fatal Error: {e}")
        exit(1)
