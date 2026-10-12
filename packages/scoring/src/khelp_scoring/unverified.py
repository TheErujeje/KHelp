"""List SATS rule entries not yet checked against the manual.

    uv run python -m khelp_scoring.unverified
"""

from __future__ import annotations

from .rules import load_rules


def report() -> list[str]:
    lines = []
    for entry in load_rules().unverified_entries():
        src = entry.get("source", {})
        label = entry.get("name") or entry.get("label") or ""
        lines.append(f"{entry['id']:<40} {label:<45} {src.get('document')} — {src.get('location')}")
    return lines


if __name__ == "__main__":
    rows = report()
    print("\n".join(rows))
    print(f"\n{len(rows)} unverified entries")
