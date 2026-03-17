"""Concurrent stream management — tracks and limits active SSE streams per user."""

import uuid
import structlog
import redis.asyncio as aioredis
from app.config import get_settings

logger = structlog.get_logger()

DEFAULT_MAX_CONCURRENT = 3


class StreamManager:
    """Redis-backed concurrent stream tracker."""

    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        if not self._redis:
            settings = get_settings()
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def register(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> bool:
        """Register a new stream. Returns False if limit exceeded."""
        try:
            r = await self._get_redis()
            key = f"streams:active:{user_id}"
            count = await r.scard(key)
            if count >= DEFAULT_MAX_CONCURRENT:
                logger.warning("concurrent_stream_limit", user_id=str(user_id), active=count)
                return False
            await r.sadd(key, str(conversation_id))
            await r.expire(key, 3600)  # 1hr cleanup
            return True
        except Exception as e:
            logger.warning("stream_register_error", error=str(e))
            return True  # Don't block on Redis errors

    async def unregister(self, user_id: uuid.UUID, conversation_id: uuid.UUID):
        """Unregister a stream."""
        try:
            r = await self._get_redis()
            await r.srem(f"streams:active:{user_id}", str(conversation_id))
        except Exception as e:
            logger.warning("stream_unregister_error", error=str(e))

    async def active_count(self, user_id: uuid.UUID) -> int:
        try:
            r = await self._get_redis()
            return await r.scard(f"streams:active:{user_id}")
        except Exception:
            return 0


stream_manager = StreamManager()
