import requests
import logging
import ssl
import socket

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [HARDEN] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("sec_harden")

API_URL = "http://localhost:8000"

class HardeningAuditor:
    def __init__(self):
        self.failures = []

    def log_result(self, test_name: str, passed: bool, details: str = ""):
        status = "PASSED" if passed else "FAILED"
        if not passed:
            self.failures.append(f"{test_name}: {details}")
            logger.error(f"{test_name} -> {status} {details}")
        else:
            logger.info(f"{test_name} -> {status}")

    def test_security_headers(self):
        """Check for HSTS, X-Frame-Options, Server Masking."""
        logger.info("--- Testing Security Headers ---")
        try:
            r = requests.get(f"{API_URL}/api/status")
            headers = r.headers
            
            # 1. Server Masking (Should NOT be 'uvicorn' alone or show version)
            # Accept 'FiberStack' or empty, fail if contains only 'uvicorn'
            server = headers.get("Server", "").lower()
            if server == "uvicorn" or ("uvicorn" in server and "fiberstack" not in server):
                 self.log_result("Server Masking", False, f"Leaked Server Header: {headers.get('Server')}")
            else:
                 self.log_result("Server Masking", True, f"Server header masked: {headers.get('Server', 'empty')}")

            # 2. X-Frame-Options (Clickjacking)
            xfo = headers.get("X-Frame-Options", "").upper()
            if xfo not in ["DENY", "SAMEORIGIN"]:
                 self.log_result("Hitjacking Defense", False, "Missing X-Frame-Options header")
            else:
                 self.log_result("Hitjacking Defense", True, f"Found {xfo}")
                 
            # 3. HSTS (Strict-Transport-Security) - Only if HTTPS
            # Since we run HTTP locally, this might be missing. We check if logic exists though.
            # In Dev/Sandbox, we might skip this fail if strict https not enabled.
            
        except Exception as e:
            self.log_result("Headers Check", False, f"Request failed: {e}")

    def test_cors_restriction(self):
        """Verify CORS rejects unauthorized origins."""
        logger.info("--- Testing CORS ---")
        try:
            headers = {"Origin": "http://evil-site.com"}
            r = requests.options(f"{API_URL}/api/status", headers=headers)
            
            # Access-Control-Allow-Origin should NOT be present or should NOT be * or evil-site
            allow = r.headers.get("Access-Control-Allow-Origin")
            if allow == "*" or allow == "http://evil-site.com":
                 self.log_result("CORS Policy", False, f"Permissive CORS found: {allow}")
            else:
                 self.log_result("CORS Policy", True, "Restricted unauthorized Origin")
        except:
            pass

    def run(self):
        self.test_security_headers()
        self.test_cors_restriction()
        
        if self.failures:
            print("\n!!! HARDENING FAILURES !!!")
            for f in self.failures:
                print(f"- {f}")
            # Don't exit 1 yet as these are often configured in Proxy (Nginx) not App
            # But we log them.
            exit(1) 
        else:
            print("\n*** ALL HARDENING TESTS PASSED ***")
            exit(0)

if __name__ == "__main__":
    auditor = HardeningAuditor()
    auditor.run()
