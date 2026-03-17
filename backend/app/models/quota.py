"""Quota and budget models."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Numeric, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Quota(Base):
    __tablename__ = "quotas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    # Scope: org, division, department, team, user
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="org")
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Limits
    period: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")  # daily/weekly/monthly
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_requests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Enforcement
    enforcement: Mapped[str] = mapped_column(String(20), nullable=False, default="soft")  # soft (warn) or hard (block)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
