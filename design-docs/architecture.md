# CognitionShift Enterprise AI Gateway
## Design Document v0.1

**Authors:** Eric Whyne, Data Machines / CognitionShift
**Date:** March 16, 2026
**Status:** DRAFT — Architecture & Vision

---

## 1. Vision

CognitionShift Enterprise AI Gateway is a deployable enterprise platform that gives organizations secure, governed, model-agnostic access to frontier AI capabilities. It is designed from the ground up for regulated environments — education (FERPA), government (FedRAMP), healthcare (HIPAA), and financial services (SOC 2) — where AI adoption is constrained not by demand but by the absence of trust, governance, and control.

The platform is not a chatbot wrapper. It is an **AI operations layer** that sits between an organization's users and the frontier model ecosystem, providing:

- **Governance** — Who can use what, how much, and at what cost
- **Safety** — Content filtering, DLP, prompt injection defense, audit trails
- **Flexibility** — Any model, any provider, including self-hosted
- **Extensibility** — Agentic workflows with sandboxed execution
- **Compliance** — SOC 2, FedRAMP, FERPA, HIPAA, WCAG 2.2 from architecture, not afterthought

**The core insight:** Every enterprise will need an AI gateway. The question is whether they build it themselves, buy it from a model vendor (and get locked in), or deploy a platform purpose-built for governance and flexibility. CognitionShift is that platform.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Web Chat │  │ LMS/LTI  │  │ REST API │  │ Agent UI │           │
│  │   (UI)   │  │  Plugin  │  │ (Custom) │  │Dashboard │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │              │              │              │                 │
└───────┼──────────────┼──────────────┼──────────────┼─────────────────┘
        │              │              │              │
