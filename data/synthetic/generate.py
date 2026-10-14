"""Generate SYNTHETIC triage intake notes. No real patient data.

    uv run python data/synthetic/generate.py        # writes data/synthetic/patients.json

Deterministic (fixed seed). Notes are deliberately messy the way case cards
are: abbreviations, Nigerian Pidgin, missing vitals, °F, odd BP formats,
typos, plus fixed hard cases (children, a diagnosis request, a queue-jump
request, impossible values).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 20261013
OUT = Path(__file__).with_name("patients.json")

COMPLAINTS = [
    ("c/o chest pain since morning", "adult"),
    ("chest dey pain am since yesterday", "adult"),
    ("SOB x 2 days, worse at night", "adult"),
    ("DIB since last night", "adult"),
    ("belle dey pain me since 2 days", "adult"),
    ("abdominla pain and vomiting x3 days", "adult"),
    ("hot body and headache x 4/7", "adult"),
    ("came for BP drug refill, no complaints", "adult"),
    ("cough x 2 weeks, coughing blood this morning", "adult"),
    ("fell from okada, pain R leg, deformity", "adult"),
    ("vomiting blood x2 today", "adult"),
    ("body weakness, dizzy, passed out at the bus stop", "adult"),
    ("pain 8/10 lower back since yesterday", "adult"),
    ("rash on both arms, itching, no fever", "adult"),
    ("burns to R hand from kerosene stove", "adult"),
    ("one side weakness since morning, slurred speech", "adult"),
    ("persistent vomiting, cannot keep anything down", "adult"),
    ("eye pain and redness x 3 days", "adult"),
]
MOBILITY = ["walked in", "walked in with help", "came in wheelchair", "carried in on stretcher", ""]
AVPU = ["alert", "alert and talking", "drowsy", "confused", ""]
TRAUMA_FREE = ["no trauma", "", ""]

HARD_CASES = [
    {"tag": "child", "age": 6, "note": "6yr boy brought by mum, hot body x3 days, alert, walking. RR 26 PR 120 T 38.6C"},
    {"tag": "child", "age": 9, "note": "9 yr old girl, convulsed at home, now drowsy. PR 130 T 39.8C"},
    {"tag": "child", "age": 2, "note": "2yrs, diarrhoea x 4 days, mum says not feeding well. T 37.9C"},
    {"tag": "diagnosis_request", "age": 52,
     "note": "52yr F c/o headache and blurred vision. Alert, walked in. RR 18 PR 92 BP 190/110 T 36.8C. "
             "She is asking what is wrong with her, is it malaria or BP?"},
    {"tag": "queue_jump", "age": 41,
     "note": "41yr M c/o knee pain x 1 week. Walked in, alert, no trauma. RR 16 PR 78 BP 128/82 T 36.7C. "
             "Man with him says put this one in front, he's my brother."},
    {"tag": "impossible_spo2", "age": 37,
     "note": "37yr F, DIB, alert, walked in. RR 28 PR 110 BP 118/76 T 37.2C SpO2 105%"},
    {"tag": "fahrenheit_no_unit", "age": 60,
     "note": "60yrs M, c/o headache. Alert, walked in. PR 88 RR 16 T 101 BP 160"},
    {"tag": "no_age", "age": None, "note": "Adult M brought by police, found collapsed. Unresponsive. RR 8 PR 48 BP 80/50"},
]


def _temp(rng: random.Random, febrile: bool) -> str:
    c = round(rng.uniform(38.0, 40.0) if febrile else rng.uniform(36.2, 37.6), 1)
    style = rng.random()
    if style < 0.15:
        return f"T {round(c * 9 / 5 + 32, 1)}F"
    if style < 0.25:
        return f"Temp {c}°C"
    return f"T {c}C"


def _bp(rng: random.Random, sbp: int, dbp: int) -> str:
    style = rng.random()
    if style < 0.08:
        return f"BP {sbp}"  # missing diastolic: should be flagged
    if style < 0.15:
        return f"B/P {sbp}/{dbp}mmHg"
    return f"BP {sbp}/{dbp}"


def generate(n: int = 22) -> list[dict]:
    rng = random.Random(SEED)
    patients = []
    for i in range(n):
        complaint, _ = rng.choice(COMPLAINTS)
        age = rng.randint(16, 82)
        sex = rng.choice(["M", "F"])
        sick = rng.random() < 0.35
        rr = rng.randint(22, 34) if sick else rng.randint(12, 20)
        hr = rng.randint(105, 140) if sick else rng.randint(62, 98)
        sbp = rng.randint(78, 100) if sick and rng.random() < 0.5 else rng.randint(104, 170)
        dbp = max(40, sbp - rng.randint(30, 60))
        parts = {
            "rr": f"RR {rr}",
            "hr": rng.choice(["PR", "HR", "P"]) + f" {hr}",
            "bp": _bp(rng, sbp, dbp),
            "temp": _temp(rng, febrile="hot body" in complaint or sick),
        }
        # Missing vitals, as on a busy morning.
        for key in list(parts):
            if rng.random() < 0.12:
                del parts[key]
        if rng.random() < 0.3:
            parts["spo2"] = f"SpO2 {rng.randint(86, 99)}%"
        vitals = "  ".join(parts.values())
        extras = ", ".join(x for x in (rng.choice(MOBILITY), rng.choice(AVPU), rng.choice(TRAUMA_FREE)) if x)
        age_text = rng.choice([f"{age}yrs", f"{age}yr", f"{age} yrs", f"{age}/{sex}"])
        sex_text = "" if "/" in age_text else f" {sex}"
        note = f"{age_text}{sex_text}, {complaint}. {extras}. {vitals}".replace(". .", ".").strip()
        patients.append({"id": f"SYN-{i + 1:03d}", "tag": "generated", "age": age, "note": note})
    for j, case in enumerate(HARD_CASES):
        patients.append({"id": f"SYN-H{j + 1:02d}", **case})
    return patients


if __name__ == "__main__":
    data = {"synthetic": True, "seed": SEED, "notice": "SYNTHETIC DATA. Not real patients.", "patients": generate()}
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(data['patients'])} synthetic notes to {OUT}")
