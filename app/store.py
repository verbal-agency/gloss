from __future__ import annotations
import json
import redis.asyncio as aioredis
from app.config import settings


_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def set_json(key: str, value: dict | list, ttl_seconds: int = 86400) -> None:
    r = get_redis()
    await r.setex(key, ttl_seconds, json.dumps(value))


async def get_json(key: str) -> dict | list | None:
    r = get_redis()
    raw = await r.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def rpush_json(key: str, value: dict, ttl_seconds: int = 86400) -> None:
    r = get_redis()
    await r.rpush(key, json.dumps(value))
    await r.expire(key, ttl_seconds)


async def lrange_json(key: str) -> list[dict]:
    r = get_redis()
    items = await r.lrange(key, 0, -1)
    return [json.loads(i) for i in items]
