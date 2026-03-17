"""Prometheus-compatible metrics endpoint."""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from sqlalchemy import select, func, text
from app.database import async_session
from app.models.usage import UsageLog
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.models.audit import AuditLog

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def prometheus_metrics():
    """Prometheus-compatible metrics endpoint."""
    lines = []

    try:
        async with async_session() as db:
            now = datetime.now(timezone.utc)
            hour_ago = now - timedelta(hours=1)
            day_ago = now - timedelta(days=1)

            # Total users
            users_total = (await db.execute(
                select(func.count()).select_from(User).where(User.deleted_at.is_(None))
            )).scalar()
            lines.append(f"csgateway_users_total {users_total}")

            # Active users (1h)
            active_1h = (await db.execute(
                select(func.count(func.distinct(UsageLog.user_id))).where(UsageLog.created_at >= hour_ago)
            )).scalar()
            lines.append(f"csgateway_active_users_1h {active_1h}")

            # Total conversations
            convos_total = (await db.execute(
                select(func.count()).select_from(Conversation).where(Conversation.deleted_at.is_(None))
            )).scalar()
            lines.append(f"csgateway_conversations_total {convos_total}")

            # Messages (24h)
            msgs_24h = (await db.execute(
                select(func.count()).select_from(Message).where(Message.created_at >= day_ago)
            )).scalar()
            lines.append(f"csgateway_messages_24h {msgs_24h}")

            # Token usage (24h)
            usage = (await db.execute(
                select(
                    func.coalesce(func.sum(UsageLog.input_tokens), 0).label("input"),
                    func.coalesce(func.sum(UsageLog.output_tokens), 0).label("output"),
                    func.coalesce(func.sum(UsageLog.cost_usd), 0).label("cost"),
                    func.count().label("requests"),
                ).where(UsageLog.created_at >= day_ago)
            )).one()
            lines.append(f"csgateway_tokens_input_24h {int(usage.input)}")
            lines.append(f"csgateway_tokens_output_24h {int(usage.output)}")
            lines.append(f'csgateway_cost_usd_24h {float(usage.cost):.6f}')
            lines.append(f"csgateway_requests_24h {int(usage.requests)}")

            # Safety events (24h)
            safety = (await db.execute(
                select(func.count()).select_from(AuditLog).where(
                    AuditLog.safety_event == True, AuditLog.created_at >= day_ago
                )
            )).scalar()
            lines.append(f"csgateway_safety_events_24h {safety}")

            # Average latency (24h)
            avg_latency = (await db.execute(
                select(func.coalesce(func.avg(UsageLog.latency_ms), 0)).where(
                    UsageLog.created_at >= day_ago, UsageLog.latency_ms.isnot(None)
                )
            )).scalar()
            lines.append(f"csgateway_avg_latency_ms {float(avg_latency):.1f}")

    except Exception as e:
        lines.append(f"# Error collecting metrics: {e}")

    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content="\n".join(lines) + "\n",
        media_type="text/plain",
    )
