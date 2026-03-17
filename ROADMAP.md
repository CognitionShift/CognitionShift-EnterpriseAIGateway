# CognitionShift Enterprise AI Gateway — Development Roadmap

**INTERNAL ONLY — Do not commit to public repo.**

Last updated: 2026-03-16

---

## Philosophy

Ship a working product fast. Every phase ends with something deployable and demonstrable. No phase depends on having the "whole platform" done. Customers can start using Phase 1 output while we build Phase 2.

**Critical path:** Chat works → Governance works → Safety works → RAG works → Agents work.

A customer who can chat with governed, safe, audited access to frontier models on day one is a customer. Everything else is expansion.

---

## Implementation Sequencing — Build Order

The order matters. Each layer depends on the one below it. Building out of order creates integration debt.

```
1. Core Chat + Streaming Pipeline        ← the product's heartbeat
   └─ Model router, SSE streaming, conversation persistence
   └─ This is what users touch. If this is broken, nothing else matters.

2. Governance Engine (Quotas + Cost)      ← the business model
   └─ Without cost tracking, we can't sell. Without quotas, we can't govern.
   └─ Must be in the request pipeline before any pilot.

3. Content Safety (Inbound → Outbound)    ← the trust layer
   └─ Inbound first (block bad input), then outbound (catch bad output).
   └─ Streaming safety halt depends on (1) being solid.
   └─ Enterprise buyers ask about this in the first meeting.

4. Audit Trail                            ← the compliance backbone
   └─ Append-only, tamper-proof. Every action logged.
   └─ FERPA/HIPAA/SOC 2 auditors will ask for this on day one.

5. Identity (SSO + SCIM)                  ← the enterprise on-ramp
   └─ Institutions won't manage another user database.
   └─ Built-in auth is fine for pilots; SSO is required for contracts.

6. File Management + RAG                  ← the differentiation
   └─ Upload docs → chunk → embed → retrieve → cite.
   └─ This is where the product becomes more than a ChatGPT wrapper.

7. Agent Execution                        ← the moat
   └─ Governed agentic AI is what no one else offers in this space.
   └─ Depends on all prior layers (auth, quotas, safety, audit).
   └─ Build the isolation layer (agent-isolation.md) properly.
```

**Do not skip ahead.** Phase 1 (chat) and Phase 2 (governance + safety) are the minimum viable product. Everything after that is expansion. A pilot customer with governed chat is more valuable than a demo with half-built agents.

---

## Phase 1: Foundation (Weeks 1–4)

**Goal:** A user can log in, chat with a model, and an admin can see what happened.

### Week 1: Project Scaffold & Core Backend

- [ ] Repository structure: monorepo with `backend/`, `frontend/`, `infra/`, `docs/`
- [ ] Python project setup: FastAPI, uvicorn, SQLAlchemy (async), Alembic migrations, pytest
- [ ] PostgreSQL + pgvector schema: `organizations`, `users`, `conversations`, `messages`, `api_keys` (from database-schema.md)
- [ ] Docker Compose for local dev: FastAPI + PostgreSQL + Redis + nginx
- [ ] Health check endpoint (`GET /health`)
- [ ] OpenTelemetry skeleton: basic request tracing, structured logging
- [ ] CI: GitHub Actions — lint (ruff), type check (mypy), test, build Docker image

### Week 2: Authentication & Multi-Tenancy

- [ ] Built-in auth for dev/eval mode: email + password, JWT issuance (no Keycloak yet)
- [ ] User registration, login, session management (15-min access token, 8-hr refresh)
- [ ] Tenant context middleware: every request scoped to `org_id`
- [ ] Row-level security policies in PostgreSQL (defense-in-depth)
- [ ] RBAC: Admin, User roles (expand later)
- [ ] API key generation, hashing (bcrypt), validation, scoping
- [ ] Cross-tenant isolation integration tests (most important tests in the system)

### Week 3: Model Router & Chat API

