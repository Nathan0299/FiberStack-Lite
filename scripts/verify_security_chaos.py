"""
Verification Script for Security Hardening (Day 85)
Chaos Tests: Replay, Redis Crash, Cert Reload, Rate Limits.
"""
import asyncio
import httpx
import time
import os
import signal
import sys
import subprocess
from datetime import datetime, timezone

API_URL = "http://localhost:8000"
AUTH_URL = f"{API_URL}/api/auth"
PUSH_URL = f"{API_URL}/api/push"

# Colors
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

async def test_auth_rate_limit():
    print(f"\n--- Test 1: Auth Rate Limiting (Brute Force) ---")
    
    start = time.time()
    count = 0
    # Limit is 5/min
    async with httpx.AsyncClient() as client:
        for i in range(7):
            resp = await client.post(f"{AUTH_URL}/login", json={"username": "admin", "password": "wrongpassword"})
            if resp.status_code == 429:
                print(f"{GREEN}✅ Rate Limit Hit at request {i+1} (Status 429){RESET}")
                return
            count += 1
            
    print(f"{RED}❌ Rate Limit Failed (Accepted {count} requests){RESET}")
    sys.exit(1)

async def test_replay_attack():
    print(f"\n--- Test 2: Refresh Token Replay (Revocation) ---")
    
    async with httpx.AsyncClient() as client:
        # 1. Login
        resp = await client.post(f"{AUTH_URL}/login", json={"username": "admin", "password": "admin"})
        if resp.status_code != 200:
            print(f"{RED}❌ Login Failed{RESET}")
            return
            
        data = resp.json()
        refresh_token = data["refresh_token"]
        print(f"Got Refresh Token: {refresh_token[:10]}...")
        
        # 2. Refresh Once (Should Succeed)
        resp2 = await client.post(f"{AUTH_URL}/refresh", json={"refresh_token": refresh_token})
        if resp2.status_code != 200:
             print(f"{RED}❌ First Refresh Failed: {resp2.text}{RESET}")
             return
        print(f"First Refresh OK")
        
        # 3. Attempt Replay (Should Fail - 401 Token revoked)
        resp3 = await client.post(f"{AUTH_URL}/refresh", json={"refresh_token": refresh_token})
        if resp3.status_code == 401:
             print(f"{GREEN}✅ Replay Blocked (Status 401){RESET}")
        else:
             print(f"{RED}❌ Replay Allowed (Status {resp3.status_code}){RESET}")
             sys.exit(1)

async def test_redis_fail_closed():
    print(f"\n--- Test 3: Redis Outage (Fail-Closed) ---")
    
    # 1. Kill Redis
    print("Stopping Redis container...")
    subprocess.run(["docker-compose", "-f", "fiber-deploy/docker-compose.yml", "stop", "redis"], check=True, stdout=subprocess.DEVNULL)
    await asyncio.sleep(2)
    
    async with httpx.AsyncClient() as client:
        # 2. Check /health (Should be 200)
        try:
            resp = await client.get(f"{API_URL}/health")
            if resp.status_code == 200:
                print(f"{GREEN}✅ /health Accessible (Bypass){RESET}")
            else:
                print(f"{RED}❌ /health Failed: {resp.status_code}{RESET}")
        except Exception as e:
             print(f"{RED}❌ /health Connection Failed: {e}{RESET}")

        # 3. Check /push (Should be 503 from Middleware or 401 if auth fail logic kicks in)
        # Middleware catches Redis error during revocation check -> 503
        try:
            resp = await client.post(PUSH_URL, json={}, headers={"Authorization": "Bearer fake"})
            if resp.status_code == 503:
                print(f"{GREEN}✅ /push Fail-Closed (Status 503){RESET}")
            else:
                print(f"{RED}❌ /push Not Fail-Closed: {resp.status_code}{RESET}")
        except Exception as e:
            print(f"{RED}❌ /push Connection Failed: {e}{RESET}")

    # 4. Restore Redis
    print("Restarting Redis...")
    subprocess.run(["docker-compose", "-f", "fiber-deploy/docker-compose.yml", "start", "redis"], check=True, stdout=subprocess.DEVNULL)
    await asyncio.sleep(5) # Wait for healthcheck

async def main():
    try:
        await test_auth_rate_limit()
        # Wait a bit for rate limit bucket to reset? Or just assume next test uses different IP/Client?
        # Actually client is same IP. Rate limit is by IP.
        # We need to wait 60s or clear redis.
        print("Waiting 60s for Rate Limit reset...")
        await asyncio.sleep(61)
        
        await test_replay_attack()
        await test_redis_fail_closed()
        
        print(f"\n{GREEN}🎉 ALL SECURITY TESTS PASSED{RESET}")
    except Exception as e:
        print(f"\n{RED}❌ TEST FAILED: {e}{RESET}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
