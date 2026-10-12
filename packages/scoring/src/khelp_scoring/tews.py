"""Deterministic SATS adult TEWS calculation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .rules import RuleSet, load_rules
from .vitals import VitalIssue, normalise_vitals


@dataclass
class TewsItem:
    parameter: str
    label: str
    value: Any
    unit: str | None
    band_id: str
    band_label: str
    points: int
    source: dict[str, Any]
    verified: bool


@dataclass
class UnresolvedInput:
    parameter: str
    label: str
    min_points: int
    max_points: int


@dataclass
class TewsResult:
    total_known: int
    total_min: int
    total_max: int
    complete: bool
    breakdown: list[TewsItem] = field(default_factory=list)
    unresolved: list[UnresolvedInput] = field(default_factory=list)
    issues: list[VitalIssue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def total(self) -> int | None:
        return self.total_known if self.complete else None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total"] = self.total
        return data


def _find_band(spec: dict[str, Any], value: Any) -> dict[str, Any] | None:
    for band in spec["bands"]:
        if spec["kind"] == "categorical":
            if band["value"] == value:
                return band
        else:
            lower, upper = band.get("lower"), band.get("upper")
            if (lower is None or value >= lower) and (upper is None or value < upper):
                return band
    return None


def compute_tews(raw_vitals: dict[str, Any], rules: RuleSet | None = None) -> TewsResult:
    rules = rules or load_rules()
    norm = normalise_vitals(raw_vitals, rules)

    breakdown: list[TewsItem] = []
    unresolved: list[UnresolvedInput] = []
    for name, spec in rules.parameters.items():
        points_range = [b["points"] for b in spec["bands"]]
        value = norm.values.get(name)
        band = _find_band(spec, value) if value is not None else None
        if band is None:
            unresolved.append(UnresolvedInput(name, spec["label"], min(points_range), max(points_range)))
            continue
        breakdown.append(TewsItem(
            parameter=name,
            label=spec["label"],
            value=value,
            unit=spec.get("unit"),
            band_id=band["id"],
            band_label=band["label"],
            points=band["points"],
            source=band["source"],
            verified=bool(band.get("verified", False)),
        ))

    known = sum(item.points for item in breakdown)
    return TewsResult(
        total_known=known,
        total_min=known + sum(u.min_points for u in unresolved),
        total_max=known + sum(u.max_points for u in unresolved),
        complete=not unresolved,
        breakdown=breakdown,
        unresolved=unresolved,
        issues=norm.issues,
        notes=norm.notes,
        extras=norm.extras,
    )
