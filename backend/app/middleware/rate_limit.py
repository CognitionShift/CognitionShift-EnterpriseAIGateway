"""Redis-backed rate limiting middleware."""

import time
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as aioredis
import structlog

from app.config import get_settings

logger = structlog.get_logger()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Token-bucket rate limiting via Redis.
    
    Limits per authenticated user, falls back to IP for unauthenticated.
    Default: 60 requests per minute per user, 200 per minute per IP.
    """

    def __init__(self, app, user_rpm: int = 60, ip_rpm: int = 200):
        super().__init__(app)
        self.user_rpm = user_rpm
        self.ip_rpm = ip_rpm
        self._redis = None

    async def _get_redis(self):
        if not self._redis:
            settings = get_settings()
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path.startswith("/api/v1/health"):
            return await call_next(request)

        try:
            redis = await self._get_redis()

            # Determine key and limit
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer "):
                # Extract user from JWT (quick decode without validation for key only)
                import base64
                try:
                    payload = auth.split(".")[1]
                    payload += "=" * (4 - len(payload) % 4)
                    decoded = base64.urlsafe_b64decode(payload)
                    import json
                    data = json.loads(decoded)
                    key = f"rl:user:{data.get('sub', 'unknown')}"
                    limit = self.user_rpm
                except Exception:
                    key = f"rl:ip:{request.client.host if request.client else 'unknown'}"
                    limit = self.ip_rpm
            else:
                key = f"rl:ip:{request.client.host if request.client else 'unknown'}"
                limit = self.ip_rpm

            # Sliding window counter
            now = int(time.time())
            window_key = f"{key}:{now // 60}"

            pipe = redis.pipeline()
            pipe.incr(window_key)
            pipe.expire(window_key, 120)  # 2 min TTL
            results = await pipe.execute()
            count = results[0]

            # Set rate limit headers
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
            response.headers["X-RateLimit-Reset"] = str((now // 60 + 1) * 60)

            if count > limit:
                logger.warning("rate_limit_exceeded", key=key, count=count, limit=limit)
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please slow down.",
                    headers={
                        "Retry-After": str(60 - (now % 60)),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            return response

        except HTTPException:
            raise
        except Exception as e:
            # Rate limiting should never break the app
            logger.warning("rate_limit_error", error=str(e))
            return await call_next(request)
