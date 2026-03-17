# CognitionShift Enterprise AI Gateway — Dev Log

## Session: March 16-17, 2026 (Overnight Build)

### Summary
Built a working enterprise AI gateway from scratch in one session. All Phase 1 goals met, plus significant Phase 2 work on governance and content safety.

---

### Phase 1 — COMPLETE ✅

#### 1. Project Scaffold (21:21)
- FastAPI backend with async SQLAlchemy + asyncpg
- Next.js 15 frontend with TypeScript + Tailwind CSS v4
- Docker Compose for all services
- Git initialized with commits at every milestone

#### 2. Database Schema (21:28)
- Alembic migration 001: full enterprise schema
- Tables: organizations, divisions, departments, teams, users, team_memberships, conversations, messages, api_keys, audit_log, usage_log
- Alembic migration 002: quotas table
- PostgreSQL 16 with pgvector extension

#### 3. Auth System (21:33)
- JWT auth: register, login, refresh, /me
- Email/password with bcrypt hashing
- First user in org auto-promoted to admin
- Tenant context middleware (extracts user/org from JWT on every request)
- RBAC: admin, manager, member, viewer, pending roles
- 15-min access tokens, 8-hour refresh tokens

#### 4. Model Router (21:35)
- Provider abstraction layer (BaseProvider interface)
- Anthropic Claude implementation (streaming + non-streaming)
- Models: Claude Sonnet 4, Claude 3.5 Haiku, Claude Opus 4
- Fallback chains: Opus → Sonnet → Haiku
- Health check system per provider
- Model listing endpoint

#### 5. Chat API (21:36)
- `POST /api/v1/conversations/:id/messages` with SSE streaming
- Full message history context sent to model
- Auto-titling from first user message
- Post-stream: saves assistant message + usage log with token counts and cost
- System prompt support per conversation

#### 6. Frontend (21:39)
- **Login/Register** page with email/password
- **Chat** page:
  - Sidebar with conversation list (create, delete, select)
  - Model selector dropdown (Claude Sonnet 4, Haiku, Opus)
  - Streaming message display with real-time token rendering
  - System prompt modal (⚡ persists per-conversation)
  - Markdown rendering: code blocks with language labels, inline code, bold, italic
  - Copy-to-clipboard on AI messages
  - Token count and cost display per message
  - Auto-scroll, keyboard navigation, ARIA labels
  - Dark theme (slate/blue palette)
- **Usage Dashboard** page:
  - Personal and org-wide usage stats
  - Period selector (daily/weekly/monthly)
  - Breakdown by model or day (table view)

#### 7. Integration (21:39)
- Frontend → Backend → Anthropic: fully working end-to-end
- SSE streaming from Anthropic through FastAPI to React
- Token refresh on 401 (auto-retry)

---

### Phase 2 — PARTIAL ✅

#### 8. Governance ✅
- **Usage tracking**: every model call logged with tokens, cost, latency
- **Usage API**: `/usage/me`, `/usage/summary`, `/usage/breakdown` (by model/user/day)
- **Quota system**: 
  - Configurable per-org and per-user
  - Limits: max tokens, max cost, max requests per period
  - Soft enforcement (warn) and hard enforcement (block with 429)
  - Admin CRUD: create, list, update, delete quotas
- **Admin user management**: list, get, update role, deactivate users

#### 9. Content Safety ✅
- **PII detection**: SSN, credit card, email, phone, IP address patterns
- **Prompt injection detection**: 7 pattern categories
  - "Ignore previous instructions"
  - DAN/jailbreak attempts
  - System token injection ([SYSTEM], [INST], etc.)
  - Override safety filter attempts
- **Configurable policy**: block or warn per category
- **Integrated into chat endpoint**: blocks before model call

---

### Test Results
- **29/29 tests passing** (all green)
- `test_auth.py` (7 tests): register, login, duplicate, bad password, /me, unauth, refresh
- `test_model_router.py` (8 tests): provider, model resolution, default, unknown, chat, stream, health, fallbacks
- `test_content_safety.py` (12 tests): SSN, CC, email, no-PII, injection patterns, policy modes
- `test_health.py` (2 tests): health, root

---

### Running Services
All accessible at `http://10.1.1.112:PORT`:

| Service | Container | Port | Status |
|---------|-----------|------|--------|
| PostgreSQL 16 + pgvector | csgateway-postgres | 5432 | ✅ Healthy |
| Redis 7 | csgateway-redis | 6379 | ✅ Healthy |
| FastAPI Backend | csgateway-backend | 8000 | ✅ Healthy |
| Next.js Frontend | csgateway-frontend | 3000 | ✅ Healthy |
| Nginx Proxy | csgateway-nginx | 80 | ✅ Running |

### Quick Access
- **Chat UI**: http://10.1.1.112:3000/chat
- **Login**: http://10.1.1.112:3000/login
- **Dashboard**: http://10.1.1.112:3000/dashboard
- **API Docs**: http://10.1.1.112:8000/docs
- **Test Account**: eric@cognitionshift.com / TestPass123!

### API Endpoints
```
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/refresh
GET  /api/v1/auth/me

GET  /api/v1/models

POST /api/v1/conversations
GET  /api/v1/conversations
GET  /api/v1/conversations/:id
PATCH /api/v1/conversations/:id
DELETE /api/v1/conversations/:id
GET  /api/v1/conversations/:id/messages
GET  /api/v1/conversations/:id/export?format=markdown|json
POST /api/v1/conversations/:id/messages (streaming SSE)

GET  /api/v1/usage/me?period=daily|weekly|monthly
GET  /api/v1/usage/summary
GET  /api/v1/usage/breakdown?group_by=model|user|day

GET  /api/v1/admin/users
GET  /api/v1/admin/users/:id
PATCH /api/v1/admin/users/:id
DELETE /api/v1/admin/users/:id

GET  /api/v1/admin/quotas
POST /api/v1/admin/quotas
PATCH /api/v1/admin/quotas/:id
DELETE /api/v1/admin/quotas/:id

GET  /api/v1/health
GET  /api/v1/health/detailed
```

### Git Log
```
789e500 UI polish: system prompts, markdown rendering, copy-to-clipboard
e16034d Phase 2: Quota system with enforcement, admin endpoints, migration
ed641c1 Frontend dashboard, conversation export, UI polish
02ee836 Phase 2: Usage dashboard API, admin users, content safety (29/29 tests)
09ecf8c Tests: 17/17 passing - auth, model router, health, fallback chains
482439c Frontend: Next.js chat UI with auth, conversations, streaming SSE
5dda9df Phase 1: Backend scaffold, database, auth, model router, streaming chat API
```

### What's Not Done Yet
- [ ] OpenAI provider (no API key available on this machine)
- [ ] Google Gemini provider
- [ ] Rate limiting middleware (Redis-backed)
- [ ] Websocket support (currently SSE only)
- [ ] Email verification flow
- [ ] Password reset flow
- [ ] File upload / vision support
- [ ] Conversation sharing/team features
- [ ] SSO/SAML integration
- [ ] Audit log viewer in frontend
- [ ] More sophisticated PII redaction (vs detection)
- [ ] Load testing
