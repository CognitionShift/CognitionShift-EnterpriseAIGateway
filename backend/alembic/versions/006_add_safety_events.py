"""Add safety events table.

Revision ID: 006
Revises: 005
Create Date: 2026-03-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "safety_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("action_taken", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False, server_default="inbound"),
        sa.Column("flags", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("content_snippet", sa.Text, nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_safety_events_org_created", "safety_events", ["org_id", "created_at"])
    op.create_index("ix_safety_events_type", "safety_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_safety_events_type")
    op.drop_index("ix_safety_events_org_created")
    op.drop_table("safety_events")
