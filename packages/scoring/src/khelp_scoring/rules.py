"""Load the SATS rule YAML files (sats/*.yaml)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PRIORITY_ORDER = ("GREEN", "YELLOW", "ORANGE", "RED")


def priority_rank(priority: str) -> int:
    return PRIORITY_ORDER.index(priority)


def max_priority(*priorities: str | None) -> str | None:
    present = [p for p in priorities if p is not None]
    return max(present, key=priority_rank) if present else None


@dataclass(frozen=True)
class RuleSet:
    tews: dict[str, Any]
    discriminators: dict[str, Any]
    priority_rules: dict[str, Any]
    sats_dir: Path

    @property
    def parameters(self) -> dict[str, Any]:
        return self.tews["parameters"]

    @property
    def min_age_years(self) -> int:
        return self.tews["applies_to"]["min_age_years"]

    def target(self, priority: str) -> dict[str, Any]:
        """SATS target time to be seen for a priority (manual p.7, Table 3)."""
        return next(t for t in self.priority_rules["target_minutes"] if t["priority"] == priority)

    def discriminator(self, disc_id: str) -> dict[str, Any] | None:
        for entry in self.discriminators["discriminators"]:
            if entry["id"] == disc_id:
                return entry
        return None

    def all_entries(self) -> list[dict[str, Any]]:
        """Every rule entry that carries a `source` and `verified` field."""
        entries: list[dict[str, Any]] = []
        for param in self.parameters.values():
            entries.extend(param["bands"])
        entries.extend(self.discriminators["discriminators"])
        entries.extend(self.priority_rules["tews_to_priority"])
        entries.extend(self.priority_rules.get("target_minutes", []))
        entries.append(self.priority_rules["missing_inputs"])
        return entries

    def unverified_entries(self) -> list[dict[str, Any]]:
        """SATS entries not yet checked against the manual (project rules are not SATS)."""
        return [e for e in self.all_entries()
                if e.get("kind") != "project_rule" and not e.get("verified", False)]


def _default_sats_dir() -> Path:
    env = os.environ.get("KHELP_SATS_DIR")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "sats"
        if (candidate / "tews.yaml").exists():
            return candidate
    raise FileNotFoundError("Could not find sats/tews.yaml; set KHELP_SATS_DIR")


@lru_cache(maxsize=4)
def load_rules(sats_dir: str | Path | None = None) -> RuleSet:
    path = Path(sats_dir) if sats_dir else _default_sats_dir()

    def read(name: str) -> dict[str, Any]:
        with open(path / name, encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    return RuleSet(
        tews=read("tews.yaml"),
        discriminators=read("discriminators.yaml"),
        priority_rules=read("priority_rules.yaml"),
        sats_dir=path,
    )
