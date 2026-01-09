from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import redis.asyncio as redis
import asyncpg
import os
from .logger import get_logger
from .routes import router
from .middleware import AuthMiddleware  # Day 78

# Initialize logging
logger = get_logger("fiber-api", env=os.getenv("ENV", "dev"))


import signal
import asyncio
from . import config

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - Redis
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    logger.info(f"Connecting to Redis")
    redis_pool = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    app.state.redis = redis_pool
    
    # Startup - Database
    logger.info("Connecting to TimescaleDB")
    async def create_db_pool():
        return await asyncpg.create_pool(
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASS", "postgres"),
            database=os.getenv("DB_NAME", "fiberstack"),
            host=os.getenv("DB_HOST", "localhost"),
            min_size=int(os.getenv("DB_POOL_MIN", "5")),
            max_size=int(os.getenv("DB_POOL_MAX", "20")),
            ssl=config.get_db_ssl_context()
        )
    
    app.state.db = await create_db_pool()
    
    # Signal Handler for Cert Rotation
    def handle_sighup():
        logger.info("Received SIGHUP - Reloading DB Pool (Cert Rotation)")
        asyncio.create_task(reload_db(app, create_db_pool))
        
    try:
        signal.signal(signal.SIGHUP, lambda s, f: handle_sighup())
    except Exception: 
        pass # Signal might fail in some envs
    
    yield
    
    # Shutdown
    logger.info("Closing connections")
    await redis_pool.close()
    await app.state.db.close()

async def reload_db(app, factory):
    try:
        old_pool = app.state.db
        app.state.db = await factory()
        await old_pool.close()
        logger.info("DB Pool Reloaded Successfully")
    except Exception as e:
        logger.error(f"DB Reload Failed: {e}")

app = FastAPI(
    title="FiberStack API",
    version="0.1.0",
    lifespan=lifespan
)

# Security Headers Middleware (Day 95 Hardening)
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # 1. HSTS (Strict-Transport-Security)
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        # 2. X-Frame-Options (Clickjacking)
        response.headers["X-Frame-Options"] = "DENY"
        # 3. X-Content-Type-Options (MIME Sniffing)
        response.headers["X-Content-Type-Options"] = "nosniff"
        # 4. Content-Security-Policy (XSS)
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: https:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
        # 5. Server Masking - Note: uvicorn sets header after middleware in dev mode.
        # In production behind nginx/traefik, configure proxy to override Server header.
        # For now, we attempt to override but it may be appended in dev. 
        try:
            del response.headers["server"]
        except KeyError:
            pass
        response.headers["Server"] = "FiberStack"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# CORS (Restricted)
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Day 78: Auth Middleware (zero anonymous access)
app.add_middleware(AuthMiddleware)

# Routes prefixed with /api
app.include_router(router, prefix="/api")



@app.get("/")
async def root():
    return {"message": "FiberStack API v0.1.0"}


@app.get("/health")
async def health():
    """Shallow Liveness Check for Docker/Orchestrators."""
    return {"status": "ok"}

