# API Contract

## Principles

1. **REST with SSE for streaming.** Standard REST for CRUD operations. Server-Sent Events for chat streaming. No WebSockets — SSE is simpler, works through proxies/CDNs, and auto-reconnects.

2. **OpenAPI-first.** The API spec is the source of truth. Auto-generated from FastAPI's Pydantic models. Frontend developers build against the spec, not the implementation.

3. **Consistent response format.** Every endpoint returns the same envelope:

```json
{
  "data": { ... },       // The response payload
  "meta": {              // Pagination, timing, etc.
    "request_id": "uuid",
    "timestamp": "ISO-8601"
  }
}
```

Errors:

```json
{
  "error": {
    "code": "quota_exceeded",
    "message": "Daily token limit reached. Resets at midnight UTC.",
    "details": { ... }
  },
  "meta": { "request_id": "uuid" }
}
```

4. **Versioned.** All endpoints prefixed with `/api/v1/`. Breaking changes get a new version.

5. **Authenticated.** Every request carries a Bearer token (JWT from session or API key). Org context is derived from the token.

---

## Endpoints

### Authentication

```
POST   /api/v1/auth/login              # Email/password login (internal auth)
POST   /api/v1/auth/logout             # Invalidate session
POST   /api/v1/auth/refresh            # Refresh JWT
GET    /api/v1/auth/sso/redirect       # Initiate SSO flow (redirect to Keycloak)
POST   /api/v1/auth/sso/callback       # SSO callback (exchange code for token)
GET    /api/v1/auth/me                 # Current user profile
```

### Chat

```
# Conversations
POST   /api/v1/conversations                    # Create new conversation
GET    /api/v1/conversations                    # List user's conversations (paginated)
GET    /api/v1/conversations/:id                # Get conversation with messages
PATCH  /api/v1/conversations/:id                # Update title, model, pin, archive
DELETE /api/v1/conversations/:id                # Soft-delete conversation

# Messages
POST   /api/v1/conversations/:id/messages       # Send message (returns SSE stream)
GET    /api/v1/conversations/:id/messages       # Get message history (paginated)
POST   /api/v1/conversations/:id/messages/:id/regenerate  # Regenerate response (creates branch)
POST   /api/v1/conversations/:id/messages/:id/edit        # Edit user message (creates branch)
DELETE /api/v1/conversations/:id/messages/:id   # Delete a message

# Branches
GET    /api/v1/conversations/:id/branches       # List branch points
POST   /api/v1/conversations/:id/branches/:message_id/switch  # Switch active branch

# Sharing
POST   /api/v1/conversations/:id/share          # Share with team/department
DELETE /api/v1/conversations/:id/share          # Revoke sharing

# Export
GET    /api/v1/conversations/:id/export         # Export as markdown/JSON/PDF
```

#### Chat Message Request

```json
POST /api/v1/conversations/:id/messages
Content-Type: application/json
Accept: text/event-stream

{
  "content": "Explain quantum computing in simple terms",
  "model": "gpt-4o",                    // optional, uses conversation default
  "attachments": ["file-uuid-1"],        // optional file references
  "knowledge_bases": ["kb-uuid-1"],      // optional RAG knowledge bases
  "system_prompt_override": null,        // optional, admin-controlled
  "max_tokens": 4096,                    // optional
  "temperature": 0.7                     // optional
}
```

Response is SSE stream (see streaming-architecture.md for format).

### Models

```
GET    /api/v1/models                           # List available models (filtered by user's permissions)
GET    /api/v1/models/:id                       # Get model details and capabilities
GET    /api/v1/models/:id/health                # Model provider health status
POST   /api/v1/models/:id/estimate              # Estimate cost for a given input
```

#### Model List Response

