"""Admin content policy configuration."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.database import get_db
from app.middleware.tenant import require_admin, TenantContext
from app.models.organization import Organization

router = APIRouter(prefix="/admin/content-policy", tags=["admin-content-policy"])


class ContentPolicyUpdate(BaseModel):
    pii_action: str = "warn"  # block, warn, redact, allow
    injection_action: str = "block"  # block, warn, allow
    dlp_enabled: bool = True
    outbound_scan: bool = True
    custom_dlp_rules: list[dict] | None = None  # [{name, type, pattern, action}]


@router.get("")
async def get_content_policy(
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get current content policy for the org."""
    result = await db.execute(
        select(Organization).where(Organization.id == tenant.org_id)
    )
    org = result.scalar_one()

    default_policy = {
        "pii_action": "warn",
        "injection_action": "block",
        "dlp_enabled": True,
        "outbound_scan": True,
        "custom_dlp_rules": [],
    }

    policy = {**default_policy, **org.content_policy}
    return {"data": policy}


@router.put("")
async def update_content_policy(
    req: ContentPolicyUpdate,
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update content policy for the org."""
    result = await db.execute(
        select(Organization).where(Organization.id == tenant.org_id)
    )
    org = result.scalar_one()

    org.content_policy = {
        "pii_action": req.pii_action,
        "injection_action": req.injection_action,
        "dlp_enabled": req.dlp_enabled,
        "outbound_scan": req.outbound_scan,
        "custom_dlp_rules": req.custom_dlp_rules or [],
    }
    await db.flush()

    return {"data": org.content_policy, "message": "Content policy updated"}
