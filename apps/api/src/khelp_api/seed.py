"""Seed the waiting room with SYNTHETIC patients from data/synthetic/patients.json.

    python -m khelp_api.seed            # only if the database has no patients
    python -m khelp_api.seed --force    # add them anyway

Patients are created with their intake note only: no proposals, approvals or
agent runs are fabricated. Each one is scored live from the dashboard.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import func, select

from khelp_db import AuditLog, Intake, Patient, session_factory

from .agent.runner import REPO_ROOT

SOURCE = Path(os.environ.get("KHELP_SYNTHETIC_FILE", REPO_ROOT / "data" / "synthetic" / "patients.json"))


def seed(count: int, force: bool = False) -> int:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    assert data.get("synthetic") is True, "refusing to seed from a file not marked synthetic"
    with session_factory()() as s, s.begin():
        if not force and s.scalar(select(func.count(Patient.id))):
            return 0
        now = datetime.now(timezone.utc)
        chosen = data["patients"][:count]
        for i, item in enumerate(chosen):
            # Stagger arrivals over the last hour so wait times look like a morning queue.
            arrived = now - timedelta(minutes=(len(chosen) - i) * 4)
            patient = Patient(display_name=f"Synthetic {item['id']}", arrived_at=arrived, is_synthetic=True)
            s.add(patient)
            s.flush()
            s.add(Intake(patient_id=patient.id, kind="INITIAL", note_text=item["note"], created_at=arrived))
            s.add(AuditLog(event_type="SEEDED", source="seed", patient_id=patient.id,
                           inputs={"synthetic_id": item["id"]}, outputs={"note": item["note"]}))
        return len(chosen)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=int(os.environ.get("KHELP_SEED_COUNT", "8")))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    n = seed(args.count, args.force)
    print(f"seeded {n} synthetic patients" if n else "database already has patients; not seeding")


if __name__ == "__main__":
    main()