- [ ] Model provider abstraction: common interface for all providers
- [ ] OpenAI provider implementation (completions + streaming)
- [ ] Anthropic provider implementation (messages + streaming)
- [ ] Google Gemini provider implementation
- [ ] `POST /api/v1/chat/completions` — non-streaming
- [ ] `POST /api/v1/chat/completions` with `stream: true` — SSE response
- [ ] Token counting (tiktoken for OpenAI, provider-specific for others)
- [ ] Model configuration per tenant (which models are enabled, default model)
- [ ] Fallback chain configuration (admin sets primary → fallback sequence)
- [ ] Basic health checking: active checks every 30s per provider

### Week 4: Frontend Shell & Chat UI

- [ ] Next.js project setup: TypeScript, Tailwind CSS, Radix UI primitives
- [ ] Login page (built-in auth mode)
- [ ] Chat interface: conversation list (sidebar), message view, input box
- [ ] SSE streaming: tokens render as they arrive
- [ ] Model selector (dropdown of tenant-enabled models)
- [ ] New conversation, conversation history
- [ ] Responsive layout (desktop + tablet + mobile)
- [ ] Keyboard navigation audit (Tab, Enter, Escape behavior)
- [ ] Skip-to-content link, semantic HTML, ARIA labels on all interactive elements

### Phase 1 Deliverable
- **Demo:** User logs in, selects a model, chats, sees streaming response. Admin can view user list.
- **Deployable:** Docker Compose single-server. Could hand to a customer for eval.
- **Tests:** Auth isolation tests, model router tests, streaming tests, basic accessibility audit.

---

## Phase 2: Governance & Safety (Weeks 5–8)

**Goal:** Admins control who uses what, how much, and content is scanned.

### Week 5: Governance Engine

- [ ] Quota system: org → division → department → team → user hierarchy
- [ ] Budget tracking: per-request cost calculation (input tokens × model price + output tokens × model price)
- [ ] Enforcement modes: hard cap, soft cap, throttle
- [ ] `quota.check()` in request pipeline — runs before every model call
- [ ] Usage dashboard API: `GET /api/v1/admin/usage` with time range, group-by
- [ ] Cost projection: trailing 7d average extrapolated to month/quarter
- [ ] Chargeback report export (CSV)

### Week 6: Content Safety — Inbound

- [ ] Safety pipeline abstraction: pluggable scanners
- [ ] PII detector: regex + NER (SSN, credit card, phone, email, medical record number)
- [ ] Prompt injection detector: known-pattern matching + LLM classifier
- [ ] DLP engine: configurable rules per tenant (custom regex patterns, keyword lists)
- [ ] Toxicity classifier: integrate Azure AI Content Safety (or Perspective API)
- [ ] Pipeline integration: scan runs between auth and model routing
- [ ] Configurable actions per category: block, redact, warn, allow-and-log
- [ ] Content policy configuration per tenant (YAML/JSON in admin UI)

### Week 7: Content Safety — Outbound + Audit Trail

- [ ] Outbound safety scan: runs on completed model response (post-stream)
- [ ] Two-pass streaming safety: partial scan during stream (halt on critical), full scan post-stream
- [ ] PII leakage detection on model output
- [ ] Audit log system: append-only table + async S3 replication
- [ ] Audit events: every request, auth event, admin action, safety event, file access
- [ ] Audit log API for tenant admins: `GET /api/v1/admin/audit` with filters
- [ ] Audit log integrity: SHA-256 hash chain, S3 Object Lock (WORM)
- [ ] CSAM detection integration (PhotoDNA or hash-based): cannot be disabled, mandatory reporting workflow

### Week 8: Admin UI

- [ ] Admin dashboard: usage overview (requests, tokens, cost, trends)
- [ ] User management: list, view details, disable/enable
- [ ] Model configuration: enable/disable models, set fallback chains, set per-group model access
- [ ] Quota management: set budgets at each org hierarchy level
- [ ] Content policy editor: set safety rules per tenant
- [ ] Safety event viewer: recent blocks/redactions with category and action
- [ ] Audit log viewer: searchable, filterable, exportable

