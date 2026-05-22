"""Redis cache for LLM completions: key = md5(prompt), TTL from settings."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

log = logging.getLogger(__name__)


def cache_key_for_prompt(prompt: str, *, prefix: str = "llm") -> str:
    digest = hashlib.md5(prompt.encode("utf-8")).hexdigest()
    return f"{prefix}:md5:{digest}"


async def cache_get(redis: Redis | None, key: str) -> str | None:
    if redis is None:
        return None
    try:
        return await redis.get(key)
    except Exception as exc:
        log.error("Redis GET failed: %s", exc)
        return None


async def cache_set(redis: Redis | None, key: str, value: str, ttl_sec: int) -> None:
    if redis is None:
        return
    try:
        await redis.set(key, value, ex=ttl_sec)
    except Exception as exc:
        log.error("Redis SET failed: %s", exc)
