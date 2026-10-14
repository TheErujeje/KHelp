"""Intakes, queue, patients, proposals and re-check flags.

The approval gate lives here. `approve_proposal`, `override_proposal` and
`acknowledge_flag` (MANUAL_TRIAGE only) are the only code paths that set a
patient's approved priority, and each needs a named clinician.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from khelp_db import AgentRun, Approval, AuditLog, Intake, Patient, Proposal, RecheckFlag, VitalsReading
from khelp_scoring import priority_rank

from .. import serializers as ser
from ..agent.runner import Settings, write_note_file
from ..deps import get_session
from ..schemas import AcknowledgeIn, ApproveIn, IntakeIn, OverrideIn, RecheckIn, SeenIn
from ..worker import submit_run

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(s: Session, *, event_type: str, patient_id: int, actor: str | None, outputs: dict[str, Any],
           inputs: dict[str, Any] | None = None, run_id: str | None = None) -> None:
    s.add(AuditLog(event_type=event_type, source="api", patient_id=patient_id, actor=actor,
                   inputs=inputs, outputs=outputs, run_id=run_id))


def _start_run(s: Session, patient: Patient, note_text: str, kind: str) -> dict[str, Any]:
    intake = Intake(patient_id=patient.id, kind=kind, note_text=note_text)
    s.add(intake)
    s.flush()
    intake.note_path = str(write_note_file(Settings(), patient.id, intake.id, note_text))
    run_id = str(uuid.uuid4())
    _audit(s, event_type=f"{kind}_SUBMITTED", patient_id=patient.id, actor=None,
           inputs={"note_text": note_text}, outputs={"intake_id": intake.id, "run_id": run_id}, run_id=run_id)
    return {"patient_id": patient.id, "intake_id": intake.id, "run_id": run_id}


# --------------------------------------------------------------------------- intakes

@router.post("/intakes", status_code=202)
def create_intake(body: IntakeIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    with s.begin():
        patient = Patient(display_name=body.display_name or "Synthetic patient")
        s.add(patient)
        s.flush()
        if not body.display_name:
            patient.display_name = f"Synthetic patient #{patient.id}"
        started = _start_run(s, patient, body.note_text, "INITIAL")
    submit_run(started["patient_id"], started["intake_id"], "INITIAL", started["run_id"])
    return started


@router.post("/patients/{patient_id}/recheck", status_code=202)
def create_recheck(patient_id: int, body: RecheckIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    with s.begin():
        patient = s.get(Patient, patient_id)
        if patient is None:
            raise HTTPException(404, "patient not found")
        if patient.status != "WAITING":
            raise HTTPException(409, f"patient is {patient.status}, not WAITING")
        started = _start_run(s, patient, body.note_text, "RECHECK")
    submit_run(started["patient_id"], started["intake_id"], "RECHECK", started["run_id"])
    return started


@router.post("/patients/{patient_id}/score", status_code=202)
def score_patient(patient_id: int, s: Session = Depends(get_session)) -> dict[str, Any]:
    """Run the agent on a waiting patient's existing intake note (e.g. seeded patients)."""
    with s.begin():
        patient = s.get(Patient, patient_id)
        if patient is None:
            raise HTTPException(404, "patient not found")
        if patient.status != "WAITING":
            raise HTTPException(409, f"patient is {patient.status}, not WAITING")
        running = s.scalars(select(AgentRun).where(AgentRun.patient_id == patient_id,
                                                   AgentRun.status == "RUNNING")).first()
        if running:
            raise HTTPException(409, "the agent is already scoring this patient")
        intake = s.scalars(select(Intake).where(Intake.patient_id == patient_id, Intake.kind == "INITIAL")
                           .order_by(Intake.id.desc()).limit(1)).first()
        if intake is None:
            raise HTTPException(409, "patient has no intake note")
        if not intake.note_path:
            intake.note_path = str(write_note_file(Settings(), patient_id, intake.id, intake.note_text))
        run_id = str(uuid.uuid4())
        _audit(s, event_type="SCORE_REQUESTED", patient_id=patient_id, actor=None,
               outputs={"intake_id": intake.id, "run_id": run_id}, run_id=run_id)
        started = {"patient_id": patient_id, "intake_id": intake.id, "run_id": run_id}
    submit_run(patient_id, started["intake_id"], "INITIAL", run_id)
    return started


