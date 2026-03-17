"""Conversation management endpoints."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.tenant import get_current_user, TenantContext
from app.models.conversation import Conversation, Message
from app.schemas.chat import ConversationCreate, ConversationUpdate, ConversationResponse, MessageResponse

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    req: ConversationCreate,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = Conversation(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        title=req.title,
        model_id=req.model_id,
        system_prompt=req.system_prompt,
    )
    db.add(conv)
    await db.flush()
    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        model_id=conv.model_id,
        pinned=conv.pinned,
        archived=conv.archived,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=0,
    )


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    limit: int = 50,
    offset: int = 0,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get conversations with message count
    stmt = (
        select(Conversation)
        .where(
            Conversation.org_id == tenant.org_id,
            Conversation.user_id == tenant.user_id,
            Conversation.deleted_at.is_(None),
        )
        .order_by(desc(Conversation.updated_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    conversations = result.scalars().all()

    responses = []
    for conv in conversations:
        # Count messages
        count_stmt = select(func.count()).select_from(Message).where(
            Message.conversation_id == conv.id, Message.deleted_at.is_(None)
        )
        count_result = await db.execute(count_stmt)
        msg_count = count_result.scalar() or 0

        # Last message preview
        preview = None
        if msg_count > 0:
            last_msg_stmt = (
                select(Message.content)
                .where(Message.conversation_id == conv.id, Message.deleted_at.is_(None))
                .order_by(desc(Message.sequence))
                .limit(1)
            )
            last_result = await db.execute(last_msg_stmt)
            last_content = last_result.scalar()
            if last_content:
                preview = last_content[:100] + ("..." if len(last_content) > 100 else "")

        responses.append(ConversationResponse(
            id=conv.id,
            title=conv.title,
            model_id=conv.model_id,
            pinned=conv.pinned,
            archived=conv.archived,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=msg_count,
            last_message_preview=preview,
        ))

    return responses


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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

    count_result = await db.execute(
        select(func.count()).select_from(Message).where(
            Message.conversation_id == conv.id, Message.deleted_at.is_(None)
        )
    )

    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        model_id=conv.model_id,
        pinned=conv.pinned,
        archived=conv.archived,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=count_result.scalar() or 0,
    )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: uuid.UUID,
    req: ConversationUpdate,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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

    if req.title is not None:
        conv.title = req.title
    if req.model_id is not None:
        conv.model_id = req.model_id
    if req.pinned is not None:
        conv.pinned = req.pinned
    if req.archived is not None:
        conv.archived = req.archived
    conv.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        model_id=conv.model_id,
        pinned=conv.pinned,
        archived=conv.archived,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
    conv.deleted_at = datetime.now(timezone.utc)
    await db.flush()


@router.get("/{conversation_id}/export")
async def export_conversation(
    conversation_id: uuid.UUID,
    format: str = "markdown",
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export conversation as markdown or JSON."""
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

    msgs_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.deleted_at.is_(None))
        .order_by(Message.sequence)
    )
    messages = msgs_result.scalars().all()

    if format == "json":
        return {
            "conversation": {
                "id": str(conv.id),
                "title": conv.title,
                "model_id": conv.model_id,
                "created_at": conv.created_at.isoformat(),
            },
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "model_id": m.model_id,
                    "tokens": (m.input_tokens or 0) + (m.output_tokens or 0),
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        }
    else:
        # Markdown format
        lines = [f"# {conv.title or 'Untitled Conversation'}\n"]
        lines.append(f"*Created: {conv.created_at.isoformat()}*\n")
        if conv.model_id:
            lines.append(f"*Model: {conv.model_id}*\n")
        lines.append("---\n")
        for m in messages:
            role_label = "**You:**" if m.role == "user" else f"**AI ({m.model_id or 'unknown'}):**"
            lines.append(f"\n{role_label}\n\n{m.content}\n")
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(
            content="\n".join(lines),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=conversation-{conversation_id}.md"},
        )


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
    tenant: TenantContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify conversation belongs to user
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.org_id == tenant.org_id,
            Conversation.user_id == tenant.user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Conversation not found")

    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.deleted_at.is_(None))
        .order_by(Message.sequence)
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()

    return [
        MessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            model_id=m.model_id,
            input_tokens=m.input_tokens,
            output_tokens=m.output_tokens,
            cost_usd=float(m.cost_usd) if m.cost_usd else None,
            created_at=m.created_at,
        )
        for m in messages
    ]
