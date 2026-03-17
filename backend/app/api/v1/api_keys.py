"""API key management endpoints — for programmatic access."""

import uuid
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from app.database import get_db
from app.middleware.tenant import get_current_user, TenantContext
from app.models.api_key import ApiKey

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1)
    scopes: list[str] = Field(default=["chat", "files", "agents"])
    expires_in_days: int | None = Field(default=90, ge=1, le=365)


@router.post("", status_code=201)
async def create_api_key(
    req: ApiKeyCreate,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key. The raw key is only shown once."""
    raw_key = f"csg_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]

    expires_at = None
    if req.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=req.expires_in_days)

    api_key = ApiKey(
        user_id=tenant.user_id,
        org_id=tenant.org_id,
        name=req.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=req.scopes,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.flush()

    return {
        "data": {
            "id": str(api_key.id),
            "name": api_key.name,
            "key": raw_key,  # Only shown once!
            "key_prefix": key_prefix,
            "scopes": req.scopes,
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
        "warning": "Save this key now — it won't be shown again.",
    }


@router.get("")
async def list_api_keys(
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's API keys (without the raw key)."""
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.user_id == tenant.user_id,
            ApiKey.revoked_at.is_(None),
        ).order_by(ApiKey.created_at)
    )
    keys = result.scalars().all()

    return {
        "data": [
            {
                "id": str(k.id),
                "name": k.name,
                "key_prefix": k.key_prefix,
                "scopes": k.scopes,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "created_at": k.created_at.isoformat(),
            }
            for k in keys
        ]
    }


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an API key."""
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.user_id == tenant.user_id,
            ApiKey.revoked_at.is_(None),
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    key.revoked_at = datetime.now(timezone.utc)
    await db.flush()
