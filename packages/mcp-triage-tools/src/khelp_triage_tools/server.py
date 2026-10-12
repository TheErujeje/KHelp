"""triage-tools MCP server (stdio).

Five tools. Scoring logic lives in khelp_scoring; these are thin wrappers
plus the two write paths (PENDING proposal, PENDING re-check flag). Every
call is written to audit_log. Errors come back as structured results, never
as exceptions that end the agent's run.
"""

from __future__ import annotations

import time
import traceback
from typing import Any, Callable

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from sqlalchemy.orm import Session

from khelp_scoring import compute_tews as _compute_tews
from khelp_scoring import lookup_discriminators as _lookup
from khelp_scoring import max_priority, tews_priority_rule

from . import data
from .checks import check_proposal

FLAG_TYPES = ("MISSING_VITALS", "DETERIORATION", "MANUAL_TRIAGE", "OTHER")

server = MCPServer(
    name="triage-tools",
    instructions=(
        "SATS adult triage scoring tools. They score and cite; they never diagnose or treat. "
        "propose_priority only creates a PENDING proposal for a named clinician to approve. "
        "No tool can change a patient's queue position."
    ),
)


def _fail(code: str, message: str, how_to_fix: str, **details: Any) -> dict[str, Any]:
    return {"ok": False, "errors": [{"code": code, "message": message, "how_to_fix": how_to_fix,
                                     "details": details}]}


def _audited(tool_name: str, inputs: dict[str, Any], patient_id: int | None,
             fn: Callable[[Session], dict[str, Any]]) -> dict[str, Any]:
    """Run a tool and write its audit row in the SAME transaction.

    If the audit row cannot be written, the tool's writes roll back too: an
    unlogged action never stands.
    """
    started = time.perf_counter()
    s = data.session()
    try:
        try:
            result = fn(s)
        except Exception as exc:  # report, don't crash the agent's run
            s.rollback()
            result = _fail("INTERNAL_ERROR", f"{type(exc).__name__}: {exc}",
                           "Retry once; if it fails again, call request_recheck with flag_type='OTHER'.",
                           trace=traceback.format_exc(limit=3))
        latency_ms = int((time.perf_counter() - started) * 1000)
        data.add_audit(s, tool_name=tool_name, inputs=inputs, outputs=result,
                       is_error=not result.get("ok", True), latency_ms=latency_ms, patient_id=patient_id)
        s.commit()
        return result
    except Exception as exc:
        s.rollback()
        return _fail("AUDIT_WRITE_FAILED", f"could not write audit log: {str(exc).splitlines()[0]}",
                     "Nothing was saved. Stop and report the error.")
    finally:
        s.close()


def _tews_summary(tews: dict[str, Any]) -> dict[str, Any]:
    low = tews_priority_rule(tews["total_min"])["priority"]
    high = tews_priority_rule(tews["total_max"])["priority"]
    return {"tews_priority_low": low, "tews_priority_high": high}


@server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def get_queue() -> dict[str, Any]:
    """Current waiting patients, ordered by APPROVED priority then arrival time.

    Shows each patient's approved priority (set only by a clinician), any
    pending proposal, and pending re-check flags. Read-only.
    """
    def run(s: Session) -> dict[str, Any]:
        return {"ok": True, "patients": data.queue(s)}
    return _audited("get_queue", {}, None, run)


@server.tool(annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False))
def lookup_discriminators(complaint_text: str) -> dict[str, Any]:
    """Match a presenting complaint against the SATS adult emergency-sign list.

    Deterministic keyword/synonym matching (English, common abbreviations such
    as SOB / DIB / c/o, and Nigerian Pidgin). Pass the complaint exactly as
    written in the note. Returns matched signs with ids, matched phrase,
    priority and source. Negated mentions ("no chest pain") are returned with
    negated=true and must not be cited.
    """
    def run(s: Session) -> dict[str, Any]:
        matches = [m.to_dict() for m in _lookup(complaint_text)]
        active = [m for m in matches if not m["negated"]]
        return {
            "ok": True,
            "matches": active,
            "negated": [m for m in matches if m["negated"]],
            "cite_these_ids": [m["id"] for m in active],
            "highest_priority": max_priority(*(m["priority"] for m in active)),
        }
    return _audited("lookup_discriminators", {"complaint_text": complaint_text}, None, run)


@server.tool(annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False))
def compute_tews(vitals: dict[str, Any]) -> dict[str, Any]:
    """Compute the SATS adult Triage Early Warning Score from vitals.

    `vitals` keys (aliases accepted): respiratory_rate (rr), heart_rate (hr,
    pulse), bp as "sys/dia" or systolic_bp, temperature (temp, with unit e.g.
    "38.2C" or "101F"), spo2, avpu (alert/confused/voice/pain/unresponsive),
    mobility (walking/with_help/stretcher), trauma (yes/no). Pass only values
    written in the note; omit anything not recorded. Returns total, per-vital
    breakdown (value, band, points, source), and missing/implausible inputs.
    """
    def run(s: Session) -> dict[str, Any]:
        tews = _compute_tews(vitals or {}).to_dict()
        return {"ok": True, **tews, **_tews_summary(tews)}
    return _audited("compute_tews", {"vitals": vitals}, None, run)


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False,
                                         open_world_hint=False))
