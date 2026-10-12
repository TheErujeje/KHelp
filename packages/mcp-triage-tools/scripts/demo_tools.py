"""Call every triage-tools tool over stdio, as the agent will, then show the guards.

    DATABASE_URL=... MCP_DATABASE_URL=... uv run python packages/mcp-triage-tools/scripts/demo_tools.py

Creates one SYNTHETIC patient. Uses the owner role only to set up the
patient/intake/run and to read back the audit log.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError

from khelp_db import AgentRun, AuditLog, Intake, Patient, session_factory

NOTE = ("SYNTHETIC PATIENT. 45yr M, c/o chest pain since morning, no SOB. Walked in, alert. "
        "RR 22  PR 118  BP 150/90  T 37.1C  SpO2 96%")
VITALS = {"rr": 22, "hr": 118, "bp": "150/90", "temp": "37.1C", "spo2": "96%",
          "avpu": "alert", "mobility": "walking"}


def show(title: str, payload: object) -> None:
    print(f"\n=== {title}")
    print(json.dumps(payload, indent=2, default=str)[:2500])


def setup() -> tuple[int, str]:
    with session_factory()() as s, s.begin():
        patient = Patient(display_name="Synthetic Patient A", age_years=None)
        s.add(patient)
        s.flush()
        s.add(Intake(patient_id=patient.id, note_text=NOTE))
        run_id = str(uuid.uuid4())
        s.add(AgentRun(id=run_id, patient_id=patient.id, model="demo-script (no model)"))
        return patient.id, run_id


async def call_tools(patient_id: int, run_id: str) -> None:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "khelp_triage_tools.server"],
        env={**os.environ, "KHELP_RUN_ID": run_id},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        show("list_tools", [{"name": t.name, "readOnly": t.annotations.read_only_hint if t.annotations else None}
                            for t in tools.tools])

        async def call(name: str, args: dict) -> dict:
            result = await session.call_tool(name, args)
            payload = result.structured_content or {"text": [c.text for c in result.content]}
            show(f"{name}({', '.join(args)})", payload)
            return payload

        await call("get_queue", {})
        await call("lookup_discriminators", {"complaint_text": NOTE})
        await call("compute_tews", {"vitals": VITALS})
        base = {"patient_id": patient_id, "vitals": VITALS, "age_years": 45,
                "discriminator_ids": ["disc.orange.chest_pain"],
                "rationale": "Chest pain is an ORANGE emergency sign; TEWS 4 from RR 22 and HR 118."}
        # Deliberately wrong first: the server recomputes and rejects it.
        await call("propose_priority", {**base, "priority": "YELLOW"})
        # Deliberately ungrounded: HR 88 is not in the note.
        await call("propose_priority", {**base, "priority": "ORANGE", "vitals": {**VITALS, "hr": 88}})
        await call("propose_priority", {**base, "priority": "ORANGE"})
        await call("request_recheck", {
            "patient_id": patient_id, "flag_type": "DETERIORATION",
            "reason": "Re-assessment after 40 min: RR and HR higher than at triage.",
            "new_vitals": {**VITALS, "rr": 30, "hr": 135},
        })
        await call("get_queue", {})


def guards(patient_id: int) -> None:
    print("\n=== Guards (direct SQL)")
    mcp_engine = create_engine(os.environ["MCP_DATABASE_URL"])
    attempts = {
        "MCP role: UPDATE patients SET approved_priority":
            f"UPDATE patients SET approved_priority='RED' WHERE id={patient_id}",
        "MCP role: INSERT INTO approvals":
            f"INSERT INTO approvals (patient_id, proposal_id, clinician_name, action) "
            f"VALUES ({patient_id}, 1, 'agent', 'APPROVE')",
        "MCP role: UPDATE proposals SET status='APPROVED'":
            f"UPDATE proposals SET status='APPROVED' WHERE patient_id={patient_id}",
    }
    for label, sql in attempts.items():
        try:
            with mcp_engine.begin() as conn:
                conn.execute(text(sql))
            print(f"  {label}: ALLOWED  <-- this should not happen")
        except DBAPIError as exc:
            print(f"  {label}: refused ({str(exc.orig).splitlines()[0]})")
    owner = create_engine(os.environ["DATABASE_URL"])
    try:
        with owner.begin() as conn:
            conn.execute(text("DELETE FROM audit_log"))
        print("  Owner role: DELETE FROM audit_log: ALLOWED  <-- this should not happen")
    except DBAPIError as exc:
        print(f"  Owner role: DELETE FROM audit_log: refused ({str(exc.orig).splitlines()[0]})")


def audit(run_id: str) -> None:
    print(f"\n=== audit_log for run {run_id}")
    with session_factory()() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.run_id == run_id).order_by(AuditLog.id)):
            print(f"  {row.created_at:%H:%M:%S} {row.source:<12} {row.tool_name:<22} "
                  f"error={row.is_error!s:<5} {row.latency_ms:>4} ms")
        p = s.get(Patient, patient_id_global)
        print(f"\n  patients.approved_priority after all calls: {p.approved_priority!r}")


if __name__ == "__main__":
    patient_id_global, run = setup()
    print(f"patient_id={patient_id_global} run_id={run}")
    asyncio.run(call_tools(patient_id_global, run))
    guards(patient_id_global)
    audit(run)
