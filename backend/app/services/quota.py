"""Quota enforcement service."""

import uuid
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models.quota import Quota
from app.models.usage import UsageLog

logger = structlog.get_logger()


@dataclass
class QuotaCheck:
    allowed: bool = True
    warnings: list[str] | None = None
    quota_id: uuid.UUID | None = None
    current_usage: dict | None = None
    limits: dict | None = None


def _period_start(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    if period == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # monthly
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def check_quota(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> QuotaCheck:
    """
    Check if a user is within their quota.
    Checks user-level quotas first, then org-level.
    """
    # Find applicable quotas (user-level first, then org-level)
    result = await db.execute(
        select(Quota).where(
            Quota.org_id == org_id,
            Quota.active == True,
        ).order_by(Quota.scope.desc())  # 'user' sorts after 'org'
    )
    quotas = result.scalars().all()

    if not quotas:
        return QuotaCheck(allowed=True)

    for quota in quotas:
        # Check if this quota applies to the user
        if quota.scope == "user" and quota.scope_id != user_id:
            continue
        if quota.scope == "org" or (quota.scope == "user" and quota.scope_id == user_id):
            check = await _check_single_quota(db, quota, org_id, user_id)
            if not check.allowed:
                return check
            if check.warnings:
                return check

    return QuotaCheck(allowed=True)


async def _check_single_quota(
    db: AsyncSession,
    quota: Quota,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> QuotaCheck:
    """Check a single quota against current usage."""
    period_start = _period_start(quota.period)

    # Build filter based on scope
    filters = [UsageLog.created_at >= period_start]
    if quota.scope == "user":
        filters.append(UsageLog.user_id == user_id)
    else:
        filters.append(UsageLog.org_id == org_id)

    result = await db.execute(
        select(
            func.coalesce(func.sum(UsageLog.input_tokens + UsageLog.output_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(UsageLog.cost_usd), 0).label("total_cost"),
            func.count().label("total_requests"),
        ).where(*filters)
    )
    row = result.one()
    current = {
        "tokens": int(row.total_tokens),
        "cost_usd": float(row.total_cost),
        "requests": int(row.total_requests),
    }
    limits = {
        "max_tokens": quota.max_tokens,
        "max_cost_usd": float(quota.max_cost_usd) if quota.max_cost_usd else None,
        "max_requests": quota.max_requests,
    }

    warnings = []
    exceeded = False

    # Check token limit
    if quota.max_tokens and current["tokens"] >= quota.max_tokens:
        exceeded = True
        warnings.append(f"Token limit reached ({current['tokens']}/{quota.max_tokens})")
    elif quota.max_tokens and current["tokens"] >= quota.max_tokens * 0.8:
        warnings.append(f"Token usage at {current['tokens']}/{quota.max_tokens} (80%+)")

    # Check cost limit
    if quota.max_cost_usd and current["cost_usd"] >= float(quota.max_cost_usd):
        exceeded = True
        warnings.append(f"Cost limit reached (${current['cost_usd']:.2f}/${float(quota.max_cost_usd):.2f})")
    elif quota.max_cost_usd and current["cost_usd"] >= float(quota.max_cost_usd) * 0.8:
        warnings.append(f"Cost at ${current['cost_usd']:.2f}/${float(quota.max_cost_usd):.2f} (80%+)")

    # Check request limit
    if quota.max_requests and current["requests"] >= quota.max_requests:
        exceeded = True
        warnings.append(f"Request limit reached ({current['requests']}/{quota.max_requests})")

    if exceeded and quota.enforcement == "hard":
        logger.warning("quota_exceeded_hard", org_id=str(org_id), user_id=str(user_id), scope=quota.scope)
        return QuotaCheck(
            allowed=False,
            warnings=warnings,
            quota_id=quota.id,
            current_usage=current,
            limits=limits,
        )

    return QuotaCheck(
        allowed=True,
        warnings=warnings if warnings else None,
        quota_id=quota.id,
        current_usage=current,
        limits=limits,
    )
