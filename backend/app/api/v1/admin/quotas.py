"""Admin quota management endpoints."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.database import get_db
from app.middleware.tenant import require_admin, TenantContext
from app.models.quota import Quota

router = APIRouter(prefix="/admin/quotas", tags=["admin-quotas"])


class QuotaCreate(BaseModel):
    scope: str = "org"  # org, user
    scope_id: uuid.UUID | None = None
    period: str = "monthly"  # daily, weekly, monthly
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    max_requests: int | None = None
    enforcement: str = "soft"  # soft, hard


class QuotaUpdate(BaseModel):
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    max_requests: int | None = None
    enforcement: str | None = None
    active: bool | None = None


@router.get("")
async def list_quotas(
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all quotas for the org."""
    result = await db.execute(
        select(Quota).where(Quota.org_id == tenant.org_id).order_by(Quota.created_at)
    )
    quotas = result.scalars().all()
    return {
        "data": [
            {
                "id": str(q.id),
                "scope": q.scope,
                "scope_id": str(q.scope_id) if q.scope_id else None,
                "period": q.period,
                "max_tokens": q.max_tokens,
                "max_cost_usd": float(q.max_cost_usd) if q.max_cost_usd else None,
                "max_requests": q.max_requests,
                "enforcement": q.enforcement,
                "active": q.active,
            }
            for q in quotas
        ]
    }


@router.post("", status_code=201)
async def create_quota(
    req: QuotaCreate,
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new quota."""
    quota = Quota(
        org_id=tenant.org_id,
        scope=req.scope,
        scope_id=req.scope_id,
        period=req.period,
        max_tokens=req.max_tokens,
        max_cost_usd=req.max_cost_usd,
        max_requests=req.max_requests,
        enforcement=req.enforcement,
    )
    db.add(quota)
    await db.flush()
    return {
        "data": {
            "id": str(quota.id),
            "scope": quota.scope,
            "period": quota.period,
            "max_tokens": quota.max_tokens,
            "max_cost_usd": float(quota.max_cost_usd) if quota.max_cost_usd else None,
            "max_requests": quota.max_requests,
            "enforcement": quota.enforcement,
            "active": quota.active,
        }
    }


@router.patch("/{quota_id}")
async def update_quota(
    quota_id: uuid.UUID,
    req: QuotaUpdate,
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a quota."""
    result = await db.execute(
        select(Quota).where(Quota.id == quota_id, Quota.org_id == tenant.org_id)
    )
    quota = result.scalar_one_or_none()
    if not quota:
        raise HTTPException(status_code=404, detail="Quota not found")

    if req.max_tokens is not None:
        quota.max_tokens = req.max_tokens
    if req.max_cost_usd is not None:
        quota.max_cost_usd = req.max_cost_usd
    if req.max_requests is not None:
        quota.max_requests = req.max_requests
    if req.enforcement is not None:
        quota.enforcement = req.enforcement
    if req.active is not None:
        quota.active = req.active
    quota.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return {"data": {"id": str(quota.id), "updated": True}}


@router.delete("/{quota_id}", status_code=204)
async def delete_quota(
    quota_id: uuid.UUID,
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a quota."""
    result = await db.execute(
        select(Quota).where(Quota.id == quota_id, Quota.org_id == tenant.org_id)
    )
    quota = result.scalar_one_or_none()
    if not quota:
        raise HTTPException(status_code=404, detail="Quota not found")
    await db.delete(quota)
    await db.flush()
