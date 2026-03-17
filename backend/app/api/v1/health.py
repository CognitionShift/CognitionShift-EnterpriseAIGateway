"""Health check endpoints."""

from fastapi import APIRouter
from sqlalchemy import text
from app.database import async_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "csgateway"}


@router.get("/health/detailed")
async def health_detailed():
    checks = {"api": True, "database": False, "redis": False}

    # Database check
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
            checks["database"] = True
    except Exception:
        pass

    # Redis check
    try:
        import redis.asyncio as aioredis
        from app.config import get_settings
        settings = get_settings()
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        checks["redis"] = True
        await r.aclose()
    except Exception:
        pass

    # Model providers
    try:
        from app.main import model_router
        provider_health = await model_router.health_check()
        checks["providers"] = provider_health
    except Exception:
        checks["providers"] = {}

    all_ok = checks["database"] and checks["redis"]
    return {
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
    }
