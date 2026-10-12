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


def test_numeric_bands_are_contiguous():
    for name, spec in load_rules().parameters.items():
        if spec["kind"] != "numeric":
            continue
        bands = spec["bands"]
        assert "lower" not in bands[0] and "upper" not in bands[-1], name
        for a, b in zip(bands, bands[1:]):
            assert a["upper"] == b["lower"], f"{name}: gap between {a['id']} and {b['id']}"


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
