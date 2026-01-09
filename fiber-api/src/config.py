"""
Configuration Module (Day 85)
Centralized config with file-based secret support (Docker/K8s compatible).
Fail-fast validation for critical secrets.
"""
import os
import sys
import logging
import ssl
from typing import Optional, List
from pathlib import Path

logger = logging.getLogger("fiber-api.config")

def get_secret(key: str, default: Optional[str] = None, required: bool = False) -> str:
    """
    Load secret from file (Docker/K8s) or environment.
    Priority:
    1. /run/secrets/{key_lower}
    2. Environment Variable {KEY}
    3. Default
    """
    # 1. Try Switch Secret File (Lower case usually)
    secret_path = Path(f"/run/secrets/{key.lower()}")
    if secret_path.exists():
        try:
            return secret_path.read_text().strip()
        except Exception as e:
            logger.warning(f"Failed to read secret file {secret_path}: {e}")
    
    # 2. Try Env
    val = os.getenv(key)
    if val is not None:
        return val
        
    # 3. Default
    if default is not None:
        return default
        
    if required:
         raise ValueError(f"CRITICAL: Missing required configuration for {key}")
         
    return "" # Default to empty string if not required and no default provided (legacy behavior precaution)

# --- Core Secrets ---
try:
    JWT_SECRET = get_secret("JWT_SECRET", required=True)
    FEDERATION_SECRET = get_secret("FEDERATION_SECRET", required=True)
    
    # Auth Config
    JWT_ALGORITHM = "HS256"
    JWT_ACCESS_EXPIRY_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRY_MINUTES", "15"))
    JWT_REFRESH_EXPIRY_DAYS = int(os.getenv("JWT_REFRESH_EXPIRY_DAYS", "7"))
    JWT_ISSUER = "fiber-api"
    JWT_AUDIENCE = "fiber-dashboard"
    
except ValueError as e:
    logger.critical(str(e))
    sys.exit(1)

# --- TLS Config ---
DB_SSL_CA = os.getenv("DB_SSL_CA") # Path to CA file
API_SSL_CA = os.getenv("API_SSL_CA") # Path to CA file

def get_db_ssl_context() -> Optional[ssl.SSLContext]:
    """Create strict SSL context for DB if CA provided."""
    if not DB_SSL_CA:
        return None  # None = 'prefer' or 'require' without verify depending on driver default, usually asyncpg needs False or ssl context
        
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=DB_SSL_CA)
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = True
    return ctx

# --- Role Config ---
ADMIN_USERS = [u.strip() for u in get_secret("ADMIN_USERS", "admin").split(",") if u.strip()]
OPERATOR_USERS = [u.strip() for u in get_secret("OPERATOR_USERS", "operator").split(",") if u.strip()]

# --- Rate Limiting (Day 86) ---
RATE_LIMIT_INGEST_RATE = float(os.getenv("RATE_LIMIT_INGEST_RATE", "1.0")) # 60/min = 1.0/sec
RATE_LIMIT_INGEST_BURST = int(os.getenv("RATE_LIMIT_INGEST_BURST", "10"))
RATE_LIMIT_LOCAL_RATE = float(os.getenv("RATE_LIMIT_LOCAL_RATE", "5.0")) # Per process
RATE_LIMIT_GLOBAL_MAX = int(os.getenv("RATE_LIMIT_GLOBAL_MAX", "200"))
RATE_LIMIT_TRUSTED_PROXIES = [ip.strip() for ip in os.getenv("RATE_LIMIT_TRUSTED_PROXIES", "127.0.0.1").split(",")]

