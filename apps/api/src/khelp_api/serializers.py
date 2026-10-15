from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from khelp_db import AgentRun, Approval, AuditLog, Intake, Patient, Proposal, RecheckFlag, VitalsReading


def _ts(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def wait_minutes(patient: Patient) -> int:
    return int((datetime.now(timezone.utc) - patient.arrived_at).total_seconds() // 60)


def patient(p: Patient) -> dict[str, Any]:
    return {
        "id": p.id, "display_name": p.display_name, "age_years": p.age_years, "sex": p.sex,
        "arrived_at": _ts(p.arrived_at), "wait_minutes": wait_minutes(p), "status": p.status,
        "approved_priority": p.approved_priority, "approved_by": p.approved_by,
        "approved_at": _ts(p.approved_at), "called_at": _ts(p.called_at), "called_by": p.called_by,
        "is_synthetic": p.is_synthetic,
    }


def intake(i: Intake) -> dict[str, Any]:
    return {"id": i.id, "patient_id": i.patient_id, "kind": i.kind, "note_text": i.note_text,
            "created_at": _ts(i.created_at)}


def proposal(p: Proposal) -> dict[str, Any]:
    return {
        "id": p.id, "patient_id": p.patient_id, "run_id": p.run_id, "priority": p.priority, "status": p.status,
        "citations": p.citations, "decision": p.decision, "rationale": p.rationale,
        "needs_recheck": p.needs_recheck, "created_at": _ts(p.created_at),
    }


def flag(f: RecheckFlag) -> dict[str, Any]:
    return {"id": f.id, "patient_id": f.patient_id, "run_id": f.run_id, "flag_type": f.flag_type,
            "reason": f.reason, "details": f.details, "status": f.status, "created_at": _ts(f.created_at)}


def approval(a: Approval) -> dict[str, Any]:
    return {"id": a.id, "patient_id": a.patient_id, "proposal_id": a.proposal_id,
            "recheck_flag_id": a.recheck_flag_id, "clinician_name": a.clinician_name, "clinician_role": a.clinician_role, "action": a.action,
            "priority": a.priority, "reason": a.reason, "created_at": _ts(a.created_at)}


def vitals(v: VitalsReading) -> dict[str, Any]:
    return {"id": v.id, "run_id": v.run_id, "raw": v.raw, "tews_total": v.tews_total,
            "tews_min": v.tews.get("total_min"), "tews_max": v.tews.get("total_max"),
            "created_at": _ts(v.created_at)}


def run(r: AgentRun) -> dict[str, Any]:
    return {"id": r.id, "patient_id": r.patient_id, "intake_id": r.intake_id, "kind": r.kind,
            "status": r.status, "model": r.model, "started_at": _ts(r.started_at),
            "finished_at": _ts(r.finished_at), "tool_calls": r.tool_calls, "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens, "latency_ms": r.latency_ms, "final_message": r.final_message,
            "error": r.error}


def audit(a: AuditLog) -> dict[str, Any]:
    return {"id": a.id, "created_at": _ts(a.created_at), "run_id": a.run_id, "patient_id": a.patient_id,
            "event_type": a.event_type, "source": a.source, "tool_name": a.tool_name, "inputs": a.inputs,
            "outputs": a.outputs, "is_error": a.is_error, "model": a.model, "latency_ms": a.latency_ms,
            "actor": a.actor}
