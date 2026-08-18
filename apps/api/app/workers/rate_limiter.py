"""Redis-backed token bucket for pacing outbound sends across all workers.

A plain GET -> compute -> SET round trip races between concurrent worker
jobs checking the same bucket, so refill + debit happens atomically in a
single Lua script instead. Uses the Redis server's own clock (TIME) rather
than each worker's local clock, so bucket state stays correct even if
workers run on hosts with slightly different clocks.
"""

from arq.connections import ArqRedis

_TOKEN_BUCKET_SCRIPT = """
local bucket_key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])

local state = redis.call('HMGET', bucket_key, 'tokens', 'ts')
local tokens = tonumber(state[1])
local ts = tonumber(state[2])

local now = redis.call('TIME')
local now_ms = tonumber(now[1]) * 1000 + tonumber(now[2]) / 1000

if tokens == nil then
    tokens = capacity
    ts = now_ms
end

local elapsed_seconds = math.max(0, now_ms - ts) / 1000
tokens = math.min(capacity, tokens + elapsed_seconds * rate)

local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end

redis.call('HMSET', bucket_key, 'tokens', tostring(tokens), 'ts', tostring(now_ms))
redis.call('EXPIRE', bucket_key, 60)

return allowed
"""


async def acquire_token(redis: ArqRedis, key: str, rate_per_second: int) -> bool:
    """Try to take one token from `key`'s bucket.

    Returns False if the bucket is currently empty (caller should back off
    and retry rather than send). Bucket capacity equals `rate_per_second`,
    i.e. at most one second's worth of burst.
    """
    allowed = await redis.eval(_TOKEN_BUCKET_SCRIPT, 1, key, rate_per_second, rate_per_second)
    return bool(allowed)
