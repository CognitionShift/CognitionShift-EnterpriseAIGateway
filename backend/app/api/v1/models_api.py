"""Model listing and detail endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from app.middleware.tenant import get_current_user, TenantContext
from app.schemas.chat import ModelInfo
from app.core.response import make_meta

router = APIRouter(prefix="/models", tags=["models"])


def _get_model_router():
    from app.main import model_router
    return model_router


@router.get("")
async def list_models(tenant: TenantContext = Depends(get_current_user)):
    model_router = _get_model_router()
    models = model_router.list_models()
    default = model_router._default_model
    return {
        "data": [
            {
                "id": m.id,
                "display_name": m.display_name,
                "provider": m.provider,
                "capabilities": {
                    "streaming": m.supports_streaming,
                    "vision": m.supports_vision,
                    "max_context": m.max_context_tokens,
                },
                "cost": {
                    "input_per_1k": m.input_cost_per_1k,
                    "output_per_1k": m.output_cost_per_1k,
                },
                "is_default": m.id == default,
            }
            for m in models
        ],
        "meta": make_meta(),
    }


@router.get("/{model_id}")
async def get_model(model_id: str, tenant: TenantContext = Depends(get_current_user)):
    """Get model details and capabilities."""
    model_router = _get_model_router()
    try:
        _, provider, defn = model_router.resolve_model(model_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Model not found")

    from app.services.resilience import health_tracker
    provider_health = health_tracker.get_stats(provider.provider_name)

    return {
        "data": {
            "id": defn.id,
            "display_name": defn.display_name,
            "provider": defn.provider,
            "capabilities": {
                "streaming": defn.supports_streaming,
                "vision": defn.supports_vision,
                "max_context": defn.max_context_tokens,
            },
            "cost": {
                "input_per_1k": defn.input_cost_per_1k,
                "output_per_1k": defn.output_cost_per_1k,
            },
            "fallback_chain": model_router._fallback_chains.get(model_id, []),
            "health": provider_health.get("status", "unknown"),
        },
        "meta": make_meta(),
    }


@router.get("/{model_id}/health")
async def model_health(model_id: str, tenant: TenantContext = Depends(get_current_user)):
    """Get model provider health status."""
    model_router = _get_model_router()
    try:
        _, provider, defn = model_router.resolve_model(model_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Model not found")

    from app.services.resilience import health_tracker, circuit_breaker
    stats = health_tracker.get_stats(provider.provider_name)
    cb_state = circuit_breaker.get_state(provider.provider_name)

    return {
        "data": {
            "model_id": model_id,
            "provider": provider.provider_name,
            "health": stats,
            "circuit_breaker": cb_state,
        },
        "meta": make_meta(),
    }
