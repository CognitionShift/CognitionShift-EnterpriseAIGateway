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
│  │  Multi-Tenant Context (Org → Division → Dept → Team)   │  │
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
Organization (e.g., Acme Global Corp)
  ├── Division (e.g., North America, EMEA, APAC)
  │     ├── Department (e.g., Engineering, Legal, Marketing)
  │     │     ├── Team (e.g., Platform Engineering, Patent Review)
  │     │     │     ├── User (employee, contractor, admin)
  │     │     │     └── User
  │     │     └── Team
  │     └── Department
  └── Division

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
- SAML 2.0 / Shibboleth (widely used in education and government)
- OIDC / OAuth 2.0 (modern enterprise)
- LDAP / Active Directory (legacy)
- SCIM 2.0 (automated provisioning/deprovisioning)

**Implementation:** Keycloak as the identity broker. Each institution configures their IdP once. The gateway handles the rest.

**Authentication Flow (transparent to users):**
1. User clicks platform URL
2. Gateway redirects → Keycloak → Institution's IdP
3. User sees their familiar login page (only visible step)
4. IdP returns SAML/OIDC assertion with attributes
5. Keycloak maps: division, department, role, teams
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
# Example: Acme Global Corp
organization:
  monthly_budget: $50,000
  divisions:
    north_america:
      monthly_budget: $25,000
      departments:
        engineering:
          monthly_budget: $10,000
          teams:
            platform_engineering:
              per_user_daily_tokens: unlimited
              per_user_daily_cost: $20.00
              allowed_models: [gpt-4o, claude-opus, gemini-2.5-pro]
            contractors:
              per_user_daily_tokens: 100,000
              per_user_daily_cost: $2.00
              allowed_models: [gpt-4o-mini, claude-sonnet]
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
| **PII/PHI Detection** | SSNs, credit cards, health records, employee IDs | Strip or block, log attempt |
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
- **Deletion** — Hard delete with cryptographic verification (compliance with data deletion requirements — FERPA, GDPR, CCPA)

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
- **Writing Assistant** — Style analysis, revision suggestions, document review
- **Code Review Agent** — Analyze code, suggest improvements, enforce coding standards
- **Document Analyzer** — Check methodology, verify calculations, extract insights
- **Data Analysis Agent** — Process datasets, generate visualizations, statistical analysis
- **Workflow Designer** — Generate process documentation, checklists, operational plans
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

### 3.8 External Platform Integration

First-class integration with enterprise platforms via standard protocols:

- **LTI 1.3** — Launch directly within LMS platforms (Brightspace, Canvas, Blackboard, Moodle) for education deployments
- **OAuth 2.0 / OpenID Connect** — Embed within existing enterprise portals and intranets
- **Webhook & Event API** — Integrate with workflow automation (ServiceNow, Jira, Slack, Teams)
- **Embeddable Widget** — Drop-in AI assistant for any web application
- **Context-aware** — The platform understands the originating application context (project, workflow, document)

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
| **Frontend** | Next.js (React) + TypeScript | Mature ecosystem, extensive accessibility libraries (Radix UI, React Aria), large talent pool, SSR + SPA hybrid |
| **Backend** | Python (FastAPI) | Single backend language for entire platform — gateway core, model router, RAG, content safety, agent orchestration, admin API. Async/uvicorn for concurrency. Full ML/AI ecosystem access. |
| **Identity** | Keycloak | Only mature open-source solution covering SAML 2.0 + OIDC + LDAP + SCIM in one deployment |
| **Database** | PostgreSQL + pgvector | Relational + vector search in one database. No separate vector DB to operate. Proven at scale. |
| **Cache/Queue** | Redis | Session management, rate limiting, job queues, pub/sub |
| **Object Storage** | S3 (or compatible) | Files, audit logs, backups. Encrypted, versioned. |
| **Container Orchestration** | EKS | Agent execution, application scaling. Kubernetes-native network policies for agent isolation. |
| **Secrets** | AWS Secrets Manager | Agent credential injection. Zero operational overhead in AWS-native deployments. |
| **Observability** | OpenTelemetry + Grafana | Open standards, self-hostable, distributed tracing across all components |
| **IaC** | Terraform | Reproducible, auditable infrastructure |
| **CI/CD** | GitHub Actions | Integrated with source repository |

### Architecture Pattern

