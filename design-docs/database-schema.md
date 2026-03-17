# Database Schema Design

## Principles

1. **Multi-tenancy is row-level, not schema-level.** Every table that holds tenant data includes an `org_id` foreign key. Queries are always scoped. This keeps operations simple (one database, one migration path) while maintaining logical isolation.

2. **Soft deletes for compliance.** Records are marked `deleted_at` rather than removed. Hard deletion is a separate, audited process triggered by retention policies or explicit compliance requests.

3. **Audit trail is append-only and separate.** Audit events write to a dedicated `audit_log` table (and optionally to S3 for long-term, tamper-proof storage). The primary database stays lean.

4. **UUIDs for all primary keys.** No auto-incrementing integers that leak information about record counts or creation order.

5. **Timestamps are UTC, stored as `timestamptz`.** No timezone ambiguity.

---

## Core Tables

### Organizations & Tenancy

```sql
-- Top-level organization (one per customer deployment in multi-tenant mode)
CREATE TABLE organizations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,  -- URL-safe identifier
    settings        JSONB NOT NULL DEFAULT '{}',  -- org-wide configuration
    content_policy  JSONB NOT NULL DEFAULT '{}',  -- content safety rules
    retention_policy JSONB NOT NULL DEFAULT '{}', -- data retention rules
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

-- Divisions within an organization (campuses, regions, business units)
CREATE TABLE divisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL,
    settings        JSONB NOT NULL DEFAULT '{}',  -- overrides org settings
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,
    UNIQUE(org_id, slug)
);

-- Departments within a division
CREATE TABLE departments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    division_id     UUID NOT NULL REFERENCES divisions(id),
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL,
    settings        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,
    UNIQUE(division_id, slug)
);

-- Teams within a department (classes, project groups, labs)
CREATE TABLE teams (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    department_id   UUID NOT NULL REFERENCES departments(id),
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL,
    settings        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,
    UNIQUE(department_id, slug)
);
```

### Users & Membership

```sql
CREATE TYPE user_role AS ENUM ('admin', 'manager', 'member', 'viewer', 'pending');

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    email           TEXT NOT NULL,
    name            TEXT NOT NULL,
    role            user_role NOT NULL DEFAULT 'pending',
    password_hash   TEXT,  -- NULL when using SSO-only
    avatar_url      TEXT,
    settings        JSONB NOT NULL DEFAULT '{}',  -- personal preferences
    idp_subject     TEXT,  -- external IdP subject identifier
    idp_provider    TEXT,  -- which IdP authenticated this user
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,
    UNIQUE(org_id, email)
);

-- Users can belong to multiple teams
CREATE TABLE team_memberships (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    team_id         UUID NOT NULL REFERENCES teams(id),
    role            user_role NOT NULL DEFAULT 'member',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, team_id)
);

-- Users also have a primary division and department (from IdP mapping)
-- This is denormalized on the user for fast lookups
ALTER TABLE users ADD COLUMN division_id UUID REFERENCES divisions(id);
ALTER TABLE users ADD COLUMN department_id UUID REFERENCES departments(id);
```

### Conversations & Messages

```sql
CREATE TYPE conversation_visibility AS ENUM ('private', 'team', 'department', 'org');

CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    title           TEXT,  -- auto-generated or user-set
    visibility      conversation_visibility NOT NULL DEFAULT 'private',
    team_id         UUID REFERENCES teams(id),  -- set when visibility = 'team'
    model_id        TEXT,  -- default model for this conversation
    system_prompt   TEXT,  -- custom system prompt if any
    metadata        JSONB NOT NULL DEFAULT '{}',
    is_ephemeral    BOOLEAN NOT NULL DEFAULT false,  -- zero-retention mode
    pinned          BOOLEAN NOT NULL DEFAULT false,
    archived        BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    org_id          UUID NOT NULL REFERENCES organizations(id),
    sequence        INTEGER NOT NULL,  -- monotonically increasing within conversation
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content         TEXT NOT NULL,
    model_id        TEXT,  -- which model generated this (NULL for user messages)
    
    -- Token accounting
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_usd        NUMERIC(10, 6),  -- cost in USD for this message
    
    -- Content safety
    safety_flags    JSONB,  -- any flags raised by content safety scanning
    
    -- Attachments/files referenced
    file_ids        UUID[],  -- array of file IDs attached to this message
    
    -- For tool use / agent responses
    tool_calls      JSONB,
    tool_results    JSONB,
    
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,
    UNIQUE(conversation_id, sequence)
);

-- Tags for organizing conversations
CREATE TABLE tags (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    name            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, name)
);

CREATE TABLE conversation_tags (
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    tag_id          UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (conversation_id, tag_id)
);
```

