"""Model Registry — catalog of institutional AI models."""

import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, UniqueConstraint, Enum, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ModelVisibility(str, enum.Enum):
    private = "private"
    department = "department"
    organization = "organization"


class VersionStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    deprecated = "deprecated"


class AccessGranteeType(str, enum.Enum):
    user = "user"
    department = "department"
    organization = "organization"


class AccessPermission(str, enum.Enum):
    view = "view"
    use = "use"
    edit = "edit"
    admin = "admin"


class RegisteredModel(Base):
    __tablename__ = "model_registry"
    __table_args__ = (UniqueConstraint("org_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[ModelVisibility] = mapped_column(
        Enum(ModelVisibility, name="model_visibility"), nullable=False, default=ModelVisibility.private
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions = relationship("ModelVersion", back_populates="model", lazy="selectin")
    access_grants = relationship("ModelAccess", back_populates="model", lazy="selectin")


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("model_registry.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[VersionStatus] = mapped_column(
        Enum(VersionStatus, name="version_status"), nullable=False, default=VersionStatus.draft
    )
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    training_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    intended_use: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    license: Mapped[str | None] = mapped_column(String(100), nullable=True)
    architecture: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    eval_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    artifact_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    artifact_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gateway_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    model = relationship("RegisteredModel", back_populates="versions")


class ModelAccess(Base):
    __tablename__ = "model_access"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("model_registry.id"), nullable=False)
    grantee_type: Mapped[AccessGranteeType] = mapped_column(
        Enum(AccessGranteeType, name="access_grantee_type"), nullable=False
    )
    grantee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    permission: Mapped[AccessPermission] = mapped_column(
        Enum(AccessPermission, name="access_permission"), nullable=False
    )
    granted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    model = relationship("RegisteredModel", back_populates="access_grants")
