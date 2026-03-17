# Testing Strategy

## Principles

1. **Never call real model APIs in CI.** Model API calls are expensive, slow, and non-deterministic. Every test that hits a real provider is a flaky test waiting to happen.

2. **Test the gateway logic, not the model.** We don't need to verify that GPT-4o can answer questions. We need to verify that our routing, quota enforcement, content safety, and streaming pipeline work correctly.

3. **Record once, replay forever.** For integration tests that need realistic model responses, record real responses once and replay them in CI.

4. **Load test before every release.** The streaming pipeline under concurrent load is where bugs hide.

---

## Test Layers

### Unit Tests (pytest)

Fast, isolated, no external dependencies. Run in < 30 seconds.

**What we test:**
- Token counting algorithms
- Cost calculation logic
- Quota enforcement (given usage X and quota Y, is the request allowed?)
- Content safety rules (given input X, is it flagged?)
- Cache key generation
- Fallback chain resolution
- Request/response serialization
- Tenant context isolation
- Data model validation (Pydantic models)

**Mocking strategy:**

```python
# Mock model provider — returns predictable responses
class MockModelProvider:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.call_count = 0
    
    async def stream(self, messages):
        response = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        for token in response.split():
            yield StreamChunk(text=token + " ")
            await asyncio.sleep(0.01)  # simulate streaming delay

# Mock Redis — in-memory dict
class MockRedis:
    def __init__(self):
        self.store = {}
    
    async def get(self, key):
        return self.store.get(key)
    
    async def set(self, key, value, ex=None):
        self.store[key] = value

# Fixture for tenant context
@pytest.fixture
def tenant():
    return TenantContext(
        org_id=uuid4(),
        user_id=uuid4(),
        division_id=uuid4(),
        department_id=uuid4(),
    )
```

### Integration Tests (pytest + testcontainers)

Test component interactions with real databases but mock model providers. Run in < 5 minutes.

