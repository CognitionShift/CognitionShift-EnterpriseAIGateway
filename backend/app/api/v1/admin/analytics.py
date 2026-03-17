"""Admin analytics endpoints — overview, adoption, costs, safety."""

import csv
import io
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, cast, Date, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.tenant import require_admin, TenantContext
from app.models.usage import UsageLog
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.models.audit import AuditLog

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])


@router.get("/overview")
async def overview(
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard overview stats."""
    org_id = tenant.org_id
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    # Users count
    users_count = (await db.execute(
        select(func.count()).select_from(User).where(User.org_id == org_id, User.deleted_at.is_(None))
    )).scalar()

    # Active users (7d)
    active_users = (await db.execute(
        select(func.count(func.distinct(UsageLog.user_id))).where(
            UsageLog.org_id == org_id, UsageLog.created_at >= week_ago
        )
    )).scalar()

    # Conversations (7d)
    convos_week = (await db.execute(
        select(func.count()).select_from(Conversation).where(
            Conversation.org_id == org_id, Conversation.created_at >= week_ago
        )
    )).scalar()

    # Messages (7d)
    msgs_week = (await db.execute(
        select(func.count()).select_from(Message).where(
            Message.org_id == org_id, Message.created_at >= week_ago
        )
    )).scalar()

    # Total tokens and cost (7d)
    usage = (await db.execute(
        select(
            func.coalesce(func.sum(UsageLog.input_tokens + UsageLog.output_tokens), 0).label("tokens"),
            func.coalesce(func.sum(UsageLog.cost_usd), 0).label("cost"),
            func.count().label("requests"),
        ).where(UsageLog.org_id == org_id, UsageLog.created_at >= week_ago)
    )).one()

    # Safety events (7d)
    safety_count = (await db.execute(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.org_id == org_id, AuditLog.safety_event == True, AuditLog.created_at >= week_ago
        )
    )).scalar()

    return {
        "data": {
            "period": "7d",
            "users": {"total": users_count, "active": active_users},
            "conversations": convos_week,
            "messages": msgs_week,
            "usage": {
                "tokens": int(usage.tokens),
                "cost_usd": round(float(usage.cost), 4),
                "requests": int(usage.requests),
            },
            "safety_events": safety_count,
        }
    }


@router.get("/adoption")
async def adoption(
    days: int = Query(default=30, ge=1, le=90),
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """User adoption over time."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            cast(UsageLog.created_at, Date).label("date"),
            func.count(func.distinct(UsageLog.user_id)).label("active_users"),
            func.count().label("requests"),
        ).where(
            UsageLog.org_id == tenant.org_id, UsageLog.created_at >= since
        ).group_by(cast(UsageLog.created_at, Date)).order_by(cast(UsageLog.created_at, Date))
    )
    return {
        "data": [
            {"date": str(r.date), "active_users": r.active_users, "requests": r.requests}
            for r in result.all()
        ]
    }


@router.get("/models")
async def model_usage(
    days: int = Query(default=30, ge=1, le=90),
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Model usage distribution."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            UsageLog.model_id,
            func.count().label("requests"),
            func.coalesce(func.sum(UsageLog.input_tokens + UsageLog.output_tokens), 0).label("tokens"),
            func.coalesce(func.sum(UsageLog.cost_usd), 0).label("cost"),
            func.coalesce(func.avg(UsageLog.latency_ms), 0).label("avg_latency_ms"),
        ).where(
            UsageLog.org_id == tenant.org_id, UsageLog.created_at >= since
        ).group_by(UsageLog.model_id).order_by(desc(func.count()))
    )
    return {
        "data": [
            {
                "model_id": r.model_id,
                "requests": r.requests,
                "tokens": int(r.tokens),
                "cost_usd": round(float(r.cost), 4),
                "avg_latency_ms": round(float(r.avg_latency_ms)),
            }
            for r in result.all()
        ]
    }


