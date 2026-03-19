"""Context portability endpoints: export and import .csgw bundles."""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.tenant import get_current_user, TenantContext
from app.models.context_job import ContextExportJob, ContextImportJob, ExportJobStatus, ImportJobStatus
from app.schemas.context import ExportRequest, ExportJobResponse, ImportJobResponse
from app.services.context_portability import ContextExporter, ContextImporter, BundleValidator
from app.core.response import make_meta

logger = structlog.get_logger()
router = APIRouter(prefix="/context", tags=["context-portability"])

# Storage directory for bundles
BUNDLE_DIR = Path(os.environ.get("BUNDLE_STORAGE_DIR", "/tmp/csgw-bundles"))


def _ensure_bundle_dir() -> None:
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/export", status_code=201)
async def create_export(
    req: ExportRequest,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a context export job. Builds a .csgw portable bundle."""
    _ensure_bundle_dir()

    # Check for recent exports (rate limit: 1 per hour)
    one_hour_ago = datetime.now(timezone.utc).replace(
        minute=datetime.now(timezone.utc).minute,
        second=0,
        microsecond=0,
    )
    from datetime import timedelta
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

    recent_result = await db.execute(
        select(ContextExportJob).where(
            ContextExportJob.user_id == tenant.user_id,
            ContextExportJob.org_id == tenant.org_id,
            ContextExportJob.created_at >= one_hour_ago,
            ContextExportJob.status != ExportJobStatus.failed,
        )
    )
    if recent_result.scalar_one_or_none():
        raise HTTPException(status_code=429, detail="Export rate limit: one export per hour")

    # Create job record
    job = ContextExportJob(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        status=ExportJobStatus.running,
        options={
            "conversation_ids": [str(cid) for cid in req.conversation_ids] if req.conversation_ids else None,
            "date_from": req.date_from.isoformat() if req.date_from else None,
            "date_to": req.date_to.isoformat() if req.date_to else None,
            "include_files": req.include_files,
            "include_embeddings": req.include_embeddings,
        },
    )
    db.add(job)
    await db.flush()

    # Build the bundle synchronously (for MVP; large exports should be async via task queue)
    output_path = str(BUNDLE_DIR / f"{job.id}.csgw")
    try:
        exporter = ContextExporter(db, tenant.org_id, tenant.user_id)
        file_size = await exporter.export_bundle(
            output_path=output_path,
            conversation_ids=req.conversation_ids,
            date_from=req.date_from,
            date_to=req.date_to,
            include_files=req.include_files,
            include_embeddings=req.include_embeddings,
            user_email=tenant.email,
        )
        job.status = ExportJobStatus.completed
        job.file_path = output_path
        job.file_size = file_size
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()

        logger.info("context_export_completed", job_id=str(job.id), file_size=file_size)

    except Exception as e:
        job.status = ExportJobStatus.failed
        job.error_message = str(e)
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        logger.error("context_export_failed", job_id=str(job.id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

    return {
        "data": {
            "job_id": str(job.id),
            "status": job.status.value,
            "file_size": job.file_size,
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        },
        "meta": make_meta(),
    }


@router.get("/export/{job_id}")
async def get_export_status(
    job_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check export job status."""
    result = await db.execute(
        select(ContextExportJob).where(
            ContextExportJob.id == job_id,
            ContextExportJob.org_id == tenant.org_id,
            ContextExportJob.user_id == tenant.user_id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")

    return {
        "data": {
            "job_id": str(job.id),
            "status": job.status.value,
            "file_size": job.file_size,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        },
        "meta": make_meta(),
    }


@router.get("/export/{job_id}/download")
async def download_export(
    job_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a completed export bundle."""
    result = await db.execute(
        select(ContextExportJob).where(
            ContextExportJob.id == job_id,
            ContextExportJob.org_id == tenant.org_id,
            ContextExportJob.user_id == tenant.user_id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")

    if job.status != ExportJobStatus.completed:
        raise HTTPException(status_code=400, detail=f"Export not ready. Status: {job.status.value}")

    if not job.file_path or not os.path.exists(job.file_path):
        raise HTTPException(status_code=404, detail="Export file not found on disk")

    return FileResponse(
        path=job.file_path,
        filename=f"context-export-{job_id}.csgw",
        media_type="application/octet-stream",
    )


@router.post("/import", status_code=201)
async def create_import(
    file: UploadFile = FastAPIFile(...),
    mode: str = Query(default="merge", regex="^(merge|replace)$"),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload and import a .csgw bundle."""
    _ensure_bundle_dir()

    # Save uploaded file
    job_id = uuid.uuid4()
    bundle_path = str(BUNDLE_DIR / f"import-{job_id}.csgw")

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    with open(bundle_path, "wb") as f:
        f.write(data)

    # Validate bundle
    validator = BundleValidator(bundle_path)
    if not validator.validate():
        os.remove(bundle_path)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bundle: {'; '.join(validator.errors)}",
        )

    # Create job record
    job = ContextImportJob(
        id=job_id,
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        status=ImportJobStatus.importing,
        options={"mode": mode},
        file_path=bundle_path,
    )
    db.add(job)
    await db.flush()

    # Run import synchronously (MVP; large imports should be async)
    try:
        importer = ContextImporter(db, tenant.org_id, tenant.user_id)
        stats = await importer.import_bundle(bundle_path, mode=mode)
        job.status = ImportJobStatus.completed
        job.stats = stats
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()

        logger.info("context_import_completed", job_id=str(job.id), stats=stats)

    except Exception as e:
        job.status = ImportJobStatus.failed
        job.error_message = str(e)
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        logger.error("context_import_failed", job_id=str(job.id), error=str(e))
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

    return {
        "data": {
            "job_id": str(job.id),
            "status": job.status.value,
            "stats": job.stats,
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        },
        "meta": make_meta(),
    }


@router.get("/import/{job_id}")
async def get_import_status(
    job_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check import job status."""
    result = await db.execute(
        select(ContextImportJob).where(
            ContextImportJob.id == job_id,
            ContextImportJob.org_id == tenant.org_id,
            ContextImportJob.user_id == tenant.user_id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")

    return {
        "data": {
            "job_id": str(job.id),
            "status": job.status.value,
            "stats": job.stats,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        },
        "meta": make_meta(),
    }
