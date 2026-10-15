"""clinician role on approvals; patients can be called into consultation

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("approvals", sa.Column("clinician_role", sa.String(16), nullable=True))
    op.create_check_constraint(
        "approvals_role", "approvals",
        "clinician_role IS NULL OR clinician_role IN ('TRIAGE_NURSE', 'DOCTOR', 'SENIOR_NURSE')")
    op.add_column("patients", sa.Column("called_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("patients", sa.Column("called_by", sa.String(120), nullable=True))
    op.drop_constraint("patients_status", "patients", type_="check")
    op.create_check_constraint("patients_status", "patients", "status IN ('WAITING', 'IN_CONSULT', 'SEEN', 'LEFT')")


def downgrade() -> None:
    op.drop_constraint("patients_status", "patients", type_="check")
    op.execute("UPDATE patients SET status = 'WAITING' WHERE status = 'IN_CONSULT'")
    op.create_check_constraint("patients_status", "patients", "status IN ('WAITING', 'SEEN', 'LEFT')")
    op.drop_column("patients", "called_by")
    op.drop_column("patients", "called_at")
    op.drop_constraint("approvals_role", "approvals", type_="check")
    op.drop_column("approvals", "clinician_role")
