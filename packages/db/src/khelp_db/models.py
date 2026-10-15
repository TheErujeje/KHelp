"""Postgres schema. All patient rows are synthetic (`is_synthetic` defaults true).

Write paths by role:
- app owner role (API): everything below, except UPDATE/DELETE on audit_log
  (blocked by a trigger).
- khelp_mcp role (triage-tools MCP server): SELECT on clinical tables and
  INSERT on proposals, recheck_flags, vitals_readings and audit_log only.
  It has no grant to write approvals or to update patients, so it cannot
  change queue position even if the agent misbehaves.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

PRIORITIES = ("GREEN", "YELLOW", "ORANGE", "RED")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint(_in("status", ("WAITING", "IN_CONSULT", "SEEN", "LEFT")), name="patients_status"),
        CheckConstraint(f"approved_priority IS NULL OR {_in('approved_priority', PRIORITIES)}",
                        name="patients_approved_priority"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    age_years: Mapped[float | None] = mapped_column(Float)
    sex: Mapped[str | None] = mapped_column(String(16))
    arrived_at: Mapped[datetime] = created_at()
    status: Mapped[str] = mapped_column(String(16), default="WAITING", server_default="WAITING")
    # Only the API approval/override endpoints set these.
    approved_priority: Mapped[str | None] = mapped_column(String(8))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(120))
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    called_by: Mapped[str | None] = mapped_column(String(120))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Intake(Base):
    __tablename__ = "intakes"
    __table_args__ = (CheckConstraint(_in("kind", ("INITIAL", "RECHECK")), name="intakes_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="INITIAL", server_default="INITIAL")
    note_text: Mapped[str] = mapped_column(Text)
    note_path: Mapped[str | None] = mapped_column(String(255))  # file under data/intake/
    created_at: Mapped[datetime] = created_at()


class VitalsReading(Base):
    __tablename__ = "vitals_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    intake_id: Mapped[int | None] = mapped_column(ForeignKey("intakes.id"))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
    tews: Mapped[dict[str, Any]] = mapped_column(JSONB)  # full TewsResult
    tews_total: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at()


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(_in("status", ("RUNNING", "COMPLETED", "FAILED", "TIMEOUT", "LIMIT_EXCEEDED")),
                        name="agent_runs_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid4
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    intake_id: Mapped[int | None] = mapped_column(ForeignKey("intakes.id"))
    kind: Mapped[str] = mapped_column(String(16), default="INITIAL")
    status: Mapped[str] = mapped_column(String(16), default="RUNNING", server_default="RUNNING")
    model: Mapped[str] = mapped_column(String(120))
    started_at: Mapped[datetime] = created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tool_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    final_message: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class Proposal(Base):
    __tablename__ = "proposals"
    __table_args__ = (
        CheckConstraint(_in("status", ("PENDING", "APPROVED", "OVERRIDDEN", "SUPERSEDED")), name="proposals_status"),
        CheckConstraint(_in("priority", PRIORITIES), name="proposals_priority"),
        # The server never stores an uncited proposal.
        CheckConstraint("jsonb_array_length(citations) > 0", name="proposals_has_citations"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    vitals_reading_id: Mapped[int | None] = mapped_column(ForeignKey("vitals_readings.id"))
    priority: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING")
    citations: Mapped[list[Any]] = mapped_column(JSONB)
    decision: Mapped[dict[str, Any]] = mapped_column(JSONB)
    rationale: Mapped[str] = mapped_column(Text)
    needs_recheck: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = created_at()


class RecheckFlag(Base):
    __tablename__ = "recheck_flags"
    __table_args__ = (
        CheckConstraint(_in("status", ("PENDING", "ACKNOWLEDGED")), name="recheck_flags_status"),
        CheckConstraint(_in("flag_type", ("MISSING_VITALS", "DETERIORATION", "MANUAL_TRIAGE", "OTHER")),
                        name="recheck_flags_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    flag_type: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING")
    created_at: Mapped[datetime] = created_at()


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(_in("action", ("APPROVE", "OVERRIDE", "ACKNOWLEDGE")), name="approvals_action"),
        CheckConstraint("length(trim(clinician_name)) > 0", name="approvals_named_clinician"),
        CheckConstraint("action <> 'OVERRIDE' OR (reason IS NOT NULL AND length(trim(reason)) > 0)",
                        name="approvals_override_reason"),
        CheckConstraint("(proposal_id IS NULL) <> (recheck_flag_id IS NULL)", name="approvals_one_target"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    proposal_id: Mapped[int | None] = mapped_column(ForeignKey("proposals.id"))
    recheck_flag_id: Mapped[int | None] = mapped_column(ForeignKey("recheck_flags.id"))
    clinician_name: Mapped[str] = mapped_column(String(120))
    clinician_role: Mapped[str | None] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(16))
    priority: Mapped[str | None] = mapped_column(String(8))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


class AuditLog(Base):
    """Append-only. A database trigger rejects UPDATE and DELETE."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = created_at()
    run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    patient_id: Mapped[int | None] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(32))  # TOOL_CALL, APPROVAL, OVERRIDE, RUN_START, ...
    source: Mapped[str] = mapped_column(String(32))  # triage-tools, agent, api
    tool_name: Mapped[str | None] = mapped_column(String(64))
    inputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    outputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    model: Mapped[str | None] = mapped_column(String(120))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    actor: Mapped[str | None] = mapped_column(String(120))  # clinician name for human actions
