"""Admin user management endpoints."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.database import get_db
from app.middleware.tenant import require_admin, TenantContext
from app.models.user import User, UserRole

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


class UserListItem(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    last_login_at: str | None
    created_at: str

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None


@router.get("")
async def list_users(
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List users in the org (admin only)."""
    stmt = select(User).where(
        User.org_id == tenant.org_id,
        User.deleted_at.is_(None),
    )
    if search:
        stmt = stmt.where(
            User.email.ilike(f"%{search}%") | User.name.ilike(f"%{search}%")
        )
    stmt = stmt.order_by(desc(User.created_at)).offset(offset).limit(limit)

    result = await db.execute(stmt)
    users = result.scalars().all()

    # Count total
    count_stmt = select(func.count()).select_from(User).where(
        User.org_id == tenant.org_id, User.deleted_at.is_(None)
    )
    if search:
        count_stmt = count_stmt.where(
            User.email.ilike(f"%{search}%") | User.name.ilike(f"%{search}%")
        )
    total = (await db.execute(count_stmt)).scalar()

    return {
        "data": [
            {
                "id": str(u.id),
                "email": u.email,
                "name": u.name,
                "role": u.role.value,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.get("/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get user detail (admin only)."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.org_id == tenant.org_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "data": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "created_at": user.created_at.isoformat(),
        }
    }


@router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    req: UserUpdate,
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update user role/settings (admin only)."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.org_id == tenant.org_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.name is not None:
        user.name = req.name
    if req.role is not None:
        try:
            user.role = UserRole(req.role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")

    user.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return {
        "data": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
        }
    }


@router.delete("/{user_id}", status_code=204)
async def deactivate_user(
    user_id: uuid.UUID,
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete (deactivate) a user (admin only)."""
    if user_id == tenant.user_id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    result = await db.execute(
        select(User).where(User.id == user_id, User.org_id == tenant.org_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.deleted_at = datetime.now(timezone.utc)
    await db.flush()
