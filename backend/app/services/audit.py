"""Audit logging service — append-only event recording."""

import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditLog
from app.database import async_session
import structlog

logger = structlog.get_logger()


async def log_event(
    org_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    actor_type: str,  # "user", "api_key", "system"
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None = None,
    details: dict | None = None,
    actor_ip: str | None = None,
    safety_event: bool = False,
) -> None:
    """Record an audit event. Fire-and-forget — never blocks request."""
    try:
        async with async_session() as db:
            entry = AuditLog(
                org_id=org_id,
                actor_id=actor_id,
                actor_type=actor_type,
                actor_ip=actor_ip,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details or {},
                safety_event=safety_event,
            )
            db.add(entry)
            await db.commit()
    except Exception as e:
        logger.error("audit_log_failed", error=str(e), action=action)
