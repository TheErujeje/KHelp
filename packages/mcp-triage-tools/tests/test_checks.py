from khelp_triage_tools.checks import check_proposal

NOTE = ("SYNTHETIC. 45yr M c/o chest pain since morning, no SOB. walked in, alert. "
        "RR 22 PR 118 BP 150/90 T 37.1C SpO2 96%")
VITALS = {"rr": 22, "hr": 118, "bp": "150/90", "temp": "37.1C", "avpu": "alert", "mobility": "walking"}


def codes(result):
    return {e["code"] for e in result.errors}


def propose(**overrides):
    args = dict(priority="ORANGE", vitals=VITALS, age_years=45, discriminator_ids=["disc.orange.chest_pain"],
                rationale="Chest pain is an ORANGE emergency sign; TEWS 4 (RR 22, HR 118).", note=NOTE)
    args.update(overrides)
    return check_proposal(**args)


def test_valid_proposal_passes_with_citations():
    r = propose()
    assert r.ok, r.errors
    assert r.decision["priority"] == "ORANGE"
    types = {c["type"] for c in r.citations}
    assert {"vital", "tews_rule", "discriminator"} <= types
    # trauma was not written in the note, so it is outstanding but cannot change ORANGE
    assert r.decision["outstanding_inputs"] == ["trauma"]


def test_wrong_priority_is_rejected_with_expected_value():
    r = propose(priority="YELLOW")
    assert codes(r) == {"PRIORITY_MISMATCH"}
    assert r.errors[0]["details"]["expected"] == "ORANGE"


def test_uncited_discriminator_is_rejected():
    r = propose(discriminator_ids=[])
    assert "UNCITED_DISCRIMINATOR" in codes(r)


def test_negated_sign_cannot_be_cited():
    r = propose(discriminator_ids=["disc.orange.chest_pain", "disc.orange.sob_acute"])
    assert "DISCRIMINATOR_NOT_IN_NOTE" in codes(r)


def test_invented_vital_is_rejected():
    r = propose(vitals={**VITALS, "hr": 88})
    assert "UNGROUNDED_VITALS" in codes(r)


def test_invented_categorical_value_is_rejected():
    r = propose(vitals={**VITALS, "trauma": "no"})
    assert "UNGROUNDED_VITALS" in codes(r)


def test_invented_age_is_rejected():
    assert "UNGROUNDED_AGE" in codes(propose(age_years=50))


def test_diagnostic_or_treatment_rationale_is_rejected():
    assert "NOT_SCORING_LANGUAGE" in codes(propose(rationale="Most likely a heart attack."))
    assert "NOT_SCORING_LANGUAGE" in codes(propose(rationale="ORANGE; give aspirin 300 mg."))
    # Seen in a real qwen2.5:3b run:
    assert "NOT_SCORING_LANGUAGE" in codes(propose(
        rationale="Heart rate 118 and systolic 150, indicating possible cardiac issues."))
    assert "NOT_SCORING_LANGUAGE" in codes(propose(rationale="ORANGE: chest pain, query malaria."))


def test_missing_vitals_low_risk_must_recheck_instead():
    note = "SYNTHETIC. 30yr F c/o headache. alert, walking. RR 16 PR 80"
    r = check_proposal(priority="GREEN", vitals={"rr": 16, "hr": 80, "avpu": "alert", "mobility": "walking"},
                       age_years=30, discriminator_ids=[], rationale="TEWS low.", note=note)
    assert codes(r) == {"OUTCOME_RECHECK"}


def test_child_must_go_to_manual_triage():
    note = "SYNTHETIC. 6yr boy, fever, alert, walking. RR 24 PR 110 BP 100/60 T 38.0C"
    r = check_proposal(priority="YELLOW", vitals={"rr": 24, "hr": 110, "bp": "100/60", "temp": "38.0C"},
                       age_years=6, discriminator_ids=[], rationale="TEWS.", note=note)
    assert codes(r) == {"OUTCOME_MANUAL_TRIAGE"}


def test_mismatch_with_missing_inputs_says_propose_not_recheck():
    note = "SYNTHETIC. 28yr F abdo pain. walked in with help, alert. RR 18 PR 104 BP 100/70 T 38.9C"
    vitals = {"rr": 18, "hr": 104, "bp": "100/70", "temp": "38.9C", "avpu": "alert", "mobility": "with_help"}
    r = check_proposal(priority="RED", vitals=vitals, age_years=28, discriminator_ids=["disc.yellow.abdominal_pain"],
                       rationale="TEWS 6.", note=note)
    assert codes(r) == {"PRIORITY_MISMATCH"}
    err = r.errors[0]
    assert err["details"]["next_call"] == {"tool": "propose_priority", "priority": "ORANGE"}
    assert "Do NOT call request_recheck" in err["how_to_fix"]
