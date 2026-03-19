# Context Portability: Portable SQLite Bundles for Cross-Model Migration

## Status
**Draft** | Author: CognitionShift Engineering | Date: 2026-03-18

---

## 1. Problem Statement

Users are locked into model providers because their context (conversation history, document embeddings, knowledge bases) is stored in provider-specific formats. When a team decides to switch from one model to another, they lose months of accumulated conversational context, carefully curated knowledge bases, and the vector embeddings that power semantic search.

This creates vendor lock-in at the data layer, not the API layer. The gateway already abstracts provider APIs; now it needs to abstract data portability.

## 2. Solution: Portable Context Bundles

A self-contained SQLite database file (`.csgw` extension, short for CognitionShift Gateway) that packages everything a user needs to reconstruct their working context on any compatible gateway instance:

- **Conversations and messages**: full text, no truncation, including token counts and model attribution
- **File metadata and text chunks**: extracted text content (not raw binary files, which would bloat bundles)
- **Knowledge base structure**: document organization, chunk boundaries, source text
- **Vector embeddings via sqlite-vec**: immediately usable for semantic search on import, no re-embedding required if models match
- **Embedding model metadata**: so the importing system knows whether vectors are compatible or need re-computation
- **Export metadata**: timestamp, source instance URL, gateway version, user identity

## 3. Schema Design

The SQLite bundle uses a simplified, denormalized schema optimized for portability rather than production query patterns.

### `_meta` table
Key-value pairs for export metadata.

| Column | Type | Description |
|--------|------|-------------|
| key | TEXT PK | Metadata key |
| value | TEXT | Metadata value |

Required keys: `schema_version`, `exported_at`, `gateway_version`, `source_instance`, `user_id`, `user_email`, `org_id`.

### `conversations` table

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | UUID as string |
| title | TEXT | Conversation title |
| model_id | TEXT | Primary model used |
| system_prompt | TEXT | System prompt if set |
| created_at | TEXT | ISO 8601 UTC timestamp |
| updated_at | TEXT | ISO 8601 UTC timestamp |
| message_count | INTEGER | Total messages |

### `messages` table

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | UUID as string |
| conversation_id | TEXT FK | References conversations.id |
| sequence | INTEGER | Message order within conversation |
| role | TEXT | user, assistant, system, tool |
| content | TEXT | Full message content |
| model_id | TEXT | Model that generated this message |
| input_tokens | INTEGER | Input token count |
| output_tokens | INTEGER | Output token count |
| created_at | TEXT | ISO 8601 UTC timestamp |

### `files` table

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | UUID as string |
| name | TEXT | Original filename |
| mime_type | TEXT | MIME type |
| size_bytes | INTEGER | Original file size |
| sha256_hash | TEXT | Content hash |
| chunk_count | INTEGER | Number of text chunks |
| created_at | TEXT | ISO 8601 UTC timestamp |

### `file_chunks` table

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | UUID as string |
| file_id | TEXT FK | References files.id |
| chunk_index | INTEGER | Chunk order |
| content | TEXT | Chunk text content |
| token_count | INTEGER | Estimated token count |

### `knowledge_bases` table

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | UUID as string |
| name | TEXT | Knowledge base name |
| description | TEXT | Description |
| embedding_model | TEXT | Model used for embeddings |

### `kb_documents` table

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | UUID as string |
| knowledge_base_id | TEXT FK | References knowledge_bases.id |
| file_id | TEXT FK | References files.id |
| chunk_count | INTEGER | Number of chunks |

### `embeddings` table
Uses sqlite-vec virtual table for vector storage.

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | UUID as string |
| source_type | TEXT | "file_chunk" or "kb_document" |
| source_id | TEXT | References source record |
| chunk_index | INTEGER | Chunk position |
| content | TEXT | Source text (for re-embedding) |
| embedding | FLOAT[N] | Vector via sqlite-vec |

### `embedding_config` table

| Column | Type | Description |
|--------|------|-------------|
| model_name | TEXT PK | Embedding model identifier |
| dimensions | INTEGER | Vector dimensions |
| provider | TEXT | Model provider |

