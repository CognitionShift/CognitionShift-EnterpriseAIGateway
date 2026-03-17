# Design Doc Compliance Audit

**Date:** 2026-03-16
**Auditor:** Skippy
**Codebase:** 6,296 lines Python backend, 2,390 lines TypeScript frontend

---

## API Contract (api-contract.md) — 60+ endpoints specified

### Authentication (6 endpoints specified)
- [x] `POST /auth/login` — implemented
- [x] `POST /auth/refresh` — implemented
- [x] `GET /auth/me` — implemented
- [ ] `POST /auth/logout` — **MISSING** (token invalidation)
- [ ] `GET /auth/sso/redirect` — MISSING (Phase 3, acceptable)
- [ ] `POST /auth/sso/callback` — MISSING (Phase 3, acceptable)
- [x] `POST /auth/register` — implemented (not in spec but needed for dev mode)

### Chat (10 endpoints specified)
- [x] `POST /conversations` — implemented
- [x] `GET /conversations` — implemented
- [ ] `GET /conversations/:id` — **MISSING** (get single conversation with messages)
- [ ] `PATCH /conversations/:id` — **MISSING** (update title, model, pin, archive)
- [x] `DELETE /conversations/:id` — implemented
- [x] `POST /conversations/:id/messages` — implemented (streaming + non-streaming)
- [x] `GET /conversations/:id/messages` — implemented
- [ ] `POST /conversations/:id/share` — **MISSING**
- [ ] `DELETE /conversations/:id/share` — **MISSING**
- [ ] `GET /conversations/:id/export` — **MISSING** (frontend has export but no backend endpoint)

### Models (4 endpoints specified)
- [x] `GET /models` — implemented
- [ ] `GET /models/:id` — **MISSING**
- [ ] `GET /models/:id/health` — **MISSING**
- [ ] `POST /models/:id/estimate` — **MISSING**

### Files (6 endpoints specified)
- [x] `POST /files/upload` — implemented
- [x] `GET /files` — implemented
- [x] `GET /files/:id` — implemented
- [ ] `GET /files/:id/download` — **MISSING**
- [x] `DELETE /files/:id` — implemented
- [ ] `POST /files/:id/share` — **MISSING**

### Knowledge Bases (8 endpoints specified)
- [x] `POST /knowledge-bases` — implemented
- [x] `GET /knowledge-bases` — implemented
- [ ] `GET /knowledge-bases/:id` — **MISSING** (single KB detail)
- [ ] `PATCH /knowledge-bases/:id` — **MISSING**
- [ ] `DELETE /knowledge-bases/:id` — **MISSING**
- [ ] `POST /knowledge-bases/:id/documents` — **MISSING** (doc management)
- [ ] `GET /knowledge-bases/:id/documents` — **MISSING**
- [ ] `POST /knowledge-bases/:id/search` — **MISSING** (semantic search)

