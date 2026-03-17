"""Safety event persistence — logs all safety events to the database."""

import uuid
import structlog
from datetime import datetime, timezone
from app.database import async_session
from app.models.safety_event import SafetyEvent

logger = structlog.get_logger()


async def log_safety_event(
    org_id: uuid.UUID,
    event_type: str,
    action_taken: str,
    flags: dict,
    user_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    message_id: uuid.UUID | None = None,
    severity: str = "medium",
    direction: str = "inbound",
    content_snippet: str | None = None,
    details: dict | None = None,
):
    """Persist a safety event to the database (fire-and-forget safe)."""
    try:
        async with async_session() as db:
            event = SafetyEvent(
                org_id=org_id,
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
                event_type=event_type,
                severity=severity,
                action_taken=action_taken,
                direction=direction,
                flags=flags,
                content_snippet=content_snippet[:200] if content_snippet else None,
                details=details or {},
            )
            db.add(event)
            await db.commit()
            logger.info("safety_event_logged", event_type=event_type, action=action_taken)
    except Exception as e:
        logger.error("safety_event_log_failed", error=str(e), event_type=event_type)
