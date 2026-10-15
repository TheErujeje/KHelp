import pytest

from khelp_api.policy import can_call_in, can_override, can_set_manual_priority
from khelp_scoring import load_rules


@pytest.mark.parametrize("role,proposed,new,allowed", [
    ("TRIAGE_NURSE", "YELLOW", "YELLOW", True),   # confirm
    ("TRIAGE_NURSE", "YELLOW", "RED", True),      # raise
    ("TRIAGE_NURSE", "ORANGE", "GREEN", False),   # lower: senior only
    ("DOCTOR", "ORANGE", "GREEN", True),
    ("SENIOR_NURSE", "RED", "YELLOW", True),
])
def test_only_seniors_lower_a_priority(role, proposed, new, allowed):
    assert can_override(role, proposed, new) is allowed


def test_manual_triage_and_call_in_are_senior_actions():
    assert not can_set_manual_priority("TRIAGE_NURSE")
    assert can_set_manual_priority("DOCTOR")
    assert not can_call_in("TRIAGE_NURSE")
    assert can_call_in("SENIOR_NURSE")


def test_target_times_from_manual_table_3():
    rules = load_rules()
    assert [rules.target(p)["minutes"] for p in ("RED", "ORANGE", "YELLOW", "GREEN")] == [0, 10, 60, 240]
    assert rules.target("ORANGE")["source"]["location"].startswith("p.7")