# --------------------------------------------------------------------------- queue / patients

def _latest_run(s: Session, patient_id: int) -> AgentRun | None:
    return s.scalars(select(AgentRun).where(AgentRun.patient_id == patient_id)
                     .order_by(AgentRun.started_at.desc()).limit(1)).first()


@router.get("/queue")
def get_queue(s: Session = Depends(get_session)) -> dict[str, Any]:
    patients = s.scalars(select(Patient).where(Patient.status == "WAITING")).all()
    rows = []
    for p in patients:
        pending = s.scalars(select(Proposal).where(Proposal.patient_id == p.id, Proposal.status == "PENDING")
                            .order_by(Proposal.id.desc()).limit(1)).first()
        flags = s.scalars(select(RecheckFlag).where(RecheckFlag.patient_id == p.id,
                                                    RecheckFlag.status == "PENDING")).all()
        run = _latest_run(s, p.id)
        rows.append({
            **ser.patient(p),
            "pending_proposal": {"id": pending.id, "priority": pending.priority} if pending else None,
            "pending_flags": [ser.flag(f) for f in flags],
            "latest_run": {"id": run.id, "status": run.status, "kind": run.kind} if run else None,
        })
    # Approved priority first (RED .. GREEN), then patients not yet prioritised; each by arrival.
    rows.sort(key=lambda r: (-priority_rank(r["approved_priority"]) if r["approved_priority"] else 1,
                             r["arrived_at"]))
    return {"patients": rows}


@router.get("/patients/{patient_id}")
def get_patient(patient_id: int, s: Session = Depends(get_session)) -> dict[str, Any]:
    p = s.get(Patient, patient_id)
    if p is None:
        raise HTTPException(404, "patient not found")

    def rows(model, order):
        return s.scalars(select(model).where(model.patient_id == patient_id).order_by(order)).all()

    return {
        "patient": ser.patient(p),
        "intakes": [ser.intake(i) for i in rows(Intake, Intake.id)],
        "vitals": [ser.vitals(v) for v in rows(VitalsReading, VitalsReading.id)],
        "proposals": [ser.proposal(x) for x in rows(Proposal, Proposal.id)],
        "flags": [ser.flag(f) for f in rows(RecheckFlag, RecheckFlag.id)],
        "approvals": [ser.approval(a) for a in rows(Approval, Approval.id)],
        "runs": [ser.run(r) for r in rows(AgentRun, AgentRun.started_at)],
    }