### Governance & Quotas

```sql
CREATE TYPE quota_scope AS ENUM ('org', 'division', 'department', 'team', 'user');
CREATE TYPE quota_period AS ENUM ('hourly', 'daily', 'weekly', 'monthly');
CREATE TYPE enforcement_mode AS ENUM ('hard', 'soft', 'throttle');

CREATE TABLE quota_policies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    scope           quota_scope NOT NULL,
    scope_id        UUID NOT NULL,  -- references org/division/dept/team/user id
    
    -- Limits
    max_tokens      BIGINT,  -- NULL = unlimited
    max_cost_usd    NUMERIC(10, 2),  -- NULL = unlimited
    max_requests    INTEGER,  -- NULL = unlimited
    period          quota_period NOT NULL DEFAULT 'daily',
    enforcement     enforcement_mode NOT NULL DEFAULT 'hard',
    
    -- Model restrictions
    allowed_models  TEXT[],  -- NULL = all models allowed
    blocked_models  TEXT[],
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

-- Rolling usage counters (updated in real-time, reset by period)
CREATE TABLE usage_counters (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    scope           quota_scope NOT NULL,
    scope_id        UUID NOT NULL,
    period          quota_period NOT NULL,
    period_start    TIMESTAMPTZ NOT NULL,  -- start of current period
    
    total_tokens    BIGINT NOT NULL DEFAULT 0,
    input_tokens    BIGINT NOT NULL DEFAULT 0,
    output_tokens   BIGINT NOT NULL DEFAULT 0,
    total_cost_usd  NUMERIC(10, 4) NOT NULL DEFAULT 0,
    total_requests  INTEGER NOT NULL DEFAULT 0,
    
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(scope, scope_id, period, period_start)
);

-- Detailed usage log for analytics and chargeback
CREATE TABLE usage_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    conversation_id UUID REFERENCES conversations(id),
    message_id      UUID REFERENCES messages(id),
    
    model_id        TEXT NOT NULL,
    provider        TEXT NOT NULL,  -- openai, anthropic, google, ollama, etc.
    
    input_tokens    INTEGER NOT NULL,
    output_tokens   INTEGER NOT NULL,
    cost_usd        NUMERIC(10, 6) NOT NULL,
    latency_ms      INTEGER,
    
    -- Denormalized for fast analytics queries
    division_id     UUID,
    department_id   UUID,
    team_id         UUID,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Partition usage_log by month for performance
-- CREATE TABLE usage_log_2026_03 PARTITION OF usage_log
--     FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
```

### Model Configuration