## 4. Re-embedding Strategy

Vectors are only useful if the target system uses the same embedding model. The bundle always includes source text alongside vectors, enabling two import paths:

**Fast path (model match):** When the importing system's embedding model matches the bundle's `embedding_config.model_name`, vectors are loaded directly into pgvector. Semantic search works immediately.

**Slow path (model mismatch):** When models differ, source text from the `content` column is re-embedded using the target system's model. This runs as a background job to avoid blocking the import. The import job transitions through states: `importing` -> `re_embedding` -> `completed`.

Import status tracking per job:
- `pending`: job created, not started
- `running`: reading bundle, validating
- `importing`: inserting records into PostgreSQL
- `re_embedding`: vectors being recomputed (slow path)
- `completed`: all data available
- `failed`: error occurred

## 5. API Endpoints

### Export

**`POST /api/v1/context/export`**
Generate a portable bundle for the authenticated user.

Request body:
```json
{
  "conversation_ids": ["uuid1", "uuid2"],  // optional, null = all
  "date_from": "2025-01-01T00:00:00Z",     // optional
  "date_to": "2026-03-18T00:00:00Z",       // optional
  "include_files": true,                     // default true
  "include_embeddings": true                 // default true
}
```

Response: `{"data": {"job_id": "uuid", "status": "pending"}, "meta": {...}}`

**`GET /api/v1/context/export/{job_id}`**
Check export job status.

Response: `{"data": {"job_id": "uuid", "status": "completed", "file_size": 12345678}, "meta": {...}}`

**`GET /api/v1/context/export/{job_id}/download`**
Download the completed bundle. Returns the `.csgw` file as `application/octet-stream`.

### Import

**`POST /api/v1/context/import`**
Upload a `.csgw` bundle for import.

Query parameters:
- `mode`: `merge` (default) or `replace`

Response: `{"data": {"job_id": "uuid", "status": "pending"}, "meta": {...}}`

**`GET /api/v1/context/import/{job_id}`**
Check import job status, including re-embedding progress.

Response:
```json
{
  "data": {
    "job_id": "uuid",
    "status": "re_embedding",
    "stats": {
      "conversations": 42,
      "messages": 1337,
      "files": 15,
      "file_chunks": 230,
      "knowledge_bases": 3,
      "embeddings_total": 500,
      "embeddings_processed": 312
    }
  },
  "meta": {...}
}
```

## 6. Security Considerations

- **Tenant isolation**: Bundles contain data from a single user within a single org. Export queries are always scoped by `org_id` and `user_id`.
- **Schema validation**: On import, the bundle is validated against the expected schema version and required tables before any data is read.
- **Content safety**: Imported messages can optionally be scanned through the existing content safety pipeline. Configurable per tenant: `scan` (default) or `trust`.
- **Admin control**: Export/import can be enabled or disabled per tenant via organization settings.
- **Legal holds**: If a legal hold is active on the user's account, export is blocked with a 403 response.
- **Excluded data**: Bundles never contain passwords, API keys, session tokens, audit logs, or usage/billing data.

## 7. Governance

- Every export generates an `audit_log` entry with action `context_export`, including job ID and options.
- Every import generates an `audit_log` entry with action `context_import`, including job ID, bundle metadata, and import stats.
- Admins can be notified on export via webhook (configurable).
- Rate limiting: one export per user per hour by default (configurable per org).

## 8. File Format Details

- Extension: `.csgw` (CognitionShift Gateway)
- Internal format: SQLite 3 database
- Vector storage: sqlite-vec extension (vectors stored as float arrays)
- Text encoding: UTF-8 throughout
- Timestamps: ISO 8601 UTC strings
- IDs: UUID v4 stored as TEXT
- Schema version: `1` (for forward compatibility)

## 9. Future Considerations

- Bundle encryption (AES-256-GCM with user-provided key)
- Selective import (pick specific conversations from a bundle)
- Bundle diffing (import only new/changed data)
- Cross-org transfer with admin approval workflow
- CLI tool for offline bundle inspection
