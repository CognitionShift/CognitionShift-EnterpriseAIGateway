"""Authentication service — registration, login, token management."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, UserRole
from app.models.organization import Organization
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.config import get_settings

settings = get_settings()


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code


async def ensure_default_org(db: AsyncSession) -> Organization:
    """Create the default organization if it doesn't exist."""
    result = await db.execute(select(Organization).where(Organization.slug == "default"))
    org = result.scalar_one_or_none()
    if not org:
        org = Organization(name="Default Organization", slug="default")
        db.add(org)
        await db.flush()
    return org


async def register_user(
    db: AsyncSession,
    email: str,
    password: str,
    name: str,
    org_slug: str = "default",
) -> User:
    """Register a new user. First user in an org becomes admin."""
    # Find or create org
    result = await db.execute(select(Organization).where(Organization.slug == org_slug))
    org = result.scalar_one_or_none()
    if not org:
        org = Organization(name=org_slug.replace("-", " ").title(), slug=org_slug)
        db.add(org)
        await db.flush()

    # Check for existing user
    result = await db.execute(
        select(User).where(User.org_id == org.id, User.email == email, User.deleted_at.is_(None))
    )
    if result.scalar_one_or_none():
        raise AuthError("User with this email already exists", 409)

    # First user in org is admin
    result = await db.execute(select(User).where(User.org_id == org.id, User.deleted_at.is_(None)))
    existing_users = result.scalars().all()
    role = UserRole.admin if len(existing_users) == 0 else UserRole.member

    user = User(
        org_id=org.id,
        email=email,
        name=name,
        role=role,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.flush()
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str, org_slug: str = "default") -> User:
    """Validate credentials and return user."""
    result = await db.execute(select(Organization).where(Organization.slug == org_slug))
    org = result.scalar_one_or_none()
    if not org:
        raise AuthError("Invalid credentials")

    result = await db.execute(
        select(User).where(User.org_id == org.id, User.email == email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user or not user.password_hash:
        raise AuthError("Invalid credentials")

    if not verify_password(password, user.password_hash):
        raise AuthError("Invalid credentials")

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()
    return user


def generate_tokens(user: User) -> dict:
    """Generate access + refresh token pair."""
    access = create_access_token(user.id, user.org_id, user.role.value)
    refresh = create_refresh_token(user.id, user.org_id)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }
