"""Redis connection wrapper for session memory."""

import logging
from typing import Optional

import redis

from config.settings import REDIS_HOST, REDIS_PORT, REDIS_URL

logger = logging.getLogger(__name__)

_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """Return a shared Redis client, or None if unavailable."""
    global _client
    if _client is not None:
        return _client
    try:
        if REDIS_URL and REDIS_URL.startswith("redis://"):
            _client = redis.from_url(REDIS_URL, decode_responses=True)
        else:
            _client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        _client.ping()
        logger.info("Redis connection established.")
        return _client
    except Exception as exc:
        logger.warning("Redis unavailable: %s", exc)
        _client = None
        return None


def check_redis_connection() -> bool:
    client = get_redis_client()
    if not client:
        return False
    try:
        return bool(client.ping())
    except Exception:
        return False