### Phase 2 Deliverable
- **Demo:** Admin sets a $50/day budget for a department. Users in that department hit the cap and get a clear message. PII in a prompt is redacted before it reaches the model. Admin reviews safety events and audit trail.
- **Deployable:** Full eval-ready platform. A real institution could run a pilot.
- **Tests:** Governance enforcement tests, safety scanner accuracy tests, audit integrity tests.

---

## Phase 3: Enterprise Identity & File Management (Weeks 9–12)

**Goal:** Real SSO, file uploads, and the beginning of RAG.

### Week 9: Keycloak Integration

- [ ] Keycloak deployment (Docker Compose for dev, Helm for production)
- [ ] SAML 2.0 integration: institution IdP → Keycloak → gateway
- [ ] OIDC integration: for modern enterprise IdPs
- [ ] Auto-provisioning on first login (map IdP attributes → org/division/department/role)
- [ ] SCIM 2.0 endpoint: automated user provisioning/deprovisioning
- [ ] Session binding: user-agent + IP range
- [ ] MFA verification: check `amr` claim from IdP
- [ ] Graceful switchover: built-in auth → Keycloak (config flag, no data migration)

### Week 10: File Management

- [ ] File upload API: multipart upload with size limits
- [ ] Virus/malware scanning on upload (ClamAV or similar)
- [ ] S3 storage backend with per-tenant prefixes
- [ ] File metadata in PostgreSQL (name, type, size, hash, owner, org_id, access)
- [ ] Access control: user-private, group-shared, org-wide (admin-controlled)
- [ ] File processing pipeline: upload → scan → parse → store
- [ ] Document parsing: PDF, DOCX, XLSX, PPTX, CSV, TXT (Apache Tika or unstructured.io)
- [ ] Retention policies: per-tenant auto-deletion schedules
- [ ] File encryption at rest: AES-256 via S3 SSE-KMS

### Week 11: RAG — Indexing

- [ ] Chunking engine: configurable strategies (semantic, fixed-size, paragraph) per document type
- [ ] Embedding generation: OpenAI embeddings API (default), configurable provider
- [ ] pgvector storage: embeddings linked to chunks linked to files linked to tenants
- [ ] Knowledge base management: admin creates KBs, assigns to groups/departments
- [ ] Personal knowledge: users upload docs to their own searchable collection
- [ ] Background indexing: file upload triggers async indexing job via Redis queue
- [ ] Re-indexing on file update/replace

### Week 12: RAG — Retrieval & Chat Integration

- [ ] Retrieval API: given a query, return top-k relevant chunks with scores
- [ ] Context injection: retrieved chunks prepended to model prompt with source attribution
- [ ] Citation generation: model response includes `[1]`, `[2]` markers linked to source docs
- [ ] Citation verification: check that cited content actually exists in retrieved chunks
- [ ] RAG toggle: users can enable/disable RAG per conversation
- [ ] Knowledge base selector: users pick which KBs to search (within their access scope)
- [ ] Frontend: citation rendering with clickable source links, citation sidebar

### Phase 3 Deliverable
- **Demo:** User logs in via their institution's SSO. Uploads a PDF. Asks a question — gets an answer with citations linking back to specific pages in their PDF. Admin manages knowledge bases per department.
- **Deployable:** Production-ready for institutions that need SSO + document Q&A.
- **Tests:** SSO integration tests (mock IdP), file processing pipeline tests, RAG retrieval accuracy tests, citation verification tests.

---

## Phase 4: Agent Execution & Platform Integrations (Weeks 13–18)

**Goal:** Governed agentic AI and LMS integration.

### Weeks 13–14: Agent Orchestrator

- [ ] Agent permission manifest schema
- [ ] Container provisioning on EKS (or Docker for single-server mode)
- [ ] Ephemeral container lifecycle: provision → inject creds → execute → collect results → destroy
- [ ] Gateway proxy: all agent traffic routes through proxy with logging
- [ ] Network policies: deny-all egress except gateway proxy
- [ ] gVisor runtime class for agent containers (stronger isolation than default)
- [ ] Resource limits: CPU, memory, time, network egress per agent
- [ ] Real-time monitoring: anomaly scoring, escape indicators, syscall logging
- [ ] Kill switch: admin can terminate all agents for a tenant instantly
- [ ] Cost attribution: agent model usage charged to triggering user's quota