┌───────▼──────────────▼──────────────▼──────────────▼─────────────────┐
│                     GATEWAY CORE                                     │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    API GATEWAY / LOAD BALANCER                 │  │
│  │              (Auth, Rate Limiting, TLS Termination)            │  │
│  └────────────────────────┬───────────────────────────────────────┘  │
│                           │                                          │
│  ┌────────────────────────▼───────────────────────────────────────┐  │
│  │                    IDENTITY & ACCESS                           │  │
│  │  Keycloak (SAML/OIDC/LDAP/SCIM) → Session Management         │  │
│  │  Multi-Tenant Context (Institution → Campus → Dept → Group)   │  │
│  └────────────────────────┬───────────────────────────────────────┘  │
│                           │                                          │
│  ┌────────────┐  ┌───────▼────────┐  ┌────────────────────────┐     │
│  │  CONTENT   │  │    REQUEST     │  │     GOVERNANCE         │     │
│  │  SAFETY    │◄─┤    PIPELINE    ├─►│     ENGINE             │     │
│  │            │  │                │  │                        │     │
│  │ • DLP      │  │ • Validate    │  │ • Quota check          │     │
│  │ • PII scan │  │ • Enrich      │  │ • Cost estimate        │     │
│  │ • Toxicity │  │ • Route       │  │ • Budget enforcement   │     │
│  │ • Jailbreak│  │ • Log         │  │ • Policy evaluation    │     │
│  │ • CSAM     │  │ • Cache       │  │ • Chargeback tracking  │     │
│  └────────────┘  └───────┬────────┘  └────────────────────────┘     │
│                          │                                           │
│  ┌───────────────────────▼───────────────────────────────────────┐   │
│  │                    MODEL ROUTER                               │   │
│  │                                                               │   │
│  │  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │   │
│  │  │ OpenAI  │ │Anthropic │ │ Google │ │  Open  │ │Custom/ │  │   │
│  │  │ GPT-4o  │ │ Claude   │ │ Gemini │ │ Source │ │Finetuned│ │   │
│  │  │ o3      │ │ Opus     │ │ 2.5Pro │ │ Llama  │ │ Models │  │   │
│  │  └─────────┘ └──────────┘ └────────┘ └────────┘ └────────┘  │   │
│  │                                                               │   │
│  │  • Fallback chains    • Cost-optimized routing                │   │
│  │  • Load balancing     • Provider health monitoring            │   │
│  │  • Response caching   • Token counting & attribution          │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    RESPONSE PIPELINE                           │  │
│  │                                                                │  │
│  │  Model Response → Content Safety Scan → DLP Scan →            │  │
│  │  Citation Verification → Token Accounting → Audit Log →       │  │
│  │  Deliver to Client                                            │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                     DATA & SERVICES LAYER                            │
│                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐    │
│  │PostgreSQL│  │  Redis   │  │   S3     │  │  Vector Store    │    │
│  │+ pgvector│  │ (Cache,  │  │ (Files,  │  │  (RAG Embeddings)│    │
│  │(Primary) │  │  Queues) │  │  Audit)  │  │                  │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘    │
│                                                                      │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐     │
│  │    Audit Store       │  │    Observability                 │     │
│  │  (Append-only,       │  │  OpenTelemetry → Grafana         │     │
│  │   tamper-proof)      │  │  Alerts, Dashboards, Traces      │     │
│  └──────────────────────┘  └──────────────────────────────────┘     │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                     AGENT EXECUTION LAYER                            │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    AGENT ORCHESTRATOR                        │   │
│  │                                                              │   │
│  │  • Receives agent workflow requests from Gateway Core        │   │
│  │  • Provisions ephemeral containers on EKS/Fargate            │   │
│  │  • Injects scoped credentials via Vault/KMS                  │   │
│  │  • Applies network policies (gateway-only egress)            │   │
│  │  • Monitors execution, enforces timeouts                     │   │
│  │  • Collects results, destroys container                      │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                             │                                        │
│  ┌──────────────────────────▼───────────────────────────────────┐   │
│  │                    AGENT CONTAINERS (Ephemeral)              │   │
│  │                                                              │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │   │
│  │  │ Research │  │ Writing  │  │  Code    │  │  Custom  │   │   │
│  │  │ Agent    │  │ Tutor    │  │ Sandbox  │  │  Agent   │   │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │   │
│  │       │              │              │              │         │   │
│  │  ALL TRAFFIC ROUTES THROUGH GATEWAY PROXIES ONLY            │   │
│  │       │              │              │              │         │   │
│  │  ┌────▼──────────────▼──────────────▼──────────────▼─────┐  │   │
│  │  │              GATEWAY PROXY LAYER                       │  │   │
│  │  │  • Model access (via Gateway Core model router)        │  │   │
│  │  │  • Web browsing (via audited proxy)                    │  │   │
│  │  │  • File access (via Gateway file management API)       │  │   │
│  │  │  • Code execution (sandboxed, resource-limited)        │  │   │
│  │  │  • NO direct internet access                           │  │   │
│  │  │  • ALL actions logged to audit trail                   │  │   │
│  │  └───────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Components

### 3.1 Multi-Tenant Data Model

```
Institution (e.g., University of Maine System)
  ├── Campus (e.g., UMaine Orono, USM, UMA)
  │     ├── Department (e.g., Computer Science, English)
  │     │     ├── Group (e.g., CS 101 Fall 2026, Research Lab)
  │     │     │     ├── User (student, faculty, staff, admin)
  │     │     │     └── User
  │     │     └── Group
  │     └── Department
  └── Campus

Each level inherits and can override:
  - Model access policies
  - Usage quotas and budgets
  - Content safety rules
  - Data retention policies
  - Feature flags
```

**Tenant isolation is the foundation, not a feature.** Every database query, every API call, every file access is scoped to the tenant context. There is no "global" mode where data leaks across institutions.

### 3.2 Identity & Access Management

**Supported Protocols:**
- SAML 2.0 / Shibboleth (higher ed standard)
- OIDC / OAuth 2.0 (modern enterprise)
- LDAP / Active Directory (legacy)
- SCIM 2.0 (automated provisioning/deprovisioning)

