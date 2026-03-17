"""Admin audit log endpoints."""

import uuid
import csv
import io
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.tenant import require_admin, TenantContext
from app.models.audit import AuditLog

router = APIRouter(prefix="/admin/audit", tags=["admin-audit"])


@router.get("")
async def list_audit_events(
    action: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    safety_only: bool = Query(default=False),
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Query audit log with filters."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    filters = [AuditLog.org_id == tenant.org_id, AuditLog.created_at >= since]
    if action:
        filters.append(AuditLog.action.ilike(f"%{action}%"))
    if actor_id:
        filters.append(AuditLog.actor_id == uuid.UUID(actor_id))
    if resource_type:
        filters.append(AuditLog.resource_type == resource_type)
    if safety_only:
        filters.append(AuditLog.safety_event == True)

    # Count
    count_result = await db.execute(
        select(func.count()).select_from(AuditLog).where(*filters)
    )
    total = count_result.scalar()

    # Fetch
    result = await db.execute(
        select(AuditLog)
        .where(*filters)
        .order_by(desc(AuditLog.created_at))
        .offset(offset)
        .limit(limit)
    )
    events = result.scalars().all()

    return {
        "data": [
            {
                "id": str(e.id),
                "actor_id": str(e.actor_id) if e.actor_id else None,
                "actor_type": e.actor_type,
                "actor_ip": e.actor_ip,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": str(e.resource_id) if e.resource_id else None,
                "details": e.details,
                "safety_event": e.safety_event,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.get("/export")
async def export_audit_log(
    days: int = Query(default=30, ge=1, le=365),
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Export audit log as CSV."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.org_id == tenant.org_id, AuditLog.created_at >= since)
        .order_by(AuditLog.created_at)
    )
    events = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "actor_id", "actor_type", "actor_ip", "action", "resource_type", "resource_id", "safety_event", "details"])
    for e in events:
        writer.writerow([
            e.created_at.isoformat(),
            str(e.actor_id) if e.actor_id else "",
            e.actor_type,
            e.actor_ip or "",
            e.action,
            e.resource_type,
            str(e.resource_id) if e.resource_id else "",
            str(e.safety_event),
            str(e.details),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=audit-log-{days}d.csv"},
    )


@router.get("/stats")
async def audit_stats(
    days: int = Query(default=7, ge=1, le=90),
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Audit log statistics."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    filters = [AuditLog.org_id == tenant.org_id, AuditLog.created_at >= since]

    # Total events
    total_result = await db.execute(
        select(func.count()).select_from(AuditLog).where(*filters)
    )
    total = total_result.scalar()

    # Safety events
    safety_result = await db.execute(
        select(func.count()).select_from(AuditLog).where(*filters, AuditLog.safety_event == True)
    )
    safety_count = safety_result.scalar()

    # By action type
    action_result = await db.execute(
        select(AuditLog.action, func.count().label("count"))
        .where(*filters)
        .group_by(AuditLog.action)
        .order_by(desc(func.count()))
        .limit(20)
    )
    by_action = [{"action": r.action, "count": r.count} for r in action_result.all()]

    return {
        "data": {
            "total_events": total,
            "safety_events": safety_count,
            "by_action": by_action,
            "period_days": days,
        }
    }
