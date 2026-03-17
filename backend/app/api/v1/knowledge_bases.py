"""Knowledge base management endpoints — full CRUD + documents + search."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.database import get_db
from app.middleware.tenant import get_current_user, TenantContext
from app.models.file import KnowledgeBase, FileAccess, File, FileChunk
from app.core.response import make_meta

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


class KBCreate(BaseModel):
    name: str
    description: str | None = None
    access: str = "org"


class KBUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    access: str | None = None
    embedding_model: str | None = None


class KBSearchRequest(BaseModel):
    query: str
    limit: int = 10


def _kb_dict(kb: KnowledgeBase, doc_count: int = 0) -> dict:
    return {
        "id": str(kb.id),
        "name": kb.name,
        "description": kb.description,
        "access": kb.access.value,
        "embedding_model": kb.embedding_model,
        "document_count": doc_count,
        "created_at": kb.created_at.isoformat(),
        "updated_at": kb.updated_at.isoformat(),
    }


async def _get_kb_or_404(kb_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession) -> KnowledgeBase:
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.org_id == org_id,
            KnowledgeBase.deleted_at.is_(None),
        )
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


async def _doc_count(kb_id: uuid.UUID, db: AsyncSession) -> int:
    result = await db.execute(
        text("SELECT COUNT(*) FROM knowledge_base_files WHERE kb_id = :kb_id"),
        {"kb_id": kb_id},
    )
    return result.scalar() or 0


@router.post("", status_code=201)
async def create_kb(
    req: KBCreate,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a knowledge base."""
    kb = KnowledgeBase(
        org_id=tenant.org_id,
        name=req.name,
        description=req.description,
        access=FileAccess(req.access),
        created_by=tenant.user_id,
    )
    db.add(kb)
    await db.flush()
    return {
        "data": _kb_dict(kb),
        "meta": make_meta(),
    }


