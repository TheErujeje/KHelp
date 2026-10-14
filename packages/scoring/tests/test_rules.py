import os
import warnings

import pytest

from khelp_scoring import load_rules
from khelp_scoring.unverified import report


def test_every_entry_has_source_and_verified_flag():
    for entry in load_rules().all_entries():
        assert entry.get("id"), entry
        assert {"document", "edition", "location"} <= set(entry["source"]), entry["id"]
        assert isinstance(entry.get("verified"), bool), entry["id"]


def test_ids_are_unique():
    ids = [e["id"] for e in load_rules().all_entries()]
    assert len(ids) == len(set(ids))


def test_numeric_bands_cover_every_value_exactly_once():
    from khelp_scoring.tews import band_contains
    for name, spec in load_rules().parameters.items():
        if spec["kind"] != "numeric":
            continue
        lo, hi = spec["plausible"]["min"], spec["plausible"]["max"]
        step = 1 if spec.get("integer") else 0.01
        value = lo
        while value <= hi:
            hits = [b["id"] for b in spec["bands"] if band_contains(b, round(value, 2))]
            assert len(hits) == 1, f"{name}={value}: {hits}"
            value += step


def test_all_sats_entries_cite_a_manual_page():
    for entry in load_rules().all_entries():
        if entry.get("kind") == "project_rule":
            continue
        assert entry["verified"] is True, entry["id"]
        assert entry["source"]["location"].startswith("p."), entry["id"]


def test_unverified_rules_report():
    """Lists every entry still to be checked against the SATS manual.

    Run with `-s` to see the list. Set KHELP_REQUIRE_VERIFIED=1 to make this fail
    while anything is unverified (e.g. before a release).
    """
    rows = report()
    print("\nUNVERIFIED SATS RULE ENTRIES:\n" + "\n".join(rows) + f"\n{len(rows)} unverified")
    if rows:
        warnings.warn(f"{len(rows)} SATS rule entries are unverified", stacklevel=1)
    if os.environ.get("KHELP_REQUIRE_VERIFIED") == "1":
        pytest.fail(f"{len(rows)} unverified SATS rule entries")