**Implementation:** Keycloak as the identity broker. Each institution configures their IdP once. The gateway handles the rest.

**Authentication Flow (transparent to users):**
1. User clicks platform URL
2. Gateway redirects → Keycloak → Institution's IdP
3. User sees their familiar login page (only visible step)
4. IdP returns SAML/OIDC assertion with attributes
5. Keycloak maps: campus, department, role, groups
6. Gateway auto-provisions user with correct permissions
7. User lands in platform, ready to use

**Lifecycle Management:**
- Auto-provision on first login
- Role sync on subsequent logins
- Auto-deprovision via SCIM when user leaves institution
- Configurable grace period before data deletion

### 3.3 Governance Engine

The governance engine is the economic brain of the platform. It answers: **who can use what, how much, and at what cost.**

#### 3.3.1 Usage Quotas

Quotas are defined at any level of the tenant hierarchy and cascade downward:

```yaml
# Example: University of Maine System
institution:
  monthly_budget: $50,000
  campuses:
    umaine_orono:
      monthly_budget: $25,000
      departments:
        computer_science:
          monthly_budget: $5,000
          groups:
            cs101_fall2026:
              per_user_daily_tokens: 100,000
              per_user_daily_cost: $2.00
              allowed_models: [gpt-4o-mini, claude-sonnet]
            faculty:
              per_user_daily_tokens: unlimited
              per_user_daily_cost: $20.00
              allowed_models: [gpt-4o, claude-opus, gemini-2.5-pro]
```

**Enforcement modes:**
- **Hard cap** — Request rejected when quota exhausted. User sees clear message with reset time.
- **Soft cap** — Requests continue but flagged for admin review. User warned.
- **Throttle** — Requests slow down (increased latency) as budget approaches limit.
- **Escalation** — User can request temporary quota increase from department admin.

#### 3.3.2 Cost Calculator & Projections

Real-time cost tracking with forecasting:

- **Per-request cost estimation** — Before a request is sent to a model, the gateway estimates the cost based on input tokens + expected output tokens. Users can see the estimated cost.
- **Dashboard views** — Institution, campus, department, group, and individual usage with drill-down.
- **Projection engine** — Based on trailing usage patterns, projects monthly/quarterly/annual costs. Alerts when projected costs exceed budgets.
- **Model cost comparison** — "This query would cost $0.02 on GPT-4o-mini vs. $0.15 on Claude Opus." Admins can enable user-visible cost hints.
- **Chargeback reports** — Monthly export for each cost center (department, grant, project) for internal billing.

#### 3.3.3 Smart Model Routing

Not all queries need the most expensive model:

- **Complexity-based routing** — Simple questions (definitions, summaries, translations) auto-route to cost-effective models. Complex reasoning, code generation, and research queries route to frontier models.
- **Admin-configurable rules** — "Route all queries from CS courses to code-optimized models." "Route all queries containing patient data to HIPAA-compliant endpoints only."
- **User override** — If enabled by admin, users can manually select a specific model.
- **A/B testing** — Admins can route a percentage of traffic to a new model for evaluation before full rollout.

### 3.4 Content Safety System

Two-pass scanning: **inbound (user → model)** and **outbound (model → user)**.

#### 3.4.1 Inbound Safety

Before any prompt reaches a model:

| Check | Purpose | Action |
|-------|---------|--------|
| **PII/PHI Detection** | SSNs, credit cards, health records, student IDs | Strip or block, log attempt |
| **Prompt Injection Detection** | Jailbreak attempts, system prompt extraction | Block, flag user for review |
| **CSAM Detection** | Child sexual abuse material indicators | Block immediately, alert admin, log for mandatory reporting |
| **Toxicity/Hate Speech** | Harassment, threats, discrimination | Block or warn based on policy |
| **Policy Violations** | Institution-specific rules (e.g., no weapons instructions) | Configurable per-institution |
| **File Safety** | Malware scan on uploaded files | Block infected files |

#### 3.4.2 Outbound Safety

