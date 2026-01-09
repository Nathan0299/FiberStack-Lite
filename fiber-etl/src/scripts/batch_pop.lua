-- scripts/batch_pop.lua
-- PROTOTYPE: BATCH_POP(queue_key, batch_size)
-- Atomically pops N items from the head of the list.

local queue = KEYS[1]
local size = tonumber(ARGV[1])

-- Get range
local items = redis.call('LRANGE', queue, 0, size - 1)

-- Trim if items found
if #items > 0 then
    redis.call('LTRIM', queue, #items, -1)
end

return items
