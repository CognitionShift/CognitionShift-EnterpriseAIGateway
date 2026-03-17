"""Consistent response envelope and error handling per API contract."""

import uuid
from datetime import datetime, timezone
from typing import Any
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class MetaInfo(BaseModel):
    request_id: str
    timestamp: str


def make_meta(request_id: str | None = None) -> dict:
    """Build standard meta block."""
    return {
        "request_id": request_id or str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def success_response(data: Any, meta_extra: dict | None = None, status_code: int = 200) -> JSONResponse:
    """Wrap data in standard envelope: {"data": ..., "meta": {...}}"""
    meta = make_meta()
    if meta_extra:
        meta.update(meta_extra)
    return JSONResponse(
        status_code=status_code,
        content={"data": data, "meta": meta},
    )


def error_response(code: str, message: str, details: Any = None, status_code: int = 400, request_id: str | None = None) -> JSONResponse:
    """Standard error envelope: {"error": {...}, "meta": {...}}"""
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "meta": make_meta(request_id)},
    )


def paginated_response(data: list, has_more: bool, next_cursor: str | None = None, total_count: int | None = None) -> JSONResponse:
    """Paginated list response with cursor metadata."""
    meta = make_meta()
    meta["has_more"] = has_more
    if next_cursor:
        meta["next_cursor"] = next_cursor
    if total_count is not None:
        meta["total_count"] = total_count
    return JSONResponse(content={"data": data, "meta": meta})


# --- Exception handlers for FastAPI app ---

async def http_exception_handler(request: Request, exc: HTTPException):
    """Convert FastAPI HTTPExceptions to standard error envelope."""
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get("code", f"http_{exc.status_code}")
        message = detail.get("message", str(detail))
        details = {k: v for k, v in detail.items() if k not in ("code", "message")}
    else:
        code = f"http_{exc.status_code}"
        message = str(detail)
        details = None

    return error_response(
        code=code,
        message=message,
        details=details or None,
        status_code=exc.status_code,
        request_id=getattr(request.state, "request_id", None),
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions."""
    import structlog
    logger = structlog.get_logger()
    logger.error("unhandled_exception", error=str(exc), path=request.url.path, exc_info=True)
    return error_response(
        code="internal_error",
        message="An internal error occurred",
        status_code=500,
        request_id=getattr(request.state, "request_id", None),
    )