```json
{
  "data": [
    {
      "id": "gpt-4o",
      "display_name": "GPT-4o",
      "provider": "openai",
      "capabilities": {
        "vision": true,
        "tools": true,
        "streaming": true,
        "max_context": 128000
      },
      "cost": {
        "input_per_1k": 0.0025,
        "output_per_1k": 0.01
      },
      "health": "healthy",
      "is_default": true
    }
  ]
}
```

### Files

```
POST   /api/v1/files/upload                     # Upload file (multipart)
GET    /api/v1/files                            # List user's files (paginated)
GET    /api/v1/files/:id                        # Get file metadata
GET    /api/v1/files/:id/download               # Download file content
DELETE /api/v1/files/:id                        # Delete file
POST   /api/v1/files/:id/share                  # Share with team/department
```

### Knowledge Bases (RAG)

```
POST   /api/v1/knowledge-bases                  # Create knowledge base
GET    /api/v1/knowledge-bases                  # List accessible knowledge bases
GET    /api/v1/knowledge-bases/:id              # Get KB details with document list
PATCH  /api/v1/knowledge-bases/:id              # Update KB settings
DELETE /api/v1/knowledge-bases/:id              # Delete KB

# Documents within a KB
POST   /api/v1/knowledge-bases/:id/documents    # Add document (file_id reference)
GET    /api/v1/knowledge-bases/:id/documents    # List documents with indexing status
DELETE /api/v1/knowledge-bases/:id/documents/:id # Remove document

# Search (for testing/debugging RAG)
POST   /api/v1/knowledge-bases/:id/search       # Semantic search against KB
```

### Governance & Usage

```
# Quotas (admin)
GET    /api/v1/admin/quotas                     # List quota policies
POST   /api/v1/admin/quotas                     # Create quota policy
PATCH  /api/v1/admin/quotas/:id                 # Update quota policy
DELETE /api/v1/admin/quotas/:id                 # Delete quota policy

# Usage (scoped to user's permissions)
GET    /api/v1/usage/me                         # Current user's usage and remaining quota
GET    /api/v1/usage/summary                    # Usage summary (admin: org-wide, user: personal)
GET    /api/v1/usage/breakdown                  # Breakdown by model/division/department/team
GET    /api/v1/usage/export                     # Export usage data as CSV

# Cost projections
GET    /api/v1/usage/projection                 # Projected costs based on trailing usage
```

#### Usage Response

```json
{
  "data": {
    "period": "daily",
    "period_start": "2026-03-16T00:00:00Z",
    "usage": {
      "tokens": { "input": 45230, "output": 12100, "total": 57330 },
      "cost_usd": 1.23,
      "requests": 42
    },
    "quota": {
      "max_tokens": 100000,
      "max_cost_usd": 5.00,
      "remaining_tokens": 42670,
      "remaining_cost_usd": 3.77,
      "enforcement": "hard",
      "resets_at": "2026-03-17T00:00:00Z"
    }
  }
}
```

### Admin — Users & Organization

```
# Users
GET    /api/v1/admin/users                      # List users (paginated, searchable)
GET    /api/v1/admin/users/:id                  # Get user detail
PATCH  /api/v1/admin/users/:id                  # Update user role/settings
DELETE /api/v1/admin/users/:id                  # Deactivate user

# Divisions
GET    /api/v1/admin/divisions                  # List divisions
POST   /api/v1/admin/divisions                  # Create division
PATCH  /api/v1/admin/divisions/:id              # Update division
DELETE /api/v1/admin/divisions/:id              # Delete division

# Departments
GET    /api/v1/admin/departments                # List departments
POST   /api/v1/admin/departments                # Create department
PATCH  /api/v1/admin/departments/:id            # Update department
DELETE /api/v1/admin/departments/:id            # Delete department

# Teams
GET    /api/v1/admin/teams                      # List teams
POST   /api/v1/admin/teams                      # Create team
PATCH  /api/v1/admin/teams/:id                  # Update team
DELETE /api/v1/admin/teams/:id                  # Delete team
POST   /api/v1/admin/teams/:id/members          # Add member
DELETE /api/v1/admin/teams/:id/members/:user_id # Remove member
```

