"""RAG search endpoint."""

import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.tenant import get_current_user, TenantContext
from app.services.rag import search_chunks, build_rag_context

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    file_ids: str | None = Query(default=None, description="Comma-separated file IDs to search within"),
    limit: int = Query(default=5, ge=1, le=20),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search across uploaded documents using keyword matching."""
    fids = None
    if file_ids:
        fids = [uuid.UUID(fid.strip()) for fid in file_ids.split(",") if fid.strip()]

    chunks = await search_chunks(db, q, tenant.org_id, file_ids=fids, limit=limit)
    context = build_rag_context(chunks)

    return {
        "data": {
            "query": q,
            "results": [
                {
                    "chunk_id": str(c.chunk_id),
                    "file_id": str(c.file_id),
                    "content": c.content[:500],
                    "chunk_index": c.chunk_index,
                    "score": c.score,
                }
                for c in chunks
            ],
            "context_preview": context.context_text[:500] if context.context_text else None,
            "source_files": [str(f) for f in context.source_files],
        }
    }