@router.get("")
async def list_kbs(
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List knowledge bases accessible to the user."""
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.org_id == tenant.org_id,
            KnowledgeBase.deleted_at.is_(None),
        ).order_by(desc(KnowledgeBase.created_at))
    )
    kbs = result.scalars().all()

    data = []
    for kb in kbs:
        count = await _doc_count(kb.id, db)
        data.append(_kb_dict(kb, count))

    return {"data": data, "meta": make_meta()}


@router.get("/{kb_id}")
async def get_kb(
    kb_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get knowledge base details with document list."""
    kb = await _get_kb_or_404(kb_id, tenant.org_id, db)
    count = await _doc_count(kb_id, db)
    return {"data": _kb_dict(kb, count), "meta": make_meta()}


@router.patch("/{kb_id}")
async def update_kb(
    kb_id: uuid.UUID,
    req: KBUpdate,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update knowledge base settings."""
    kb = await _get_kb_or_404(kb_id, tenant.org_id, db)
    if req.name is not None:
        kb.name = req.name
    if req.description is not None:
        kb.description = req.description
    if req.access is not None:
        kb.access = FileAccess(req.access)
    if req.embedding_model is not None:
        kb.embedding_model = req.embedding_model
    kb.updated_at = datetime.now(timezone.utc)
    await db.flush()
    count = await _doc_count(kb_id, db)
    return {"data": _kb_dict(kb, count), "meta": make_meta()}


@router.delete("/{kb_id}", status_code=204)
async def delete_kb(
    kb_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a knowledge base."""
    kb = await _get_kb_or_404(kb_id, tenant.org_id, db)
    kb.deleted_at = datetime.now(timezone.utc)
    await db.flush()


# --- Document management ---

@router.post("/{kb_id}/documents", status_code=201)
async def add_document(
    kb_id: uuid.UUID,
    file_id: uuid.UUID = Query(..., alias="file_id"),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a file (document) to a knowledge base."""
    await _get_kb_or_404(kb_id, tenant.org_id, db)

    # Verify file exists
    file_result = await db.execute(
        select(File).where(File.id == file_id, File.org_id == tenant.org_id, File.deleted_at.is_(None))
    )
    if not file_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="File not found")

    await db.execute(
        text("INSERT INTO knowledge_base_files (kb_id, file_id) VALUES (:kb_id, :file_id) ON CONFLICT DO NOTHING"),
        {"kb_id": kb_id, "file_id": file_id},
    )
    await db.flush()
    return {"data": {"kb_id": str(kb_id), "file_id": str(file_id), "added": True}, "meta": make_meta()}


@router.get("/{kb_id}/documents")
async def list_documents(
    kb_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List documents in a knowledge base with file details."""
    await _get_kb_or_404(kb_id, tenant.org_id, db)

    result = await db.execute(
        text("""
            SELECT f.id, f.name, f.mime_type, f.size_bytes, f.status, f.chunk_count, f.created_at
            FROM knowledge_base_files kbf
            JOIN files f ON f.id = kbf.file_id
            WHERE kbf.kb_id = :kb_id AND f.deleted_at IS NULL
            ORDER BY f.created_at DESC
        """),
        {"kb_id": kb_id},
    )
    rows = result.fetchall()
    return {
        "data": [
            {
                "id": str(r.id),
                "name": r.name,
                "mime_type": r.mime_type,
                "size_bytes": r.size_bytes,
                "status": r.status,
                "chunk_count": r.chunk_count,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "meta": make_meta(),
    }


@router.delete("/{kb_id}/documents/{file_id}", status_code=204)
async def remove_document(
    kb_id: uuid.UUID,
    file_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a document from a knowledge base."""
    await _get_kb_or_404(kb_id, tenant.org_id, db)
    await db.execute(
        text("DELETE FROM knowledge_base_files WHERE kb_id = :kb_id AND file_id = :file_id"),
        {"kb_id": kb_id, "file_id": file_id},
    )
    await db.flush()


# Legacy route (backward compat)
@router.post("/{kb_id}/files/{file_id}")
async def add_file_to_kb(
    kb_id: uuid.UUID,
    file_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a file to a knowledge base (legacy route)."""
    await _get_kb_or_404(kb_id, tenant.org_id, db)
    await db.execute(
        text("INSERT INTO knowledge_base_files (kb_id, file_id) VALUES (:kb_id, :file_id) ON CONFLICT DO NOTHING"),
        {"kb_id": kb_id, "file_id": file_id},
    )
    await db.flush()
    return {"data": {"kb_id": str(kb_id), "file_id": str(file_id), "added": True}, "meta": make_meta()}


@router.delete("/{kb_id}/files/{file_id}", status_code=204)
async def remove_file_from_kb(
    kb_id: uuid.UUID,
    file_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a file from a knowledge base (legacy route)."""
    await db.execute(
        text("DELETE FROM knowledge_base_files WHERE kb_id = :kb_id AND file_id = :file_id"),
        {"kb_id": kb_id, "file_id": file_id},
    )
    await db.flush()


# --- Semantic search ---

@router.post("/{kb_id}/search")
async def search_kb(
    kb_id: uuid.UUID,
    req: KBSearchRequest,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search a knowledge base (keyword search — semantic search requires embeddings)."""
    await _get_kb_or_404(kb_id, tenant.org_id, db)

    # Keyword search across file chunks in the KB
    result = await db.execute(
        text("""
            SELECT fc.id, fc.content, fc.chunk_index, fc.token_count, f.name as file_name, f.id as file_id
            FROM file_chunks fc
            JOIN files f ON f.id = fc.file_id
            JOIN knowledge_base_files kbf ON kbf.file_id = f.id
            WHERE kbf.kb_id = :kb_id
              AND f.deleted_at IS NULL
              AND fc.content ILIKE :query
            ORDER BY fc.chunk_index
            LIMIT :limit
        """),
        {"kb_id": kb_id, "query": f"%{req.query}%", "limit": req.limit},
    )
    rows = result.fetchall()

    return {
        "data": {
            "query": req.query,
            "results": [
                {
                    "chunk_id": str(r.id),
                    "file_id": str(r.file_id),
                    "file_name": r.file_name,
                    "chunk_index": r.chunk_index,
                    "content": r.content[:500],
                    "token_count": r.token_count,
                    "relevance": "keyword_match",
                }
                for r in rows
            ],
            "total_results": len(rows),
        },
        "meta": make_meta(),
    }
