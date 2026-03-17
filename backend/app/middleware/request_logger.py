"""Request logging middleware — structured access logs."""

import time
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

logger = structlog.get_logger()


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """Logs every request with timing, status, and correlation ID."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start = time.monotonic()

        # Bind correlation ID
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)

        duration_ms = int((time.monotonic() - start) * 1000)

        # Only log non-health-check requests
        if not request.url.path.startswith("/api/v1/health"):
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
                client=request.client.host if request.client else "unknown",
            )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        structlog.contextvars.unbind_contextvars("request_id")

        return response
