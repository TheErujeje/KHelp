"""Data access for the triage-tools server.

Connects with MCP_DATABASE_URL (the restricted `khelp_mcp` role). Nothing
here updates patients or writes approvals; the role would be refused if it
tried.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from khelp_db import AuditLog, Intake, Patient, Proposal, RecheckFlag, VitalsReading, session_factory
from khelp_scoring import priority_rank

_URL_ENV = "MCP_DATABASE_URL" if os.environ.get("MCP_DATABASE_URL") else "DATABASE_URL"


def session() -> Session:
    return session_factory(_URL_ENV)()


def current_run_id() -> str | None:
    """The agent runner starts one server process per run and passes its id."""
    return os.environ.get("KHELP_RUN_ID") or None


def add_audit(s: Session, *, tool_name: str, inputs: dict[str, Any], outputs: dict[str, Any], is_error: bool,
              latency_ms: int, patient_id: int | None) -> None:
    """Add an audit row to the caller's transaction (committed with the tool's writes)."""
    s.add(AuditLog(
        run_id=current_run_id(), patient_id=patient_id, event_type="TOOL_CALL", source="triage-tools",
        tool_name=tool_name, inputs=inputs, outputs=outputs, is_error=is_error, latency_ms=latency_ms,
        model=os.environ.get("KHELP_MODEL_LABEL"),
    ))
    s.flush()


def get_patient(s: Session, patient_id: int) -> Patient | None:
    return s.get(Patient, patient_id)


def notes_for_patient(s: Session, patient_id: int) -> str:
    rows = s.scalars(select(Intake.note_text).where(Intake.patient_id == patient_id).order_by(Intake.id))
    return "\n".join(rows)


def latest_vitals(s: Session, patient_id: int) -> VitalsReading | None:
    return s.scalars(select(VitalsReading).where(VitalsReading.patient_id == patient_id)
                     .order_by(VitalsReading.id.desc()).limit(1)).first()


def queue(s: Session) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    patients = s.scalars(select(Patient).where(Patient.status == "WAITING")).all()
    rows = []
    for p in patients:
        pending = s.scalars(select(Proposal).where(Proposal.patient_id == p.id, Proposal.status == "PENDING")
                            .order_by(Proposal.id.desc()).limit(1)).first()
        rechecks = s.scalars(select(RecheckFlag).where(RecheckFlag.patient_id == p.id,
                                                       RecheckFlag.status == "PENDING")).all()
        rows.append({
            "patient_id": p.id,
            "display_name": p.display_name,
            "age_years": p.age_years,
            "arrived_at": p.arrived_at.isoformat(),
            "wait_minutes": int((now - p.arrived_at).total_seconds() // 60),
            "approved_priority": p.approved_priority,
            "approved_by": p.approved_by,
            "pending_proposal": ({"proposal_id": pending.id, "priority": pending.priority} if pending else None),
            "pending_rechecks": [{"flag_id": f.id, "flag_type": f.flag_type, "reason": f.reason} for f in rechecks],
        })
    rows.sort(key=lambda r: (-(priority_rank(r["approved_priority"]) if r["approved_priority"] else -1),
                             r["arrived_at"]))
    return rows


def insert_vitals(s: Session, patient_id: int, raw: dict[str, Any], tews: dict[str, Any]) -> VitalsReading:
    reading = VitalsReading(patient_id=patient_id, run_id=current_run_id(), raw=raw, tews=tews,
                            tews_total=tews.get("total"))
    s.add(reading)
    s.flush()
    return reading


def insert_proposal(s: Session, *, patient_id: int, priority: str, citations: list[dict[str, Any]],
                    decision: dict[str, Any], rationale: str, vitals_reading_id: int,
                    needs_recheck: bool) -> Proposal:
    proposal = Proposal(patient_id=patient_id, run_id=current_run_id(), priority=priority, status="PENDING",
                        citations=citations, decision=decision, rationale=rationale,
                        vitals_reading_id=vitals_reading_id, needs_recheck=needs_recheck)
    s.add(proposal)
    s.flush()
    return proposal


def insert_recheck(s: Session, *, patient_id: int, flag_type: str, reason: str,
                   details: dict[str, Any]) -> RecheckFlag:
    flag = RecheckFlag(patient_id=patient_id, run_id=current_run_id(), flag_type=flag_type, reason=reason,
                       details=details, status="PENDING")
    s.add(flag)
    s.flush()
    return flag