### Weeks 15–16: Agent Templates & UI

- [ ] Agent template framework: define capabilities, tools, prompts, constraints
- [ ] Research Assistant template: web search (via proxy), summarize, cite
- [ ] Writing Assistant template: style analysis, revision suggestions
- [ ] Code Review template: analyze code, suggest improvements
- [ ] Document Analyzer template: methodology check, calculation verification
- [ ] Agent execution UI: trigger agent, see progress, view results
- [ ] Agent history: past executions, results, cost
- [ ] Admin: manage available agent templates per tenant, set execution limits

### Weeks 17–18: Platform Integrations

- [ ] LTI 1.3 launch: embed gateway within LMS (Canvas, Brightspace, Moodle, Blackboard)
- [ ] Context passing: LTI sends course ID, assignment context
- [ ] Embeddable widget: drop-in `<script>` tag for any web application
- [ ] Webhook API: outbound events for workflow automation (Slack, Teams, ServiceNow)
- [ ] OAuth 2.0 provider: allow third-party apps to authenticate via gateway

### Phase 4 Deliverable
- **Demo:** Student launches AI assistant from within their LMS. Runs a research agent that searches the web, analyzes papers, and produces a cited summary — all governed by institutional policies.
- **Deployable:** Full platform with agentic capabilities for pilot institutions.
- **Tests:** Agent isolation tests (penetration-style), LTI launch flow tests, proxy enforcement tests.

---

## Phase 5: Production Hardening & Compliance (Weeks 19–22)

**Goal:** SOC 2 extension, HECVAT completion, production deployment pipeline.

### Weeks 19–20: Infrastructure & Deployment

- [ ] Terraform modules: VPC, ECS/EKS, RDS, ElastiCache, S3, ALB, WAF, CloudFront
- [ ] Helm chart for Kubernetes-native deployments
- [ ] Docker Compose production profile (single-server with TLS, backups, log rotation)
- [ ] Blue/green deployment pipeline in GitHub Actions
- [ ] Database migration strategy: zero-downtime migrations via Alembic
- [ ] Backup automation: daily full + continuous WAL archiving, cross-region replication
- [ ] DR runbook: tested regional failover procedure
- [ ] Load testing: Locust test suite simulating 1,000 concurrent users

### Weeks 21–22: Compliance & Security

- [ ] HECVAT Full completion (~250 questions — SOC 2 covers 90%+)
- [ ] VPAT (WCAG 2.2 AA): automated axe-core audit + manual screen reader testing
- [ ] Penetration test: engage third-party firm (OWASP methodology)
- [ ] Incident response plan: formalize, assign roles, test with tabletop exercise
- [ ] Business continuity plan: document, test DR procedure
- [ ] DPA template: reviewed by privacy counsel
- [ ] BAA template: reviewed by healthcare privacy counsel
- [ ] Privacy policy and terms of service
- [ ] Responsible disclosure policy: security@cognitionshift.com
- [ ] All runbooks from observability-slos.md written and reviewed

### Phase 5 Deliverable
- **Demo:** Full platform running on production infrastructure with monitoring, alerting, automated backups, and blue/green deployments.
- **Deployable:** Production. Real customers, real data, real compliance posture.
- **Compliance:** HECVAT complete, VPAT published, pen test report available, IRP tested.

---

## Phase 6: Scale & Differentiation (Weeks 23–30)

**Goal:** Self-hosted models, advanced analytics, and the features that win competitive deals.

### Weeks 23–25: Self-Hosted Model Support

- [ ] Ollama integration: model router treats local Ollama as another provider
- [ ] vLLM integration: for GPU-accelerated self-hosted inference
- [ ] Air-gapped deployment profile: everything local, no external API calls
- [ ] Local embedding models for RAG (e.g., BGE, E5)
- [ ] Local content safety classifiers (replace Azure AI Content Safety)
- [ ] GPU resource management: model loading, unloading, queue depth monitoring

### Weeks 26–28: Advanced Analytics & Features

