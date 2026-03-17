"""Usage tracking and dashboard endpoints."""

import csv
import io
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.tenant import get_current_user, TenantContext
from app.models.usage import UsageLog

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/me")
async def my_usage(
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's usage for the current period."""
    now = datetime.now(timezone.utc)
    if period == "daily":
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        period_start = now - timedelta(days=now.weekday())
        period_start = period_start.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(
            func.coalesce(func.sum(UsageLog.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(UsageLog.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost"),
            func.count().label("request_count"),
        ).where(
            UsageLog.user_id == tenant.user_id,
            UsageLog.created_at >= period_start,
        )
    )
    row = result.one()

    # Get quota info
    quota_info = None
    try:
        from app.models.quota import Quota
        quota_result = await db.execute(
            select(Quota).where(
                Quota.org_id == tenant.org_id,
                Quota.deleted_at.is_(None),
            ).limit(1)
        )
        quota = quota_result.scalar_one_or_none()
        if quota:
            total_tokens = int(row.input_tokens) + int(row.output_tokens)
            max_tokens = quota.max_tokens_per_day if period == "daily" else (quota.max_tokens_per_day * (7 if period == "weekly" else 30))
            max_cost = quota.max_cost_per_day if period == "daily" else (quota.max_cost_per_day * (7 if period == "weekly" else 30))
            quota_info = {
                "max_tokens": max_tokens,
                "max_cost_usd": float(max_cost),
                "remaining_tokens": max(0, max_tokens - total_tokens),
                "remaining_cost_usd": round(max(0, float(max_cost) - float(row.total_cost)), 4),
                "enforcement": quota.enforcement.value if hasattr(quota, 'enforcement') else "soft",
            }
    except Exception:
        pass

    response = {
        "data": {
            "period": period,
            "period_start": period_start.isoformat(),
            "usage": {
                "tokens": {
                    "input": int(row.input_tokens),
                    "output": int(row.output_tokens),
                    "total": int(row.input_tokens) + int(row.output_tokens),
                },
                "cost_usd": round(float(row.total_cost), 4),
                "requests": int(row.request_count),
            },
        }
    }
    if quota_info:
        response["data"]["quota"] = quota_info
    return response


@router.get("/summary")
async def usage_summary(
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Usage summary. Admins see org-wide; users see personal."""
    now = datetime.now(timezone.utc)
    if period == "daily":
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        period_start = now - timedelta(days=now.weekday())
        period_start = period_start.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    filters = [UsageLog.created_at >= period_start]
    if tenant.role == "admin":
        filters.append(UsageLog.org_id == tenant.org_id)
    else:
        filters.append(UsageLog.user_id == tenant.user_id)

    result = await db.execute(
        select(
            func.coalesce(func.sum(UsageLog.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(UsageLog.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost"),
            func.count().label("request_count"),
            func.count(func.distinct(UsageLog.user_id)).label("active_users"),
        ).where(*filters)
    )
    row = result.one()

    return {
        "data": {
            "period": period,
            "period_start": period_start.isoformat(),
            "scope": "org" if tenant.role == "admin" else "personal",
            "usage": {
                "tokens": {
                    "input": int(row.input_tokens),
                    "output": int(row.output_tokens),
                    "total": int(row.input_tokens) + int(row.output_tokens),
                },
                "cost_usd": round(float(row.total_cost), 4),
                "requests": int(row.request_count),
                "active_users": int(row.active_users),
            },
        }
    }


@router.get("/breakdown")
async def usage_breakdown(
    group_by: str = Query(default="model", pattern="^(model|user|day)$"),
    days: int = Query(default=7, ge=1, le=90),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Usage breakdown by model, user, or day."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    filters = [UsageLog.created_at >= since]
    if tenant.role == "admin":
        filters.append(UsageLog.org_id == tenant.org_id)
    else:
        filters.append(UsageLog.user_id == tenant.user_id)

    if group_by == "model":
        result = await db.execute(
            select(
                UsageLog.model_id,
                func.coalesce(func.sum(UsageLog.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(UsageLog.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost"),
                func.count().label("request_count"),
            ).where(*filters).group_by(UsageLog.model_id).order_by(func.sum(UsageLog.cost_usd).desc())
        )
    elif group_by == "day":
        result = await db.execute(
            select(
                cast(UsageLog.created_at, Date).label("date"),
                func.coalesce(func.sum(UsageLog.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(UsageLog.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost"),
                func.count().label("request_count"),
            ).where(*filters).group_by(cast(UsageLog.created_at, Date)).order_by(cast(UsageLog.created_at, Date))
        )
    else:  # user
        result = await db.execute(
            select(
                UsageLog.user_id,
                func.coalesce(func.sum(UsageLog.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(UsageLog.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost"),
                func.count().label("request_count"),
            ).where(*filters).group_by(UsageLog.user_id).order_by(func.sum(UsageLog.cost_usd).desc())
        )

    rows = result.all()
    breakdown = []
    for row in rows:
        entry = {
            "input_tokens": int(row.input_tokens),
            "output_tokens": int(row.output_tokens),
            "total_tokens": int(row.input_tokens) + int(row.output_tokens),
            "cost_usd": round(float(row.total_cost), 4),
            "requests": int(row.request_count),
        }
        if group_by == "model":
            entry["model_id"] = row.model_id
        elif group_by == "day":
            entry["date"] = str(row.date)
        else:
            entry["user_id"] = str(row.user_id)
        breakdown.append(entry)

    return {"data": {"group_by": group_by, "days": days, "breakdown": breakdown}}


@router.get("/export")
async def export_usage(
    days: int = Query(default=30, ge=1, le=90),
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export usage data as CSV."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    filters = [UsageLog.created_at >= since]
    if tenant.role == "admin":
        filters.append(UsageLog.org_id == tenant.org_id)
    else:
        filters.append(UsageLog.user_id == tenant.user_id)

    result = await db.execute(
        select(UsageLog).where(*filters).order_by(UsageLog.created_at.desc()).limit(10000)
    )
    rows = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "user_id", "model_id", "provider", "input_tokens", "output_tokens", "cost_usd", "latency_ms", "created_at"])
    for r in rows:
        writer.writerow([
            str(r.id),
            str(r.user_id),
            r.model_id,
            r.provider,
            r.input_tokens,
            r.output_tokens,
            f"{float(r.cost_usd):.6f}",
            r.latency_ms or "",
            r.created_at.isoformat(),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=usage-export-{days}d.csv"},
    )
