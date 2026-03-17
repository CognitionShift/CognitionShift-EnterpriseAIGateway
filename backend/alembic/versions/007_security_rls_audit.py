"""Row-level security, audit trail integrity, soft delete enforcement.

Revision ID: 007
Revises: 006
Create Date: 2026-03-16
"""
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- Row-Level Security (RLS) ----
    # Enable RLS on all tenant-scoped tables
    tenant_tables = [
        "conversations", "messages", "files", "file_chunks",
        "knowledge_bases", "usage_log", "audit_log", "safety_events",
    ]

    for table in tenant_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # Policy: app user can only see rows in their org
        # Note: these policies apply when SET ROLE csgateway_app is used
        op.execute(f"""
            CREATE POLICY {table}_org_isolation ON {table}
            FOR ALL
            USING (org_id = current_setting('app.current_org_id', true)::uuid)
            WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """)

    # Users table: users can see their own org members
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY users_org_isolation ON users
        FOR ALL
        USING (org_id = current_setting('app.current_org_id', true)::uuid)
        WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
    """)

    # ---- Audit Trail Integrity ----
    # Make audit_log append-only: create a trigger that prevents UPDATE and DELETE
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Audit log is append-only. UPDATE and DELETE are not allowed.';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER audit_log_no_update
        BEFORE UPDATE ON audit_log
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_modification();
    """)

    op.execute("""
        CREATE TRIGGER audit_log_no_delete
        BEFORE DELETE ON audit_log
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_modification();
    """)

    # Same protection for safety_events
    op.execute("""
        CREATE TRIGGER safety_events_no_update
        BEFORE UPDATE ON safety_events
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_modification();
    """)

    op.execute("""
        CREATE TRIGGER safety_events_no_delete
        BEFORE DELETE ON safety_events
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_modification();
    """)


def downgrade() -> None:
    # Remove triggers
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS safety_events_no_update ON safety_events")
    op.execute("DROP TRIGGER IF EXISTS safety_events_no_delete ON safety_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_modification()")

    # Disable RLS
    tables = [
        "conversations", "messages", "files", "file_chunks",
        "knowledge_bases", "usage_log", "audit_log", "safety_events", "users",
    ]
    for table in tables:
        op.execute(f"DROP POLICY IF EXISTS {table}_org_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
