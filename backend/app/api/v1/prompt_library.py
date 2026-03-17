"""Prompt library — shared prompt templates across the organization."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import JSONB
from pydantic import BaseModel, Field
from app.database import get_db
from app.middleware.tenant import get_current_user, TenantContext

router = APIRouter(prefix="/prompts", tags=["prompts"])


class PromptCreate(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    category: str = "general"
    tags: list[str] = []
    is_public: bool = True  # Visible to org


class PromptUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    is_public: bool | None = None


# We'll store prompts in the org settings JSONB for simplicity
# In a production system, this would be its own table
# For now, use a lightweight approach with an in-memory + Redis cache

@router.get("")
async def list_prompts(
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List available prompt templates."""
    from app.models.organization import Organization
    result = await db.execute(select(Organization).where(Organization.id == tenant.org_id))
    org = result.scalar_one()

    prompts = org.settings.get("prompt_library", [])

    # Filter
    if category:
        prompts = [p for p in prompts if p.get("category") == category]
    if search:
        search_lower = search.lower()
        prompts = [p for p in prompts if search_lower in p.get("title", "").lower() or search_lower in p.get("content", "").lower()]

    return {"data": prompts}


@router.post("", status_code=201)
async def create_prompt(
    req: PromptCreate,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a prompt template."""
    from app.models.organization import Organization
    result = await db.execute(select(Organization).where(Organization.id == tenant.org_id))
    org = result.scalar_one()

    prompt = {
        "id": str(uuid.uuid4()),
        "title": req.title,
        "content": req.content,
        "category": req.category,
        "tags": req.tags,
        "is_public": req.is_public,
        "created_by": str(tenant.user_id),
        "created_by_name": tenant.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "uses": 0,
    }

    library = org.settings.get("prompt_library", [])
    library.append(prompt)
    org.settings = {**org.settings, "prompt_library": library}
    await db.flush()

    return {"data": prompt}


@router.delete("/{prompt_id}", status_code=204)
async def delete_prompt(
    prompt_id: str,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a prompt template."""
    from app.models.organization import Organization
    result = await db.execute(select(Organization).where(Organization.id == tenant.org_id))
    org = result.scalar_one()

    library = org.settings.get("prompt_library", [])
    library = [p for p in library if p.get("id") != prompt_id]
    org.settings = {**org.settings, "prompt_library": library}
    await db.flush()
