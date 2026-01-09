-- Token Bucket Rate Limit
-- KEYS[1]: bucket key
-- ARGV[1]: rate (tokens/sec)
-- ARGV[2]: capacity (max burst)
-- ARGV[3]: requested tokens
-- ARGV[4]: refill_time (sec) - Optional for stateful refill, or we calculate diff
-- ARGV[5]: TTL (sec)

local key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local requested = tonumber(ARGV[3])
local ttl = tonumber(ARGV[5]) or 600

-- Get current time from Redis (seconds, microseconds)
local time = redis.call('TIME')
local now_sec = tonumber(time[1])
local now_usec = tonumber(time[2])
local now_float = now_sec + (now_usec / 1000000)

-- Get current state
local state = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(state[1])
local last_refill = tonumber(state[2])

-- Init if missing
if not tokens then
    tokens = capacity
    last_refill = now_float
end

-- Refill
local delta = math.max(0, now_float - last_refill)
local filled_tokens = math.min(capacity, tokens + (delta * rate))

local allowed = 0
local remaining = filled_tokens
local retry_after = -1

if filled_tokens >= requested then
    allowed = 1
    filled_tokens = filled_tokens - requested
    remaining = filled_tokens
    
    -- Update state
    redis.call('HMSET', key, 'tokens', filled_tokens, 'last_refill', now_float)
    redis.call('EXPIRE', key, ttl)
else
    -- Not allowed
    allowed = 0
    local deficit = requested - filled_tokens
    retry_after = deficit / rate
end

-- Calculate Reset Time (when full)
local time_to_full = (capacity - filled_tokens) / rate
local reset_time = now_sec + math.ceil(time_to_full)

return {allowed, remaining, reset_time, capacity, retry_after}
