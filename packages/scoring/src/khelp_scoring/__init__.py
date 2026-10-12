"""Deterministic SATS scoring for KHelp. No model calls live here."""

from .discriminators import DiscriminatorMatch, lookup_discriminators
from .priority import Decision, decide, tews_priority_rule
from .rules import PRIORITY_ORDER, RuleSet, load_rules, max_priority, priority_rank
from .tews import TewsResult, compute_tews

__all__ = [
    "PRIORITY_ORDER",
    "Decision",
    "DiscriminatorMatch",
    "RuleSet",
    "TewsResult",
    "compute_tews",
    "decide",
    "load_rules",
    "lookup_discriminators",
    "max_priority",
    "priority_rank",
    "tews_priority_rule",
]