- [ ] Smart model routing: complexity-based auto-routing (simple queries → cheap model)
- [ ] A/B testing framework: route % of traffic to new model for evaluation
- [ ] Advanced cost analytics: model comparison, what-if scenarios, optimization recommendations
- [ ] Conversation analytics: usage patterns, peak times, topic clustering (privacy-preserving)
- [ ] Custom agent builder: admin creates agents via UI (no code)
- [ ] Knowledge base auto-refresh: connect to Drive, SharePoint, institutional repos

### Weeks 29–30: FedRAMP Preparation

- [ ] GovCloud deployment configuration
- [ ] FIPS 140-2 validated crypto modules (CloudHSM)
- [ ] System Security Plan (SSP) drafting
- [ ] Continuous monitoring automation: daily compliance checks, monthly vuln scans
- [ ] 3PAO engagement for FedRAMP assessment
- [ ] POA&M tracking system

### Phase 6 Deliverable
- **Demo:** Institution running fully air-gapped with self-hosted Llama models. Smart routing saves 40% on model costs. Custom agents built by non-technical staff.
- **Deployable:** Enterprise-scale platform handling thousands of concurrent users.
- **Compliance:** FedRAMP assessment in progress.

---

## Milestone Summary

| Milestone | Week | What Ships |
|-----------|------|-----------|
| **M1: First Chat** | 4 | Login, chat, streaming, basic UI |
| **M2: Governed & Safe** | 8 | Quotas, budgets, content safety, audit trail, admin UI |
| **M3: Enterprise-Ready** | 12 | SSO, file upload, RAG with citations |
| **M4: Agentic** | 18 | Governed agents, LMS integration, embeddable widget |
| **M5: Production** | 22 | Infra automation, compliance docs, pen test, DR tested |
| **M6: Differentiated** | 30 | Self-hosted models, smart routing, FedRAMP prep |

---

## Staffing Assumptions

This roadmap assumes:

| Role | Count | Phase Needed |
|------|-------|-------------|
| **Backend Engineer (Python/FastAPI)** | 2 | Phase 1+ |
| **Frontend Engineer (React/Next.js)** | 1 | Phase 1+ |
| **DevOps / Infrastructure** | 1 | Phase 1 (part-time), Phase 5+ (full-time) |
| **Security / Compliance** | 1 | Phase 2+ (part-time), Phase 5 (full-time) |
| **Product / Design** | 1 | Phase 1+ (part-time) |

Eric + Skippy can handle Phase 1 backend + frontend. Hire as scope demands.

---

## Dependencies & Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **Model provider pricing changes** | Cost projections for proposals become wrong | Abstracted provider layer, quick re-pricing. Contractual escalation clauses. |
| **Content safety false positive rate** | User frustration, support load | Tunable thresholds per tenant. False positive feedback loop. Start conservative, loosen with data. |
| **Keycloak complexity** | Delays Phase 3, confusing admin experience | Built-in auth as permanent fallback (not just dev mode). Keycloak hidden behind abstraction. |
| **Agent container escape (0-day)** | Security breach, trust destruction | gVisor + network policies + proxy = defense in depth. Kill switch. No single layer is the only protection. |
| **FedRAMP timeline** | 12-18 month process, delays government sales | Start documentation in Phase 5, formal assessment in Phase 6. Don't block sales on FedRAMP — sell managed deployments in customer's own GovCloud. |
| **Scope creep** | Everything takes longer | Every feature must pass: "Can we sell without this?" If no → defer. |

---

## What's NOT on the Roadmap (Intentionally)

- **Mobile native app** — PWA covers mobile. Native app is a Phase 7+ consideration if customer demand warrants it.
- **Multi-region active-active** — Warm standby is sufficient for initial customers. Active-active is complex and expensive. Add when SLA demands it.
- **Real-time collaboration** — Users don't need to see each other's chats in real-time. This isn't Google Docs.
- **Model fine-tuning** — Customers can fine-tune externally and connect via API. We don't need to build a training pipeline.
- **Marketplace / plugin ecosystem** — Too early. Agent templates cover the extensibility need for now.
