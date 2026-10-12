import pytest

from khelp_scoring import compute_tews

NORMAL = {"rr": 16, "hr": 80, "bp": "120/80", "temp": "36.8", "avpu": "alert", "mobility": "walking", "trauma": "no"}


def points(result, parameter):
    return next(i.points for i in result.breakdown if i.parameter == parameter)


def test_normal_adult_scores_complete():
    r = compute_tews(NORMAL)
    assert r.complete
    assert r.total == 1  # RR 16 falls in the 15-20 band (1 point)
    assert r.issues == []
    assert {i.parameter for i in r.breakdown} == {
        "respiratory_rate", "heart_rate", "systolic_bp", "temperature", "avpu", "mobility", "trauma",
    }
    assert all(i.source and i.verified is False for i in r.breakdown)


@pytest.mark.parametrize("rr,expected", [(8, 3), (9, 0), (14, 0), (15, 1), (20, 1), (21, 2), (29, 2), (30, 3)])
def test_respiratory_rate_band_edges(rr, expected):
    assert points(compute_tews({**NORMAL, "rr": rr}), "respiratory_rate") == expected


@pytest.mark.parametrize("hr,expected", [(40, 3), (41, 1), (50, 1), (51, 0), (100, 0), (101, 1), (110, 1), (111, 2), (129, 2), (130, 3)])
def test_heart_rate_band_edges(hr, expected):
    assert points(compute_tews({**NORMAL, "hr": hr}), "heart_rate") == expected


@pytest.mark.parametrize("sbp,expected", [(70, 3), (71, 2), (80, 2), (81, 1), (100, 1), (101, 0), (199, 0), (200, 2)])
def test_systolic_band_edges(sbp, expected):
    assert points(compute_tews({**NORMAL, "bp": f"{sbp}/50"}), "systolic_bp") == expected


@pytest.mark.parametrize("temp,expected", [("34.9", 2), ("35", 0), ("38.4", 0), ("38.5", 2)])
def test_temperature_band_edges(temp, expected):
    assert points(compute_tews({**NORMAL, "temp": temp}), "temperature") == expected


def test_categorical_aliases():
    r = compute_tews({**NORMAL, "avpu": "V", "mobility": "with help", "trauma": True})
    assert points(r, "avpu") == 1
    assert points(r, "mobility") == 1
    assert points(r, "trauma") == 1


def test_fahrenheit_with_unit_is_converted():
    r = compute_tews({**NORMAL, "temp": "101.3F"})
    item = next(i for i in r.breakdown if i.parameter == "temperature")
    assert item.value == 38.5
    assert item.points == 2
    assert any("°F" in n for n in r.notes)


def test_fahrenheit_without_unit_is_not_guessed():
    r = compute_tews({**NORMAL, "temp": "101"})
    assert not r.complete
    assert any(i.parameter == "temperature" and i.kind == "implausible" for i in r.issues)


def test_spo2_over_100_flagged():
    r = compute_tews({**NORMAL, "spo2": "104%"})
    assert any(i.parameter == "spo2" and i.kind == "implausible" for i in r.issues)
    assert r.complete  # SpO2 is not an adult TEWS input


def test_bp_not_in_sys_dia_form():
    r = compute_tews({**NORMAL, "bp": "120"})
    assert not r.complete
    assert any(i.parameter == "systolic_bp" and "systolic/diastolic" in i.reason for i in r.issues)


def test_bp_in_cmhg_is_implausible():
    r = compute_tews({**NORMAL, "bp": "12/8"})
    assert any(i.parameter == "systolic_bp" and i.kind == "implausible" for i in r.issues)


def test_bp_diastolic_above_systolic_is_implausible():
    r = compute_tews({**NORMAL, "bp": "80/120"})
    assert "systolic_bp" in [u.parameter for u in r.unresolved]


def test_missing_vitals_bounded_not_guessed():
    r = compute_tews({"rr": 16, "hr": 80, "avpu": "alert", "mobility": "walking", "trauma": "no"})
    assert not r.complete
    assert r.total is None
    assert {u.parameter for u in r.unresolved} == {"systolic_bp", "temperature"}
    assert r.total_min == 1
    assert r.total_max == 1 + 3 + 2
    assert sum(1 for i in r.issues if i.kind == "missing") == 2


def test_blank_strings_count_as_missing():
    r = compute_tews({**NORMAL, "temp": "not done", "hr": ""})
    assert {u.parameter for u in r.unresolved} == {"temperature", "heart_rate"}
