"""Google Drive OAuth and file import endpoints."""

import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.config import get_settings
from app.database import get_db
from app.middleware.tenant import get_current_user, TenantContext
from app.models.user import User, UserRole
from app.models.organization import Organization
from app.models.file import File, FileChunk, FileStatus
from app.models.google_oauth import GoogleOAuthToken
from app.services.google_drive import GoogleDriveService, encrypt_token, decrypt_token
from app.services.file_processor import process_file, save_file, compute_sha256, ALLOWED_TYPES
from app.services.auth import ensure_default_org, generate_tokens
from app.core.security import hash_password

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter(tags=["google-drive"])

drive_service = GoogleDriveService()


# -- Schemas --

class DriveImportRequest(BaseModel):
    file_id: str


# -- Public endpoints (OAuth flow) --

@router.get("/auth/google/redirect")
async def google_redirect():
    """Redirect user to Google OAuth consent screen."""
    if not settings.google_oauth_client_id:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")
    url = drive_service.get_auth_url()
    return RedirectResponse(url=url)


@router.get("/auth/google/callback")
async def google_callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback. Exchange code, create/link user, redirect with JWT."""
    if not settings.google_oauth_client_id:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")

    try:
        # Exchange code for tokens
        token_data = await drive_service.exchange_code(code)
    except Exception as e:
        logger.error("google_oauth_exchange_failed", error=str(e))
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code")

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)
    scopes = token_data.get("scope", "")

    # Get user info from Google
    try:
        user_info = await drive_service.get_user_info(access_token)
    except Exception as e:
        logger.error("google_userinfo_failed", error=str(e))
        raise HTTPException(status_code=400, detail="Failed to fetch Google user info")

    google_email = user_info.get("email", "")
    google_name = user_info.get("name", google_email.split("@")[0])

    if not google_email:
        raise HTTPException(status_code=400, detail="No email returned from Google")

    # Find or create user
    org = await ensure_default_org(db)

    result = await db.execute(
        select(User).where(User.org_id == org.id, User.email == google_email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if not user:
        # Check if first user in org (admin)
        result = await db.execute(select(User).where(User.org_id == org.id, User.deleted_at.is_(None)))
        existing_users = result.scalars().all()
        role = UserRole.admin if len(existing_users) == 0 else UserRole.member

        user = User(
            org_id=org.id,
            email=google_email,
            name=google_name,
            role=role,
        )
        db.add(user)
        await db.flush()
        logger.info("google_user_created", email=google_email, org_id=str(org.id))

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)

    # Store or update OAuth tokens
    result = await db.execute(
        select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user.id)
    )
    oauth_record = result.scalar_one_or_none()

    encrypted_access = encrypt_token(access_token)
    encrypted_refresh = encrypt_token(refresh_token) if refresh_token else ""
    token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    if oauth_record:
        oauth_record.google_email = google_email
        oauth_record.access_token = encrypted_access
        if refresh_token:
            oauth_record.refresh_token = encrypted_refresh
        oauth_record.token_expiry = token_expiry
        oauth_record.scopes = scopes
        oauth_record.updated_at = datetime.now(timezone.utc)
    else:
        oauth_record = GoogleOAuthToken(
            user_id=user.id,
            org_id=org.id,
            google_email=google_email,
            access_token=encrypted_access,
            refresh_token=encrypted_refresh,
            token_expiry=token_expiry,
            scopes=scopes,
        )
        db.add(oauth_record)

    await db.commit()

    # Generate JWT tokens
    tokens = generate_tokens(user)

    # Redirect to frontend with token
    frontend_url = settings.cors_origins[0] if settings.cors_origins else "http://localhost:3000"
    redirect_url = f"{frontend_url}/drive?access_token={tokens['access_token']}&refresh_token={tokens['refresh_token']}"
    return RedirectResponse(url=redirect_url)


# -- Protected endpoints --

@router.get("/auth/google/status")
async def google_status(
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if the user has connected their Google account."""
    result = await db.execute(
        select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == tenant.user_id)
    )
    oauth_record = result.scalar_one_or_none()

    if oauth_record:
        return {
            "data": {
                "connected": True,
                "google_email": oauth_record.google_email,
                "scopes": oauth_record.scopes,
                "connected_at": oauth_record.created_at.isoformat(),
            }
        }
    return {"data": {"connected": False}}


