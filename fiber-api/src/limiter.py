"""
Day 86: Rate Limiting Middleware
Distributed Token Bucket (Redis) with Local Guard and Hysteresis.
"""
import time
import logging
import asyncio
from pathlib import Path
from fastapi import Request, HTTPException, Depends
from redis.exceptions import RedisError
from . import config

logger = logging.getLogger("fiber-api.limiter")

# Prometheus Metrics
try:
    from prometheus_client import Counter
    RATELIMIT_COUNTER = Counter(
        'ratelimit_total', 
        'Rate limit decisions',
        ['status', 'key_type']
    )
except ImportError:
    RATELIMIT_COUNTER = None
    logger.warning("prometheus_client not installed, metrics disabled")

# Load Lua Script
LUA_SCRIPT_PATH = Path(__file__).parent / "lua" / "rate_limit.lua"
try:
    LUA_SCRIPT = LUA_SCRIPT_PATH.read_text()
except Exception as e:
    logger.critical(f"Failed to load Lua script: {e}")
    LUA_SCRIPT = ""

class LeakyBucket:
    """Simple in-memory leaky bucket for local fallback."""
    def __init__(self, rate: float, capacity: int):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self.lock = asyncio.Lock()

    async def consume(self, amount: int = 1) -> bool:
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.last_update = now
            
            # Refill
            self.tokens = min(self.capacity, self.tokens + (elapsed * self.rate))
            
            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False

# Global Safety Cap (Per Worker)
global_guard = LeakyBucket(config.RATE_LIMIT_GLOBAL_MAX, config.RATE_LIMIT_GLOBAL_MAX)