```sql
CREATE TABLE model_providers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    name            TEXT NOT NULL,  -- display name
    provider_type   TEXT NOT NULL,  -- openai, anthropic, google, ollama, custom
    base_url        TEXT NOT NULL,
    api_key_ref     TEXT,  -- reference to secrets manager, never stored plaintext
    is_enabled      BOOLEAN NOT NULL DEFAULT true,
    health_status   TEXT NOT NULL DEFAULT 'unknown',
    last_health_check TIMESTAMPTZ,
    settings        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE models (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    provider_id     UUID NOT NULL REFERENCES model_providers(id),
    model_id        TEXT NOT NULL,  -- provider's model identifier (e.g., gpt-4o)
    display_name    TEXT NOT NULL,
    
    -- Cost per token (for quota/budget calculations)
    input_cost_per_token  NUMERIC(12, 10),  -- e.g., 0.0000025 for GPT-4o input
    output_cost_per_token NUMERIC(12, 10),
    
    -- Capabilities
    supports_vision     BOOLEAN NOT NULL DEFAULT false,
    supports_tools      BOOLEAN NOT NULL DEFAULT false,
    supports_streaming  BOOLEAN NOT NULL DEFAULT true,
    max_context_tokens  INTEGER,
    
    is_enabled      BOOLEAN NOT NULL DEFAULT true,
    is_default      BOOLEAN NOT NULL DEFAULT false,
    
    -- Fallback chain
    fallback_model_id UUID REFERENCES models(id),
    
    settings        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Files & Knowledge

```sql
CREATE TABLE files (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    
    filename        TEXT NOT NULL,
    content_type    TEXT NOT NULL,
    size_bytes      BIGINT NOT NULL,
    storage_key     TEXT NOT NULL,  -- S3 key or storage path
    
    -- Processing status
    status          TEXT NOT NULL DEFAULT 'uploaded'
                    CHECK (status IN ('uploaded', 'scanning', 'processing', 'ready', 'failed', 'quarantined')),
    scan_result     JSONB,  -- virus/malware scan results
    
    -- Sharing
    visibility      conversation_visibility NOT NULL DEFAULT 'private',
    team_id         UUID REFERENCES teams(id),
    
    -- Retention
    expires_at      TIMESTAMPTZ,  -- auto-deletion date
    
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

-- Knowledge bases (collections of documents for RAG)
CREATE TABLE knowledge_bases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    name            TEXT NOT NULL,
    description     TEXT,
    
    -- Ownership and visibility
    owner_type      TEXT NOT NULL CHECK (owner_type IN ('user', 'team', 'department', 'org')),
    owner_id        UUID NOT NULL,
    visibility      conversation_visibility NOT NULL DEFAULT 'private',
    
    -- Embedding configuration
    embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-small',
    chunk_strategy  TEXT NOT NULL DEFAULT 'semantic',
    chunk_size      INTEGER NOT NULL DEFAULT 512,
    chunk_overlap   INTEGER NOT NULL DEFAULT 50,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

-- Documents within a knowledge base
CREATE TABLE knowledge_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    file_id         UUID NOT NULL REFERENCES files(id),
    
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'indexed', 'failed')),
    chunk_count     INTEGER,
    error_message   TEXT,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Vector embeddings for RAG (using pgvector)
CREATE TABLE embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    document_id     UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,  -- the text chunk
    embedding       vector(1536),   -- dimensionality depends on model
    
    -- Source reference for citations
    source_page     INTEGER,
    source_section  TEXT,
    
    metadata        JSONB NOT NULL DEFAULT '{}'
);

-- Index for vector similarity search
CREATE INDEX ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

### Audit Trail

```sql
CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    
    -- Who
    actor_id        UUID,  -- user ID, NULL for system actions
    actor_type      TEXT NOT NULL CHECK (actor_type IN ('user', 'admin', 'system', 'agent')),
    actor_ip        INET,
    
    -- What
    action          TEXT NOT NULL,  -- e.g., 'message.create', 'file.upload', 'user.login'
    resource_type   TEXT NOT NULL,  -- e.g., 'conversation', 'file', 'user', 'quota'
    resource_id     UUID,
    
    -- Details
    details         JSONB NOT NULL DEFAULT '{}',
    
    -- Content safety events
    safety_event    BOOLEAN NOT NULL DEFAULT false,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Partition by month for performance
-- Audit log is append-only — no UPDATE or DELETE operations permitted
-- Application enforces this; database role for audit writes has INSERT-only grants

CREATE INDEX idx_audit_log_org_created ON audit_log (org_id, created_at DESC);
CREATE INDEX idx_audit_log_actor ON audit_log (actor_id, created_at DESC);
CREATE INDEX idx_audit_log_resource ON audit_log (resource_type, resource_id);
CREATE INDEX idx_audit_log_safety ON audit_log (org_id, created_at DESC) WHERE safety_event = true;
```

### Agent Workflows