@router.get("/costs")
async def cost_breakdown(
    days: int = Query(default=30, ge=1, le=90),
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Cost breakdown by day."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            cast(UsageLog.created_at, Date).label("date"),
            func.coalesce(func.sum(UsageLog.cost_usd), 0).label("cost"),
            func.coalesce(func.sum(UsageLog.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(UsageLog.output_tokens), 0).label("output_tokens"),
        ).where(
            UsageLog.org_id == tenant.org_id, UsageLog.created_at >= since
        ).group_by(cast(UsageLog.created_at, Date)).order_by(cast(UsageLog.created_at, Date))
    )
    rows = result.all()

    # Cost projection
    if rows:
        recent_cost = sum(float(r.cost) for r in rows[-7:]) if len(rows) >= 7 else sum(float(r.cost) for r in rows)
        daily_avg = recent_cost / min(7, len(rows))
        monthly_projection = daily_avg * 30
    else:
        daily_avg = 0
        monthly_projection = 0

    return {
        "data": {
            "daily": [
                {
                    "date": str(r.date),
                    "cost_usd": round(float(r.cost), 4),
                    "input_tokens": int(r.input_tokens),
                    "output_tokens": int(r.output_tokens),
                }
                for r in rows
            ],
            "projection": {
                "daily_avg_usd": round(daily_avg, 4),
                "monthly_usd": round(monthly_projection, 2),
                "quarterly_usd": round(monthly_projection * 3, 2),
            },
        }
    }


@router.get("/safety")
async def safety_analytics(
    days: int = Query(default=30, ge=1, le=90),
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Content safety event trends."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Try safety_events table first, fall back to audit_log
    try:
        from app.models.safety_event import SafetyEvent
        # By type
        type_result = await db.execute(
            select(
                SafetyEvent.event_type,
                func.count().label("count"),
            ).where(
                SafetyEvent.org_id == tenant.org_id,
                SafetyEvent.created_at >= since,
            ).group_by(SafetyEvent.event_type).order_by(desc(func.count()))
        )
        by_type = [{"event_type": r.event_type, "count": r.count} for r in type_result.all()]

        # By day
        daily_result = await db.execute(
            select(
                cast(SafetyEvent.created_at, Date).label("date"),
                func.count().label("count"),
            ).where(
                SafetyEvent.org_id == tenant.org_id,
                SafetyEvent.created_at >= since,
            ).group_by(cast(SafetyEvent.created_at, Date)).order_by(cast(SafetyEvent.created_at, Date))
        )
        by_day = [{"date": str(r.date), "count": r.count} for r in daily_result.all()]

        # By severity
        severity_result = await db.execute(
            select(
                SafetyEvent.severity,
                func.count().label("count"),
            ).where(
                SafetyEvent.org_id == tenant.org_id,
                SafetyEvent.created_at >= since,
            ).group_by(SafetyEvent.severity)
        )
        by_severity = [{"severity": r.severity, "count": r.count} for r in severity_result.all()]

        total = sum(item["count"] for item in by_type)
    except Exception:
        # Fallback to audit_log safety events
        total_result = await db.execute(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.org_id == tenant.org_id,
                AuditLog.safety_event == True,
                AuditLog.created_at >= since,
            )
        )
        total = total_result.scalar() or 0
        by_type = []
        by_day = []
        by_severity = []

    return {
        "data": {
            "period_days": days,
            "total_events": total,
            "by_type": by_type,
            "by_day": by_day,
            "by_severity": by_severity,
        }
    }


@router.get("/chargeback")
async def chargeback_export(
    days: int = Query(default=30, ge=1, le=90),
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Export chargeback report as CSV (grouped by user)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Get usage grouped by user
    result = await db.execute(
        select(
            UsageLog.user_id,
            func.count().label("requests"),
            func.coalesce(func.sum(UsageLog.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(UsageLog.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(UsageLog.cost_usd), 0).label("cost"),
        ).where(
            UsageLog.org_id == tenant.org_id, UsageLog.created_at >= since
        ).group_by(UsageLog.user_id).order_by(desc(func.sum(UsageLog.cost_usd)))
    )
    rows = result.all()

    # Get user names
    user_names = {}
    for row in rows:
        user_result = await db.execute(select(User.name, User.email).where(User.id == row.user_id))
        user_data = user_result.one_or_none()
        if user_data:
            user_names[row.user_id] = (user_data.name, user_data.email)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_id", "name", "email", "requests", "input_tokens", "output_tokens", "total_tokens", "cost_usd"])
    for row in rows:
        name, email = user_names.get(row.user_id, ("Unknown", "unknown"))
        writer.writerow([
            str(row.user_id),
            name,
            email,
            row.requests,
            int(row.input_tokens),
            int(row.output_tokens),
            int(row.input_tokens) + int(row.output_tokens),
            f"{float(row.cost):.4f}",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=chargeback-{days}d.csv"},
    )
