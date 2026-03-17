"""Tests for new API endpoints added in audit fix."""

import uuid
import pytest
from httpx import AsyncClient


async def register_and_get_headers(client: AsyncClient) -> dict:
    """Register a test user and return auth headers."""
    email = f"test-{uuid.uuid4().hex[:8]}@test.com"
    resp = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "TestPass123!", "name": "Test User",
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- Unauthenticated / system endpoints ---

@pytest.mark.asyncio
async def test_system_version(client: AsyncClient):
    resp = await client.get("/api/v1/system/version")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert data["data"]["version"] == "0.1.0"
    assert data["data"]["api_version"] == "v1"
    assert "meta" in data
    assert "request_id" in data["meta"]
    assert "timestamp" in data["meta"]


@pytest.mark.asyncio
async def test_health_detailed_envelope(client: AsyncClient):
    resp = await client.get("/api/v1/health/detailed")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "meta" in data
    assert data["data"]["checks"]["api"] is True


@pytest.mark.asyncio
async def test_error_envelope_401(client: AsyncClient):
    """Verify 401 errors return standard envelope."""
    resp = await client.get(
        "/api/v1/conversations",
        headers={"Authorization": "Bearer invalid_token"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert "error" in data
    assert "meta" in data
    assert data["error"]["code"] == "http_401"


# --- Authenticated endpoints ---

@pytest.mark.asyncio
async def test_models_list_envelope(client: AsyncClient):
    headers = await register_and_get_headers(client)
    resp = await client.get("/api/v1/models", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "meta" in data
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_conversations_list_envelope(client: AsyncClient):
    headers = await register_and_get_headers(client)
    resp = await client.get("/api/v1/conversations", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "meta" in data
    assert "has_more" in data["meta"]


@pytest.mark.asyncio
async def test_conversation_crud(client: AsyncClient):
    """Test full conversation CRUD with envelopes."""
    headers = await register_and_get_headers(client)

    # Create
    resp = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "Test Conv", "model_id": "claude-sonnet-4-20250514"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "data" in data
    conv_id = data["data"]["id"]

    # Get
    resp = await client.get(f"/api/v1/conversations/{conv_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "Test Conv"

    # Update
    resp = await client.patch(
        f"/api/v1/conversations/{conv_id}",
        headers=headers,
        json={"title": "Updated Title"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "Updated Title"

    # Delete
    resp = await client.delete(f"/api/v1/conversations/{conv_id}", headers=headers)
    assert resp.status_code == 204

    # Verify gone
    resp = await client.get(f"/api/v1/conversations/{conv_id}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_messages_cursor_pagination(client: AsyncClient):
    headers = await register_and_get_headers(client)
    resp = await client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "Pagination Test"},
    )
    conv_id = resp.json()["data"]["id"]

    resp = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"] == []
    assert data["meta"]["has_more"] is False


@pytest.mark.asyncio
async def test_model_detail(client: AsyncClient):
    headers = await register_and_get_headers(client)
    resp = await client.get("/api/v1/models", headers=headers)
    models = resp.json()["data"]
    if not models:
        pytest.skip("No models available")

    model_id = models[0]["id"]
    resp = await client.get(f"/api/v1/models/{model_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == model_id
    assert "capabilities" in data


@pytest.mark.asyncio
async def test_model_health(client: AsyncClient):
    headers = await register_and_get_headers(client)
    resp = await client.get("/api/v1/models", headers=headers)
    models = resp.json()["data"]
    if not models:
        pytest.skip("No models available")

    model_id = models[0]["id"]
    resp = await client.get(f"/api/v1/models/{model_id}/health", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "health" in data
    assert "circuit_breaker" in data


@pytest.mark.asyncio
async def test_model_not_found(client: AsyncClient):
    headers = await register_and_get_headers(client)
    resp = await client.get("/api/v1/models/nonexistent-model", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_auth_logout(client: AsyncClient):
    headers = await register_and_get_headers(client)
    resp = await client.post("/api/v1/auth/logout", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data


@pytest.mark.asyncio
async def test_usage_me(client: AsyncClient):
    headers = await register_and_get_headers(client)
    resp = await client.get("/api/v1/usage/me?period=daily", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "period" in data
    assert "usage" in data
    assert "tokens" in data["usage"]


@pytest.mark.asyncio
async def test_usage_breakdown(client: AsyncClient):
    headers = await register_and_get_headers(client)
    resp = await client.get("/api/v1/usage/breakdown?group_by=model&days=7", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["group_by"] == "model"


@pytest.mark.asyncio
async def test_usage_export(client: AsyncClient):
    headers = await register_and_get_headers(client)
    resp = await client.get("/api/v1/usage/export?days=7", headers=headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_knowledge_base_crud(client: AsyncClient):
    headers = await register_and_get_headers(client)

    # Create
    resp = await client.post(
        "/api/v1/knowledge-bases",
        headers=headers,
        json={"name": "Test KB", "description": "A test knowledge base"},
    )
    assert resp.status_code == 201
    kb_id = resp.json()["data"]["id"]

    # Get
    resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Test KB"

    # Update
    resp = await client.patch(
        f"/api/v1/knowledge-bases/{kb_id}",
        headers=headers,
        json={"name": "Updated KB"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Updated KB"

    # List
    resp = await client.get("/api/v1/knowledge-bases", headers=headers)
    assert resp.status_code == 200
    assert any(kb["id"] == kb_id for kb in resp.json()["data"])

    # Delete
    resp = await client.delete(f"/api/v1/knowledge-bases/{kb_id}", headers=headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_resilience_circuit_breaker():
    """Unit test circuit breaker logic."""
    from app.services.resilience import CircuitBreaker

    cb = CircuitBreaker()
    provider = "test_provider"

    assert cb.get_state(provider) == "closed"
    assert cb.is_available(provider) is True

    # Record failures up to threshold
    for i in range(4):
        cb.record_failure(provider)
        assert cb.get_state(provider) == "closed"

    # Fifth failure trips the circuit
    cb.record_failure(provider)
    assert cb.get_state(provider) == "open"
    assert cb.is_available(provider) is False

    # Success resets
    cb.record_success(provider)
    assert cb.get_state(provider) == "closed"
    assert cb.is_available(provider) is True


@pytest.mark.asyncio
async def test_resilience_health_tracker():
    """Unit test passive health tracker."""
    from app.services.resilience import PassiveHealthTracker

    tracker = PassiveHealthTracker()
    provider = "test_provider"

    assert tracker.status(provider) == "unknown"

    # Record healthy requests
    for _ in range(10):
        tracker.record(provider, success=True, latency_ms=100)
    assert tracker.status(provider) == "healthy"

    stats = tracker.get_stats(provider)
    assert stats["requests"] == 10
    assert stats["error_rate"] == 0.0
    assert stats["avg_latency_ms"] == 100


@pytest.mark.asyncio
async def test_response_envelope_helpers():
    """Unit test response envelope functions."""
    from app.core.response import make_meta, success_response, error_response

    meta = make_meta()
    assert "request_id" in meta
    assert "timestamp" in meta

    resp = success_response({"key": "value"})
    body = resp.body
    import json
    data = json.loads(body)
    assert data["data"] == {"key": "value"}
    assert "meta" in data

    err = error_response("test_error", "Something went wrong", status_code=400)
    err_data = json.loads(err.body)
    assert err_data["error"]["code"] == "test_error"
    assert err_data["error"]["message"] == "Something went wrong"