Before any model response reaches the user:

| Check | Purpose | Action |
|-------|---------|--------|
| **PII Leakage** | Model generating PII from training data | Strip or flag |
| **Harmful Content** | Violence instructions, self-harm, illegal activity | Block, substitute safe response |
| **Copyright Concerns** | Verbatim reproduction of copyrighted text | Flag, provide citation |
| **Citation Verification** | RAG citations match actual source documents | Mark unverified citations |
| **Hallucination Indicators** | Confidence scoring on factual claims | Flag low-confidence assertions |

#### 3.4.3 Content Safety Configuration

Each institution defines their content policy:

```yaml
content_policy:
  strictness: high  # low | medium | high | custom
  
  inbound:
    pii_detection: block_and_strip
    prompt_injection: block
    csam: block_and_report  # mandatory, cannot be disabled
    toxicity_threshold: 0.7
    custom_blocked_topics:
      - weapons_manufacturing
      - drug_synthesis
    
  outbound:
    pii_leakage: strip
    harmful_content: block
    citation_verification: flag_unverified
    
  escalation:
    alert_admin_on: [csam, repeated_injection, pii_breach]
    mandatory_reporting: [csam]
```

**CSAM detection and mandatory reporting cannot be disabled.** This is a non-negotiable platform default.

### 3.5 File Management

Enterprise-grade file handling designed for SOC 2 and FedRAMP:

- **Encrypted at rest** (AES-256) and in transit (TLS 1.3)
- **Virus/malware scanning** on all uploads before processing
- **Access control** — Files scoped to user, group, department, or institution
- **Retention policies** — Configurable per-tenant auto-deletion schedules
- **Audit trail** — Every file access logged (who, when, what, action)
- **Supported formats** — PDF, DOCX, XLSX, PPTX, CSV, TXT, images, audio, video
- **Processing pipeline** — Upload → scan → parse → chunk → embed → index
- **Sharing** — Permission-based sharing within and across groups (admin-controlled)
- **Export** — Users can export all their files and data (data portability)
- **Deletion** — Hard delete with cryptographic verification (for FERPA "right to delete")

### 3.6 RAG (Retrieval-Augmented Generation)

- **Knowledge bases** — Admin-managed document collections per institution/department
- **Personal knowledge** — Users can upload and query their own documents
- **Citation with source links** — Every RAG-assisted response includes clickable citations to source documents with page/section references
- **Citation verification** — Citations are checked against actual indexed content, not hallucinated
- **Embedding models** — Configurable (OpenAI, Cohere, self-hosted)
- **Vector store** — pgvector (primary), with support for Milvus/Qdrant at scale
- **Chunking strategies** — Configurable per-document-type (semantic, fixed-size, paragraph)
- **Freshness** — Knowledge bases can be set to auto-refresh from connected sources (Drive, SharePoint, institutional repositories)

### 3.7 Agent Execution Layer

This is the platform's most differentiated capability — **governed agentic AI**.

#### 3.7.1 Architecture

Agents run in **ephemeral, isolated containers** dynamically provisioned on EKS/Fargate. Each agent:

1. **Has a permission manifest** defining exactly what it can access
2. **Can only reach the gateway** — No direct internet, no lateral network movement
3. **Gets scoped credentials** injected at runtime via AWS Secrets Manager / HashiCorp Vault
4. **Is monitored in real-time** with kill-switch capability
5. **Is destroyed after execution** — No persistent state outside the gateway's control

#### 3.7.2 Agent Capabilities (via Gateway Proxies)

| Capability | Implementation | Governance |
|------------|---------------|------------|
| **Model Access** | Agent calls Gateway model router | Same quota/cost rules as interactive use |
| **Web Browsing** | Gateway web proxy with URL allowlisting | Admin defines allowed domains |
| **File Access** | Gateway file API with scoped permissions | Agent can only access files in its scope |
| **Code Execution** | Sandboxed runtime (Firecracker/gVisor) | CPU, memory, time, network limits |
| **Database Access** | Gateway DB proxy with read-only options | Query logging, result size limits |
| **External APIs** | Gateway API proxy with allowlisted endpoints | Request/response logging |

