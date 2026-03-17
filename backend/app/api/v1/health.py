"""Health check and system endpoints."""

from fastapi import APIRouter
from sqlalchemy import text
from app.database import async_session
from app.core.response import make_meta

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

    # Passive health stats
    try:
        from app.services.resilience import health_tracker
        for provider_name in checks.get("providers", {}):
            checks[f"provider_{provider_name}_stats"] = health_tracker.get_stats(provider_name)
    except Exception:
        pass

    all_ok = checks["database"] and checks["redis"]
    return {
        "data": {
            "status": "healthy" if all_ok else "degraded",
            "checks": checks,
        },
        "meta": make_meta(),
    }


@router.get("/system/version")
async def system_version():
    """Platform version info."""
    return {
        "data": {
            "version": "0.1.0",
            "name": "CognitionShift Enterprise AI Gateway",
            "api_version": "v1",
            "build": "dev",
        },
        "meta": make_meta(),
    }
