"""restricted MCP role and append-only audit log

The triage-tools MCP server connects as `khelp_mcp`. That role can read the
clinical tables and insert proposals, re-check flags, vitals readings and
audit rows. It cannot insert approvals or update patients, so the agent
cannot change a patient's queue position, whatever it is told.

audit_log rejects UPDATE and DELETE for every role (trigger).

Revision ID: 0002
Revises: 0001
"""
import os
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MCP_ROLE = "khelp_mcp"
# audit_log needs SELECT because INSERT ... RETURNING reads back id/created_at.
READ_TABLES = ("patients", "intakes", "vitals_readings", "agent_runs", "proposals", "recheck_flags", "approvals",
               "audit_log")
INSERT_TABLES = ("proposals", "recheck_flags", "vitals_readings", "audit_log")


def upgrade() -> None:
    password = os.environ.get("MCP_DB_PASSWORD")
    if not password:
        raise RuntimeError("MCP_DB_PASSWORD must be set to create the khelp_mcp role")
    bind = op.get_bind()
    # Pass the password as a bound parameter rather than formatting it into SQL.
    bind.exec_driver_sql("SELECT set_config('khelp.mcp_password', %s, true)", (password,))
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{MCP_ROLE}') THEN
                EXECUTE format('CREATE ROLE {MCP_ROLE} LOGIN PASSWORD %L',
                               current_setting('khelp.mcp_password'));
            ELSE
                EXECUTE format('ALTER ROLE {MCP_ROLE} LOGIN PASSWORD %L',
                               current_setting('khelp.mcp_password'));
            END IF;
            EXECUTE format('GRANT CONNECT ON DATABASE %I TO {MCP_ROLE}', current_database());
        END
        $$;
    """)
    op.execute(f"GRANT USAGE ON SCHEMA public TO {MCP_ROLE}")
    op.execute(f"GRANT SELECT ON {', '.join(READ_TABLES)} TO {MCP_ROLE}")
    op.execute(f"GRANT INSERT ON {', '.join(INSERT_TABLES)} TO {MCP_ROLE}")
    for table in INSERT_TABLES:
        op.execute(f"GRANT USAGE ON SEQUENCE {table}_id_seq TO {MCP_ROLE}")

    op.execute("""
        CREATE FUNCTION audit_log_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only';
        END
        $$ LANGUAGE plpgsql;
    """)
    # Statement-level, so it fires even when the statement matches no rows.
    op.execute("""
        CREATE TRIGGER audit_log_append_only
        BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_log
        FOR EACH STATEMENT EXECUTE FUNCTION audit_log_append_only();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_append_only()")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {MCP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {MCP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {MCP_ROLE}")
    op.execute(f"REVOKE ALL ON DATABASE {op.get_bind().engine.url.database} FROM {MCP_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {MCP_ROLE}")