#### 3.7.3 Agent Templates

Pre-built, customizable agent workflows:

- **Research Assistant** — Web search, paper analysis, literature review with citations
- **Writing Tutor** — Rubric-aware feedback, style analysis, revision suggestions
- **Code Review Agent** — Analyze student code, suggest improvements, check for plagiarism
- **Lab Report Analyzer** — Check methodology, verify calculations, suggest improvements
- **Data Analysis Agent** — Process datasets, generate visualizations, statistical analysis
- **Course Design Assistant** — Generate syllabi, learning objectives, assessment plans
- **Accessibility Checker** — Audit documents and content for accessibility compliance

#### 3.7.4 Agent Lifecycle

```
1. User/System triggers agent workflow
2. Orchestrator validates permissions and budget
3. Orchestrator provisions container on EKS/Fargate
4. Container boots with agent code + permission manifest
5. Credentials injected via Vault/KMS
6. Network policies applied (gateway-only egress)
7. Agent executes, all actions proxied through gateway
8. Results collected, content safety scanned
9. Container destroyed
10. Results delivered to user, cost attributed
```

### 3.8 LMS Integration (LTI 1.3)

First-class integration with Learning Management Systems:

- **LTI 1.3 Tool Provider** — Platform launches directly within Brightspace, Canvas, Blackboard, Moodle
- **Deep Linking** — Instructors embed specific AI tools/agents into course modules
- **Names and Roles Provisioning** — Auto-map LMS roster to platform groups
- **Assignment and Grade Services** — AI-assisted feedback can flow back to the LMS gradebook
- **Context-aware** — The platform knows which course, assignment, and student context it's operating in

### 3.9 Accessibility (WCAG 2.2 AA)

Accessibility is a design constraint, not a retrofit:

- **Semantic HTML** — Proper heading hierarchy, landmarks, ARIA labels
- **Keyboard navigation** — Full functionality without a mouse
- **Screen reader support** — Tested with NVDA, JAWS, VoiceOver
- **Color contrast** — Minimum 4.5:1 ratio for normal text, 3:1 for large text
- **Focus management** — Visible focus indicators, logical tab order
- **Skip navigation** — Skip-to-content links on every page
- **Error identification** — Form errors announced to assistive technology
- **Responsive design** — Functional at 200% zoom, all breakpoints
- **Motion reduction** — Respects `prefers-reduced-motion`
- **VPAT** — Published and maintained with each release

### 3.10 Observability & Operations

- **OpenTelemetry** — Distributed tracing across all components
- **Grafana dashboards** — Real-time system health, usage, costs, errors
- **Alerting** — PagerDuty/Slack/email integration for incidents
- **Health checks** — Every component exposes /health endpoints
- **Automated scaling** — EKS horizontal pod autoscaling based on request volume
- **Zero-downtime deployments** — Blue/green or canary deployment strategies
- **Backup & DR** — Automated cross-region backup, RPO < 1 hour, RTO < 15 minutes

---

## 4. Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Frontend** | SvelteKit | Fast, accessible, SSR, small bundle size |
| **API** | Go or Rust (gateway core) | Performance-critical proxy layer needs low latency |
| **Business Logic** | Python (FastAPI) | ML ecosystem, RAG pipeline, agent orchestration |
| **Identity** | Keycloak | SAML + OIDC + LDAP + SCIM in one |
| **Database** | PostgreSQL + pgvector | Relational + vector search, proven at scale |
| **Cache/Queue** | Redis | Session management, rate limiting, job queues |
| **Object Storage** | S3 (or compatible) | Files, audit logs, backups |
| **Container Orchestration** | EKS / Fargate | Agent execution, application scaling |
| **Secrets** | AWS Secrets Manager / Vault | Agent credential injection |
| **Observability** | OpenTelemetry + Grafana | Tracing, metrics, dashboards |
| **IaC** | Terraform | Reproducible infrastructure |
| **CI/CD** | GitHub Actions | Automated testing, deployment |

