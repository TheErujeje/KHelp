"""Combine TEWS and discriminators into a SATS priority decision.

Outcomes:
- PROPOSE              priority is fixed by the evidence, even if inputs are missing
- PROPOSE_AND_RECHECK  inputs are missing, but the lower bound is already urgent
                       enough to propose now; vitals still need taking
- RECHECK              missing/implausible inputs could change the priority
- MANUAL_TRIAGE        outside the adult scale (age < 12 or age unknown)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .rules import RuleSet, load_rules, max_priority, priority_rank
from .tews import TewsResult


@dataclass
class Decision:
    outcome: str
    priority: str | None
    priority_low: str | None = None
    priority_high: str | None = None
    tews_priority_rule_ids: list[str] = field(default_factory=list)
    tews_band_ids: list[str] = field(default_factory=list)
    discriminator_ids: list[str] = field(default_factory=list)
    outstanding_inputs: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def tews_priority_rule(total: int, rules: RuleSet | None = None) -> dict[str, Any]:
    rules = rules or load_rules()
    for rule in rules.priority_rules["tews_to_priority"]:
        if total >= rule["min"] and (rule["max"] is None or total <= rule["max"]):
            return rule
    raise ValueError(f"No priority rule covers TEWS total {total}")


def decide(
    tews: TewsResult,
    discriminator_ids: list[str],
    age_years: float | None,
    rules: RuleSet | None = None,
) -> Decision:
    rules = rules or load_rules()

    if age_years is None or age_years < rules.min_age_years:
        why = "age not recorded" if age_years is None else f"age {age_years:g} is under {rules.min_age_years}"
        return Decision(
            outcome="MANUAL_TRIAGE",
            priority=None,
            reasons=[f"{why}; adult TEWS applies only from age {rules.min_age_years}. "
                     "Paediatric triage is out of scope — triage this patient manually."],
        )

    disc_entries = []
    for disc_id in dict.fromkeys(discriminator_ids):
        entry = rules.discriminator(disc_id)
        if entry is None:
            raise ValueError(f"Unknown discriminator id: {disc_id}")
        disc_entries.append(entry)
    disc_priority = max_priority(*(e["priority"] for e in disc_entries))

    low_rule = tews_priority_rule(tews.total_min, rules)
    high_rule = tews_priority_rule(tews.total_max, rules)
    low = max_priority(disc_priority, low_rule["priority"])
    high = max_priority(disc_priority, high_rule["priority"])

    decision = Decision(
        outcome="",
        priority=None,
        priority_low=low,
        priority_high=high,
        tews_priority_rule_ids=list(dict.fromkeys([low_rule["id"], high_rule["id"]])),
        tews_band_ids=[item.band_id for item in tews.breakdown],
        discriminator_ids=[e["id"] for e in disc_entries],
        outstanding_inputs=[u.parameter for u in tews.unresolved],
    )

    if tews.complete:
        decision.reasons.append(f"TEWS {tews.total_known} -> {low_rule['priority']} ({low_rule['id']})")
    else:
        decision.reasons.append(
            f"TEWS between {tews.total_min} and {tews.total_max} with "
            f"{', '.join(decision.outstanding_inputs)} unresolved"
        )
    for e in disc_entries:
        decision.reasons.append(f"Emergency sign {e['name']} -> {e['priority']} ({e['id']})")

    propose_floor = rules.priority_rules["missing_inputs"]["propose_with_missing_at_or_above"]
    if low == high:
        decision.outcome = "PROPOSE"
        decision.priority = low
        if not tews.complete:
            decision.reasons.append("Unresolved inputs cannot change this priority; record them when possible")
    elif priority_rank(low) >= priority_rank(propose_floor):
        decision.outcome = "PROPOSE_AND_RECHECK"
        decision.priority = low
        decision.reasons.append(
            f"Already {low} on available evidence; could rise to {high} — take missing vitals now"
        )
    else:
        decision.outcome = "RECHECK"
        decision.reasons.append(
            f"Priority could be anywhere from {low} to {high}; missing or implausible vitals must be re-taken"
        )
    return decision
