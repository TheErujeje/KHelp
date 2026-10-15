"""Who may do what. Enforced by the API, not just hidden in the UI.

SATS Training Manual 2012, p.6: the senior healthcare professional's discretion "allows the
clinical nurse practitioner or senior doctor to override the final triage priority assigned".
So a triage nurse may approve the proposal or raise the priority; lowering it below what SATS
gives, or setting the priority of a patient sent to manual triage, needs a doctor or senior nurse.

Roles come from the sign-in session (demo sign-in); a hospital deployment would take them from
its identity provider.
"""

from __future__ import annotations

from typing import Literal

from khelp_scoring import priority_rank

Role = Literal["TRIAGE_NURSE", "DOCTOR", "SENIOR_NURSE"]
ROLES: tuple[str, ...] = ("TRIAGE_NURSE", "DOCTOR", "SENIOR_NURSE")
SENIOR_ROLES: tuple[str, ...] = ("DOCTOR", "SENIOR_NURSE")
ROLE_LABEL = {"TRIAGE_NURSE": "Triage nurse", "DOCTOR": "Doctor", "SENIOR_NURSE": "Senior nurse"}

SENIOR_RULE = ("Lowering a priority below the SATS result, or setting the priority of a patient sent "
               "to manual triage, needs a doctor or senior nurse (SATS manual p.6, senior healthcare "
               "professional's discretion).")


def can_override(role: str, proposed: str, new: str) -> bool:
    """Anyone may confirm or raise; only seniors may lower."""
    if priority_rank(new) >= priority_rank(proposed):
        return True
    return role in SENIOR_ROLES


def can_set_manual_priority(role: str) -> bool:
    return role in SENIOR_ROLES


def can_call_in(role: str) -> bool:
    """Calling a patient into a consulting room is a doctor's (or senior's) action."""
    return role in SENIOR_ROLES
