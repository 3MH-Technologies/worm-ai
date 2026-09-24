"""Redis cache and rate-limiter."""

from __future__ import annotations

import logging

import redis.asyncio as redis

from app.core.config import get_settings

log = logging.getLogger(__name__)

_client: redis.Redis | None = None


async def connect() -> redis.Redis:
    global _client
    settings = get_settings()
    kwargs: dict = dict(
        decode_responses=True,
        socket_connect_timeout=5,
        protocol=2,
    )
    if settings.redis_password:
        kwargs["password"] = settings.redis_password
    _client = redis.from_url(settings.redis_url, **kwargs)
    await _client.ping()
    log.info("redis.connected url=%s", settings.redis_url)
    return _client


async def disconnect() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


def client() -> redis.Redis:
    if _client is None:
        raise RuntimeError("Redis not initialised; call connect() first")
    return _client


# ---- Rate limit ----
async def incr(key: str, ttl_sec: int = 60) -> int:
    """Fixed-window rate limiter. Returns current count after increment."""
    c = client()
    pipe = c.pipeline()
    pipe.incr(key)
    pipe.expire(key, ttl_sec)
    result = await pipe.execute()
    return int(result[0])


async def allow(key: str, limit: int, window_sec: int = 60) -> bool:
    """True if request is within `limit` for `window_sec`."""
    count = await incr(key, window_sec)
    return count <= limit
