"""Normalise vitals as extracted from a triage note.

Input is loose (strings with units, odd BP forms, aliases). Output is either a
canonical value per TEWS parameter or an issue saying why it is missing or
implausible. Nothing is guessed: an ambiguous value becomes an issue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .rules import RuleSet

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "respiratory_rate": ("respiratory_rate", "rr", "resp", "resp_rate", "respiration"),
    "heart_rate": ("heart_rate", "hr", "pulse", "pr", "pulse_rate"),
    "systolic_bp": ("systolic_bp", "sbp", "systolic"),
    "diastolic_bp": ("diastolic_bp", "dbp", "diastolic"),
    "bp": ("bp", "blood_pressure"),
    "temperature": ("temperature", "temp", "t"),
    "spo2": ("spo2", "sats", "sat", "o2_sat", "oxygen_saturation", "sao2"),
    "avpu": ("avpu", "consciousness", "loc_avpu", "level_of_consciousness"),
    "mobility": ("mobility", "mobile"),
    "trauma": ("trauma", "injury"),
}

CATEGORY_ALIASES: dict[str, dict[str, str]] = {
    "avpu": {
        "a": "alert", "alert": "alert", "awake": "alert", "conscious": "alert",
        "confused": "confused", "new confusion": "confused", "c": "confused",
        "v": "voice", "voice": "voice", "responds to voice": "voice",
        "p": "pain", "pain": "pain", "responds to pain": "pain",
        "u": "unresponsive", "unresponsive": "unresponsive", "unconscious": "unresponsive",
    },
    "mobility": {
        "walking": "walking", "walk": "walking", "walked in": "walking",
        "ambulant": "walking", "ambulatory": "walking",
        "with help": "with_help", "with_help": "with_help", "assisted": "with_help",
        "supported": "with_help",
        "stretcher": "stretcher", "immobile": "stretcher", "carried": "stretcher",
        "stretcher/immobile": "stretcher",
    },
    "trauma": {
        "yes": "yes", "y": "yes", "true": "yes",
        "no": "no", "n": "no", "false": "no", "none": "no",
    },
}

SPO2_PLAUSIBLE = (50, 100)
DBP_PLAUSIBLE = (20, 200)


@dataclass
class VitalIssue:
    parameter: str
    kind: str  # "missing" | "implausible"
    raw: Any
    reason: str


@dataclass
class NormalisedVitals:
    values: dict[str, Any] = field(default_factory=dict)
    issues: list[VitalIssue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)  # e.g. SpO2, DBP: recorded, not scored


def _canonical_key(key: str) -> str | None:
    k = key.strip().lower().replace(" ", "_").replace("-", "_")
    for canonical, aliases in KEY_ALIASES.items():
        if k in aliases:
            return canonical
    return None


def _first_number(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        m = _NUMBER.search(raw)
        return float(m.group()) if m else None
    return None


def _is_blank(raw: Any) -> bool:
    return raw is None or (isinstance(raw, str) and raw.strip().lower() in ("", "-", "n/a", "na", "nil", "not done", "?"))


def _parse_temperature(raw: Any, out: NormalisedVitals) -> float | None:
    value = _first_number(raw)
    if value is None:
        out.issues.append(VitalIssue("temperature", "implausible", raw, "no number found"))
        return None
    text = str(raw).lower()
    unit_f = bool(re.search(r"\d\s*°?\s*f\b", text)) or "fahrenheit" in text
    unit_c = bool(re.search(r"\d\s*°?\s*c\b", text)) or "celsius" in text
    if unit_f:
        celsius = round((value - 32) * 5 / 9, 1)
        out.notes.append(f"temperature {raw!r} converted from °F to {celsius} °C")
        return celsius
    if not unit_c and 86 <= value <= 111:
        out.issues.append(VitalIssue(
            "temperature", "implausible", raw,
            "looks like °F but no unit was written; not converted — re-check and record the unit",
        ))
        return None
    return value


def _parse_bp(raw: Any, out: NormalisedVitals) -> tuple[float | None, float | None]:
    text = str(raw).strip()
    m = re.fullmatch(r"(\d{2,3})\s*(?:/|over|\\)\s*(\d{1,3})\s*(?:mm\s*hg|mmhg)?", text, flags=re.I)
    if not m:
        out.issues.append(VitalIssue(
            "systolic_bp", "implausible", raw, "BP not written as systolic/diastolic (e.g. 120/80)",
        ))
        return None, None
    return float(m.group(1)), float(m.group(2))


def _parse_category(param: str, raw: Any, out: NormalisedVitals) -> str | None:
    if isinstance(raw, bool):
        raw = "yes" if raw else "no"
    key = str(raw).strip().lower().replace("_", " ")
    mapped = CATEGORY_ALIASES[param].get(key) or CATEGORY_ALIASES[param].get(key.replace(" ", "_"))
    if mapped is None:
        out.issues.append(VitalIssue(param, "implausible", raw, f"unrecognised {param} value"))
    return mapped


def normalise_vitals(raw_vitals: dict[str, Any], rules: RuleSet) -> NormalisedVitals:
    out = NormalisedVitals()
    collected: dict[str, Any] = {}
    for key, raw in (raw_vitals or {}).items():
        canonical = _canonical_key(key)
        if canonical is None:
            out.notes.append(f"ignored unknown field {key!r}")
            continue
        if not _is_blank(raw):
            collected[canonical] = raw

    # Blood pressure: explicit systolic wins; otherwise parse "sys/dia".
    if "systolic_bp" not in collected and "bp" in collected:
        sbp, dbp = _parse_bp(collected["bp"], out)
        if sbp is not None:
            collected["systolic_bp"] = sbp
            collected.setdefault("diastolic_bp", dbp)

    params = rules.parameters
    for name, spec in params.items():
        raw = collected.get(name)
        if raw is None:
            already_flagged = any(i.parameter == name for i in out.issues)
            if not already_flagged:
                out.issues.append(VitalIssue(name, "missing", None, f"{spec['label']} not recorded"))
            continue

        if spec["kind"] == "categorical":
            value = _parse_category(name, raw, out)
            if value is not None:
                out.values[name] = value
            continue

        value = _parse_temperature(raw, out) if name == "temperature" else _first_number(raw)
        if value is None:
            if not any(i.parameter == name for i in out.issues):
                out.issues.append(VitalIssue(name, "implausible", raw, "no number found"))
            continue
        lo, hi = spec["plausible"]["min"], spec["plausible"]["max"]
        if not lo <= value <= hi:
            out.issues.append(VitalIssue(
                name, "implausible", raw, f"{value:g} {spec.get('unit', '')} is outside {lo}-{hi}; re-measure",
            ))
            continue
        out.values[name] = value

    # Recorded but not part of adult TEWS: still sanity-checked.
    if "diastolic_bp" in collected:
        dbp = _first_number(collected["diastolic_bp"])
        sbp = out.values.get("systolic_bp")
        if dbp is None or not DBP_PLAUSIBLE[0] <= dbp <= DBP_PLAUSIBLE[1] or (sbp is not None and dbp >= sbp):
            out.issues.append(VitalIssue("diastolic_bp", "implausible", collected["diastolic_bp"],
                                         "diastolic missing, out of range, or not below systolic"))
            if sbp is not None:
                # A BP pair that does not make sense makes the systolic suspect too.
                del out.values["systolic_bp"]
                out.issues.append(VitalIssue("systolic_bp", "implausible", sbp,
                                             "systolic/diastolic pair inconsistent; re-measure BP"))
        else:
            out.extras["diastolic_bp"] = dbp
    if "spo2" in collected:
        spo2 = _first_number(collected["spo2"])
        if spo2 is None or not SPO2_PLAUSIBLE[0] <= spo2 <= SPO2_PLAUSIBLE[1]:
            out.issues.append(VitalIssue("spo2", "implausible", collected["spo2"],
                                         f"SpO2 must be {SPO2_PLAUSIBLE[0]}-{SPO2_PLAUSIBLE[1]}%"))
        else:
            out.extras["spo2"] = spo2

    return out
