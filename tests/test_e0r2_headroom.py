"""E0R.2 T8.2: E0R's exit condition is "substantial E1 headroom".

97.42% of ceiling is not headroom. E1 adds an operands sidecar and the CoA mechanical dependency
closure to this same generation, so a milestone that lands at the edge of its budget has not left room
for the milestone it exists to enable — it has just deferred the breach.

Raising the ceiling is not reducing the artifact, which is why the denominator is pinned here too: a
gate whose threshold can be met by inflating what it divides by measures nothing.

This test lands in the SAME commit as the record it reads. Committing it earlier would have put a
knowingly-red test into history.
"""
from __future__ import annotations

import json
from pathlib import Path

RECORD = Path(__file__).resolve().parents[1] / "reports/client_extract/coa_e0r_acceptance_summary.json"
TARGET = 0.75
# The reviewed whole-generation ceiling (512 MiB), pinned so the gate cannot be satisfied by moving it.
REVIEWED_CEILING = 536_870_912


def _budget() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))["budget"]


def test_the_published_generation_leaves_e1_headroom():
    budget = _budget()
    used = budget["whole_generation_bytes"] / budget["ceilings"]["max_whole_generation_bytes"]
    assert used <= TARGET, f"generation uses {used:.1%} of ceiling; E1 needs room below {TARGET:.0%}"


def test_the_ceiling_the_headroom_is_measured_against_is_the_reviewed_one():
    """The denominator is half the gate. Without this, "reduce the artifact" and "raise the ceiling"
    are indistinguishable to the test."""
    assert _budget()["ceilings"]["max_whole_generation_bytes"] == REVIEWED_CEILING


def test_the_record_measured_the_generation_rather_than_asserting_it():
    """`within_budget` is a verdict the publisher recomputed from the staged children (T2.4); a record
    that carried no measured byte count would pass the ratio check vacuously."""
    budget = _budget()
    assert isinstance(budget["whole_generation_bytes"], int) and budget["whole_generation_bytes"] > 0
    assert budget["within_budget"] is True
    assert budget["breach"] == []
