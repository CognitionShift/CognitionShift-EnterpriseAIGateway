"""Tenant context middleware — extracts user/org from JWT on every request."""

import uuid
from dataclasses import dataclass
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError
from app.database import get_db
from app.core.security import decode_token
from app.models.user import User

security = HTTPBearer(auto_error=False)


@dataclass
class TenantContext:
    user_id: uuid.UUID
    org_id: uuid.UUID
    role: str
    email: str | None = None
    name: str | None = None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> TenantContext:
    """Extract and validate JWT, return tenant context."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = uuid.UUID(payload["sub"])
    org_id = uuid.UUID(payload["org_id"])

    # Verify user still exists and is active
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or deactivated")

    return TenantContext(
        user_id=user.id,
        org_id=user.org_id,
        role=user.role.value,
        email=user.email,
        name=user.name,
    )


async def require_admin(tenant: TenantContext = Depends(get_current_user)) -> TenantContext:
    """Require admin role."""
    if tenant.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return tenant
