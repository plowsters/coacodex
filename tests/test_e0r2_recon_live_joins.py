"""E0R.2 T3.1: an adjudicated-ambiguous join is still PROBED on every run. Copying the authored verdict
forward means recon cannot notice the day the client makes the join unique — the one thing the hold exists
to catch.

The old branch recorded `pair: None` straight from the policy's `adjudication: "reviewed_ambiguous"` and
returned before touching the side table. That is a quotation of a past review, not an observation of the
client in front of us; it would have reported "ambiguous" forever, including after a patch resolved it.
"""
import struct

from coa_client_extract.recordview import open_view
from coa_client_extract.spell_mechanics import probe_joins, scan_index_candidates
from tests._e0r2_recon_fixtures import SIDE_IDS, _side, ambiguous_backend, unique_backend


def test_an_ambiguous_join_is_scanned_not_asserted():
    probes = probe_joins(*ambiguous_backend())
    cast = probes["casting_time_index"]
    assert cast["scanned"] is True
    assert cast["pair"] is None
    assert len(cast["candidates"]) >= 2
    assert [c["cell"] for c in cast["candidates"]] == sorted(c["cell"] for c in cast["candidates"])
    assert all({"cell", "nonzero_count", "valid_count", "distinct_ids"} == set(c)
               for c in cast["candidates"])
    assert all(isinstance(v, int) and not isinstance(v, bool)
               for c in cast["candidates"] for v in c.values()), "metrics must be integers, not floats"


def test_the_recorded_verdict_and_its_evidence_survive_the_scan():
    # Live measurement replaces the verdict as the SOURCE of "ambiguous"; it does not erase the review
    # that adjudicated it, which is what T3.2's baseline will be anchored to.
    cast = probe_joins(*ambiguous_backend())["casting_time_index"]
    assert cast["adjudication"] == "reviewed_ambiguous"
    assert cast["evidence"]


def test_a_join_that_became_unique_is_recorded_as_unique():
    probes = probe_joins(*unique_backend())
    assert len(probes["casting_time_index"]["candidates"]) == 1


def test_a_missing_side_table_is_distinguishable_from_an_ambiguous_one():
    """Regression: the old path returned before read_effective_file, so the two were identical."""
    backend, root, attach, view, id_to_rec, policy, anchors = ambiguous_backend()
    backend.forget("DBFilesClient\\SpellCastTimes.dbc")
    probe = probe_joins(backend, root, attach, view, id_to_rec, policy, anchors)["casting_time_index"]
    assert probe["scanned"] is False
    assert probe["side_table_missing"] is True
    assert "candidates" not in probe          # nothing was measured, so nothing is claimed


def test_a_value_anchor_join_also_records_whether_it_was_scanned():
    # The two branches produce the same record keys, so a consumer never has to know which path ran to
    # know whether the client was actually read.
    backend, root, attach, view, id_to_rec, policy, _ = ambiguous_backend()
    anchors = {"casting_time_index": {
        "side_table": "SpellCastTimes", "side_id_cell": 0, "side_value_cells": [1],
        "side_value_kind": "int32",
        "anchors": [{"spell_id": 5, "expected_state": "resolved", "expected_value": 500}]}}
    probe = probe_joins(backend, root, attach, view, id_to_rec, policy, anchors)["casting_time_index"]
    assert probe["scanned"] is True and probe["side_table_missing"] is False


# --- scan_index_candidates directly ---

def _view_of(*rows, field_count):
    return open_view(struct.pack("<4sIIII", b"WDBC", len(rows), field_count, field_count * 4, 0)
                     + b"".join(struct.pack("<%dI" % field_count, *r) for r in rows))


def test_the_scan_excludes_cells_that_match_nothing_in_the_side_table():
    _b, _r, _a, view, _i, _p, _an = ambiguous_backend()
    side = open_view(_side([(999999, 1), (999998, 1)]))     # ids present in no Spell cell
    assert scan_index_candidates(view, side) == []


def test_distinct_ids_counts_referenced_side_rows_not_rows_scanned():
    _b, _r, _a, view, _i, _p, _an = ambiguous_backend()
    by_cell = {c["cell"]: c for c in scan_index_candidates(view, open_view(_side(SIDE_IDS)))}
    # Fixture rows are (5,5,71) (71,71,5) (3,3,3): cells 1 and 2 each reference {3, 5, 71}.
    assert by_cell[1] == {"cell": 1, "nonzero_count": 3, "valid_count": 3, "distinct_ids": 3}
    assert by_cell[2]["distinct_ids"] == 3


def test_a_cell_below_minimum_support_never_qualifies():
    # Cell 1 holds exactly ONE nonzero valid id; _MIN_SUPPORT is 2, so it must not survive.
    view = _view_of((900, 5), (901, 0), (902, 0), field_count=2)
    assert scan_index_candidates(view, open_view(_side(SIDE_IDS))) == []