```
Browser → Next.js (SSR shell + React SPA)
              │
              │  REST API calls
              ▼
         FastAPI (Python)
              │
              ├── Model Router (async HTTP proxy to all providers)
              ├── Content Safety (PII/DLP/toxicity scanning)
              ├── Governance Engine (quotas, budgets, cost tracking)
              ├── RAG Pipeline (upload, parse, embed, retrieve)
              ├── Agent Orchestrator (EKS provisioning, lifecycle)
              ├── Admin API (users, groups, policies, analytics)
              └── Audit Logger (append-only to S3)
              │
              ├── PostgreSQL + pgvector (data + embeddings)
              ├── Redis (cache, sessions, rate limits, queues)
              └── S3 (files, audit logs)
```

**Clean separation:** Next.js owns the UI and nothing else. FastAPI owns all business logic, data access, and external integrations. The frontend is a client of the backend API — no business logic split across layers.

### Design Decisions

**Single backend language (Python).** The gateway core, model router, RAG pipeline, content safety, and agent orchestrator all live in one Python process. Inter-component communication is function calls, not network hops. The performance bottleneck in an AI gateway is always the model provider response time (500ms–30s), never the proxy layer. Python's async capabilities with uvicorn handle the concurrency profile comfortably.

**PostgreSQL + pgvector over a separate vector database.** One database to operate, back up, and secure. pgvector handles the embedding search workload at the scale we're targeting (tens of thousands of users, millions of documents). If a deployment scales beyond pgvector's capacity, the vector store interface is abstracted and can be swapped to Milvus or Qdrant without application changes.

**AWS Secrets Manager over HashiCorp Vault.** Vault is powerful but adds operational complexity. For AWS-native deployments, Secrets Manager provides the same agent credential injection capability with zero additional infrastructure. For non-AWS deployments, Vault can be substituted.

**EKS for agent execution.** Kubernetes provides the network policy enforcement, resource limits, and ephemeral container lifecycle management that governed agent execution requires. The team has deep Kubernetes experience from prior DARPA infrastructure work.

---

## 5. Deployment Model

The platform is designed to run anywhere — from a single server for evaluation to a multi-region cloud deployment for production. The deployment unit is a **Helm chart** for Kubernetes environments and a **Docker Compose file** for single-server deployments.

### 5.1 Deployment Options

#### Option A: AWS Managed (Production Default)

For production deployments operated by CognitionShift as a managed service:

```
CloudFront (CDN, edge caching)
    │
ALB (TLS termination, WAF)
    │
ECS Fargate ──── Next.js (2+ tasks, auto-scale)
    │
ECS Fargate ──── FastAPI (2+ tasks, auto-scale)
    │
ECS Fargate ──── Keycloak (2 tasks, HA)
    │
RDS Aurora Serverless v2 (PostgreSQL + pgvector)
ElastiCache Serverless (Redis)
S3 (files, audit logs)
    │
EKS Fargate ──── Agent containers (on-demand, ephemeral)
```

**Best for:** Production deployments, managed service offerings, 1,000+ users.

#### Option B: Kubernetes-Native (Portable)

For organizations that operate their own Kubernetes clusters or require specific cloud/on-prem environments:

```
Kubernetes (EKS / AKS / GKE / OpenShift / k3s / Rancher)
    │
Ingress Controller (nginx/traefik, TLS)
├── Next.js (Deployment + HPA)
├── FastAPI (Deployment + HPA)
├── Keycloak (StatefulSet)
├── PostgreSQL (StatefulSet or operator, e.g., CloudNativePG)
├── Redis (StatefulSet or operator)
└── Agent namespace (dynamic pods, network-isolated)
```

Deployment via Helm chart:

```bash
# Cloud deployment
helm install cognitionshift ./chart \
  --set global.environment=aws \
  --set database.type=rds \
  --set storage.type=s3 \
  --set models.providers={openai,anthropic}

# On-prem deployment
helm install cognitionshift ./chart \
  --set global.environment=onprem \
  --set database.type=internal \
  --set storage.type=minio \
  --set models.providers={ollama} \
  --set models.ollama.url=http://gpu-server:11434
```

**Best for:** Organizations with existing Kubernetes infrastructure, multi-cloud requirements, or on-premises mandates.

