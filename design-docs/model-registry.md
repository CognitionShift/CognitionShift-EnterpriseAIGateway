# Model Registry

## Purpose

A centralized catalog for institutional AI assets — custom models, fine-tunes, and locally-hosted models — with version-controlled documentation, access controls, and optional gateway integration. The registry serves as the institutional record of what was built, how it was trained, and who has access, without requiring every model to route through the gateway's inference layer.

## Design Principles

1. **Metadata-first.** The registry is a documentation and cataloging system. Artifact storage (model weights) is optional and decoupled — models can live on lab GPU clusters, S3, HuggingFace, or anywhere else.

2. **Version immutability.** Published versions are append-only. You can deprecate but never mutate a published version's documentation or artifacts. This supports compliance auditing ("which model version produced this output?").

3. **Graduated access control.** Models can be private (creator only), department-scoped, or institution-wide. Access grants are explicit and auditable.

4. **Optional gateway routing.** Models with inference configuration become available in the gateway's model selector. Models without it are catalog-only entries. Both are first-class.

---

## Data Model

### model_registry

The top-level model entry. One per distinct model (not per version).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| org_id | UUID FK → organizations | Tenant isolation |
| name | TEXT | Unique within org. Slug-style: `clinical-notes-summarizer` |
| display_name | TEXT | Human-readable: "Clinical Notes Summarizer" |
| description | TEXT | What it does, who it's for |
| visibility | ENUM | `private`, `department`, `organization` |
| department_id | UUID FK → departments | Required when visibility = `department` |
| tags | JSONB | Freeform tags for search/filtering: `["nlp", "healthcare", "summarization"]` |
| created_by | UUID FK → users | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |
| deleted_at | TIMESTAMPTZ | Soft delete |

### model_versions

Immutable version records. Each version captures a complete snapshot of the model's state and documentation at a point in time.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| model_id | UUID FK → model_registry | |
| version | TEXT | Semver: `1.0.0`, `2.1.0-beta` |
| status | ENUM | `draft`, `published`, `deprecated` |
| release_notes | TEXT | What changed in this version |
| training_data | JSONB | Sources, size, date range, preprocessing |
| intended_use | TEXT | What it's designed for — and what it's not |
| limitations | TEXT | Known failure modes, biases, edge cases |
| license | TEXT | `Apache-2.0`, `Internal Only`, `CC-BY-4.0`, etc. |
| architecture | JSONB | `{ "base": "llama-3-8b", "method": "LoRA", "framework": "pytorch", "parameters": "8B" }` |
| eval_results | JSONB | `{ "mmlu": 0.72, "custom_bench": 0.89, "human_eval": 0.65 }` |
| artifact_uri | TEXT NULL | Where weights live: `s3://models/...`, NFS path, HF URL, or NULL |
| artifact_size_bytes | BIGINT NULL | Size for display/quota purposes |
| artifact_hash | TEXT NULL | SHA-256 for integrity verification |
| gateway_config | JSONB NULL | If set, model is routable through gateway inference. See below. |
| created_by | UUID FK → users | |
| published_at | TIMESTAMPTZ NULL | Set when status transitions to `published` |
| created_at | TIMESTAMPTZ | |

#### gateway_config schema

When populated, the model appears in the gateway's model selector and can be used for chat:

```json
{
  "provider": "ollama",
  "endpoint": "http://lab-gpu-01.internal:11434",
  "model_name": "clinical-summarizer:v1.2",
  "api_key": null,
  "max_context_tokens": 8192,
  "supports_streaming": true,
  "supports_vision": false,
  "cost_input_per_1k": 0,
  "cost_output_per_1k": 0
}
```

### model_access

Explicit access grants. The model creator always has admin access implicitly.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| model_id | UUID FK → model_registry | |
| grantee_type | ENUM | `user`, `department`, `organization` |
| grantee_id | UUID | Points to users.id, departments.id, or organizations.id |
| permission | ENUM | `view`, `use`, `edit`, `admin` |
| granted_by | UUID FK → users | |
| created_at | TIMESTAMPTZ | |

Permission semantics:
- **view** — can see the model card, versions, documentation
- **use** — can use the model via gateway (if gateway_config is set)
- **edit** — can create new versions, update metadata
- **admin** — can manage access grants, archive the model