def propose_priority(
    patient_id: int,
    priority: str,
    vitals: dict[str, Any],
    discriminator_ids: list[str],
    rationale: str,
    age_years: float | None = None,
) -> dict[str, Any]:
    """Propose a SATS priority for a named clinician to approve. Does NOT change the queue.

    The server recomputes TEWS from `vitals` (the same values you passed to
    compute_tews), checks every vital and the age against the intake note,
    checks `discriminator_ids` against lookup_discriminators on the note, and
    recomputes the priority. If anything disagrees it returns ok=false with
    errors and how_to_fix; correct the call and try again. On success it
    stores a PENDING proposal with citations.

    `rationale`: one or two sentences on the scoring evidence only. Never a
    diagnosis, likely condition, or treatment.
    """
    inputs = {"patient_id": patient_id, "priority": priority, "vitals": vitals,
              "discriminator_ids": discriminator_ids, "rationale": rationale, "age_years": age_years}

    def run(s: Session) -> dict[str, Any]:
        patient = data.get_patient(s, patient_id)
        if patient is None:
            return _fail("UNKNOWN_PATIENT", f"no patient {patient_id}", "Use a patient_id from get_queue.")
        if patient.status != "WAITING":
            return _fail("PATIENT_NOT_WAITING", f"patient {patient_id} is {patient.status}",
                         "Only waiting patients can be scored.")
        note = data.notes_for_patient(s, patient_id)
        result = check_proposal(priority=priority, vitals=vitals, age_years=age_years,
                                discriminator_ids=discriminator_ids, rationale=rationale, note=note)
        if not result.ok:
            return {"ok": False, "errors": result.errors, "server_decision": result.decision}

        decision = result.decision
        reading = data.insert_vitals(s, patient_id, vitals, result.tews)
        needs_recheck = decision["outcome"] == "PROPOSE_AND_RECHECK"
        proposal = data.insert_proposal(
            s, patient_id=patient_id, priority=decision["priority"], citations=result.citations,
            decision={**decision, "age_years": age_years}, rationale=rationale.strip(),
            vitals_reading_id=reading.id, needs_recheck=needs_recheck)
        flag_id = None
        if needs_recheck:
            flag = data.insert_recheck(
                s, patient_id=patient_id, flag_type="MISSING_VITALS",
                reason=f"Proposed {decision['priority']} on available evidence; could be "
                       f"{decision['priority_high']} once {', '.join(decision['outstanding_inputs'])} "
                       "are recorded",
                details={"outstanding_inputs": decision["outstanding_inputs"], "proposal_id": proposal.id})
            flag_id = flag.id
        return {
            "ok": True,
            "proposal_id": proposal.id,
            "status": "PENDING",
            "priority": decision["priority"],
            "outcome": decision["outcome"],
            "recheck_flag_id": flag_id,
            "citations": result.citations,
            "note": "Awaiting approval by a named clinician. Queue position is unchanged.",
        }
    return _audited("propose_priority", inputs, patient_id, run)


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False,
                                         open_world_hint=False))
def request_recheck(
    patient_id: int,
    reason: str,
    flag_type: str = "MISSING_VITALS",
    new_vitals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Raise a PENDING re-check flag for a human to look at. Does NOT change the queue.

    flag_type: MISSING_VITALS (required vitals missing or implausible),
    DETERIORATION (re-assessment is worse), MANUAL_TRIAGE (patient under 12
    or age unknown), or OTHER. If `new_vitals` is given, TEWS is computed and
    compared with the patient's previous reading.
    """
    inputs = {"patient_id": patient_id, "reason": reason, "flag_type": flag_type, "new_vitals": new_vitals}

    def run(s: Session) -> dict[str, Any]:
        ftype = (flag_type or "").strip().upper()
        if ftype not in FLAG_TYPES:
            return _fail("INVALID_FLAG_TYPE", f"flag_type {flag_type!r} is not allowed",
                         f"Use one of {', '.join(FLAG_TYPES)}.")
        if not (reason or "").strip():
            return _fail("MISSING_REASON", "reason is empty", "Say what needs re-checking and why.")
        if data.get_patient(s, patient_id) is None:
            return _fail("UNKNOWN_PATIENT", f"no patient {patient_id}", "Use a patient_id from get_queue.")
        details: dict[str, Any] = {}
        if new_vitals:
            previous = data.latest_vitals(s, patient_id)
            tews = _compute_tews(new_vitals).to_dict()
            reading = data.insert_vitals(s, patient_id, new_vitals, tews)
            details = {
                "vitals_reading_id": reading.id,
                "new_tews": {"total": tews["total"], "min": tews["total_min"], "max": tews["total_max"]},
                "previous_tews": None,
                "issues": tews["issues"],
            }
            if previous:
                prev = previous.tews
                details["previous_tews"] = {"total": prev["total"], "min": prev["total_min"],
                                            "max": prev["total_max"], "vitals_reading_id": previous.id}
                # Ranges, so a missing input on either reading does not hide a change.
                details["definitely_worse"] = tews["total_min"] > prev["total_max"]
                details["possibly_worse"] = tews["total_max"] > prev["total_min"]
        flag = data.insert_recheck(s, patient_id=patient_id, flag_type=ftype, reason=reason.strip(),
                                   details=details)
        return {"ok": True, "flag_id": flag.id, "status": "PENDING", "flag_type": ftype, "details": details,
                "note": "Flag raised for a clinician to acknowledge. Queue position is unchanged."}
    return _audited("request_recheck", inputs, patient_id, run)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
