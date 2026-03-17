"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_new_user(client: AsyncClient):
    """New user registration should return tokens."""
    resp = await client.post("/api/v1/auth/register", json={
        "email": f"test-{__import__('uuid').uuid4().hex[:8]}@test.com",
        "password": "TestPass123!",
        "name": "Test User",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """Duplicate email in same org should fail."""
    email = f"dup-{__import__('uuid').uuid4().hex[:8]}@test.com"
    # First registration
    resp1 = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "TestPass123!", "name": "User 1",
    })
    assert resp1.status_code == 200

    # Duplicate
    resp2 = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "TestPass123!", "name": "User 2",
    })
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_login_valid(client: AsyncClient):
    """Valid credentials should return tokens."""
    email = f"login-{__import__('uuid').uuid4().hex[:8]}@test.com"
    # Register
    await client.post("/api/v1/auth/register", json={
        "email": email, "password": "TestPass123!", "name": "Login Test",
    })
    # Login
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": "TestPass123!",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient):
    """Wrong password should return 401."""
    email = f"bad-{__import__('uuid').uuid4().hex[:8]}@test.com"
    await client.post("/api/v1/auth/register", json={
        "email": email, "password": "TestPass123!", "name": "Bad Pass Test",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": "WrongPass!",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoint(client: AsyncClient):
    """Authenticated /me should return user info."""
    email = f"me-{__import__('uuid').uuid4().hex[:8]}@test.com"
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "TestPass123!", "name": "Me Test",
    })
    token = reg.json()["access_token"]

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == email
    assert data["name"] == "Me Test"
    assert data["role"] in ("admin", "member")  # First user is admin, subsequent are member


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient):
    """Unauthenticated /me should return 401."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    """Refresh token should return new access token."""
    email = f"refresh-{__import__('uuid').uuid4().hex[:8]}@test.com"
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "TestPass123!", "name": "Refresh Test",
    })
    refresh_token = reg.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": refresh_token,
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()