@router.post("/patients/{patient_id}/seen")
def mark_seen(patient_id: int, body: SeenIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    with s.begin():
        p = s.scalars(select(Patient).where(Patient.id == patient_id).with_for_update()).first()
        if p is None:
            raise HTTPException(404, "patient not found")
        p.status = "SEEN"
        _audit(s, event_type="PATIENT_SEEN", patient_id=p.id, actor=body.clinician_name, outputs={"status": "SEEN"})
    return ser.patient(p)


# --------------------------------------------------------------------------- proposals (approval gate)

@router.get("/proposals")
def list_proposals(status: str | None = Query(default=None), s: Session = Depends(get_session)) -> dict[str, Any]:
    q = select(Proposal).order_by(Proposal.created_at)
    if status:
        q = q.where(Proposal.status == status.upper())
    out = []
    for prop in s.scalars(q).all():
        patient = s.get(Patient, prop.patient_id)
        note = s.scalars(select(Intake.note_text).where(Intake.patient_id == prop.patient_id)
                         .order_by(Intake.id).limit(1)).first()
        out.append({**ser.proposal(prop), "patient": ser.patient(patient), "note_text": note})
    return {"proposals": out}


def _lock_pending(s: Session, proposal_id: int) -> tuple[Proposal, Patient]:
    prop = s.scalars(select(Proposal).where(Proposal.id == proposal_id).with_for_update()).first()
    if prop is None:
        raise HTTPException(404, "proposal not found")
    if prop.status != "PENDING":
        raise HTTPException(409, f"proposal is already {prop.status}")
    patient = s.scalars(select(Patient).where(Patient.id == prop.patient_id).with_for_update()).one()
    if patient.status != "WAITING":
        raise HTTPException(409, f"patient is {patient.status}, not WAITING")
    return prop, patient


def _commit_priority(s: Session, prop: Proposal, patient: Patient, *, status: str, priority: str,
                     clinician: str, reason: str | None) -> Approval:
    prop.status = status
    patient.approved_priority = priority
    patient.approved_by = clinician
    patient.approved_at = _now()
    for other in s.scalars(select(Proposal).where(Proposal.patient_id == patient.id, Proposal.status == "PENDING",
                                                  Proposal.id != prop.id)):
        other.status = "SUPERSEDED"
    action = "APPROVE" if status == "APPROVED" else "OVERRIDE"
    approval = Approval(patient_id=patient.id, proposal_id=prop.id, clinician_name=clinician, action=action,
                        priority=priority, reason=reason)
    s.add(approval)
    s.flush()
    _audit(s, event_type=action, patient_id=patient.id, actor=clinician, run_id=prop.run_id,
           inputs={"proposal_id": prop.id, "proposed": prop.priority, "reason": reason},
           outputs={"approved_priority": priority, "approval_id": approval.id})
    return approval


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: int, body: ApproveIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    with s.begin():
        prop, patient = _lock_pending(s, proposal_id)
        approval = _commit_priority(s, prop, patient, status="APPROVED", priority=prop.priority,
                                    clinician=body.clinician_name, reason=None)
    return {"approval": ser.approval(approval), "patient": ser.patient(patient)}


@router.post("/proposals/{proposal_id}/override")
def override_proposal(proposal_id: int, body: OverrideIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    with s.begin():
        prop, patient = _lock_pending(s, proposal_id)
        approval = _commit_priority(s, prop, patient, status="OVERRIDDEN", priority=body.priority,
                                    clinician=body.clinician_name, reason=body.reason.strip())
    return {"approval": ser.approval(approval), "patient": ser.patient(patient)}


# --------------------------------------------------------------------------- re-check flags

@router.get("/flags")
def list_flags(status: str | None = Query(default="PENDING"), s: Session = Depends(get_session)) -> dict[str, Any]:
    q = select(RecheckFlag).order_by(RecheckFlag.created_at)
    if status:
        q = q.where(RecheckFlag.status == status.upper())
    out = []
    for f in s.scalars(q).all():
        out.append({**ser.flag(f), "patient": ser.patient(s.get(Patient, f.patient_id))})
    return {"flags": out}


@router.post("/flags/{flag_id}/acknowledge")
def acknowledge_flag(flag_id: int, body: AcknowledgeIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    with s.begin():
        flag = s.scalars(select(RecheckFlag).where(RecheckFlag.id == flag_id).with_for_update()).first()
        if flag is None:
            raise HTTPException(404, "flag not found")
        if flag.status != "PENDING":
            raise HTTPException(409, f"flag is already {flag.status}")
        patient = s.scalars(select(Patient).where(Patient.id == flag.patient_id).with_for_update()).one()
        if body.priority is not None:
            if flag.flag_type != "MANUAL_TRIAGE":
                raise HTTPException(422, "a priority can only be set when acknowledging a MANUAL_TRIAGE flag; "
                                         "use the proposal approve/override endpoints otherwise")
            patient.approved_priority = body.priority
            patient.approved_by = body.clinician_name
            patient.approved_at = _now()
        flag.status = "ACKNOWLEDGED"
        approval = Approval(patient_id=patient.id, recheck_flag_id=flag.id, clinician_name=body.clinician_name,
                            action="ACKNOWLEDGE", priority=body.priority, reason=body.note)
        s.add(approval)
        s.flush()
        _audit(s, event_type="ACKNOWLEDGE", patient_id=patient.id, actor=body.clinician_name, run_id=flag.run_id,
               inputs={"flag_id": flag.id, "flag_type": flag.flag_type, "note": body.note},
               outputs={"approved_priority": patient.approved_priority, "approval_id": approval.id})
    return {"approval": ser.approval(approval), "patient": ser.patient(patient), "flag": ser.flag(flag)}
