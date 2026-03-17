"""Shared test fixtures."""

import os
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Use test database URL — use 'postgres' hostname in Docker, 'localhost' outside
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://csgateway:csgateway@postgres:5432/csgateway"
)
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://redis:6379/1")
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["DEBUG"] = "false"

from app.main import app
from app.database import engine


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    # Dispose engine connections between tests to avoid pool issues
    await engine.dispose()


@pytest.fixture
def auth_headers():
    """Generate valid auth headers for testing."""
    from app.core.security import create_access_token
    token = create_access_token(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role="admin",
    )
    return {"Authorization": f"Bearer {token}"}