**Infrastructure:** [testcontainers-python](https://github.com/testcontainers/testcontainers-python) spins up PostgreSQL and Redis in Docker for each test run. Tests get a clean database every time.

**What we test:**
- Full request pipeline: HTTP request → auth → quota check → model call (mocked) → response → persist → audit
- Database migrations (Alembic up/down)
- Multi-tenant isolation (create two orgs, verify data doesn't leak)
- Quota enforcement end-to-end (send requests, verify counter updates, verify rejection at limit)
- File upload → parse → embed → RAG query pipeline
- SSE streaming end-to-end (send request, verify SSE events arrive correctly)
- Session management (login, refresh, logout)
- Cache hit/miss behavior

```python
@pytest.fixture
async def app(postgres_container, redis_container):
    """Full application with real DB but mocked model providers."""
    config = TestConfig(
        database_url=postgres_container.get_connection_url(),
        redis_url=redis_container.get_connection_url(),
        model_provider=MockModelProvider(["Hello, how can I help you today?"]),
    )
    app = create_app(config)
    
    # Run migrations
    await run_migrations(config.database_url)
    
    # Seed test data
    await seed_test_org(app)
    
    yield app

async def test_chat_message_creates_audit_entry(app, auth_headers):
    # Send a chat message
    response = await app.client.post(
        "/api/v1/conversations/test-conv/messages",
        json={"content": "Hello"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    
    # Verify audit log entry was created
    audit = await app.db.fetch_one(
        "SELECT * FROM audit_log WHERE action = 'message.assistant_response' ORDER BY created_at DESC LIMIT 1"
    )
    assert audit is not None
    assert audit["resource_type"] == "conversation"
```

### Recorded Response Tests

For testing with realistic model behavior without API costs:

```python
# Record real responses (run manually, committed to repo)
# python -m tests.record_responses

RECORDED_RESPONSES = {
    "simple_greeting": {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Hello"}],
        "response": "Hello! How can I help you today?",
        "input_tokens": 2,
        "output_tokens": 9,
        "latency_ms": 450,
    },
    "code_generation": {
        "model": "claude-sonnet",
        "messages": [{"role": "user", "content": "Write a Python hello world"}],
        "response": "```python\nprint('Hello, World!')\n```\n\nThis simple program...",
        "input_tokens": 8,
        "output_tokens": 45,
        "latency_ms": 1200,
    },
    # ... more scenarios
}

class RecordedModelProvider:
    """Replays recorded responses matching the input."""
    
    def __init__(self, recordings: dict):
        self.recordings = recordings
    
    async def stream(self, messages):
        # Find matching recording
        for recording in self.recordings.values():
            if recording["messages"] == messages:
                for token in recording["response"].split():
                    yield StreamChunk(text=token + " ")
                    await asyncio.sleep(0.05)
                return
        
        # No recording found — return generic response
        yield StreamChunk(text="I don't have a recorded response for this input.")
```

### End-to-End Tests (Playwright)

Test the full user experience through the browser. Run in < 10 minutes.

**What we test:**
- Login flow (internal auth and SSO redirect)
- Create conversation, send message, see streaming response
- File upload and RAG query
- Admin console: manage users, set quotas, view analytics
- Model switching mid-conversation
- Conversation sharing with a team
- Keyboard navigation and screen reader compatibility (accessibility)
- Mobile responsive behavior

```typescript
// Playwright test example
test('user can send a message and see streaming response', async ({ page }) => {
    await page.goto('/');
    await page.fill('[data-testid="email"]', 'test@example.com');
    await page.fill('[data-testid="password"]', 'testpass');
    await page.click('[data-testid="login"]');
    
    // Create new conversation
    await page.click('[data-testid="new-conversation"]');
    
    // Send message
    await page.fill('[data-testid="message-input"]', 'Hello');
    await page.click('[data-testid="send"]');
    
    // Verify streaming response appears
    await expect(page.locator('[data-testid="assistant-message"]')).toBeVisible();
    await expect(page.locator('[data-testid="assistant-message"]')).toContainText('Hello');
});
```

### Accessibility Tests (axe + Playwright)

Automated WCAG 2.2 AA checks on every page:

```typescript
import AxeBuilder from '@axe-core/playwright';

test('chat page has no accessibility violations', async ({ page }) => {
    await page.goto('/chat');
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
});
```

Run on every page/component. Integrated into CI — a WCAG violation fails the build.

### Load Tests (Locust)

Simulate production-scale concurrent usage.

```python
# locustfile.py
from locust import HttpUser, task, between

class ChatUser(HttpUser):
    wait_time = between(5, 15)  # 5-15 seconds between messages
    
    def on_start(self):
        # Login
        response = self.client.post("/api/v1/auth/login", json={
            "email": f"loadtest-{self.environment.runner.user_count}@test.com",
            "password": "loadtest",
        })
        self.token = response.json()["data"]["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Create conversation
        response = self.client.post("/api/v1/conversations",
            json={"title": "Load Test"},
            headers=self.headers,
        )
        self.conversation_id = response.json()["data"]["id"]
    
    @task(10)
    def send_message(self):
        self.client.post(
            f"/api/v1/conversations/{self.conversation_id}/messages",
            json={"content": "Explain quantum computing briefly"},
            headers=self.headers,
            stream=True,  # SSE
        )
    
    @task(3)
    def list_conversations(self):
        self.client.get("/api/v1/conversations", headers=self.headers)
    
    @task(1)
    def check_usage(self):
        self.client.get("/api/v1/usage/me", headers=self.headers)
```

**Load test targets:**
- 1,000 concurrent users: baseline
- 5,000 concurrent users: peak load
- 10,000 concurrent users: stress test
- Sustained 500 concurrent SSE streams: streaming stability

**Metrics to monitor:**
- P50/P95/P99 response latency (first token)
- SSE stream stability (dropped connections)
- Database connection pool utilization
- Redis memory and operation latency
- CPU and memory per container

### Security Tests

- **OWASP ZAP** — Automated security scan on every deployment to staging
- **SQL injection** — Parameterized queries verified (SQLAlchemy enforces this, but test the edges)
- **XSS** — Content Security Policy headers, output encoding verification
- **Auth bypass** — Attempt to access resources without valid token, with expired token, with token from different org
- **Tenant isolation** — Create resources in Org A, attempt to read from Org B
- **Rate limiting** — Verify rate limits actually reject requests

---

## CI Pipeline

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -e ".[test]"
      - run: pytest tests/unit/ -v --cov=src --cov-report=xml
      - uses: codecov/codecov-action@v4

  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg17
        env:
          POSTGRES_DB: test
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports: ['5432:5432']
      redis:
        image: redis:7-alpine
        ports: ['6379:6379']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -e ".[test]"
      - run: pytest tests/integration/ -v

  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: cd frontend && npm ci && npx playwright install
      - run: docker compose -f docker-compose.test.yml up -d
      - run: cd frontend && npx playwright test
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: frontend/playwright-report/

  accessibility:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: cd frontend && npm ci && npx playwright install
      - run: docker compose -f docker-compose.test.yml up -d
      - run: cd frontend && npx playwright test tests/accessibility/

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ruff mypy
      - run: ruff check src/
      - run: mypy src/ --strict
```

**CI rules:**
- All tests must pass before merge to main
- Code coverage must not decrease
- Accessibility violations fail the build
- Linting (ruff) and type checking (mypy) enforced

---

## Test Data Strategy

### Seed Data

A standard test dataset that creates:
- 2 organizations (for multi-tenant isolation testing)
- 3 divisions, 5 departments, 10 teams per org
- 50 users with various roles
- 100 conversations with message history
- 10 files with various formats
- 2 knowledge bases with indexed documents
- Quota policies at org, division, and team level

### Factories

```python
# Test data factories for on-demand creation
class UserFactory:
    @staticmethod
    def create(org_id: UUID, role: str = "member", **overrides) -> User:
        defaults = {
            "id": uuid4(),
            "org_id": org_id,
            "email": f"user-{uuid4().hex[:8]}@test.com",
            "name": f"Test User {uuid4().hex[:4]}",
            "role": role,
        }
        return User(**{**defaults, **overrides})
```

### Fixtures Reset

Every integration test starts with a clean database (truncate all tables). This is slower than transactions but avoids subtle test pollution from uncommitted state.
