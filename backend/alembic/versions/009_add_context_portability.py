"""Add context portability job tracking tables

Revision ID: 009
Revises: 008
Create Date: 2026-03-18
"""
from typing import Sequence, Union
from alembic import op

revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE export_job_status AS ENUM ('pending', 'running', 'completed', 'failed');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE import_job_status AS ENUM ('pending', 'running', 'importing', 're_embedding', 'completed', 'failed');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS context_export_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID NOT NULL REFERENCES users(id),
            status export_job_status NOT NULL DEFAULT 'pending',
            options JSONB NOT NULL DEFAULT '{}',
            file_path TEXT,
            file_size BIGINT,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_export_jobs_user ON context_export_jobs (org_id, user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_export_jobs_status ON context_export_jobs (status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS context_import_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID NOT NULL REFERENCES users(id),
            status import_job_status NOT NULL DEFAULT 'pending',
            options JSONB NOT NULL DEFAULT '{}',
            file_path TEXT,
            stats JSONB NOT NULL DEFAULT '{}',
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_import_jobs_user ON context_import_jobs (org_id, user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_import_jobs_status ON context_import_jobs (status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS context_import_jobs")
    op.execute("DROP TABLE IF EXISTS context_export_jobs")
    op.execute("DROP TYPE IF EXISTS import_job_status")
    op.execute("DROP TYPE IF EXISTS export_job_status")
