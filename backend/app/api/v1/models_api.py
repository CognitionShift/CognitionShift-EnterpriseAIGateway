"""Model listing endpoints."""

from fastapi import APIRouter, Depends
from app.middleware.tenant import get_current_user, TenantContext
from app.schemas.chat import ModelInfo

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelInfo])
async def list_models(tenant: TenantContext = Depends(get_current_user)):
    from app.main import model_router
    models = model_router.list_models()
    return [
        ModelInfo(
            id=m.id,
            display_name=m.display_name,
            provider=m.provider,
            supports_streaming=m.supports_streaming,
            max_context_tokens=m.max_context_tokens,
            input_cost_per_1k=m.input_cost_per_1k,
            output_cost_per_1k=m.output_cost_per_1k,
        )
        for m in models
    ]