| Environment | Kubernetes Distribution | Storage Backend |
|---|---|---|
| AWS | EKS | RDS, S3, ElastiCache |
| Azure | AKS | Azure Database for PostgreSQL, Blob Storage |
| GCP | GKE | Cloud SQL, Cloud Storage |
| On-Prem (VMware) | Rancher / OpenShift / k3s | Local PostgreSQL, MinIO, local Redis |
| On-Prem (bare metal) | k3s / kubeadm | Local PostgreSQL, MinIO, local Redis |
| Air-gapped | k3s + local registry | Everything local, self-hosted models only |

#### Option C: Single-Server (Development / Evaluation / Small Deployments)

Everything runs on one machine via Docker Compose:

```
Docker Compose
├── nginx (reverse proxy, TLS termination)
├── Next.js (frontend)
├── FastAPI (backend)
├── Keycloak (identity)
├── PostgreSQL + pgvector (database)
└── Redis (cache, sessions)
```

**Minimum server requirements:**

| Spec | Minimum | Recommended |
|---|---|---|
| **CPU** | 4 vCPU | 8 vCPU |
| **RAM** | 8 GB | 16 GB |
| **Storage** | 50 GB SSD | 100 GB SSD |
| **OS** | Ubuntu 22.04+ / Amazon Linux 2023 | Ubuntu 24.04 LTS |
| **Network** | HTTP/HTTPS outbound to model providers | Same + inbound for users |

Resource budget (single-server):

| Service | RAM | CPU | Notes |
|---|---|---|---|
| FastAPI (uvicorn, 4 workers) | ~2 GB | 2 cores | Scales with concurrent users |
| Next.js (Node.js) | ~512 MB | 0.5 cores | Lightweight after SSR |
| PostgreSQL + pgvector | ~2 GB | 1 core | Grows with data volume |
| Keycloak | ~1.5 GB | 1 core | Java — memory-hungry |
| Redis | ~256 MB | 0.25 cores | Minimal at low scale |
| nginx | ~64 MB | 0.25 cores | Reverse proxy only |
| OS + Docker overhead | ~1.5 GB | — | Base system |
| **Total** | **~8 GB** | **~5 cores** | Fits on a t3.xlarge (16 GB) comfortably |

A **t3.large (8 GB)** will technically run it but leaves no headroom. A **t3.xlarge (16 GB, 4 vCPU)** is the right size for development and evaluation with comfortable margin. No GPU required — model inference is handled by external API providers.

**Best for:** Development, demos, evaluation, small deployments under 500 users.

### 5.2 Portability by Design

Every external dependency is abstracted behind an interface:

- **Storage** — S3 in cloud, MinIO on-prem, local filesystem for development
- **Database** — RDS in cloud, local PostgreSQL on-prem (standard PostgreSQL everywhere)
- **Model Providers** — External APIs (OpenAI, Anthropic, Google) in cloud, vLLM/Ollama on-prem or air-gapped
- **Secrets** — AWS Secrets Manager in cloud, HashiCorp Vault or Kubernetes secrets on-prem
- **Identity** — Keycloak adapts to any IdP regardless of deployment environment

This abstraction means the application code is identical across all deployment options. Only configuration changes.

### 5.3 Air-Gapped Deployments

For classified or high-security environments with no internet access:

- All container images pre-loaded into a private registry
- Self-hosted models via vLLM or Ollama (no external API calls)
- Local embedding models for RAG
- Local content safety classifiers
- MinIO for S3-compatible object storage
- Keycloak connected to on-prem Active Directory / LDAP

The platform is fully functional with zero external network dependencies when configured for air-gapped operation.

## 6. Compliance & Certification Roadmap

| Standard | Status | Timeline |
|----------|--------|----------|
| **SOC 2 Type II** | Certified (maintained 4+ years) | Extend to gateway platform |
| **FERPA** | Audited & certified | Built into architecture |
| **FedRAMP** | Architecture designed for compliance | Pursue after initial deployments |
| **HIPAA** | Architecture supports BAA requirements | Enable for healthcare clients |
| **WCAG 2.2 AA** | Design constraint from day one | Audit with each release |
| **HECVAT** | Template ready | Complete per-deployment |
| **ISO 27001** | Aligned with SOC 2 controls | Pursue Year 2 |
| **StateRAMP** | Aligned with FedRAMP | Pursue for state university clients |

---