@router.get("/drive/files")
async def list_drive_files(
    page_size: int = Query(default=50, ge=1, le=100),
    page_token: str | None = Query(default=None),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List files from the user's connected Google Drive."""
    result = await db.execute(
        select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == tenant.user_id)
    )
    oauth_record = result.scalar_one_or_none()
    if not oauth_record:
        raise HTTPException(status_code=400, detail="Google Drive not connected. Please connect your account first.")

    try:
        files_data = await drive_service.list_files(oauth_record, page_size=page_size, page_token=page_token)
        await db.commit()  # Persist any token refresh updates
    except Exception as e:
        logger.error("drive_list_failed", error=str(e), user_id=str(tenant.user_id))
        raise HTTPException(status_code=502, detail="Failed to list Google Drive files")

    return {
        "data": files_data.get("files", []),
        "meta": {
            "next_page_token": files_data.get("nextPageToken"),
        },
    }


@router.post("/drive/import")
async def import_drive_file(
    req: DriveImportRequest,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import a file from Google Drive into the platform."""
    result = await db.execute(
        select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == tenant.user_id)
    )
    oauth_record = result.scalar_one_or_none()
    if not oauth_record:
        raise HTTPException(status_code=400, detail="Google Drive not connected")

    # Download from Drive
    try:
        data, filename, mime_type = await drive_service.download_file(oauth_record, req.file_id)
        await db.flush()  # Persist any token refresh updates
    except Exception as e:
        logger.error("drive_download_failed", error=str(e), file_id=req.file_id)
        raise HTTPException(status_code=502, detail=f"Failed to download file from Drive: {str(e)}")

    # Validate type (map to allowed types, fall back to application/pdf for exports)
    if mime_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type after download: {mime_type}. Supported: {list(ALLOWED_TYPES.keys())}",
        )

    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Downloaded file is empty")

    # Create file record and process through existing pipeline
    file_id = uuid.uuid4()
    sha256 = compute_sha256(data)
    ext = ALLOWED_TYPES.get(mime_type, ".bin")
    storage_path = save_file(data, tenant.org_id, file_id, ext)

    db_file = File(
        id=file_id,
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        name=filename,
        mime_type=mime_type,
        size_bytes=len(data),
        sha256_hash=sha256,
        storage_path=storage_path,
        status=FileStatus.processing,
    )
    db.add(db_file)
    await db.flush()

    try:
        processed = process_file(data, mime_type, filename)

        for i, chunk_text in enumerate(processed.chunks):
            chunk = FileChunk(
                file_id=file_id,
                org_id=tenant.org_id,
                chunk_index=i,
                content=chunk_text,
                token_count=len(chunk_text) // 4,
                metadata_={"source": filename, "chunk_index": i, "origin": "google_drive", "drive_file_id": req.file_id},
            )
            db.add(chunk)

        db_file.status = FileStatus.ready
        db_file.chunk_count = len(processed.chunks)
        db_file.metadata_ = {**processed.metadata, "origin": "google_drive", "drive_file_id": req.file_id}
        await db.commit()

        logger.info("drive_file_imported", file_id=str(file_id), name=filename, chunks=len(processed.chunks))

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
        db_file.metadata_ = {"error": str(e), "origin": "google_drive"}
        await db.commit()
        logger.error("drive_import_processing_failed", file_id=str(file_id), error=str(e))
        raise HTTPException(status_code=500, detail=f"File processing failed: {str(e)}")


@router.delete("/auth/google/disconnect")
async def google_disconnect(
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke Google OAuth tokens and remove stored credentials."""
    result = await db.execute(
        select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == tenant.user_id)
    )
    oauth_record = result.scalar_one_or_none()
    if not oauth_record:
        raise HTTPException(status_code=404, detail="Google account not connected")

    # Revoke with Google
    if oauth_record.refresh_token:
        await drive_service.revoke_token(oauth_record.refresh_token)

    await db.delete(oauth_record)
    await db.commit()

    logger.info("google_disconnected", user_id=str(tenant.user_id))
    return {"data": {"message": "Google account disconnected successfully"}}