---

## API Design

All endpoints are org-scoped via JWT tenant context.

### Model CRUD

```
POST   /api/v1/registry                     Create model
GET    /api/v1/registry                     List/search models (filtered by access + visibility)
GET    /api/v1/registry/:id                 Get model with latest published version
PATCH  /api/v1/registry/:id                 Update model metadata
DELETE /api/v1/registry/:id                 Soft delete (archive)
```

### Versions

```
POST   /api/v1/registry/:id/versions        Create version (draft)
GET    /api/v1/registry/:id/versions         List all versions
GET    /api/v1/registry/:id/versions/:vid    Get specific version
PATCH  /api/v1/registry/:id/versions/:vid    Update draft version
POST   /api/v1/registry/:id/versions/:vid/publish   Publish (locks version)
POST   /api/v1/registry/:id/versions/:vid/deprecate  Deprecate
```

### Access Control

```
GET    /api/v1/registry/:id/access           List access grants
POST   /api/v1/registry/:id/access           Grant access
DELETE /api/v1/registry/:id/access/:aid       Revoke access
```

### Search & Discovery

The `GET /api/v1/registry` endpoint supports query parameters:

| Param | Type | Description |
|-------|------|-------------|
| q | string | Full-text search across name, display_name, description, tags |
| visibility | string | Filter: `private`, `department`, `organization` |
| tags | string[] | Filter by tags (AND) |
| framework | string | Filter by architecture.framework |
| has_gateway | bool | Only models with gateway_config |
| sort | string | `created_at`, `updated_at`, `name` |
| limit / cursor | int/string | Pagination |

---

## Access Control Logic

Model visibility determines the base access rule:

1. **private** — Only the creator and users with explicit `model_access` grants can see/use it.
2. **department** — All users in the specified `department_id` can view it. Use/edit requires explicit grants.
3. **organization** — All users in the org can view it. Use/edit requires explicit grants.

The creator always has implicit `admin` permission.

Admin users (org admins) can see and manage all models in their org.

---

## Frontend

### Models Page (`/models`)

- **Browse tab** — Card grid or list view of accessible models. Search bar, tag filters, visibility filter.
- **My Models tab** — Models created by the current user.
- **Create button** — Opens the create/publish wizard.

### Model Detail Page (`/models/:id`)

Tabbed view:
- **Overview** — Display name, description, tags, visibility, creation info
- **Versions** — Version list with status badges. Click to expand: release notes, documentation, eval results.
- **Model Card** — Structured documentation: intended use, limitations, training data, architecture, eval results. Renders as a readable document.
- **Access** — Who has access, grant/revoke UI (for model admins).
- **Gateway** — If connected to gateway: endpoint config, usage stats. If not: "This model is catalog-only" with option to add gateway config.

### Publish Wizard

Step-by-step form for new versions that encourages thorough documentation:

1. **Version & Release Notes** — semver, what changed
2. **Architecture** — base model, method, framework, parameter count
3. **Training Data** — sources, size, date range, preprocessing
4. **Intended Use & Limitations** — free text with guidance prompts
5. **Evaluation** — key-value pairs for benchmark results
6. **Artifacts** — optional URI/upload
7. **Review & Publish** — summary before locking

---

## Implementation Phases

### Phase 1 — Catalog (this implementation)
- Database tables + migration
- Full CRUD API for models, versions, access
- Frontend browse, detail, create/edit pages
- Search by name, tags, visibility
- No artifact upload, no gateway routing

### Phase 2 — Artifact Storage
- S3/MinIO upload/download endpoints
- Pre-signed URLs for large files
- SHA-256 integrity verification
- Storage quotas per org

### Phase 3 — Gateway Integration
- Models with `gateway_config` appear in model router
- Custom model provider that proxies to arbitrary endpoints
- Usage tracking for registry models
- Health checking for custom endpoints

---

## Audit & Compliance

All model registry operations emit audit events:
- `model.created`, `model.updated`, `model.archived`
- `version.created`, `version.published`, `version.deprecated`
- `access.granted`, `access.revoked`
- `artifact.uploaded`, `artifact.downloaded`

This supports institutional requirements for tracking AI asset lifecycle and access history.
