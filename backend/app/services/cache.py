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