### Language Choice: Gateway Core

The model router / proxy layer is the hottest path in the system. Every request flows through it. Two options:

- **Go** — Excellent for network services, goroutines for concurrency, simple deployment (single binary). Strong standard library for HTTP proxying.
- **Rust** — Maximum performance, memory safety, but steeper learning curve and slower iteration.

**Recommendation:** Go for the gateway core (proxy, routing, rate limiting, DLP scanning). Python for everything else (RAG, agent orchestration, admin API, analytics).

---

## 5. Deployment Model

### 5.1 Single-Tenant (Dedicated)

Each institution gets their own isolated infrastructure:

```
AWS Account (Institution-specific)
├── VPC (US region, per data residency requirements)
│   ├── EKS Cluster (gateway + agents)
│   ├── RDS PostgreSQL (Multi-AZ)
│   ├── ElastiCache Redis
│   ├── S3 (encrypted, versioned)
│   ├── Keycloak (institution's IdP config)
│   └── ALB (TLS termination, WAF)
└── CloudWatch / Grafana (monitoring)
```

**Best for:** Large institutions (10K+ users), government, high-security environments.

### 5.2 Multi-Tenant (Shared Infrastructure)

Multiple smaller institutions share infrastructure with logical isolation:

- Shared EKS cluster with namespace-per-tenant
- Shared RDS with row-level security
- Separate S3 buckets per tenant
- Shared Keycloak with realm-per-tenant

**Best for:** Smaller institutions, consortiums, cost-sensitive deployments.

### 5.3 Hybrid

Large campuses get dedicated, smaller satellite campuses share.

---

## 6. Compliance & Certification Roadmap

| Standard | Status | Timeline |
|----------|--------|----------|
| **SOC 2 Type II** | Data Machines certified (4 years) | Extend to gateway platform |
| **FERPA** | Data Machines audited & certified | Built into architecture |
| **FedRAMP** | Architecture designed for compliance | Pursue after initial deployments |
| **HIPAA** | Architecture supports BAA requirements | Enable for healthcare clients |
| **WCAG 2.2 AA** | Design constraint from day one | Audit with each release |
| **HECVAT** | Template ready | Complete per-deployment |
| **ISO 27001** | Aligned with SOC 2 controls | Pursue Year 2 |
| **StateRAMP** | Aligned with FedRAMP | Pursue for state university clients |

---

## 7. Business Model

### 7.1 Pricing Tiers

| Tier | Target | Includes |
|------|--------|----------|
| **Standard** | Small institutions (<5K users) | Multi-tenant, shared infra, email support |
| **Enterprise** | Large institutions (5K-50K users) | Dedicated infra, SSO, SLA, phone support |
| **Government** | Federal/state agencies | FedRAMP-authorized, dedicated, on-call support |
| **Research** | Labs, consortiums | API-first, agent workflows, custom models |

### 7.2 Revenue Components

1. **Platform license** — Annual per-user or flat-rate
2. **Model pass-through** — AI provider costs + margin (transparent markup)
3. **Professional services** — Implementation, custom integrations, training
4. **Managed operations** — 24/7 monitoring, incident response, updates
5. **Agent templates** — Premium pre-built agent workflows

### 7.3 Cost Structure

- **Infrastructure** — AWS compute, storage, networking
- **Model costs** — OpenAI, Anthropic, Google API usage (largest variable cost)
- **Engineering** — Platform development, maintenance, security updates
- **Compliance** — Annual SOC 2 audit, WCAG audits, penetration testing
- **Support** — Customer success, technical support, training

---

## 8. Competitive Positioning

