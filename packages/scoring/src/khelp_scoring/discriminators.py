"""Deterministic emergency-sign (discriminator) lookup. No model calls."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .rules import RuleSet, load_rules

_ABBREVIATIONS = {
    r"\bc/o\b": " complains of ",
    r"\bh/o\b": " history of ",
    r"\bw/o\b": " without ",
    r"\bs/p\b": " status post ",
}
_CLAUSE_SPLIT = re.compile(r"[,.;:!?\n]+|\bbut\b")
_NEGATION_WINDOW = 4  # tokens before the phrase, within the same clause


@dataclass
class DiscriminatorMatch:
    id: str
    name: str
    priority: str
    matched_phrase: str
    negated: bool
    clause: str
    source: dict[str, Any]
    verified: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalise_text(text: str) -> str:
    t = text.lower()
    for pattern, repl in _ABBREVIATIONS.items():
        t = re.sub(pattern, repl, t)
    t = t.replace("’", "'")
    t = re.sub(r"[-_()\[\]\"*#]+", " ", t)
    return t


def _clauses(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", c).strip() for c in _CLAUSE_SPLIT.split(text) if c.strip()]


def _phrase_regex(phrase: str) -> re.Pattern[str]:
    words = normalise_text(phrase).split()
    return re.compile(r"(?<![\w/])" + r"\s+".join(re.escape(w) for w in words) + r"(?![\w/])")


def _is_negated(clause: str, start: int, cues: list[str]) -> bool:
    before = clause[:start].split()[-_NEGATION_WINDOW:]
    window = " ".join(before)
    return any(re.search(r"(?<!\w)" + re.escape(cue) + r"(?!\w)", window) for cue in cues)


def _find(clauses: list[str], phrases: list[str], cues: list[str]) -> tuple[str, str, bool] | None:
    """Return (phrase, clause, negated) for the best hit: a non-negated hit wins."""
    negated_hit = None
    for clause in clauses:
        for phrase in phrases:
            for m in _phrase_regex(phrase).finditer(clause):
                if not _is_negated(clause, m.start(), cues):
                    return phrase, clause, False
                negated_hit = negated_hit or (phrase, clause, True)
    return negated_hit


def lookup_discriminators(complaint_text: str, rules: RuleSet | None = None) -> list[DiscriminatorMatch]:
    """Match a free-text complaint against the SATS discriminator list.

    Returns every matched sign, including negated ones (flagged `negated=True`
    so a human can see what was ruled out). Only non-negated matches should
    count towards priority.
    """
    rules = rules or load_rules()
    data = rules.discriminators
    cues = data["negation_cues"]
    phrase_sets = data["phrase_sets"]
    clauses = _clauses(normalise_text(complaint_text or ""))

    matches: list[DiscriminatorMatch] = []
    for entry in data["discriminators"]:
        if "all_of" in entry:
            hits = [_find(clauses, phrase_sets[name], cues) for name in entry["all_of"]]
            if any(h is None for h in hits):
                continue
            phrase = " + ".join(h[0] for h in hits)
            clause = " | ".join(dict.fromkeys(h[1] for h in hits))
            negated = any(h[2] for h in hits)
        else:
            hit = _find(clauses, entry["phrases"], cues)
            if hit is None:
                continue
            phrase, clause, negated = hit
        matches.append(DiscriminatorMatch(
            id=entry["id"],
            name=entry["name"],
            priority=entry["priority"],
            matched_phrase=phrase,
            negated=negated,
            clause=clause,
            source=entry["source"],
            verified=bool(entry.get("verified", False)),
        ))
    return matches
