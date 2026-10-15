from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Priority = Literal["GREEN", "YELLOW", "ORANGE", "RED"]
Role = Literal["TRIAGE_NURSE", "DOCTOR", "SENIOR_NURSE"]


def _named(value: str) -> str:
    value = value.strip()
    if len(value) < 2:
        raise ValueError("a clinician name is required")
    return value


class IntakeIn(BaseModel):
    note_text: str = Field(min_length=5, max_length=5000)
    display_name: str | None = Field(default=None, max_length=120)


class RecheckIn(BaseModel):
    note_text: str = Field(min_length=3, max_length=2000, description="New vitals / change, as written")


class ApproveIn(BaseModel):
    clinician_name: str = Field(max_length=120)
    clinician_role: Role
    _check_name = field_validator("clinician_name")(_named)


class OverrideIn(BaseModel):
    clinician_name: str = Field(max_length=120)
    clinician_role: Role
    priority: Priority
    reason: str = Field(min_length=3, max_length=1000)
    _check_name = field_validator("clinician_name")(_named)


class AcknowledgeIn(BaseModel):
    clinician_name: str = Field(max_length=120)
    clinician_role: Role
    note: str | None = Field(default=None, max_length=1000)
    # Only for MANUAL_TRIAGE flags: the clinician's own priority for the patient.
    priority: Priority | None = None
    _check_name = field_validator("clinician_name")(_named)


class SeenIn(BaseModel):
    clinician_name: str = Field(max_length=120)
    clinician_role: Role
    _check_name = field_validator("clinician_name")(_named)


class CallIn(SeenIn):
    pass
