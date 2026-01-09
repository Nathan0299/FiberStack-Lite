-- scripts/token_bucket.lua
-- PROTOTYPE: ALLOWED(key, refill_rate, capacity, now_timestamp)
-- Returns 1 if allowed, 0 if rejected.

local key = KEYS[1]
local rate = tonumber(ARGV[1])      -- tokens per second
local capacity = tonumber(ARGV[2])  -- max burst
local now = tonumber(ARGV[3])       -- current timestamp (seconds)
local requested = 1

-- Get current state
local last_refill = tonumber(redis.call("HGET", key, "last_refill") or "0")
local tokens = tonumber(redis.call("HGET", key, "tokens") or capacity)

-- Calculate refill
local delta = math.max(0, now - last_refill)
local refill = delta * rate

-- Update tokens
tokens = math.min(capacity, tokens + refill)

if tokens >= requested then
    tokens = tokens - requested
    redis.call("HMSET", key, "last_refill", now, "tokens", tokens)
    return 1 -- Allowed
else
    -- Update timestamp even on failure to prevent drift? 
    -- Actually better to only update on success or regularly, but for simplicity we rely on next success or expiration.
    -- However, we SHOULD update last_refill if we capped at capacity, but here simpler is fine.
    return 0 -- Rejected
end