### Governance & Usage (7 endpoints specified)
- [x] `GET /admin/quotas` — implemented
- [x] `POST /admin/quotas` — implemented
- [x] `PATCH /admin/quotas/:id` — implemented
- [ ] `DELETE /admin/quotas/:id` — **MISSING**
- [ ] `GET /usage/me` — **MISSING** (user's own usage + remaining quota)
- [x] `GET /usage/summary` — implemented (partial)
- [ ] `GET /usage/breakdown` — **MISSING** (by model/division/department)
- [ ] `GET /usage/export` — **MISSING**
- [ ] `GET /usage/projection` — **MISSING**

### Admin — Users & Org Hierarchy (19 endpoints specified)
- [x] `GET /admin/users` — implemented
- [ ] `GET /admin/users/:id` — **MISSING**
- [ ] `PATCH /admin/users/:id` — **MISSING**
- [ ] `DELETE /admin/users/:id` — **MISSING**
- [ ] All Division CRUD (4 endpoints) — **MISSING**
- [ ] All Department CRUD (4 endpoints) — **MISSING**
- [ ] All Team CRUD + membership (5 endpoints) — **MISSING**

### Admin — Models & Providers (7 endpoints specified)
- [x] `GET /admin/models` — implemented
- [x] `PATCH /admin/models` — implemented
- [ ] `GET /admin/providers` — **MISSING**
- [ ] `POST /admin/providers` — **MISSING**
- [ ] `PATCH /admin/providers/:id` — **MISSING**
- [ ] `DELETE /admin/providers/:id` — **MISSING**
- [ ] `POST /admin/providers/:id/test` — **MISSING**

### Admin — Content Safety (4 endpoints specified)
- [x] `GET /admin/content-policy` — implemented
- [x] `PUT /admin/content-policy` — implemented
- [ ] `GET /admin/safety-events` — **MISSING** (list safety events)
- [ ] `GET /admin/safety-events/:id` — **MISSING** (event detail)

### Admin — Audit (2 endpoints specified)
- [x] `GET /admin/audit-log` — implemented
- [x] `GET /admin/audit-log/export` — implemented

### Admin — Analytics (5 endpoints specified)
- [x] `GET /admin/analytics/overview` — implemented
- [ ] `GET /admin/analytics/adoption` — **MISSING**
- [ ] `GET /admin/analytics/models` — **MISSING**
- [ ] `GET /admin/analytics/costs` — **MISSING**
- [ ] `GET /admin/analytics/safety` — **MISSING**

### Agents (9 endpoints specified)
- [x] `GET /agents/templates` — implemented
- [x] `GET /agents/templates/:slug` — implemented
- [x] `POST /agents/run/:slug` — implemented
- [x] `GET /agents/executions` — implemented
- [x] `GET /agents/executions/:id` — implemented
- [ ] `POST /agents/runs/:id/kill` — **MISSING**
- [ ] `GET /agents/runs/:id/logs` — **MISSING** (SSE stream of agent logs)
- [ ] `POST /admin/agents/templates` — implemented but under /agents/templates
- [ ] `GET /admin/agents/runs` — **MISSING** (org-wide runs)

### Health & System (3 endpoints specified)
- [x] `GET /health` — implemented
- [ ] `GET /health/detailed` — **MISSING** (DB, Redis, providers check)
- [ ] `GET /system/version` — **MISSING**

### API Contract Patterns
- [ ] **Consistent response envelope** — NOT consistent. Some return `{"data": ...}`, others return raw lists/objects.
- [ ] **Cursor-based pagination** — NOT implemented. Using offset/limit everywhere.
- [ ] **Rate limit headers** — NOT in responses (rate limiting exists but no headers).
- [ ] **Error envelope** — Inconsistent. Some use `{"detail": ...}`, should use `{"error": {"code": ..., "message": ...}}`.

---

## Architecture (architecture.md) — Core Components

### Multi-Tenant Model
- [x] Org → Division → Department → Team hierarchy — DB models exist
- [x] `org_id` on all tenant-scoped tables — implemented
- [ ] **Row-level security (RLS) in PostgreSQL** — NOT implemented (only app-level filtering)
- [ ] Policy inheritance down hierarchy — NOT implemented

### Identity & Access
- [x] Built-in auth (dev mode) — implemented
- [x] JWT with refresh — implemented
- [ ] Session binding (IP + user-agent) — NOT implemented
- [ ] Concurrent session limit — NOT implemented
- [ ] Auto-deprovisioning — NOT implemented

### Governance Engine
- [x] Quota system with org/user levels — implemented
- [x] Hard/soft enforcement — implemented
- [ ] Division/department/team level quotas — NOT implemented (only org and user)
- [ ] Throttle enforcement mode — NOT implemented
- [ ] Escalation workflow — NOT implemented
- [ ] Cost projection engine — NOT implemented
- [ ] Model cost comparison for users — NOT implemented
- [ ] Smart/complexity-based routing — NOT implemented

### Content Safety
- [x] PII detection (regex) — implemented
- [x] Prompt injection detection (regex) — implemented
- [x] Outbound safety scanning — implemented
- [ ] **Toxicity classifier** — NOT implemented (no ML-based classification)
- [ ] **CSAM detection** — NOT implemented (mandatory per threat model)
- [ ] DLP custom rules per tenant — partial (global only)
- [ ] Two-pass streaming safety — NOT implemented (only post-stream scan)
- [ ] Content safety metrics/logging to audit trail — NOT connected

### File Management
- [x] File upload — implemented
- [x] Text extraction — implemented (TXT, CSV, PDF, DOCX, MD, JSON)
- [ ] **Virus/malware scanning** — NOT implemented
- [ ] File access scoping (user/group/department/org) — NOT implemented
- [ ] Retention policy enforcement — NOT implemented
- [ ] Hard delete with verification — NOT implemented
- [ ] File sharing — NOT implemented

### RAG
- [x] Knowledge base management — implemented
- [x] Text chunking — implemented (paragraph-aware)
- [ ] **Embedding generation** — NOT implemented (pgvector ready, no embeddings)
- [ ] **Semantic search** — NOT implemented (keyword only)
- [ ] Citation generation with source links — NOT implemented
- [ ] Citation verification — NOT implemented
- [ ] KB auto-refresh from external sources — NOT implemented

### Agent Execution
- [x] Agent templates — implemented (5 built-in)
- [x] Agent execution with cost tracking — implemented
- [ ] **Ephemeral container execution** — NOT implemented (runs in-process)
- [ ] Network isolation — NOT implemented
- [ ] Permission manifests — NOT implemented
- [ ] Scoped credential injection — NOT implemented
- [ ] Kill switch — NOT implemented
- [ ] Multi-step agent execution — NOT implemented (single model call)
- [ ] Real-time monitoring — NOT implemented

### External Integration
- [ ] LTI 1.3 — NOT implemented (Phase 4)
- [x] Embeddable widget — implemented
- [x] Webhook system — implemented
- [ ] Webhook events emitted from pipeline — NOT connected (registration only)

### Accessibility
- [ ] Skip-to-content link — NOT implemented
- [ ] Focus management on route changes — NOT implemented
- [ ] Screen reader tested — NOT tested
- [ ] Color contrast audit — NOT audited
- [ ] Keyboard navigation complete — PARTIAL
- [ ] ARIA labels on all interactive elements — PARTIAL

### Observability
- [ ] OpenTelemetry instrumentation — NOT implemented (structlog only)
- [x] Prometheus /metrics endpoint — implemented
- [ ] Distributed tracing — NOT implemented
- [ ] Grafana dashboards — NOT implemented

---

## Model Resilience (model-resilience.md)

- [x] Active health checks — implemented (basic)
- [ ] **Passive health monitoring** — NOT implemented (no sliding window tracking)
- [x] Fallback chains — implemented
- [ ] **Circuit breaker** — NOT implemented
- [ ] **Retry logic with exponential backoff** — NOT implemented
- [ ] Provider-specific error normalization — NOT implemented
- [x] Fallback notification in response — NOT implemented (meta field missing)

---

## Streaming Architecture (streaming-architecture.md)

- [x] SSE streaming — implemented
- [x] Token-by-token delivery — implemented
- [ ] **Pre-flight phase** (validate, quota, safety before stream) — PARTIAL (quota yes, safety yes, but not as explicit pipeline)
- [ ] **Post-stream content safety** — implemented but not integrated into stream response
- [ ] **Concurrent stream limit per user** — NOT implemented
- [ ] **Keepalive heartbeat** — NOT implemented
- [ ] **Timeout handling** — NOT implemented
- [ ] **Token counting during stream** — NOT implemented (only at end)

---

## Database Schema (database-schema.md)

- [x] Core tables match spec — mostly
- [ ] **Soft deletes enforced everywhere** — PARTIAL (deleted_at exists but not all queries filter)
- [ ] **Audit trail as separate append-only** — PARTIAL (audit table exists, not truly append-only)
- [ ] **Vector embeddings table** — NOT created
- [ ] **Model configurations table** — NOT created (hardcoded in code)
- [ ] **Content safety events table** — NOT created
- [ ] **Webhook delivery log table** — NOT created

---

## Summary

**Endpoints implemented:** ~28 of 60+ specified (47%)
**Major architectural gaps:** RLS, circuit breaker, embeddings/semantic search, container-based agents, CSAM detection, OpenTelemetry
**Frontend gaps:** Accessibility, responsive, error handling, missing pages for many admin functions

### Priority Fixes (what matters most for a demo/pilot)
1. Response envelope consistency across all endpoints
2. Missing CRUD endpoints (conversation get/update, user management, KB management)
3. OpenAI provider (customers expect it)
4. Usage/me endpoint (users need to see their quota)
5. Detailed health check
6. Frontend accessibility (skip-to-content, focus management, ARIA)
7. Frontend error handling (toasts, error boundaries)
8. Chat UX (show token usage, cost, model indicator on messages)
9. Outbound safety integrated into streaming
10. Cursor-based pagination on list endpoints
