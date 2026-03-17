"""Chat-related Pydantic schemas."""

import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)
    model: str | None = Field(default=None, description="Model ID override")
    max_tokens: int = Field(default=4096, ge=1, le=32768)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    stream: bool = Field(default=True)


class ConversationCreate(BaseModel):
    title: str | None = None
    model_id: str | None = None
    system_prompt: str | None = None


class ConversationUpdate(BaseModel):
    title: str | None = None
    model_id: str | None = None
    pinned: bool | None = None
    archived: bool | None = None


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    model_id: str | None
    pinned: bool
    archived: bool
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message_preview: str | None = None

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    model_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ModelInfo(BaseModel):
    id: str
    display_name: str
    provider: str
    supports_streaming: bool = True
    max_context_tokens: int | None = None
    input_cost_per_1k: float | None = None
    output_cost_per_1k: float | None = None
