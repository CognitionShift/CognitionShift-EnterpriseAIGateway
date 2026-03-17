"""Admin model configuration endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.middleware.tenant import require_admin, TenantContext

router = APIRouter(prefix="/admin/models", tags=["admin-models"])


@router.get("")
async def list_all_models(
    tenant: TenantContext = Depends(require_admin),
):
    """List all models including disabled ones."""
    from app.main import model_router
    models = model_router.list_models()
    return {
        "data": [
            {
                "id": m.id,
                "display_name": m.display_name,
                "provider": m.provider,
                "max_context_tokens": m.max_context_tokens,
                "input_cost_per_1k": m.input_cost_per_1k,
                "output_cost_per_1k": m.output_cost_per_1k,
                "supports_streaming": m.supports_streaming,
                "supports_vision": m.supports_vision,
                "enabled": True,  # All registered models are enabled
            }
            for m in models
        ]
    }


@router.get("/health")
async def provider_health(
    tenant: TenantContext = Depends(require_admin),
):
    """Get health status of all providers."""
    from app.main import model_router
    health = await model_router.health_check()
    return {"data": health}
