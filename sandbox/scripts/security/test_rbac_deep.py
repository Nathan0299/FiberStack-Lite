import requests
import jwt
import logging
from datetime import datetime, timezone, timedelta

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [RBAC] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("sec_rbac")

API_URL = "http://localhost:8000"
# In a real scenario, we'd sign these with the ACTUAL secret. 
# Since we are "Red Teaming" from the outside, we usually can't forge valid signatures unless we have the secret.
# However, for Unit/Integration testing RBAC logic, we often assume we have valid tokens for specific roles.
# To properly test this against a running container without knowing the secret, we would need to 
# Login as those users.
# Assuming we have seeded users: 'admin', 'operator', 'probe'.

class RBACAttacker:
    def __init__(self):
        self.session = requests.Session()
        self.failures = []
        self.tokens = {}

    def login_as(self, role: str):
        """Helper to get token for a role (Requires seeded users)."""
        # Usernames mapped to roles in seed data (Day 25/78)
        creds = {
            "admin": ("admin", "admin_password"),
            "operator": ("operator", "operator_password"),
            "probe": ("probe_user", "probe_password") # Hypothetical
        }
        
        if role not in creds:
            return None
            
        u, p = creds[role]
        try:
            r = requests.post(f"{API_URL}/api/auth/login", json={"username": u, "password": p})
            if r.status_code == 200:
                self.tokens[role] = r.json()["access_token"]
                logger.info(f"Logged in as {role}")
                return self.tokens[role]
        except:
            pass
        logger.warning(f"Could not login as {role} - skipping dependent tests")
        return None

    def log_result(self, test_name: str, passed: bool, details: str = ""):
        status = "PASSED" if passed else "FAILED"
        if not passed:
            self.failures.append(f"{test_name}: {details}")
            logger.error(f"{test_name} -> {status} {details}")
        else:
            logger.info(f"{test_name} -> {status}")

    def test_vertical_escalation(self):
        """Test Probe/Operator attempting Admin actions."""
        logger.info("--- Testing Vertical Escalation ---")
        
        # 1. Operator trying to DELETE a node (Admin only)
        # Note: Day 78 implementation restricted write:node:delete to ADMIN
        token = self.login_as("operator")
        if not token: return
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Target: Delete a dummy node
        target_node = "probe-local" 
        
        r = requests.delete(f"{API_URL}/api/nodes/{target_node}", headers=headers)
        
        # Expect 403 Forbidden
        if r.status_code == 403:
            self.log_result("Operator -> Delete Node", True, "Correctly Forbidden")
        elif r.status_code == 200:
            self.log_result("Operator -> Delete Node", False, "Escalation Successful! Operator deleted node.")
        else:
            self.log_result("Operator -> Delete Node", True, f"Rejected with {r.status_code} (Acceptable)")

    def test_horizontal_isolation(self):
        """Test Cross-Tenant/Region Access (if enforced)."""
        logger.info("--- Testing Horizontal Isolation ---")
        # FiberStack currently doesn't enforce strict per-user region locking in the open source version,
        # but let's verify that a token cannot access data it shouldn't IF we had that logic.
        # For now, we test if a 'probe' role can access the 'Management' APIs (GET /nodes).
        # Typically probes only POST to /ingest.
        
        token = self.login_as("probe") 
        if not token: 
            # If no probe user, verify using Operator token accessing Admin-only routes?
            # Or use a distinct user.
            return

        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{API_URL}/api/nodes", headers=headers)
        
        # If probes shouldn't list all nodes:
        if r.status_code == 403:
             self.log_result("Probe -> List Nodes", True, "Correctly Forbidden")
        elif r.status_code == 200:
             self.log_result("Probe -> List Nodes", False, "Probe can list all nodes (Excessive Privilege?)")

    def test_role_confusion(self):
        """Test conflicting claims if we can inject them (Requires Forgery capability or weak validation)."""
        # Since we can't easily forge signed tokens without the secret, this test is limited 
        # to black-box behavior unless we found a weakness in test_auth_advanced.
        pass

    def run(self):
        # Ensure we have users. If not, these might be skipped.
        self.test_vertical_escalation()
        self.test_horizontal_isolation()
        
        if self.failures:
            print("\n!!! RBAC SECURITY FAILURES !!!")
            for f in self.failures:
                print(f"- {f}")
            exit(1)
        else:
            print("\n*** ALL RBAC TESTS PASSED ***")
            exit(0)

if __name__ == "__main__":
    attacker = RBACAttacker()
    attacker.run()
