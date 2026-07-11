"""
app/services/area_cache.py — Redis cache for area cards and vibe cards.

Key format:
  vibe_cards:{destination}          TTL 24h
  area_cards:{destination}:{exp_key}  TTL 24h
"""
import json
import os

import redis.asyncio as aioredis

from app.utils.logger import get_logger

logger = get_logger(__name__)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


async def _get_redis():
    try:
        return await aioredis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        return None


async def get_cached(key: str) -> list[dict] | None:
    """Return parsed list from Redis, or None on miss/error."""
    r = await _get_redis()
    if not r:
        return None
    try:
        raw = await r.get(key)
        if raw:
            logger.info(f"[area_cache] hit: {key}")
            return json.loads(raw)
        return None
    except Exception as e:
        logger.warning(f"[area_cache] get error for {key}: {e}")
        return None


async def set_cached(key: str, data: list[dict], ttl: int = 86400) -> None:
    """Write JSON-serialised data to Redis with TTL. Silent on error."""
    r = await _get_redis()
    if not r:
        return
    try:
        await r.setex(key, ttl, json.dumps(data, default=str))
        logger.info(f"[area_cache] set: {key} ttl={ttl}s")
    except Exception as e:
        logger.warning(f"[area_cache] set error for {key}: {e}")
