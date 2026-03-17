"""Knowledge base management endpoints."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.database import get_db
from app.middleware.tenant import get_current_user, TenantContext
from app.models.file import KnowledgeBase, FileAccess

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


class KBCreate(BaseModel):
    name: str
    description: str | None = None
    access: str = "org"


class KBUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


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
        "data": {
            "id": str(kb.id),
            "name": kb.name,
            "description": kb.description,
            "access": kb.access.value,
        }
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

    return {
        "data": [
            {
                "id": str(kb.id),
                "name": kb.name,
                "description": kb.description,
                "access": kb.access.value,
                "embedding_model": kb.embedding_model,
                "created_at": kb.created_at.isoformat(),
            }
            for kb in kbs
        ]
    }


@router.post("/{kb_id}/files/{file_id}")
async def add_file_to_kb(
    kb_id: uuid.UUID,
    file_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a file to a knowledge base."""
    # Verify KB exists and user has access
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id, KnowledgeBase.org_id == tenant.org_id, KnowledgeBase.deleted_at.is_(None)
        )
    )
    if not kb_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Insert association
    await db.execute(
        text("INSERT INTO knowledge_base_files (kb_id, file_id) VALUES (:kb_id, :file_id) ON CONFLICT DO NOTHING"),
        {"kb_id": kb_id, "file_id": file_id},
    )
    await db.flush()

    return {"data": {"kb_id": str(kb_id), "file_id": str(file_id), "added": True}}


@router.delete("/{kb_id}/files/{file_id}", status_code=204)
async def remove_file_from_kb(
    kb_id: uuid.UUID,
    file_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a file from a knowledge base."""
    await db.execute(
        text("DELETE FROM knowledge_base_files WHERE kb_id = :kb_id AND file_id = :file_id"),
        {"kb_id": kb_id, "file_id": file_id},
    )
    await db.flush()


@router.delete("/{kb_id}", status_code=204)
async def delete_kb(
    kb_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a knowledge base."""
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id, KnowledgeBase.org_id == tenant.org_id, KnowledgeBase.deleted_at.is_(None)
        )
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    kb.deleted_at = datetime.now(timezone.utc)
    await db.flush()
