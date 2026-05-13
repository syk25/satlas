import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


async def init_redis() -> None:
    global _redis
    _redis = Redis.from_url(settings.redis_url, decode_responses=True)


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def cache_get(key: str) -> str | None:
    if _redis is None:
        return None
    try:
        return await _redis.get(key)
    except RedisError:
        logger.warning("Redis cache_get failed", extra={"key": key})
        return None


async def cache_set(key: str, value: str, ttl: int = 60) -> None:
    if _redis is None:
        return
    try:
        await _redis.set(key, value, ex=ttl)
    except RedisError:
        logger.warning("Redis cache_set failed", extra={"key": key})


async def cache_clear_pattern(pattern: str) -> None:
    if _redis is None:
        return
    try:
        keys = [key async for key in _redis.scan_iter(pattern)]
        if keys:
            await _redis.delete(*keys)
    except RedisError:
        logger.warning("Redis cache_clear_pattern failed", extra={"pattern": pattern})


async def cache_hash_set(key: str, mapping: dict[str, str], ttl: int) -> None:
    """Replace a hash wholesale and apply a TTL.

    Used for per-country visit-count tables (ADR-019). Pipeline ensures the
    delete + hset + expire happen atomically so readers never see a partial
    rebuild.
    """
    if _redis is None or not mapping:
        return
    try:
        async with _redis.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            pipe.hset(key, mapping=mapping)
            pipe.expire(key, ttl)
            await pipe.execute()
    except RedisError:
        logger.warning("Redis cache_hash_set failed", extra={"key": key})


async def cache_hash_mget(key: str, fields: list[str]) -> list[str | None]:
    """Fetch multiple hash fields in one round-trip. Missing fields → None."""
    if _redis is None or not fields:
        return [None] * len(fields)
    try:
        return await _redis.hmget(key, fields)
    except RedisError:
        logger.warning("Redis cache_hash_mget failed", extra={"key": key})
        return [None] * len(fields)


async def cache_pipeline_hgetall(keys: list[str]) -> list[dict[str, str]]:
    """Pipeline N HGETALL calls. Returns a list aligned with `keys`; missing
    keys yield an empty dict. Used by /stats/dashboard to aggregate 24h pass
    counts across all 234 territories in a single round-trip (~ms over
    in-region Redis) instead of N serial HGETALL calls."""
    if _redis is None or not keys:
        return [{} for _ in keys]
    try:
        async with _redis.pipeline(transaction=False) as pipe:
            for key in keys:
                pipe.hgetall(key)
            return await pipe.execute()
    except RedisError:
        logger.warning("Redis cache_pipeline_hgetall failed")
        return [{} for _ in keys]


async def cache_pipeline_delete(keys: list[str]) -> None:
    """DEL N keys in one pipeline. Used by chunked recompute (ADR-024) at
    the start of a sweep to clear stale per-country visit/passes data
    before appending fresh chunks."""
    if _redis is None or not keys:
        return
    try:
        async with _redis.pipeline(transaction=False) as pipe:
            for key in keys:
                pipe.delete(key)
            await pipe.execute()
    except RedisError:
        logger.warning("Redis cache_pipeline_delete failed")


async def cache_list_range(key: str, start: int = 0, end: int = -1) -> list[str]:
    """LRANGE — fetch a slice of a list. Returns [] on missing key or error."""
    if _redis is None:
        return []
    try:
        return await _redis.lrange(key, start, end)
    except RedisError:
        logger.warning("Redis cache_list_range failed", extra={"key": key})
        return []


async def cache_chunk_apply(
    visits_updates: dict[str, dict[str, int]],
    passes_appends: dict[str, list[str]],
    visits_ttl: int,
    passes_ttl: int,
) -> None:
    """Apply one recompute chunk to Redis in a single pipeline.

    `visits_updates[cc][norad_id] = count_delta` → HINCRBY per pair.
    `passes_appends[cc] = [encoded_event_json, ...]` → RPUSH all events.
    Every touched key gets its TTL refreshed inside the same pipeline so
    a long sweep doesn't leave keys expiring mid-write.

    Used by chunked recompute (ADR-024) — replaces the old
    `cache_hash_set + cache_set` pattern which only worked when the
    entire result set fit in memory.
    """
    if _redis is None:
        return
    if not visits_updates and not passes_appends:
        return
    try:
        async with _redis.pipeline(transaction=False) as pipe:
            for cc_key, counts in visits_updates.items():
                if not counts:
                    continue
                for field, delta in counts.items():
                    pipe.hincrby(cc_key, field, delta)
                pipe.expire(cc_key, visits_ttl)
            for cc_key, encoded_events in passes_appends.items():
                if not encoded_events:
                    continue
                pipe.rpush(cc_key, *encoded_events)
                pipe.expire(cc_key, passes_ttl)
            await pipe.execute()
    except RedisError:
        logger.warning("Redis cache_chunk_apply failed")
