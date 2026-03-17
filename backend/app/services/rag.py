"""RAG (Retrieval-Augmented Generation) service."""

import uuid
from dataclasses import dataclass, field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import httpx

from app.config import get_settings
from app.models.file import FileChunk

logger = structlog.get_logger()


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    file_id: uuid.UUID
    content: str
    chunk_index: int
    score: float
    metadata: dict = field(default_factory=dict)


@dataclass
class RAGContext:
    chunks: list[RetrievedChunk]
    context_text: str
    source_files: list[uuid.UUID]


async def generate_embedding(text: str) -> list[float] | None:
    """Generate embedding using Anthropic/OpenAI-compatible API.
    Falls back gracefully if no embedding API is available."""
    settings = get_settings()

    # Try Anthropic voyager (not available) or skip
    # For now, use a simple approach — we'll generate embeddings via the
    # provider that's available. If Anthropic doesn't have embeddings,
    # we store chunks without embeddings and use keyword search.
    logger.info("embedding_generation_skipped", reason="no_embedding_provider_configured")
    return None


async def search_chunks(
    db: AsyncSession,
    query: str,
    org_id: uuid.UUID,
    file_ids: list[uuid.UUID] | None = None,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """
    Search for relevant chunks. Uses keyword search (ILIKE) as fallback
    when vector embeddings aren't available.
    """
    # Keyword-based search (works without embeddings)
    search_terms = [t.strip() for t in query.split() if len(t.strip()) > 2]

    if not search_terms:
        return []

    # Build search condition
    conditions = []
    for term in search_terms[:5]:  # Limit to 5 terms
        conditions.append(f"content ILIKE '%{term}%'")

    where_clause = " OR ".join(conditions)
    file_filter = ""
    if file_ids:
        ids = ",".join(f"'{str(fid)}'" for fid in file_ids)
        file_filter = f"AND file_id IN ({ids})"

    query_sql = text(f"""
        SELECT id, file_id, content, chunk_index, metadata,
               (SELECT count(*) FROM unnest(ARRAY[{','.join(f"(content ILIKE '%{t}%')::int" for t in search_terms[:5])}]) AS hits WHERE hits = 1) as relevance
        FROM file_chunks
        WHERE org_id = :org_id
        AND ({where_clause})
        {file_filter}
        ORDER BY relevance DESC, chunk_index ASC
        LIMIT :limit
    """)

    try:
        result = await db.execute(query_sql, {"org_id": org_id, "limit": limit})
        rows = result.all()

        return [
            RetrievedChunk(
                chunk_id=row[0],
                file_id=row[1],
                content=row[2],
                chunk_index=row[3],
                score=float(row[5]) / len(search_terms) if search_terms else 0,
                metadata=row[4] or {},
            )
            for row in rows
        ]
    except Exception as e:
        logger.error("chunk_search_failed", error=str(e))
        return []


def build_rag_context(chunks: list[RetrievedChunk], max_tokens: int = 4000) -> RAGContext:
    """Build context string from retrieved chunks with source attribution."""
    if not chunks:
        return RAGContext(chunks=[], context_text="", source_files=[])

    context_parts = []
    total_chars = 0
    char_limit = max_tokens * 4  # Rough token-to-char ratio
    used_chunks = []
    source_files = set()

    for i, chunk in enumerate(chunks):
        if total_chars + len(chunk.content) > char_limit:
            break
        context_parts.append(f"[Source {i+1}] (file: {chunk.file_id}, chunk: {chunk.chunk_index})\n{chunk.content}")
        total_chars += len(chunk.content)
        used_chunks.append(chunk)
        source_files.add(chunk.file_id)

    context_text = "\n\n---\n\n".join(context_parts)

    return RAGContext(
        chunks=used_chunks,
        context_text=context_text,
        source_files=list(source_files),
    )


def inject_rag_context(system_prompt: str | None, rag_context: RAGContext) -> str:
    """Inject RAG context into the system prompt."""
    base = system_prompt or "You are a helpful AI assistant."

    if not rag_context.context_text:
        return base

    return f"""{base}

## Retrieved Context
The following information was retrieved from the user's documents. Use it to answer their question. 
When citing information, reference the source number in brackets like [Source 1].
If the context doesn't contain relevant information, say so honestly.

{rag_context.context_text}"""
