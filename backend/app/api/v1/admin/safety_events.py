"""Admin safety events endpoints."""

import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.tenant import require_admin, TenantContext
from app.models.safety_event import SafetyEvent
from app.core.response import make_meta

router = APIRouter(prefix="/admin/safety-events", tags=["admin-safety"])


@router.get("")
async def list_safety_events(
    event_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=90),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List safety events (admin only)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(SafetyEvent).where(
        SafetyEvent.org_id == tenant.org_id,
        SafetyEvent.created_at >= since,
    )
    count_stmt = select(func.count()).select_from(SafetyEvent).where(
        SafetyEvent.org_id == tenant.org_id,
        SafetyEvent.created_at >= since,
    )

    if event_type:
        stmt = stmt.where(SafetyEvent.event_type == event_type)
        count_stmt = count_stmt.where(SafetyEvent.event_type == event_type)
    if severity:
        stmt = stmt.where(SafetyEvent.severity == severity)
        count_stmt = count_stmt.where(SafetyEvent.severity == severity)

    stmt = stmt.order_by(desc(SafetyEvent.created_at)).offset(offset).limit(limit)
    total = (await db.execute(count_stmt)).scalar()
    result = await db.execute(stmt)
    events = result.scalars().all()

    return {
        "data": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "severity": e.severity,
                "action_taken": e.action_taken,
                "direction": e.direction,
                "flags": e.flags,
                "content_snippet": e.content_snippet,
                "user_id": str(e.user_id) if e.user_id else None,
                "conversation_id": str(e.conversation_id) if e.conversation_id else None,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
        "meta": {**make_meta(), "total": total, "limit": limit, "offset": offset},
    }


@router.get("/{event_id}")
async def get_safety_event(
    event_id: uuid.UUID,
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get safety event detail (admin only)."""
    result = await db.execute(
        select(SafetyEvent).where(
            SafetyEvent.id == event_id,
            SafetyEvent.org_id == tenant.org_id,
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Safety event not found")

    return {
        "data": {
            "id": str(event.id),
            "event_type": event.event_type,
            "severity": event.severity,
            "action_taken": event.action_taken,
            "direction": event.direction,
            "flags": event.flags,
            "content_snippet": event.content_snippet,
            "details": event.details,
            "user_id": str(event.user_id) if event.user_id else None,
            "conversation_id": str(event.conversation_id) if event.conversation_id else None,
            "message_id": str(event.message_id) if event.message_id else None,
            "created_at": event.created_at.isoformat(),
        },
        "meta": make_meta(),
    }
