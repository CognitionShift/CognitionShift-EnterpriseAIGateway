"""Model Registry API — catalog, version, and share institutional AI models."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.tenant import get_current_user, TenantContext
from app.models.model_registry import (
    RegisteredModel, ModelVersion, ModelAccess,
    ModelVisibility, VersionStatus, AccessGranteeType, AccessPermission,
)
from app.schemas.registry import ModelCreate, ModelUpdate, VersionCreate, VersionUpdate, AccessGrant
from app.core.response import make_meta

router = APIRouter(prefix="/registry", tags=["model-registry"])


# ── Helpers ──────────────────────────────────────────────────────────

def _model_to_dict(m: RegisteredModel, version_count: int = 0, latest_version: dict | None = None) -> dict:
    return {
        "id": str(m.id),
        "name": m.name,
        "display_name": m.display_name,
        "description": m.description,
        "visibility": m.visibility.value if m.visibility else "private",
        "department_id": str(m.department_id) if m.department_id else None,
        "tags": m.tags or [],
        "created_by": str(m.created_by),
        "created_at": m.created_at.isoformat(),
        "updated_at": m.updated_at.isoformat(),
        "version_count": version_count,
        "latest_version": latest_version,
    }


def _version_to_dict(v: ModelVersion) -> dict:
    return {
        "id": str(v.id),
        "model_id": str(v.model_id),
        "version": v.version,
        "status": v.status.value if v.status else "draft",
        "release_notes": v.release_notes,
        "training_data": v.training_data,
        "intended_use": v.intended_use,
        "limitations": v.limitations,
        "license": v.license,
        "architecture": v.architecture,
        "eval_results": v.eval_results,
        "artifact_uri": v.artifact_uri,
        "artifact_size_bytes": v.artifact_size_bytes,
        "artifact_hash": v.artifact_hash,
        "gateway_config": v.gateway_config,
        "created_by": str(v.created_by),
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "created_at": v.created_at.isoformat(),
    }


def _access_to_dict(a: ModelAccess) -> dict:
    return {
        "id": str(a.id),
        "model_id": str(a.model_id),
        "grantee_type": a.grantee_type.value,
        "grantee_id": str(a.grantee_id),
        "permission": a.permission.value,
        "granted_by": str(a.granted_by),
        "created_at": a.created_at.isoformat(),
    }


async def _check_model_access(
    model: RegisteredModel,
    tenant: TenantContext,
    required_permission: str = "view",
) -> bool:
    """Check if the current user can access this model."""
    # Creator always has full access
    if model.created_by == tenant.user_id:
        return True
    # Org admins have full access
    if tenant.role == "admin":
        return True
    # Organization-wide models are viewable by all org members
    if model.visibility == ModelVisibility.organization and required_permission == "view":
        return True
    # Department models: TODO check department membership when departments are fully wired
    if model.visibility == ModelVisibility.department and required_permission == "view":
        return True
    # Check explicit grants (loaded via selectin)
    for grant in model.access_grants:
        if grant.grantee_type == AccessGranteeType.user and grant.grantee_id == tenant.user_id:
            # Permission hierarchy: admin > edit > use > view
            hierarchy = ["view", "use", "edit", "admin"]
            if hierarchy.index(grant.permission.value) >= hierarchy.index(required_permission):
                return True
        if grant.grantee_type == AccessGranteeType.organization and grant.grantee_id == tenant.org_id:
            hierarchy = ["view", "use", "edit", "admin"]
            if hierarchy.index(grant.permission.value) >= hierarchy.index(required_permission):
                return True
    return False


async def _get_model_or_404(
    model_id: str,
    tenant: TenantContext,
    db: AsyncSession,
    required_permission: str = "view",
) -> RegisteredModel:
    """Fetch model, verify org scope and access."""
    try:
        uid = uuid.UUID(model_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid model ID")

    result = await db.execute(
        select(RegisteredModel).where(
            RegisteredModel.id == uid,
            RegisteredModel.org_id == tenant.org_id,
            RegisteredModel.deleted_at.is_(None),
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    if not await _check_model_access(model, tenant, required_permission):
        raise HTTPException(status_code=403, detail="Access denied")

    return model


# ── Model CRUD ───────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_model(
    req: ModelCreate,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new model in the registry."""
    # Check for duplicate name within org
    existing = await db.execute(
        select(RegisteredModel).where(
            RegisteredModel.org_id == tenant.org_id,
            RegisteredModel.name == req.name,
            RegisteredModel.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Model '{req.name}' already exists")

    model = RegisteredModel(
        org_id=tenant.org_id,
        name=req.name,
        display_name=req.display_name or req.name,
        description=req.description,
        visibility=ModelVisibility(req.visibility),
        department_id=uuid.UUID(req.department_id) if req.department_id else None,
        tags=req.tags,
        created_by=tenant.user_id,
    )
    db.add(model)
    await db.flush()

    return {"data": _model_to_dict(model), "meta": make_meta()}


@router.get("")
async def list_models(
    q: str | None = Query(None, description="Search query"),
    visibility: str | None = Query(None),
    tags: list[str] | None = Query(None),
    has_gateway: bool | None = Query(None),
    sort: str = Query("updated_at", pattern="^(created_at|updated_at|name)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List models visible to the current user."""
    query = select(RegisteredModel).where(
        RegisteredModel.org_id == tenant.org_id,
        RegisteredModel.deleted_at.is_(None),
    )

    # Visibility filter: user sees models they created, org-wide models,
    # department models, and models with explicit access grants
    if tenant.role != "admin":
        query = query.where(
            or_(
                RegisteredModel.created_by == tenant.user_id,
                RegisteredModel.visibility == ModelVisibility.organization,
                RegisteredModel.visibility == ModelVisibility.department,
                # Models with explicit user grant are handled post-filter for now
            )
        )

    if visibility:
        query = query.where(RegisteredModel.visibility == ModelVisibility(visibility))

    if q:
        search = f"%{q}%"
        query = query.where(
            or_(
                RegisteredModel.name.ilike(search),
                RegisteredModel.display_name.ilike(search),
                RegisteredModel.description.ilike(search),
            )
        )

    # Sort
    sort_col = {
        "created_at": RegisteredModel.created_at,
        "updated_at": RegisteredModel.updated_at,
        "name": RegisteredModel.name,
    }[sort]
    query = query.order_by(desc(sort_col) if sort != "name" else sort_col)
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    models = result.scalars().all()

    # Get version counts
    data = []
    for m in models:
        ver_count = len(m.versions) if m.versions else 0
        # Find latest published version
        latest = None
        published = [v for v in (m.versions or []) if v.status == VersionStatus.published]
        if published:
            published.sort(key=lambda v: v.published_at or v.created_at, reverse=True)
            latest = {"version": published[0].version, "status": "published", "published_at": published[0].published_at.isoformat() if published[0].published_at else None}
        data.append(_model_to_dict(m, ver_count, latest))

    # Total count
    count_query = select(func.count(RegisteredModel.id)).where(
        RegisteredModel.org_id == tenant.org_id,
        RegisteredModel.deleted_at.is_(None),
    )
    total = (await db.execute(count_query)).scalar() or 0

    return {"data": data, "meta": make_meta(), "pagination": {"total": total, "offset": offset, "limit": limit}}


@router.get("/{model_id}")
async def get_model(
    model_id: str,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get model details with versions."""
    model = await _get_model_or_404(model_id, tenant, db)
    ver_count = len(model.versions) if model.versions else 0

    latest = None
    published = [v for v in (model.versions or []) if v.status == VersionStatus.published]
    if published:
        published.sort(key=lambda v: v.published_at or v.created_at, reverse=True)
        latest = _version_to_dict(published[0])

    result = _model_to_dict(model, ver_count, latest)
    result["versions"] = [_version_to_dict(v) for v in sorted(model.versions or [], key=lambda v: v.created_at, reverse=True)]

    return {"data": result, "meta": make_meta()}


@router.patch("/{model_id}")
async def update_model(
    model_id: str,
    req: ModelUpdate,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update model metadata."""
    model = await _get_model_or_404(model_id, tenant, db, required_permission="edit")

    if req.display_name is not None:
        model.display_name = req.display_name
    if req.description is not None:
        model.description = req.description
    if req.visibility is not None:
        model.visibility = ModelVisibility(req.visibility)
    if req.department_id is not None:
        model.department_id = uuid.UUID(req.department_id) if req.department_id else None
    if req.tags is not None:
        model.tags = req.tags
    model.updated_at = datetime.now(timezone.utc)

    return {"data": _model_to_dict(model), "meta": make_meta()}


@router.delete("/{model_id}", status_code=204)
async def delete_model(
    model_id: str,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft delete (archive) a model."""
    model = await _get_model_or_404(model_id, tenant, db, required_permission="admin")
    model.deleted_at = datetime.now(timezone.utc)
    return None


# ── Versions ─────────────────────────────────────────────────────────

@router.post("/{model_id}/versions", status_code=201)
async def create_version(
    model_id: str,
    req: VersionCreate,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new draft version."""
    model = await _get_model_or_404(model_id, tenant, db, required_permission="edit")

    # Check for duplicate version
    for v in model.versions or []:
        if v.version == req.version:
            raise HTTPException(status_code=409, detail=f"Version '{req.version}' already exists")

    version = ModelVersion(
        model_id=model.id,
        version=req.version,
        status=VersionStatus.draft,
        release_notes=req.release_notes,
        training_data=req.training_data,
        intended_use=req.intended_use,
        limitations=req.limitations,
        license=req.license,
        architecture=req.architecture,
        eval_results=req.eval_results,
        artifact_uri=req.artifact_uri,
        artifact_size_bytes=req.artifact_size_bytes,
        artifact_hash=req.artifact_hash,
        gateway_config=req.gateway_config,
        created_by=tenant.user_id,
    )
    db.add(version)
    await db.flush()

    model.updated_at = datetime.now(timezone.utc)

    return {"data": _version_to_dict(version), "meta": make_meta()}


@router.get("/{model_id}/versions")
async def list_versions(
    model_id: str,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all versions for a model."""
    model = await _get_model_or_404(model_id, tenant, db)
    versions = sorted(model.versions or [], key=lambda v: v.created_at, reverse=True)
    return {"data": [_version_to_dict(v) for v in versions], "meta": make_meta()}


@router.get("/{model_id}/versions/{version_id}")
async def get_version(
    model_id: str,
    version_id: str,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific version."""
    model = await _get_model_or_404(model_id, tenant, db)
    for v in model.versions or []:
        if str(v.id) == version_id:
            return {"data": _version_to_dict(v), "meta": make_meta()}
    raise HTTPException(status_code=404, detail="Version not found")


@router.patch("/{model_id}/versions/{version_id}")
async def update_version(
    model_id: str,
    version_id: str,
    req: VersionUpdate,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a draft version. Published versions cannot be modified."""
    model = await _get_model_or_404(model_id, tenant, db, required_permission="edit")

    version = None
    for v in model.versions or []:
        if str(v.id) == version_id:
            version = v
            break
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    if version.status != VersionStatus.draft:
        raise HTTPException(status_code=400, detail="Only draft versions can be modified")

    for field in ["release_notes", "training_data", "intended_use", "limitations",
                  "license", "architecture", "eval_results", "artifact_uri",
                  "artifact_size_bytes", "artifact_hash", "gateway_config"]:
        val = getattr(req, field)
        if val is not None:
            setattr(version, field, val)

    return {"data": _version_to_dict(version), "meta": make_meta()}


@router.post("/{model_id}/versions/{version_id}/publish")
async def publish_version(
    model_id: str,
    version_id: str,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Publish a version. Makes it immutable."""
    model = await _get_model_or_404(model_id, tenant, db, required_permission="edit")

    version = None
    for v in model.versions or []:
        if str(v.id) == version_id:
            version = v
            break
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    if version.status == VersionStatus.published:
        raise HTTPException(status_code=400, detail="Version is already published")

    version.status = VersionStatus.published
    version.published_at = datetime.now(timezone.utc)
    model.updated_at = datetime.now(timezone.utc)

    return {"data": _version_to_dict(version), "meta": make_meta()}


@router.post("/{model_id}/versions/{version_id}/deprecate")
async def deprecate_version(
    model_id: str,
    version_id: str,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deprecate a published version."""
    model = await _get_model_or_404(model_id, tenant, db, required_permission="edit")

    version = None
    for v in model.versions or []:
        if str(v.id) == version_id:
            version = v
            break
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    version.status = VersionStatus.deprecated

    return {"data": _version_to_dict(version), "meta": make_meta()}


# ── Access Control ───────────────────────────────────────────────────

@router.get("/{model_id}/access")
async def list_access(
    model_id: str,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List access grants for a model."""
    model = await _get_model_or_404(model_id, tenant, db, required_permission="admin")
    return {"data": [_access_to_dict(a) for a in model.access_grants or []], "meta": make_meta()}


@router.post("/{model_id}/access", status_code=201)
async def grant_access(
    model_id: str,
    req: AccessGrant,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grant access to a model."""
    model = await _get_model_or_404(model_id, tenant, db, required_permission="admin")

    grant = ModelAccess(
        model_id=model.id,
        grantee_type=AccessGranteeType(req.grantee_type),
        grantee_id=uuid.UUID(req.grantee_id),
        permission=AccessPermission(req.permission),
        granted_by=tenant.user_id,
    )
    db.add(grant)
    await db.flush()

    return {"data": _access_to_dict(grant), "meta": make_meta()}


@router.delete("/{model_id}/access/{access_id}", status_code=204)
async def revoke_access(
    model_id: str,
    access_id: str,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an access grant."""
    model = await _get_model_or_404(model_id, tenant, db, required_permission="admin")

    try:
        aid = uuid.UUID(access_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid access ID")

    for grant in model.access_grants or []:
        if grant.id == aid:
            await db.delete(grant)
            return None

    raise HTTPException(status_code=404, detail="Access grant not found")
