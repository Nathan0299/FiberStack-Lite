from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import redis.asyncio as redis
import os
import logging
# from fiber_logging.configurator import init_logging
import logging
import sys
sys.path.insert(0, '/app/fiber-logging/src')
from logger import get_logger
from .routes import router

# Initialize logging
logger = get_logger("fiber-api", env=os.getenv("ENV", "dev"))

# Redis connection pool
redis_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global redis_pool
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    logger.info(f"Connecting to Redis at {redis_url}")
    redis_pool = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    app.state.redis = redis_pool
    yield
    # Shutdown
    logger.info("Closing Redis connection")
    await redis_pool.close()

app = FastAPI(
    title="FiberStack API",
    version="0.1.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In prod, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "FiberStack API v0.1.0"}
