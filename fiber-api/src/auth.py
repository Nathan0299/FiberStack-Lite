"""
Day 85: Authentication (Bulletproof)
Dual-Token (Access/Refresh), Rotation, Redis-backed Revocation.
"""
import uuid
import jwt
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple

from fastapi import HTTPException
from pydantic import BaseModel
from . import config

class LoginRequest(BaseModel):
    username: str
    password: str


logger = logging.getLogger("fiber-api.auth")

# Redis Keys
REVOKE_PREFIX = "revoked:jti:"
REFRESH_PREFIX = "refresh:jti:"

# Credential Store (Simple Env-based)
USER_CREDENTIALS: Dict[str, str] = {}
# R1 Remediation: Fail fast if no credentials provided in prod/stage
credentials_str = config.get_secret("USER_CREDENTIALS", required=True)

for entry in credentials_str.split(","):
    if ":" in entry:
        u, p = entry.split(":", 1)
        USER_CREDENTIALS[u.strip()] = hashlib.sha256(p.strip().encode()).hexdigest()

def get_user_role(username: str) -> str:
    if username in config.ADMIN_USERS: return 'ADMIN'
    if username in config.OPERATOR_USERS: return 'OPERATOR'
    return 'VIEWER' if username in USER_CREDENTIALS else 'ANONYMOUS'

def verify_credentials(username: str, password: str) -> bool:
    expected_hash = USER_CREDENTIALS.get(username)
    if not expected_hash: return False
    return hashlib.sha256(password.encode()).hexdigest() == expected_hash

# --- Token Management ---

def issue_tokens(username: str) -> Dict[str, str]:
    """Issue Access (Short) and Refresh (Long) tokens."""
    now = datetime.now(timezone.utc)
    
    # 1. Access Token
    access_id = str(uuid.uuid4())
    access_exp = now + timedelta(minutes=config.JWT_ACCESS_EXPIRY_MINUTES)
    access_token = jwt.encode({
        "sub": username,
        "iss": config.JWT_ISSUER,
        "aud": config.JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(access_exp.timestamp()),
        "jti": access_id,
        "type": "access"
    }, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
    
    # 2. Refresh Token
    refresh_id = str(uuid.uuid4())
    refresh_exp = now + timedelta(days=config.JWT_REFRESH_EXPIRY_DAYS)
    refresh_token = jwt.encode({
        "sub": username,
        "iss": config.JWT_ISSUER,
        "aud": config.JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(refresh_exp.timestamp()),
        "jti": refresh_id,
        "type": "refresh"
    }, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": config.JWT_ACCESS_EXPIRY_MINUTES * 60,
        "role": get_user_role(username)
    }

async def rotate_refresh_token(old_refresh_token: str, redis) -> Dict[str, str]:
    """
    Refresh Rotation:
    1. Validate Old Refresh Token.
    2. Check if Old JTI is Revoked (Reuse Detection).
    3. Revoke Old JTI.
    4. Issue New Pair.
    """
    try:
        claims = jwt.decode(
            old_refresh_token, 
            config.JWT_SECRET, 
            algorithms=[config.JWT_ALGORITHM],
            audience=config.JWT_AUDIENCE
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
        
    if claims.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
        
    jti = claims.get("jti")
    username = claims.get("sub")
    
    # Check Revocation (Reuse Attempt)
    if await is_jti_revoked(redis, jti):
        logger.critical(f"REPLAY ATTACK: Reused refresh token {jti} for {username}")
        # In a real system, you might ban the user here.
        raise HTTPException(status_code=401, detail="Token revoked")
        
    # Revoke Old Token
    exp_timestamp = claims.get("exp")
    ttl = max(0, exp_timestamp - int(datetime.now(timezone.utc).timestamp()))
    await revoke_jti(redis, jti, ttl)
    
    # Issue New Pair
    return issue_tokens(username)

async def revoke_jti(redis, jti: str, ttl: int):
    """Add JTI to Redis Denylist with TTL."""
    key = f"{REVOKE_PREFIX}{jti}"
    # TTL + 5 mins skew buffer
    await redis.setex(key, ttl + 300, "revoked")

async def is_jti_revoked(redis, jti: str) -> bool:
    """Check Redis Denylist (Fail-Closed handled by middleware)."""
    return await redis.exists(f"{REVOKE_PREFIX}{jti}")

def verify_token_claims(token: str) -> dict:
    """Stateless verification (Sig/Exp). Stateful check done in middleware."""
    try:
        return jwt.decode(
            token,
            config.JWT_SECRET,
            algorithms=[config.JWT_ALGORITHM],
            audience=config.JWT_AUDIENCE
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

# --- Authorization (RBAC) ---
from functools import wraps
from fastapi import Request
from . import config

PERMISSIONS = {
    "ADMIN": ["admin:roles", "admin:audit", "view:metrics", "monitor:nodes", "write:node:create", "write:node:delete"],
    "OPERATOR": ["view:metrics", "monitor:nodes", "write:node:create"],
    "VIEWER": ["view:metrics"],
    "ANONYMOUS": []
}

# Export Config Lists for Routes
ADMIN_USERS = config.ADMIN_USERS
OPERATOR_USERS = config.OPERATOR_USERS

def get_role_permissions(role: str) -> list:
    return PERMISSIONS.get(role, [])

def require_auth(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        request = kwargs.get('request') or next((arg for arg in args if isinstance(arg, Request)), None)
        user = getattr(request.state, 'user', None) if request else None
        if not user or user.get("role") == "ANONYMOUS":
            raise HTTPException(status_code=401, detail="Authentication required")
        return await func(*args, **kwargs)
    return wrapper

def require_permission(perm: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get('request') or next((arg for arg in args if isinstance(arg, Request)), None)
            user = getattr(request.state, 'user', {}) if request else {}
            role = user.get("role", "ANONYMOUS")
            
            if perm not in get_role_permissions(role):
                 raise HTTPException(status_code=403, detail="Insufficient permissions")
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def log_role_config():
    logger.info(f"RBAC Loaded: {len(ADMIN_USERS)} admins")

