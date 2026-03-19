"""Context portability Pydantic schemas."""

import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class ExportRequest(BaseModel):
    conversation_ids: list[uuid.UUID] | None = Field(
        default=None, description="Specific conversation IDs to export. Null for all."
    )
    date_from: datetime | None = Field(default=None, description="Export conversations created after this date")
    date_to: datetime | None = Field(default=None, description="Export conversations created before this date")
    include_files: bool = Field(default=True, description="Include file metadata and chunks")
    include_embeddings: bool = Field(default=True, description="Include vector embeddings")


class ExportJobResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    file_size: int | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ImportJobResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    stats: dict = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}
