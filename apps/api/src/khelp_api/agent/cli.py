"""Run the agent on one synthetic note from the command line.

    uv run khelp-agent data/synthetic/notes/chest_pain.txt
    uv run khelp-agent --text "45yr M c/o chest pain ..."
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select

from khelp_db import AgentRun, AuditLog, Intake, Patient, Proposal, RecheckFlag, session_factory

from .runner import run_agent


def _print_event(event: dict) -> None:
    mark = "ERR" if event["is_error"] else "ok "
    print(f"  [{event['n']:>2}] {mark} {event['tool']:<22} {event['latency_ms'] or 0:>5} ms  "
          f"in={json.dumps(event['inputs'])[:110]}")
    body = event["outputs"].get("json")
    if isinstance(body, dict) and body.get("ok") is False:
        for err in body.get("errors", []):
            print(f"         -> {err['code']}: {err['message']}")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run the Klaudesk triage agent on one synthetic note")
    parser.add_argument("note_file", nargs="?", type=Path)
    parser.add_argument("--text", help="note text instead of a file")
    parser.add_argument("--name", default="Synthetic CLI patient")
    args = parser.parse_args()
    text = args.text if args.text else args.note_file.read_text(encoding="utf-8")

    with session_factory()() as s, s.begin():
        patient = Patient(display_name=args.name)
        s.add(patient)
        s.flush()
        intake = Intake(patient_id=patient.id, note_text=text)
        s.add(intake)
        s.flush()
        patient_id, intake_id = patient.id, intake.id

    print(f"patient_id={patient_id} intake_id={intake_id}\nNOTE: {text.strip()}\n\nTool calls:")
    run_id = run_agent(patient_id, intake_id, on_event=_print_event)

    with session_factory()() as s:
        run = s.get(AgentRun, run_id)
        print(f"\nrun {run_id}\n  status={run.status} model={run.model} tool_calls={run.tool_calls} "
              f"latency={run.latency_ms} ms tokens in/out={run.input_tokens}/{run.output_tokens}")
        if run.error:
            print(f"  error: {run.error}")
        print(f"  agent said: {run.final_message}")
        for p in s.scalars(select(Proposal).where(Proposal.run_id == run_id)):
            print(f"  PROPOSAL #{p.id} {p.priority} ({p.status}) citations={len(p.citations)} "
                  f"rationale={p.rationale!r}")
        for f in s.scalars(select(RecheckFlag).where(RecheckFlag.run_id == run_id)):
            print(f"  RECHECK FLAG #{f.id} {f.flag_type} ({f.status}): {f.reason}")
        n = len(s.scalars(select(AuditLog.id).where(AuditLog.run_id == run_id)).all())
        print(f"  audit_log rows for this run: {n}")
        print(f"  patients.approved_priority: {s.get(Patient, patient_id).approved_priority!r}")


if __name__ == "__main__":
    main()
