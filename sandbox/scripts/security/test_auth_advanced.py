import requests
import jwt
import asyncio
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [AUTH] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("sec_auth")

API_URL = "http://localhost:8000"
# Matches sandbox_secret or whatever is configured in local dev
FEDERATION_SECRET = "sandbox_secret" 
JWT_SECRET_DEFAULT = "CHANGE-ME-IN-PRODUCTION-BUT-FAIL-IF-UNSET-IN-PROD"

class AuthAttacker:
    def __init__(self):
        self.session = requests.Session()
        self.failures = []

    def log_result(self, test_name: str, passed: bool, details: str = ""):
        status = "PASSED" if passed else "FAILED"
        if not passed:
            self.failures.append(f"{test_name}: {details}")
            logger.error(f"{test_name} -> {status} {details}")
        else:
            logger.info(f"{test_name} -> {status}")

    def test_alg_none(self):
        """Test vulnerability to 'alg': 'none' JWTs."""
        logger.info("--- Testing Alg=None Vulnerability ---")
        
        # Manually construct header/payload (PyJWT refuses to encode alg=none)
        import base64
        import json
        
        header_data = {"alg": "none", "typ": "JWT"}
        payload_data = {
            "sub": "admin",
            "role": "admin",
            "exp": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()
        }
        
        def b64url(d):
            return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=")
            
        token = f"{b64url(header_data).decode()}.{b64url(payload_data).decode()}."
        
        headers = {"Authorization": f"Bearer {token}"}
        try:
            # Target protected endpoint (/api/metrics or /api/nodes)
            r = requests.get(f"{API_URL}/api/nodes", headers=headers, timeout=10)
            
            # We expect 401 (Auth Failed) or 403 (Perms failed if user valid but role bad)
            # If 200, it means Auth accepted it -> VULNERABLE
            if r.status_code == 200:
                self.log_result("Alg=None Check", False, "API accepted unsigned 'none' algo token!")
            else:
                self.log_result("Alg=None Check", True, f"Rejected with {r.status_code}")
        except Exception as e:
            self.log_result("Alg=None Check", False, f"Request failed: {e}")

    def test_jwt_forgery_weak_secret(self):
        """Attempt to forge Admin token using default/weak secrets."""
        logger.info("--- Testing JWT Forgery (Weak Secret) ---")
        
        # Generate token signed with known default secret
        payload = {
            "sub": "hacker",
            "role": "admin",
            "permissions": ["all"],
            "exp": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp(),
            "iss": "fiber-api"
        }
        
        # Try signing with HS256 using default secret
        token = jwt.encode(payload, JWT_SECRET_DEFAULT, algorithm="HS256")
        
        headers = {"Authorization": f"Bearer {token}"}
        try:
            r = requests.delete(f"{API_URL}/api/nodes/probe-local", headers=headers, timeout=10)
            if r.status_code == 200:
                self.log_result("JWT Forgery", False, "API accepted forged token signed with default secret!")
            elif r.status_code == 404: 
                # If 404, it means auth passed but node not found -> Vulnerable
                self.log_result("JWT Forgery", False, "API accepted forged token (Got 404, implying Auth OK)")
            else:
                self.log_result("JWT Forgery", True, f"Rejected with {r.status_code}")
        except Exception as e:
            self.log_result("JWT Forgery", False, f"Exception: {e}")

    def test_replay_after_logout(self):
        """Test Token Replay: Use access token after Logout."""
        logger.info("--- Testing Token Replay after Logout ---")
        
        # 1. Login
        # Default creds in auth.py are admin:admin
        creds = {"username": "admin", "password": "admin"} 
        r = requests.post(f"{API_URL}/api/auth/login", json=creds)
        if r.status_code != 200:
            logger.warning(f"Skipping Replay Test: Login failed (Status {r.status_code})")
            return
            
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Verify Access
        r1 = requests.get(f"{API_URL}/api/nodes", headers=headers)
        if r1.status_code != 200:
            self.log_result("Replay Setup", False, f"Valid token failed (Status {r1.status_code})")
            return
            
        # 3. Logout
        requests.post(f"{API_URL}/api/auth/logout", headers=headers)
        
        # 4. Replay
        r2 = requests.get(f"{API_URL}/api/nodes", headers=headers)
        if r2.status_code == 200:
            self.log_result("Token Replay", False, "Token still valid after logout!")
        else:
            self.log_result("Token Replay", True, f"Correctly rejected with {r2.status_code}")

    def test_refresh_misuse(self):
        """Test reusing a Refresh Token (should be one-time use or rotate)."""
        logger.info("--- Testing Refresh Token Misuse ---")
        # Reuse flow needs implementation of Refresh endpoint in API (Day 78)
        # Login -> Get RT -> Refresh -> Get New RT -> Try reusing Old RT
        
        creds = {"username": "admin", "password": "admin_password"}
        r = requests.post(f"{API_URL}/api/auth/login", json=creds)
        if r.status_code != 200: return

        rt_1 = r.json()["refresh_token"]
        
        # Refresh 1
        r_ref1 = requests.post(f"{API_URL}/api/auth/refresh", json={"refresh_token": rt_1})
        if r_ref1.status_code != 200:
            self.log_result("Refresh Flow", False, "Failed to refresh token first time")
            return
            
        # Refresh 2 (Reuse RT_1)
        r_ref2 = requests.post(f"{API_URL}/api/auth/refresh", json={"refresh_token": rt_1})
        
        if r_ref2.status_code == 200:
            self.log_result("Refresh Reuse", False, "Review: Old Refresh Token was accepted again (Rotation missing?)")
            # Strictly speaking, if rotation is enforced, this applies.
        else:
            self.log_result("Refresh Reuse", True, f"Old RT rejected: {r_ref2.status_code}")

    def run(self):
        self.test_alg_none()
        self.test_jwt_forgery_weak_secret()
        self.test_replay_after_logout()
        self.test_refresh_misuse()
        
        if self.failures:
            print("\n!!! AUTH SECURITY FAILURES !!!")
            for f in self.failures:
                print(f"- {f}")
            exit(1)
        else:
            print("\n*** ALL AUTH TESTS PASSED ***")
            exit(0)

if __name__ == "__main__":
    attacker = AuthAttacker()
    attacker.run()
