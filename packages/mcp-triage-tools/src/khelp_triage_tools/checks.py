"""Server-side checks on an agent's proposal. Pure functions, no database.

The agent does not get the last word on priority. `check_proposal`
recomputes everything from the cited inputs and the intake note, and
returns structured errors the agent can read and correct.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from khelp_scoring import RuleSet, compute_tews, decide, load_rules, lookup_discriminators
from khelp_scoring.vitals import KEY_ALIASES

_NUMBER = re.compile(r"\d+(?:\.\d+)?")

# Words in the note that justify each categorical TEWS value. Without one of
# these, the agent may not assert the value (it must leave it out instead).
CATEGORY_EVIDENCE: dict[tuple[str, str], tuple[str, ...]] = {
    ("avpu", "alert"): ("alert", "conscious", "awake", "oriented", "a&o", "gcs 15", "talking"),
    ("avpu", "confused"): ("confus", "disoriented"),
    ("avpu", "voice"): ("voice", "responds to voice", "rousable"),
    ("avpu", "pain"): ("pain stimul", "responds to pain", "to pain"),
    ("avpu", "unresponsive"): ("unresponsive", "unconscious", "not responding", "no dey respond"),
    ("mobility", "walking"): ("walk", "ambula", "ambulant"),
    ("mobility", "with_help"): ("help", "assist", "support", "wheelchair", "held up"),
    ("mobility", "stretcher"): ("stretcher", "carried", "immobile", "trolley", "cannot walk", "can't walk", "no fit waka"),
    # SATS p.27: trauma is ANY injury to the patient within the past 48 hours.
    ("trauma", "yes"): ("trauma", "injur", "fell", "fall", "rta", "accident", "wound", "laceration", "beaten",
                        "assault", "okada", "stab", "knife", "burn", "scald", "gunshot", "bite", "bitten"),
    ("trauma", "no"): ("no trauma", "no injur", "nil trauma", "no history of trauma", "no fall"),
}

# Proposal rationales describe scoring only. These patterns indicate diagnosis
# or treatment language and are rejected.
FORBIDDEN_RATIONALE = (
    (re.compile(r"\b\d+(\.\d+)?\s*(mg|mcg|ml|iu|units?)\b", re.I), "dose"),
    (re.compile(r"\bprescri", re.I), "prescribing"),
    (re.compile(r"\badminister", re.I), "treatment"),
    (re.compile(r"\b(treat|start|commence)\w*\s+(with|on)\b", re.I), "treatment"),
    (re.compile(r"\b(likely|probabl[ey]|possibl[ey]|suspect\w*|suggest\w*|indicat\w*|consistent with|"
                r"diagnos[ie]s (is|of)|due to|caused by|rule out)\b", re.I),
     "diagnostic language"),
    # Naming a condition is a diagnosis, whatever the phrasing.
    (re.compile(r"\b(cardiac|heart attack|myocardial|angina|malaria|typhoid|sepsis|septic|infection|pneumonia|"
                r"stroke|asthma|diabetic|hypertensi\w*|appendicitis|ectopic|meningitis|cholera|ulcer|"
                r"tuberculosis|tb|covid|hiv)\b", re.I),
     "condition name"),
)

MAX_RATIONALE = 1500
PROPOSABLE = ("PROPOSE", "PROPOSE_AND_RECHECK")


@dataclass
class CheckResult:
    ok: bool
    errors: list[dict[str, Any]] = field(default_factory=list)
    decision: dict[str, Any] | None = None
    tews: dict[str, Any] | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    discriminators: list[dict[str, Any]] = field(default_factory=list)


def _error(code: str, message: str, how_to_fix: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "how_to_fix": how_to_fix, "details": details}


def _numbers(text: str) -> set[float]:
    return {float(n) for n in _NUMBER.findall(text)}


def _canonical(key: str) -> str | None:
    k = key.strip().lower().replace(" ", "_").replace("-", "_")
    return next((c for c, aliases in KEY_ALIASES.items() if k in aliases), None)


def ungrounded_vitals(vitals: dict[str, Any], tews: dict[str, Any], note: str) -> list[dict[str, Any]]:
    """Vitals the agent asserted that the note does not support."""
    note_lower = note.lower()
    note_numbers = _numbers(note)
    problems = []
    for key, raw in (vitals or {}).items():
        canonical = _canonical(key)
        if raw is None or canonical is None:
            continue
        if canonical in ("avpu", "mobility", "trauma"):
            item = next((b for b in tews["breakdown"] if b["parameter"] == canonical), None)
            if item is None:
                continue  # unrecognised value; already reported as an issue
            words = CATEGORY_EVIDENCE.get((canonical, item["value"]), ())
            if not any(w in note_lower for w in words):
                problems.append({"field": key, "value": raw,
                                 "reason": f"note gives no evidence for {canonical}={item['value']}"})
            continue
        if isinstance(raw, bool):
            continue
        missing = [n for n in _numbers(str(raw)) if n not in note_numbers]
        if missing:
            problems.append({"field": key, "value": raw,
                             "reason": f"number(s) {', '.join(f'{n:g}' for n in missing)} not found in the note"})
            continue
        if canonical == "temperature":
            unit = _unit(str(raw))
            number = _first_number(str(raw))
            if unit and number is not None and not _unit_written(note_lower, number, unit):
                problems.append({"field": key, "value": raw,
                                 "reason": f"the note does not write °{unit.upper()} for this temperature; do not add a "
                                           "unit that is not written (pass the value exactly as written)"})
        if canonical in ("systolic_bp", "bp"):
            sbp = _first_number(str(raw))  # systolic is the first number in "150/90"
            if sbp is not None and not re.search(rf"(?<![\d.]){sbp:g}\s*(/|over|\\)\s*\d", note_lower):
                problems.append({"field": key, "value": raw,
                                 "reason": "the note does not give this blood pressure as systolic/diastolic "
                                           "(e.g. 120/80); a single number is not scored, leave it out"})
    return problems


def _first_number(text: str) -> float | None:
    m = _NUMBER.search(text)
    return float(m.group()) if m else None


def _unit(raw: str) -> str | None:
    m = re.search(r"\d\s*°?\s*([cf])\b", raw.lower())
    return m.group(1) if m else None


def _unit_written(note_lower: str, number: float, unit: str) -> bool:
    """Is `number` followed by this unit (C or F, optional ° and space) somewhere in the note?"""
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*°?\s*([cf])\b", note_lower):
        if float(m.group(1)) == number and m.group(2) == unit:
            return True
    return False


def forbidden_language(rationale: str) -> list[str]:
    return sorted({label for pattern, label in FORBIDDEN_RATIONALE if pattern.search(rationale)})


def build_citations(tews: dict[str, Any], decision: dict[str, Any], disc_matches: list[dict[str, Any]],
                    rules: RuleSet) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for item in tews["breakdown"]:
        citations.append({
            "type": "vital", "parameter": item["parameter"], "label": item["label"],
            "value": item["value"], "unit": item["unit"], "band_id": item["band_id"],
            "band": item["band_label"], "points": item["points"],
            "source": item["source"], "verified": item["verified"],
        })
    for rule in rules.priority_rules["tews_to_priority"]:
        if rule["id"] in decision["tews_priority_rule_ids"]:
            citations.append({
                "type": "tews_rule", "rule_id": rule["id"], "priority": rule["priority"],
                "range": [rule["min"], rule["max"]],
                "tews_total": tews["total"], "tews_min": tews["total_min"], "tews_max": tews["total_max"],
                "source": rule["source"], "verified": rule["verified"],
            })
    for m in disc_matches:
        citations.append({
            "type": "discriminator", "discriminator_id": m["id"], "name": m["name"],
            "priority": m["priority"], "matched_phrase": m["matched_phrase"], "clause": m["clause"],
            "source": m["source"], "verified": m["verified"],
        })
    if decision["outstanding_inputs"]:
        rule = rules.priority_rules["missing_inputs"]
        citations.append({
            "type": "missing_inputs_rule", "rule_id": rule["id"],
            "outstanding_inputs": decision["outstanding_inputs"],
            "priority_low": decision["priority_low"], "priority_high": decision["priority_high"],
            "source": rule["source"], "verified": rule["verified"],
        })
    return citations


def check_proposal(
    *,
    priority: str,
    vitals: dict[str, Any],
    age_years: float | None,
    discriminator_ids: list[str],
    rationale: str,
    note: str,
    rules: RuleSet | None = None,
) -> CheckResult:
    rules = rules or load_rules()
    errors: list[dict[str, Any]] = []
    priority = (priority or "").strip().upper()
    discriminator_ids = list(dict.fromkeys(discriminator_ids or []))

    if priority not in ("GREEN", "YELLOW", "ORANGE", "RED"):
        errors.append(_error("INVALID_PRIORITY", f"priority {priority!r} is not a SATS priority",
                             "Use one of GREEN, YELLOW, ORANGE, RED."))

    rationale = (rationale or "").strip()
    if not rationale:
        errors.append(_error("MISSING_RATIONALE", "rationale is empty",
                             "Explain which vitals and emergency signs produced the priority."))
    elif len(rationale) > MAX_RATIONALE:
        errors.append(_error("RATIONALE_TOO_LONG", f"rationale exceeds {MAX_RATIONALE} characters",
                             "Keep the rationale to the scoring evidence."))
    elif found := forbidden_language(rationale):
        errors.append(_error("NOT_SCORING_LANGUAGE", f"rationale contains {', '.join(found)}",
                             "Describe only the TEWS and emergency-sign evidence. Do not diagnose, "
                             "name likely conditions, or suggest treatment.", categories=found))

    if age_years is not None and float(age_years) not in _numbers(note):
        errors.append(_error("UNGROUNDED_AGE", f"age {age_years:g} does not appear in the note",
                             "Use the age written in the note, or pass age_years=null if none is written."))

    unknown = [d for d in discriminator_ids if rules.discriminator(d) is None]
    if unknown:
        errors.append(_error("UNKNOWN_DISCRIMINATOR", "cited discriminator ids do not exist",
                             "Only cite ids returned by lookup_discriminators.", ids=unknown))

    matches = [m.to_dict() for m in lookup_discriminators(note, rules)]
    active = {m["id"]: m for m in matches if not m["negated"]}
    not_in_note = [d for d in discriminator_ids if d not in active and d not in unknown]
    if not_in_note:
        errors.append(_error("DISCRIMINATOR_NOT_IN_NOTE", "cited emergency signs are not matched in the note",
                             "Call lookup_discriminators on the note and cite only its non-negated matches.",
                             ids=not_in_note))
    uncited = [m for d, m in active.items() if d not in discriminator_ids]
    if uncited:
        errors.append(_error("UNCITED_DISCRIMINATOR", "the note matches emergency signs that were not cited",
                             "Cite every non-negated match from lookup_discriminators; the agent may not "
                             "drop a sign. A nurse can override if a match is wrong.",
                             ids=[m["id"] for m in uncited],
                             signs=[f"{m['name']} ({m['priority']}) via '{m['matched_phrase']}'" for m in uncited]))

    tews = compute_tews(vitals or {}, rules).to_dict()
    ungrounded = ungrounded_vitals(vitals or {}, tews, note)
    if ungrounded:
        errors.append(_error("UNGROUNDED_VITALS", "some vitals are not supported by the note",
                             "Only pass values written in the note. Leave a vital out if it was not "
                             "recorded; never fill it in.", vitals=ungrounded))

    if errors:
        return CheckResult(ok=False, errors=errors, tews=tews, discriminators=matches)

    cited = [active[d] for d in discriminator_ids]
    decision = decide(compute_tews(vitals or {}, rules), discriminator_ids, age_years, rules).to_dict()

    if decision["outcome"] not in PROPOSABLE:
        how = ("Call request_recheck with flag_type='MANUAL_TRIAGE'." if decision["outcome"] == "MANUAL_TRIAGE"
               else "Call request_recheck with flag_type='MISSING_VITALS' listing the outstanding inputs.")
        errors.append(_error(f"OUTCOME_{decision['outcome']}", "a priority cannot be proposed for this patient",
                             how, reasons=decision["reasons"], outstanding_inputs=decision["outstanding_inputs"]))
    elif decision["priority"] != priority:
        how = f"Call propose_priority again with priority={decision['priority']} and the same citations."
        if decision["outcome"] == "PROPOSE_AND_RECHECK":
            how += (f" {', '.join(decision['outstanding_inputs'])} not recorded, but the patient is already "
                    f"{decision['priority']} on the available evidence: propose now. The server raises the "
                    "re-check for the missing inputs itself. Do NOT call request_recheck instead.")
        errors.append(_error("PRIORITY_MISMATCH", f"the rules give {decision['priority']}, not {priority}", how,
                             expected=decision["priority"], reasons=decision["reasons"],
                             next_call={"tool": "propose_priority", "priority": decision["priority"]}))

    if errors:
        return CheckResult(ok=False, errors=errors, decision=decision, tews=tews, discriminators=matches)

    return CheckResult(ok=True, decision=decision, tews=tews, discriminators=matches,
                       citations=build_citations(tews, decision, cited, rules))
