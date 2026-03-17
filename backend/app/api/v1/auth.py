"""Authentication endpoints."""

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest, UserResponse
from app.services.auth import register_user, authenticate_user, generate_tokens, AuthError
from app.middleware.tenant import get_current_user, TenantContext
from app.core.security import decode_token
from jose import JWTError

logger = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await register_user(db, req.email, req.password, req.name, req.org_slug)
        await db.commit()
        tokens = generate_tokens(user)
        logger.info("user_registered", email=req.email, org=req.org_slug)
        return tokens
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await authenticate_user(db, req.email, req.password, req.org_slug)
        await db.commit()
        tokens = generate_tokens(user)
        logger.info("user_login", email=req.email)
        return tokens
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        from app.models.user import User
        from sqlalchemy import select
        import uuid

        user_id = uuid.UUID(payload["sub"])
        result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return generate_tokens(user)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.get("/me", response_model=UserResponse)
async def me(tenant: TenantContext = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.user import User
    from app.models.organization import Organization
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == tenant.user_id))
    user = result.scalar_one()
    result = await db.execute(select(Organization).where(Organization.id == tenant.org_id))
    org = result.scalar_one()

    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        org_id=user.org_id,
        org_name=org.name,
        created_at=user.created_at.isoformat(),
    )
