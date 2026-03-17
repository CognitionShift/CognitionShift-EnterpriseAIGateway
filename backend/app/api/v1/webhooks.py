"""Webhook management — outbound event notifications."""

import uuid
import hashlib
import hmac
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import httpx
import structlog

from app.database import get_db, async_session
from app.middleware.tenant import require_admin, TenantContext

logger = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookCreate(BaseModel):
    url: str
    events: list[str]  # ["chat.message", "user.login", "safety.blocked", "quota.exceeded"]
    secret: str | None = None  # For HMAC signing


class WebhookUpdate(BaseModel):
    url: str | None = None
    events: list[str] | None = None
    active: bool | None = None


VALID_EVENTS = [
    "chat.message",
    "chat.conversation_created",
    "user.login",
    "user.registered",
    "safety.blocked",
    "safety.pii_detected",
    "quota.exceeded",
    "quota.warning",
    "agent.completed",
    "agent.failed",
    "file.uploaded",
    "admin.user_updated",
]


@router.get("")
async def list_webhooks(
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List org webhooks."""
    result = await db.execute(
        text("SELECT id, url, events, active, created_at FROM webhooks WHERE org_id = :org_id ORDER BY created_at"),
        {"org_id": tenant.org_id},
    )
    rows = result.all()
    return {
        "data": [
            {"id": str(r[0]), "url": r[1], "events": r[2], "active": r[3], "created_at": r[4].isoformat()}
            for r in rows
        ]
    }


@router.post("", status_code=201)
async def create_webhook(
    req: WebhookCreate,
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a webhook endpoint."""
    # Validate events
    for event in req.events:
        if event not in VALID_EVENTS:
            raise HTTPException(status_code=400, detail=f"Invalid event: {event}. Valid: {VALID_EVENTS}")

    wh_id = uuid.uuid4()
    await db.execute(
        text("""INSERT INTO webhooks (id, org_id, url, events, secret_hash, active)
                VALUES (:id, :org_id, :url, :events, :secret_hash, true)"""),
        {
            "id": wh_id,
            "org_id": tenant.org_id,
            "url": req.url,
            "events": json.dumps(req.events),
            "secret_hash": hashlib.sha256(req.secret.encode()).hexdigest() if req.secret else None,
        },
    )
    await db.flush()

    return {"data": {"id": str(wh_id), "url": req.url, "events": req.events}}


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: uuid.UUID,
    tenant: TenantContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a webhook."""
    await db.execute(
        text("DELETE FROM webhooks WHERE id = :id AND org_id = :org_id"),
        {"id": webhook_id, "org_id": tenant.org_id},
    )
    await db.flush()


@router.get("/events")
async def list_valid_events():
    """List valid webhook event types."""
    return {"data": VALID_EVENTS}


async def dispatch_webhook_event(org_id: uuid.UUID, event: str, payload: dict) -> None:
    """Fire-and-forget webhook dispatch. Called from services."""
    try:
        async with async_session() as db:
            result = await db.execute(
                text("SELECT url, secret_hash FROM webhooks WHERE org_id = :org_id AND active = true AND events::text LIKE :event_pattern"),
                {"org_id": org_id, "event_pattern": f"%{event}%"},
            )
            webhooks = result.all()

        for url, secret_hash in webhooks:
            body = json.dumps({"event": event, "timestamp": datetime.now(timezone.utc).isoformat(), "data": payload})
            headers = {"Content-Type": "application/json", "X-CSGateway-Event": event}

            # HMAC signature if secret is set
            if secret_hash:
                sig = hmac.new(secret_hash.encode(), body.encode(), hashlib.sha256).hexdigest()
                headers["X-CSGateway-Signature"] = f"sha256={sig}"

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(url, content=body, headers=headers)
            except Exception as e:
                logger.warning("webhook_delivery_failed", url=url, event=event, error=str(e))

    except Exception as e:
        logger.error("webhook_dispatch_error", event=event, error=str(e))
