"""Agent runs, the live tool-call feed (SSE) and the audit log."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from khelp_db import AgentRun, AuditLog, Intake, Proposal, RecheckFlag, session_factory

from .. import serializers as ser
from ..deps import get_session

router = APIRouter()

POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 15
STREAM_LIMIT_SECONDS = 20 * 60


@router.get("/runs")
def list_runs(patient_id: int | None = None, limit: int = Query(default=50, le=500),
              s: Session = Depends(get_session)) -> dict[str, Any]:
    q = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)
    if patient_id is not None:
        q = q.where(AgentRun.patient_id == patient_id)
    return {"runs": [ser.run(r) for r in s.scalars(q)]}


@router.get("/runs/{run_id}")
def get_run(run_id: str, s: Session = Depends(get_session)) -> dict[str, Any]:
    run = s.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    intake = s.get(Intake, run.intake_id) if run.intake_id else None
    return {
        "run": ser.run(run),
        "note_text": intake.note_text if intake else None,
        "proposals": [ser.proposal(p) for p in s.scalars(select(Proposal).where(Proposal.run_id == run_id))],
        "flags": [ser.flag(f) for f in s.scalars(select(RecheckFlag).where(RecheckFlag.run_id == run_id))],
    }


def _events_after(run_id: str, after_id: int) -> list[dict[str, Any]]:
    with session_factory()() as s:
        rows = s.scalars(select(AuditLog).where(AuditLog.run_id == run_id, AuditLog.id > after_id)
                         .order_by(AuditLog.id)).all()
        return [ser.audit(r) for r in rows]


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request) -> StreamingResponse:
    """Server-sent events: every audit row for the run, as it is written.

    Tails audit_log, so it works across API workers and restarts, and the
    feed is exactly what the audit log records. Ends after RUN_END.
    """
    try:
        last_id = int(request.headers.get("last-event-id", "0"))
    except ValueError:
        last_id = 0

    async def stream() -> AsyncIterator[str]:
        nonlocal last_id
        started = last_beat = time.monotonic()
        yield "retry: 2000\n\n"
        while time.monotonic() - started < STREAM_LIMIT_SECONDS:
            if await request.is_disconnected():
                return
            events = await asyncio.to_thread(_events_after, run_id, last_id)
            for event in events:
                last_id = event["id"]
                yield f"id: {event['id']}\nevent: audit\ndata: {json.dumps(event, default=str)}\n\n"
                if event["event_type"] == "RUN_END":
                    yield "event: end\ndata: {}\n\n"
                    return
            if time.monotonic() - last_beat > HEARTBEAT_SECONDS:
                last_beat = time.monotonic()
                yield ": keep-alive\n\n"
            await asyncio.sleep(POLL_SECONDS)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


CSV_COLUMNS = ["id", "created_at", "run_id", "patient_id", "event_type", "source", "tool_name", "actor",
               "is_error", "model", "latency_ms", "inputs", "outputs"]


@router.get("/audit")
def get_audit(
    patient_id: int | None = None,
    run_id: str | None = None,
    event_type: str | None = None,
    source: str | None = None,
    before_id: int | None = None,
    limit: int = Query(default=200, le=5000),
    format: str = Query(default="json", pattern="^(json|csv)$"),
    s: Session = Depends(get_session),
):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if patient_id is not None:
        q = q.where(AuditLog.patient_id == patient_id)
    if run_id:
        q = q.where(AuditLog.run_id == run_id)
    if event_type:
        q = q.where(AuditLog.event_type == event_type)
    if source:
        q = q.where(AuditLog.source == source)
    if before_id:
        q = q.where(AuditLog.id < before_id)
    rows = [ser.audit(r) for r in s.scalars(q)]

    if format == "json":
        return {"entries": rows}

    def csv_lines() -> Iterator[str]:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "inputs": json.dumps(row["inputs"], default=str),
                             "outputs": json.dumps(row["outputs"], default=str)})
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)
        yield buf.getvalue()

    return StreamingResponse(csv_lines(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=khelp-audit.csv"})
