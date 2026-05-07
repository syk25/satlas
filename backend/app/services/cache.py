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
