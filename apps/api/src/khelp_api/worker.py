"""Background agent runs.

A small, bounded thread pool: each run holds a model slot for minutes, so
more parallelism only queues work on the model server. Runs are not resumed
after a restart; `mark_interrupted_runs` closes them out and flags the
patients for manual triage.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import select

from khelp_db import AgentRun, RecheckFlag, session_factory

from .agent.runner import run_agent

log = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=int(os.environ.get("KHELP_MAX_CONCURRENT_RUNS", "2")),
                           thread_name_prefix="agent-run")


def submit_run(patient_id: int, intake_id: int, kind: str, run_id: str) -> None:
    def job() -> None:
        try:
            run_agent(patient_id, intake_id, kind=kind, run_id=run_id)
        except Exception:
            log.exception("agent run %s crashed", run_id)

    _pool.submit(job)


def mark_interrupted_runs() -> int:
    with session_factory()() as s, s.begin():
        runs = s.scalars(select(AgentRun).where(AgentRun.status == "RUNNING")).all()
        for run in runs:
            run.status = "FAILED"
            run.error = "Interrupted by a server restart"
            run.finished_at = datetime.now(timezone.utc)
            if run.kind == "INITIAL":
                s.add(RecheckFlag(patient_id=run.patient_id, run_id=run.id, flag_type="MANUAL_TRIAGE",
                                  reason="Agent run interrupted by a server restart. Triage manually.",
                                  details={}, status="PENDING"))
        return len(runs)
