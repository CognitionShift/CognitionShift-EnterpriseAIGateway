"""Chat completion endpoint with SSE streaming."""

import json
import uuid
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database import get_db, async_session
from app.middleware.tenant import get_current_user, TenantContext
from app.models.conversation import Conversation, Message
from app.models.usage import UsageLog
from app.schemas.chat import ChatMessageRequest
from app.services.providers.base import ChatMessage, StreamChunk

logger = structlog.get_logger()
router = APIRouter(tags=["chat"])


def get_model_router():
    """Get the global model router instance."""
    from app.main import model_router
    return model_router


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    req: ChatMessageRequest,
    request: Request,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify conversation exists and belongs to user
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.org_id == tenant.org_id,
            Conversation.user_id == tenant.user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Get next sequence number
    seq_result = await db.execute(
        select(func.coalesce(func.max(Message.sequence), 0))
        .where(Message.conversation_id == conversation_id)
    )
    next_seq = seq_result.scalar() + 1

    # Save user message
    user_msg = Message(
        conversation_id=conversation_id,
        org_id=tenant.org_id,
        sequence=next_seq,
        role="user",
        content=req.content,
    )
    db.add(user_msg)
    await db.flush()

    # Build message history for context
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.deleted_at.is_(None))
        .order_by(Message.sequence)
    )
    history = history_result.scalars().all()

    messages = []
    # Add system prompt if set
    if conv.system_prompt:
        messages.append(ChatMessage(role="system", content=conv.system_prompt))

    for msg in history:
        messages.append(ChatMessage(role=msg.role, content=msg.content))

    # Resolve model
    model_router = get_model_router()
    model_id = req.model or conv.model_id

    # Update conversation model if changed
    if model_id and model_id != conv.model_id:
        conv.model_id = model_id

    # Auto-title from first user message
    if not conv.title and next_seq == 1:
        conv.title = req.content[:80] + ("..." if len(req.content) > 80 else "")

    conv.updated_at = datetime.now(timezone.utc)
    await db.commit()

    # Resolve model to get actual ID
    resolved_id, _, _ = model_router.resolve_model(model_id)

    if req.stream:
        return StreamingResponse(
            stream_response(
                model_router=model_router,
                messages=messages,
                model_id=resolved_id,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                conversation_id=conversation_id,
                org_id=tenant.org_id,
                user_id=tenant.user_id,
                next_seq=next_seq + 1,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        # Non-streaming response
        try:
            response = await model_router.chat(messages, model_id, req.max_tokens, req.temperature)

            # Save assistant message
            async with async_session() as save_db:
                assistant_msg = Message(
                    conversation_id=conversation_id,
                    org_id=tenant.org_id,
                    sequence=next_seq + 1,
                    role="assistant",
                    content=response.content,
                    model_id=response.model,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    cost_usd=_calc_cost(model_id, response.input_tokens, response.output_tokens, model_router),
                )
                save_db.add(assistant_msg)

                # Usage log
                usage = UsageLog(
                    org_id=tenant.org_id,
                    user_id=tenant.user_id,
                    conversation_id=conversation_id,
                    message_id=assistant_msg.id,
                    model_id=response.model,
                    provider="anthropic",
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    cost_usd=assistant_msg.cost_usd or 0,
                )
                save_db.add(usage)
                await save_db.commit()

            return {
                "data": {
                    "content": response.content,
                    "model": response.model,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "finish_reason": response.finish_reason,
                }
            }
        except Exception as e:
            logger.error("chat_error", error=str(e))
            raise HTTPException(status_code=502, detail=f"Model provider error: {str(e)}")


async def stream_response(
    model_router,
    messages: list[ChatMessage],
    model_id: str | None,
    max_tokens: int,
    temperature: float,
    conversation_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    next_seq: int,
):
    """Generator that streams SSE events."""
    full_response = []
    input_tokens = 0
    output_tokens = 0
    start_time = time.monotonic()
    actual_model = model_id or "unknown"

    try:
        async for chunk in model_router.stream(messages, model_id, max_tokens, temperature):
            if chunk.text:
                full_response.append(chunk.text)
                event = {"type": "token", "content": chunk.text}
                yield f"data: {json.dumps(event)}\n\n"

            if chunk.input_tokens is not None:
                input_tokens = chunk.input_tokens
            if chunk.output_tokens is not None:
                output_tokens = chunk.output_tokens
            if chunk.finish_reason:
                actual_model = model_id or "unknown"

        # Send done event
        done_event = {
            "type": "done",
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model": actual_model,
            },
        }
        yield f"data: {json.dumps(done_event)}\n\n"

    except Exception as e:
        logger.error("stream_error", error=str(e))
        error_event = {"type": "error", "message": str(e)}
        yield f"data: {json.dumps(error_event)}\n\n"
        return

    # Post-stream: persist message and usage
    latency_ms = int((time.monotonic() - start_time) * 1000)
    complete_text = "".join(full_response)

    if complete_text:
        try:
            cost = _calc_cost(model_id, input_tokens, output_tokens, model_router)
            async with async_session() as save_db:
                assistant_msg = Message(
                    conversation_id=conversation_id,
                    org_id=org_id,
                    sequence=next_seq,
                    role="assistant",
                    content=complete_text,
                    model_id=actual_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                )
                save_db.add(assistant_msg)

                usage = UsageLog(
                    org_id=org_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    message_id=assistant_msg.id,
                    model_id=actual_model,
                    provider="anthropic",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost or 0,
                    latency_ms=latency_ms,
                )
                save_db.add(usage)
                await save_db.commit()
        except Exception as e:
            logger.error("post_stream_save_error", error=str(e))


def _calc_cost(model_id: str | None, input_tokens: int, output_tokens: int, model_router) -> float:
    """Calculate cost based on model pricing."""
    try:
        _, _, defn = model_router.resolve_model(model_id)
        cost = (input_tokens / 1000 * defn.input_cost_per_1k) + (output_tokens / 1000 * defn.output_cost_per_1k)
        return round(cost, 6)
    except Exception:
        return 0.0