### Admin — Models & Providers

```
GET    /api/v1/admin/providers                  # List configured providers
POST   /api/v1/admin/providers                  # Add provider
PATCH  /api/v1/admin/providers/:id              # Update provider config
DELETE /api/v1/admin/providers/:id              # Remove provider
POST   /api/v1/admin/providers/:id/test         # Test provider connection

GET    /api/v1/admin/models                     # List all models (including disabled)
PATCH  /api/v1/admin/models/:id                 # Enable/disable, set default, configure fallback
```

### Admin — Content Safety

```
GET    /api/v1/admin/content-policy             # Get current content policy
PUT    /api/v1/admin/content-policy             # Update content policy
GET    /api/v1/admin/safety-events              # List safety events (paginated)
GET    /api/v1/admin/safety-events/:id          # Get safety event detail
```

### Admin — Audit

```
GET    /api/v1/admin/audit-log                  # Query audit log (paginated, filterable)
GET    /api/v1/admin/audit-log/export           # Export audit log
```

### Admin — Analytics

```
GET    /api/v1/admin/analytics/overview         # Dashboard overview stats
GET    /api/v1/admin/analytics/adoption         # User adoption over time
GET    /api/v1/admin/analytics/models           # Model usage distribution
GET    /api/v1/admin/analytics/costs            # Cost breakdown and trends
GET    /api/v1/admin/analytics/safety           # Content safety event trends
```

### Agents

```
GET    /api/v1/agents/templates                 # List available agent templates
GET    /api/v1/agents/templates/:id             # Get template details
POST   /api/v1/agents/run                       # Start an agent workflow
GET    /api/v1/agents/runs                      # List user's agent runs
GET    /api/v1/agents/runs/:id                  # Get run status and results
POST   /api/v1/agents/runs/:id/kill             # Kill a running agent
GET    /api/v1/agents/runs/:id/logs             # Stream agent execution logs (SSE)
```

### Admin — Agent Templates

```
POST   /api/v1/admin/agents/templates           # Create custom template
PATCH  /api/v1/admin/agents/templates/:id       # Update template
DELETE /api/v1/admin/agents/templates/:id       # Delete template
GET    /api/v1/admin/agents/runs                # List all runs (org-wide)
POST   /api/v1/admin/agents/runs/:id/kill       # Admin kill any run
```

### Health & System

```
GET    /api/v1/health                           # Health check (for load balancers)
GET    /api/v1/health/detailed                  # Detailed health (DB, Redis, providers)
GET    /api/v1/system/version                   # Platform version info
```

---

## Pagination

All list endpoints support cursor-based pagination:

```
GET /api/v1/conversations?limit=20&cursor=eyJjcmVhdGVkX2F0Ijo...

Response:
{
  "data": [...],
  "meta": {
    "has_more": true,
    "next_cursor": "eyJjcmVhdGVkX2F0Ijo...",
    "total_count": 142  // only when explicitly requested via ?count=true
  }
}
```

Cursor-based (not offset-based) because:
- Stable pagination when new items are added
- Better performance on large tables
- No skipped/duplicated items

---

## Rate Limiting

API rate limits are separate from token quotas:

```
X-RateLimit-Limit: 60        # requests per minute
X-RateLimit-Remaining: 42
X-RateLimit-Reset: 1710612000 # Unix timestamp
```

HTTP 429 when exceeded, with `Retry-After` header.

---

## Authentication

Two authentication methods:

1. **JWT (browser sessions):** Short-lived access token (15 min) + refresh token (7 days). Access token in `Authorization: Bearer <token>` header. Refresh token in HTTP-only cookie.

2. **API keys (programmatic access):** Long-lived keys with prefix `csg_`. Scoped to specific capabilities. In `Authorization: Bearer csg_...` header.

Both resolve to the same `TenantContext` (org_id, user_id, permissions).
