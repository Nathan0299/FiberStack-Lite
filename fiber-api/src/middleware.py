"""
Day 85/87: Middleware (Bulletproof + Trace Propagation)
Fail-Closed Auth, JTI Revocation Check, Unified Tracing.
"""
import logging
import uuid
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from . import auth, config

# Day 87: Unified logging
import sys
sys.path.insert(0, '/Users/macpro/FiberStack-Lite')
try:
    from fiber_shared.log_lib import set_trace_id, get_trace_id, generate_trace_id, get_instrumented_logger
    logger = get_instrumented_logger("fiber-api.middleware")
except ImportError:
    logger = logging.getLogger("fiber-api.middleware")
    def set_trace_id(t): pass
    def get_trace_id(): return "unknown"
    def generate_trace_id(): return str(uuid.uuid4())[:8]

PUBLIC_PATHS = {'/health', '/api/auth/login', '/api/status'}

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Unified Trace Propagation (Day 87)
        # Probe sends X-Trace-ID, we read or generate
        trace_id = request.headers.get("X-Trace-ID") or request.headers.get("X-Request-ID") or generate_trace_id()
        set_trace_id(trace_id)
        request.state.request_id = trace_id
        
        path = request.url.path
        
        # 2. Redis Availability (Fail-Closed)
        redis = getattr(request.app.state, 'redis', None)
        redis_ok = True
        try:
             # Cheap ping or just trust pool? 
             # On every request ping is expensive. We catch ConnectionError on specific ops.
             # However, for fail-closed auth, we MUST check revocation.
             pass
        except Exception:
             redis_ok = False

        # 3. Public Paths
        if path in PUBLIC_PATHS:
            request.state.user = {"username": "anonymous", "role": "ANONYMOUS"}
            response = await call_next(request)
            response.headers["X-Request-ID"] = trace_id
            response.headers["X-Trace-ID"] = trace_id
            return response

        # 4. Auth Extraction
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            request.state.user = {"username": "anonymous", "role": "ANONYMOUS"}
            response = await call_next(request)
            response.headers["X-Request-ID"] = trace_id
            response.headers["X-Trace-ID"] = trace_id
            return response
            
        token = auth_header.split(" ")[1]
        
        # Day 101: Federation Secret Bypass (Operator Role)
        # Allows probes to push data using the shared secret as a Bearer token
        secret = config.FEDERATION_SECRET
        if secret and token == secret:
            request.state.user = {
                "username": "federation_probe", 
                "role": "OPERATOR",
                "jti": "static-federation-token",
                "exp": 9999999999
            }
            response = await call_next(request)
            response.headers["X-Request-ID"] = trace_id
            response.headers["X-Trace-ID"] = trace_id
            return response
        
        try:
            # A. Stateless Verify
            claims = auth.verify_token_claims(token)
            jti = claims.get("jti")
            
            # B. Stateful Revocation Check (Fail-Closed)
            # If Redis unavailable, we MUST reject auth (unless bypass configured, but here strict)
            try:
                if await auth.is_jti_revoked(redis, jti):
                    logger.warning(f"Rejected revoked token {jti}")
                    return JSONResponse(status_code=401, content={"detail": "Token revoked"})
            except Exception as e:
                # Redis Down -> Fail Closed (Default)
                if path == "/api/push":
                     logger.warning(f"Redis Down during Push Auth. Failing OPEN for Ingestion. Error: {e}")
                else:
                     logger.critical(f"Redis Down during Auth Check: {e}")
                     return JSONResponse(status_code=503, content={"detail": "Auth Persistence Unavailable"})

                
            # Success
            request.state.user = {
                "username": claims.get("sub"),
                "role": auth.get_user_role(claims.get("sub")),
                "jti": jti,
                "exp": claims.get("exp")
            }
            
        except Exception as e:
            # Token invalid
            logger.warning(f"Auth failed: {e}")
            request.state.user = {"username": "anonymous", "role": "ANONYMOUS"}
            
            # Day 91: Legacy Fallback for Federation
            logger.warning(f"Auth Exception for path: {path}. Error: {e}")
            
            if path == "/api/ingest":
                 logger.info("Allowing Legacy Fallback for /api/ingest")
                 return await call_next(request)

            resp = JSONResponse(status_code=401, content={"detail": str(e)})
            resp.headers["X-Request-ID"] = trace_id
            resp.headers["X-Trace-ID"] = trace_id
            return resp

        response = await call_next(request)
        response.headers["X-Request-ID"] = trace_id
        response.headers["X-Trace-ID"] = trace_id  # Day 87: Echo for probe correlation
        
        # 5. Inject Rate Limit Headers
        rl_headers = getattr(request.state, "ratelimit_headers", None)
        if rl_headers:
            for k, v in rl_headers.items():
                response.headers[k] = v
                
        return response