| Competitor | Weakness We Exploit |
|------------|-------------------|
| **Microsoft Copilot** | Locked to Azure/OpenAI. No model choice. Enterprise pricing opaque. |
| **Google Gemini Enterprise** | Locked to Google Cloud. Limited customization. |
| **OpenAI ChatGPT Enterprise** | Single-model vendor. No self-hosted option. Data concerns. |
| **Anthology AI (D2L)** | LMS-vendor bolt-on. Limited model flexibility. Not AI-native. |
| **Generic Open Source (Open WebUI, LibreChat)** | No governance. No compliance. No enterprise support. No agent layer. |

**CognitionShift's moat:**
1. Compliance-first architecture (SOC 2, FERPA, FedRAMP pathway)
2. Model-agnostic with cost governance (no vendor lock-in + budget control)
3. Governed agentic AI (no competitor offers sandboxed, audited agent execution)
4. Education-domain expertise (SETA-Ed, LTI 1.3, rubric-aware tools)
5. Deployable, not SaaS-only (institutions can run it in their own cloud)

---

## 9. Development Roadmap

### Phase 1: Foundation (Weeks 1-6)
- Gateway core (Go): model router, proxy, rate limiting
- Web UI (SvelteKit): chat interface, model selection, file upload
- Auth (Keycloak): OIDC/SAML, auto-provisioning
- Database schema: multi-tenant data model
- Basic admin console: user/group management, model configuration
- Content safety: PII detection, basic toxicity filtering

### Phase 2: Enterprise (Weeks 7-12)
- Governance engine: quotas, budgets, cost tracking, chargeback
- RAG pipeline: document upload, embedding, citation
- File management: encrypted storage, access control, retention policies
- Analytics dashboard: usage, costs, projections
- WCAG 2.2 AA audit and compliance
- LTI 1.3 integration (Brightspace primary)

### Phase 3: Agents (Weeks 13-18)
- Agent orchestrator: EKS provisioning, lifecycle management
- Gateway proxies: web, file, code, model access for agents
- Agent templates: Research, Writing, Code Review
- Agent monitoring dashboard: real-time visibility, kill switch
- Network policy enforcement: gateway-only egress

### Phase 4: Compliance & Scale (Weeks 19-24)
- SOC 2 Type II evidence collection
- HECVAT completion
- VPAT publication
- FedRAMP documentation (initial)
- Load testing at 30K+ concurrent users
- Disaster recovery testing
- Production hardening

---

## 10. UMaine RFP Alignment

This platform is designed to exceed every requirement in RFP 2026-065:

| RFP Requirement | CognitionShift Response |
|-----------------|------------------------|
| Cloud-based SaaS | Dedicated AWS deployment, US-only |
| Model agnosticism | Core architectural principle — any provider, any model |
| FERPA compliance | Built-in data controls, not bolted on |
| SOC 2 Type II | Data Machines certified 4 years; platform inherits controls |
| Zero data retention | Configurable ephemeral mode, architectural guarantee |
| LTI 1.3 | First-class integration, not a plugin |
| Shibboleth SSO | Keycloak bridge, transparent to users |
| Content safety | Two-pass scanning, configurable policies, CSAM mandatory reporting |
| Usage governance | Per-user, per-group, per-department budgets with enforcement |
| Agentic workflows | Sandboxed, governed, audited agent execution |
| Accessibility | WCAG 2.2 AA as design constraint |
| 30,912 FTE | Architecture validated at comparable scale |

---

## 11. Open Questions

1. **Gateway core language** — Go vs. Rust vs. staying pure Python (simplicity vs. performance)
2. **Content safety provider** — Build vs. integrate (OpenAI Moderation API, Anthropic Constitutional AI, AWS Comprehend, custom models)
3. **Pricing model for UMaine** — Flat rate vs. consumption-based vs. hybrid
4. **Agent sandboxing** — Firecracker vs. gVisor vs. EKS pod security policies
5. **Self-hosted model support** — vLLM vs. Ollama vs. TGI for on-premises GPU inference
6. **Mobile experience** — PWA sufficient or native apps needed?
7. **Offline/degraded mode** — What happens when all model providers are down?
