"""File upload and management endpoints."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database import get_db
from app.middleware.tenant import get_current_user, TenantContext
from app.models.file import File, FileChunk, FileStatus
from app.services.file_processor import (
    process_file, save_file, compute_sha256,
    MAX_FILE_SIZE, ALLOWED_TYPES,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/files", tags=["files"])


@router.post("", status_code=201)
async def upload_file(
    file: UploadFile = FastAPIFile(...),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload and process a file."""
    # Validate type
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}. Supported: {list(ALLOWED_TYPES.keys())}",
        )

    # Read file data
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum: {MAX_FILE_SIZE // (1024*1024)}MB")

    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Create file record
    file_id = uuid.uuid4()
    sha256 = compute_sha256(data)
    ext = ALLOWED_TYPES.get(content_type, ".bin")
    storage_path = save_file(data, tenant.org_id, file_id, ext)

    db_file = File(
        id=file_id,
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        name=file.filename or "unnamed",
        mime_type=content_type,
        size_bytes=len(data),
        sha256_hash=sha256,
        storage_path=storage_path,
        status=FileStatus.processing,
    )
    db.add(db_file)
    await db.flush()

    # Process file (extract text, chunk)
    try:
        processed = process_file(data, content_type, file.filename or "unnamed")

        # Save chunks
        for i, chunk_text in enumerate(processed.chunks):
            chunk = FileChunk(
                file_id=file_id,
                org_id=tenant.org_id,
                chunk_index=i,
                content=chunk_text,
                token_count=len(chunk_text) // 4,  # Rough estimate
                metadata_={"source": file.filename, "chunk_index": i},
            )
            db.add(chunk)

        db_file.status = FileStatus.ready
        db_file.chunk_count = len(processed.chunks)
        db_file.metadata_ = processed.metadata
        await db.flush()

        logger.info("file_uploaded", file_id=str(file_id), chunks=len(processed.chunks), name=file.filename)

        return {
            "data": {
                "id": str(file_id),
                "name": db_file.name,
                "mime_type": db_file.mime_type,
                "size_bytes": db_file.size_bytes,
                "status": db_file.status.value,
                "chunk_count": db_file.chunk_count,
                "text_length": processed.metadata.get("text_length", 0),
            }
        }
    except Exception as e:
        db_file.status = FileStatus.failed
        db_file.metadata_ = {"error": str(e)}
        await db.flush()
        logger.error("file_processing_failed", file_id=str(file_id), error=str(e))
        raise HTTPException(status_code=500, detail=f"File processing failed: {str(e)}")


@router.get("")
async def list_files(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's files."""
    result = await db.execute(
        select(File).where(
            File.org_id == tenant.org_id,
            File.user_id == tenant.user_id,
            File.deleted_at.is_(None),
        ).order_by(desc(File.created_at)).offset(offset).limit(limit)
    )
    files = result.scalars().all()

    return {
        "data": [
            {
                "id": str(f.id),
                "name": f.name,
                "mime_type": f.mime_type,
                "size_bytes": f.size_bytes,
                "status": f.status.value,
                "chunk_count": f.chunk_count,
                "created_at": f.created_at.isoformat(),
            }
            for f in files
        ]
    }


@router.get("/{file_id}")
async def get_file(
    file_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get file details."""
    result = await db.execute(
        select(File).where(
            File.id == file_id,
            File.org_id == tenant.org_id,
            File.deleted_at.is_(None),
        )
    )
    f = result.scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")

    # Check access
    if f.user_id != tenant.user_id and f.access.value == "private":
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "data": {
            "id": str(f.id),
            "name": f.name,
            "mime_type": f.mime_type,
            "size_bytes": f.size_bytes,
            "status": f.status.value,
            "chunk_count": f.chunk_count,
            "access": f.access.value,
            "metadata": f.metadata_,
            "created_at": f.created_at.isoformat(),
        }
    }


@router.get("/{file_id}/download")
async def download_file(
    file_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download file content."""
    result = await db.execute(
        select(File).where(
            File.id == file_id,
            File.org_id == tenant.org_id,
            File.deleted_at.is_(None),
        )
    )
    f = result.scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    if f.user_id != tenant.user_id and f.access.value == "private":
        raise HTTPException(status_code=403, detail="Access denied")

    import os
    if not os.path.exists(f.storage_path):
        raise HTTPException(status_code=404, detail="File content not found on disk")

    from fastapi.responses import FileResponse
    return FileResponse(
        path=f.storage_path,
        filename=f.name,
        media_type=f.mime_type,
    )


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a file."""
    result = await db.execute(
        select(File).where(
            File.id == file_id,
            File.user_id == tenant.user_id,
            File.org_id == tenant.org_id,
            File.deleted_at.is_(None),
        )
    )
    f = result.scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    f.deleted_at = datetime.now(timezone.utc)
    f.status = FileStatus.deleted
    await db.flush()


@router.get("/{file_id}/chunks")
async def get_file_chunks(
    file_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get chunks for a file."""
    # Verify file access
    result = await db.execute(
        select(File).where(File.id == file_id, File.org_id == tenant.org_id, File.deleted_at.is_(None))
    )
    f = result.scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")

    chunks_result = await db.execute(
        select(FileChunk).where(FileChunk.file_id == file_id)
        .order_by(FileChunk.chunk_index).offset(offset).limit(limit)
    )
    chunks = chunks_result.scalars().all()

    return {
        "data": [
            {
                "id": str(c.id),
                "chunk_index": c.chunk_index,
                "content": c.content[:200] + ("..." if len(c.content) > 200 else ""),
                "token_count": c.token_count,
            }
            for c in chunks
        ]
    }