```sql
CREATE TABLE agent_templates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID REFERENCES organizations(id),  -- NULL = global/built-in
    name            TEXT NOT NULL,
    description     TEXT,
    
    -- Agent configuration
    system_prompt   TEXT NOT NULL,
    model_id        TEXT,  -- default model, can be overridden
    tools           JSONB NOT NULL DEFAULT '[]',
    
    -- Permission manifest
    permissions     JSONB NOT NULL DEFAULT '{}',
    -- e.g., {"web_browsing": true, "allowed_domains": ["*.edu"], 
    --        "file_access": "read", "code_execution": true,
    --        "max_runtime_seconds": 300, "max_cost_usd": 1.00}
    
    is_enabled      BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agent_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    template_id     UUID NOT NULL REFERENCES agent_templates(id),
    conversation_id UUID REFERENCES conversations(id),
    
    -- Execution
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'provisioning', 'running', 'completed', 'failed', 'killed', 'timeout')),
    container_id    TEXT,  -- Kubernetes pod name
    
    -- Resource tracking
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    total_tokens    BIGINT DEFAULT 0,
    total_cost_usd  NUMERIC(10, 4) DEFAULT 0,
    
    -- Results
    result          JSONB,
    error_message   TEXT,
    
    -- Full execution log
    execution_log   JSONB NOT NULL DEFAULT '[]',
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Sessions & Auth

```sql
CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    
    token_hash      TEXT NOT NULL UNIQUE,  -- hashed JWT or session token
    ip_address      INET,
    user_agent      TEXT,
    
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    
    name            TEXT NOT NULL,
    key_hash        TEXT NOT NULL UNIQUE,  -- hashed API key
    key_prefix      TEXT NOT NULL,  -- first 8 chars for identification (e.g., "csg_a1b2...")
    
    scopes          TEXT[] NOT NULL DEFAULT '{}',  -- e.g., {'chat', 'files', 'admin'}
    
    last_used_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ
);
```

---

## Key Indexes

```sql
-- Conversation lookups
CREATE INDEX idx_conversations_user ON conversations (user_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_conversations_team ON conversations (team_id, created_at DESC) WHERE deleted_at IS NULL AND team_id IS NOT NULL;
CREATE INDEX idx_conversations_org ON conversations (org_id, created_at DESC) WHERE deleted_at IS NULL;

-- Message lookups (linear, ordered by sequence)
CREATE INDEX idx_messages_conversation ON messages (conversation_id, sequence ASC) WHERE deleted_at IS NULL;

-- Usage analytics (the most queried table)
CREATE INDEX idx_usage_log_analytics ON usage_log (org_id, created_at DESC);
CREATE INDEX idx_usage_log_user ON usage_log (user_id, created_at DESC);
CREATE INDEX idx_usage_log_division ON usage_log (division_id, created_at DESC) WHERE division_id IS NOT NULL;
CREATE INDEX idx_usage_log_department ON usage_log (department_id, created_at DESC) WHERE department_id IS NOT NULL;
CREATE INDEX idx_usage_log_model ON usage_log (org_id, model_id, created_at DESC);

-- Quota lookups
CREATE INDEX idx_quota_policies_scope ON quota_policies (scope, scope_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_usage_counters_lookup ON usage_counters (scope, scope_id, period, period_start);

-- File lookups
CREATE INDEX idx_files_user ON files (user_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_files_expiry ON files (expires_at) WHERE expires_at IS NOT NULL AND deleted_at IS NULL;

-- Session cleanup
CREATE INDEX idx_sessions_expiry ON sessions (expires_at);
```

---

## Multi-Tenancy Enforcement

Every query that touches tenant data MUST include `org_id` in the WHERE clause. This is enforced at the application layer through a middleware that injects the org context:

```python
# Every database session carries the org context
class TenantContext:
    org_id: UUID
    user_id: UUID
    division_id: Optional[UUID]
    department_id: Optional[UUID]

# Repository base class enforces org_id filtering
class BaseRepository:
    def __init__(self, db: Session, tenant: TenantContext):
        self.db = db
        self.tenant = tenant
    
    def base_query(self, model):
        return self.db.query(model).filter(model.org_id == self.tenant.org_id)
```

For additional defense-in-depth, PostgreSQL Row Level Security (RLS) can be enabled:

```sql
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON conversations
    USING (org_id = current_setting('app.current_org_id')::UUID);
```

---

## Zero-Retention Mode

When a conversation is marked `is_ephemeral = true`:

1. Messages are stored in Redis only (not PostgreSQL) during the active session
2. Token counts and costs ARE recorded to `usage_log` (billing still works)
3. Content (prompts and responses) is NOT persisted anywhere
4. When the session ends, Redis keys are deleted
5. Audit log records that a conversation occurred (actor, timestamp, model, token count) but NOT the content

This provides a cryptographic guarantee: ephemeral content never touches disk.

---

## Migration Strategy

- **Alembic** for schema migrations (standard for SQLAlchemy/FastAPI)
- Migrations are forward-only in production (no downgrades)
- Every migration is tested against a copy of production data before deployment
- Zero-downtime migrations: additive changes first (add column), then backfill, then enforce constraints