class RateLimiter:
    def __init__(self):
        self.state = "distributed" # or "local"
        self.redis_health_streak = 0
        self.local_buckets = {} # key -> LeakyBucket
        self.script_sha = None

    def get_client_ip(self, request: Request) -> str:
        """Resolve IP with Trusted Proxy Check."""
        x_forwarded = request.headers.get("X-Forwarded-For")
        if x_forwarded:
            ips = [ip.strip() for ip in x_forwarded.split(",")]
            # In a real impl, we'd walk backwards from the right, checking trusted proxies.
            # Simplified: If client.host is trusted, take the left-most IP.
            # Otherwise use client.host.
            client_host = request.client.host
            if any(client_host.startswith(p) for p in config.RATE_LIMIT_TRUSTED_PROXIES):
                 return ips[0]
        return request.client.host

    async def check_ingest(self, request: Request, redis=None, user=None):
        # 1. Global Safety Cap
        if not await global_guard.consume(1):
             logger.critical("Global Rate Limit Exceeded (DoS Protection)")
             raise HTTPException(status_code=503, detail="System Overload")

        # 2. Identity
        if user and user.get("username") != "anonymous":
            key_id = f"user:{user['username']}"
        else:
            key_id = f"ip:{self.get_client_ip(request)}"
            
        redis_key = f"limiter:ingest:{key_id}"

        # 3. Distributed Check
        distributed_headers = None
        if redis:
            try:
                # Load Script SHA if needed
                if not self.script_sha:
                    self.script_sha = await redis.script_load(LUA_SCRIPT)

                # Execute Lua
                # ARGV: rate, capacity, requested, unused, ttl
                res = await redis.evalsha(
                    self.script_sha, 
                    1, 
                    redis_key, 
                    config.RATE_LIMIT_INGEST_RATE,
                    config.RATE_LIMIT_INGEST_BURST,
                    1, 
                    0, 
                    600
                )
                
                # res: [allowed, remaining, reset, limit, retry_after]
                allowed, remaining, reset, limit, retry_after = res
                
                # Hysteresis update (Success)
                self.record_health(True)
                
                if self.state == "distributed":
                    headers = {
                        "X-RateLimit-Policy": "distributed",
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": str(int(float(remaining))),
                        "X-RateLimit-Reset": str(reset)
                    }
                    key_type = key_id.split(':')[0]
                    if not allowed:
                        if RATELIMIT_COUNTER: RATELIMIT_COUNTER.labels(status='rejected', key_type=key_type).inc()
                        headers["Retry-After"] = str(int(float(retry_after)))
                        raise HTTPException(status_code=429, detail="Rate limit exceeded", headers=headers)
                    if RATELIMIT_COUNTER: RATELIMIT_COUNTER.labels(status='allowed', key_type=key_type).inc()
                    return headers

            except (RedisError, ConnectionError) as e:
                 err_msg = str(e)
                 if "NOSCRIPT" in err_msg or "No matching script" in err_msg:
                      try:
                          self.script_sha = await redis.script_load(LUA_SCRIPT)
                          # Success! Now retry the actual operation to avoid falling to local
                          res = await redis.evalsha(
                              self.script_sha, 1, redis_key, 
                              config.RATE_LIMIT_INGEST_RATE, config.RATE_LIMIT_INGEST_BURST, 
                              1, 0, 600
                          )
                          allowed, remaining, reset, limit, retry_after = res
                          self.record_health(True)
                          
                          if self.state == "distributed":
                              headers = {
                                  "X-RateLimit-Policy": "distributed",
                                  "X-RateLimit-Limit": str(limit),
                                  "X-RateLimit-Remaining": str(int(float(remaining))),
                                  "X-RateLimit-Reset": str(reset)
                              }
                              return headers
                      except Exception as retry_e:
                          logger.error(f"Redis Retry Failed: {retry_e}")
                          self.record_health(False)
                 else:
                      logger.error(f"Redis RateLimit Failed: {e}")
                      self.record_health(False)
            except HTTPException:
                 raise

        # 4. Local Fallback (If Redis failed OR state is 'local' waiting for recovery)
        key_type = key_id.split(':')[0]
        if RATELIMIT_COUNTER: RATELIMIT_COUNTER.labels(status='fallback', key_type=key_type).inc()
        return await self.check_local(key_id)

    async def check_local(self, key_id):
        if key_id not in self.local_buckets:
            # Create bucket with strict fallback rate
            self.local_buckets[key_id] = LeakyBucket(config.RATE_LIMIT_LOCAL_RATE, int(config.RATE_LIMIT_LOCAL_RATE))
            
        bucket = self.local_buckets[key_id]
        if await bucket.consume(1):
             return {
                 "X-RateLimit-Policy": "local",
                 "X-RateLimit-Limit": str(int(config.RATE_LIMIT_LOCAL_RATE)),
                 "X-RateLimit-Remaining": "0" # Unknown
             }
        else:
             if RATELIMIT_COUNTER: RATELIMIT_COUNTER.labels(status='rejected_local', key_type=key_id.split(':')[0]).inc()
             raise HTTPException(status_code=429, detail="Rate limit exceeded (Local)", headers={"X-RateLimit-Policy": "local"})

    def record_health(self, success: bool):
        if success:
             self.redis_health_streak += 1
             if self.state == "local" and self.redis_health_streak >= 5:
                  logger.info("Redis Health Recovered: Switching to Distributed Mode")
                  self.state = "distributed"
                  self.redis_health_streak = 0
        else:
             self.redis_health_streak = 0
             if self.state == "distributed":
                  logger.warning("Redis Failure: Switching to Local Fallback Mode")
                  self.state = "local"


limiter = RateLimiter()

# Dependency
async def check_rate_limit(request: Request):
    redis = getattr(request.app.state, 'redis', None)
    user = getattr(request.state, 'user', None)
    
    headers = await limiter.check_ingest(request, redis, user)
    
    # Store headers to be attached to response middleware? 
    # Or just return them. FastAPI deps don't easily inject resp headers directly unless we use Response object.
    # We'll attach to request state and use a middleware or APIRoute class.
    # Simplest: Attach to request state.
    request.state.ratelimit_headers = headers
    print(f"DEBUG: Limiter set headers: {headers.keys()}")
    return True
