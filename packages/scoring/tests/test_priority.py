import pytest

from khelp_scoring import compute_tews, decide, tews_priority_rule

NORMAL = {"rr": 16, "hr": 80, "bp": "120/80", "temp": "36.8", "avpu": "alert", "mobility": "walking", "trauma": "no"}


@pytest.mark.parametrize("total,expected", [(0, "GREEN"), (2, "GREEN"), (3, "YELLOW"), (4, "YELLOW"),
                                            (5, "ORANGE"), (6, "ORANGE"), (7, "RED"), (15, "RED")])
def test_tews_to_priority(total, expected):
    assert tews_priority_rule(total)["priority"] == expected


def test_complete_vitals_no_signs_is_green():
    d = decide(compute_tews(NORMAL), [], age_years=30)
    assert d.outcome == "PROPOSE"
    assert d.priority == "GREEN"
    assert d.tews_priority_rule_ids == ["prio.tews.green"]
    assert len(d.tews_band_ids) == 7


def test_discriminator_raises_priority_above_tews():
    d = decide(compute_tews(NORMAL), ["disc.orange.chest_pain"], age_years=45)
    assert (d.outcome, d.priority) == ("PROPOSE", "ORANGE")


def test_tews_raises_priority_above_discriminator():
    sick = {**NORMAL, "rr": 32, "hr": 135, "bp": "85/50"}  # 3 + 3 + 1
    d = decide(compute_tews(sick), ["disc.yellow.abdominal_pain"], age_years=60)
    assert (d.outcome, d.priority) == ("PROPOSE", "RED")


def test_missing_vitals_low_risk_requests_recheck():
    vitals = {k: v for k, v in NORMAL.items() if k not in ("bp", "temp")}
    d = decide(compute_tews(vitals), [], age_years=30)
    assert d.outcome == "RECHECK"
    assert d.priority is None
    assert set(d.outstanding_inputs) == {"systolic_bp", "temperature"}


def test_red_sign_with_missing_vitals_still_proposes():
    d = decide(compute_tews({"avpu": "unresponsive"}), ["disc.red.seizure_current"], age_years=25)
    assert d.outcome == "PROPOSE"
    assert d.priority == "RED"
    assert d.outstanding_inputs  # vitals still to be recorded


def test_orange_sign_with_missing_vitals_proposes_and_rechecks():
    vitals = {k: v for k, v in NORMAL.items() if k != "bp"}
    vitals.update(rr=22, hr=115)  # known TEWS 4; missing SBP could add 3 -> RED
    d = decide(compute_tews(vitals), ["disc.orange.sob_acute"], age_years=50)
    assert d.outcome == "PROPOSE_AND_RECHECK"
    assert (d.priority_low, d.priority_high) == ("ORANGE", "RED")
    assert d.priority == "ORANGE"


def test_missing_input_that_cannot_change_priority_still_proposes():
    vitals = {k: v for k, v in NORMAL.items() if k != "trauma"}  # TEWS 1, trauma adds at most 1
    d = decide(compute_tews(vitals), [], age_years=30)
    assert (d.outcome, d.priority) == ("PROPOSE", "GREEN")
    assert d.outstanding_inputs == ["trauma"]


@pytest.mark.parametrize("age", [0.5, 5, 11.9, None])
def test_children_and_unknown_age_go_to_manual_triage(age):
    d = decide(compute_tews(NORMAL), ["disc.red.seizure_current"], age_years=age)
    assert d.outcome == "MANUAL_TRIAGE"
    assert d.priority is None


def test_unknown_discriminator_rejected():
    with pytest.raises(ValueError):
        decide(compute_tews(NORMAL), ["disc.made_up"], age_years=30)
