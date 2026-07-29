"""E0R.2 T3.1: an adjudicated-ambiguous join is still PROBED on every run. Copying the authored verdict
forward means recon cannot notice the day the client makes the join unique — the one thing the hold exists
to catch.

The old branch recorded `pair: None` straight from the policy's `adjudication: "reviewed_ambiguous"` and
returned before touching the side table. That is a quotation of a past review, not an observation of the
client in front of us; it would have reported "ambiguous" forever, including after a patch resolved it.
"""
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from coa_client_extract.recordview import open_view
from coa_client_extract.spell_mechanics import (SCAN_ALGORITHM, SCAN_THRESHOLDS, _recon_status,
                                                ambiguity_agrees, candidates_digest, probe_joins,
                                                scan_index_candidates)
from tests._e0r2_recon_fixtures import SIDE_IDS, _side, ambiguous_backend, scanned_probe, unique_backend
from tests._e0r2_recon_fixtures import baseline as make_baseline
from tests._e0r2_recon_fixtures import candidates as make_candidates


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


# =====================================================================================================
# E0R.2 T3.2 — the reviewed ambiguity is a hash-bound baseline, not a count.
#
# `pair is None` was the whole test. A join that was never scanned, a join whose candidate cells were
# replaced wholesale, and a join whose ambiguity genuinely persisted all produced the same `verified`.
# Accepting "any candidate set of size >= 2" would be barely better: {10,11} -> {90,91} keeps the count
# and replaces the ambiguity outright.
# =====================================================================================================
_FIELD = "casting_time_index"
_GOOD_LAYOUT = {"power_type": {"matches_policy": True}, "school_mask": {"matches_policy": True},
                "name": {"matches_policy": True}}


def _status(*, scanned_cells=(10, 11), baseline_cells=(10, 11), probe=None, baseline=None,
            scanned_metrics=None, scan_thresholds=None, baseline_thresholds=None, algorithm=None):
    """One ambiguous join, scanned live, compared against a reviewed baseline. Every other leg of the
    state machine is held clean so the verdict is about the ambiguity and nothing else."""
    live = make_candidates(scanned_cells, **(scanned_metrics or {}))
    if probe is None:
        probe = scanned_probe(live, thresholds=scan_thresholds, algorithm=algorithm)
    if baseline is None:
        baseline = make_baseline({_FIELD: make_candidates(baseline_cells)},
                                 thresholds=baseline_thresholds)
    return _recon_status(
        blocking=[], bound_mismatch=[], layout_proof=_GOOD_LAYOUT, reviewed=True,
        required_joins=(_FIELD,), join_pairs={_FIELD: probe}, authored_join_cells={},
        power_type_interpretation="raw_only", power_type_signed=None,
        ambiguity_baseline=baseline)


def test_an_exactly_matching_baseline_verifies():
    assert _status(scanned_cells=(10, 11), baseline_cells=(10, 11)) == "verified"


def test_a_join_whose_candidate_SET_changed_forces_review():
    """Same count, different cells — the ambiguity did not survive, it was replaced."""
    assert _status(scanned_cells=(90, 91), baseline_cells=(10, 11)) == "review_required"


def test_a_join_whose_metrics_drifted_forces_review():
    assert _status(scanned_metrics={"distinct_ids": 12}) == "review_required"


def test_a_join_that_collapsed_to_one_candidate_forces_review():
    # The case the whole hold exists for: the client resolved the join and a human must adopt it.
    assert _status(scanned_cells=(10,), baseline_cells=(10, 11)) == "review_required"


def test_a_join_that_gained_a_candidate_forces_review():
    assert _status(scanned_cells=(10, 11, 12), baseline_cells=(10, 11)) == "review_required"


def test_an_unscanned_ambiguous_join_forces_review():
    """The exact 02e0b7c behaviour: pair=None with no machine evidence read as verified."""
    assert _status(probe={"pair": None, "adjudication": "reviewed_ambiguous"}) == "review_required"


def test_an_ambiguous_join_with_no_reviewed_baseline_forces_review():
    # A baseline block that simply has no entry for this join, and no baseline block at all.
    assert _status(baseline={"scan_algorithm": SCAN_ALGORITHM, "thresholds": dict(SCAN_THRESHOLDS),
                             "joins": {}}) == "review_required"
    assert _status(baseline={}) == "review_required"


def test_a_scan_run_under_different_thresholds_forces_review():
    assert _status(scan_thresholds={**SCAN_THRESHOLDS, "min_distinct": 5}) == "review_required"


def test_a_scan_run_under_a_different_algorithm_forces_review():
    assert _status(algorithm="fk_validity_v2") == "review_required"


def test_a_side_table_that_vanished_forces_review():
    gone = {"table": "SpellCastTimes", "pair": None, "winners": [], "scanned": False,
            "side_table_missing": True, "adjudication": "reviewed_ambiguous"}
    assert _status(probe=gone) == "review_required"


# --- ambiguity_agrees reports WHY, so a recon report is readable ---

def test_agreement_reports_the_specific_disagreement():
    live = make_candidates((90, 91))
    base = make_baseline({_FIELD: make_candidates((10, 11))})["joins"][_FIELD]
    base["scan_algorithm"], base["thresholds"] = SCAN_ALGORITHM, dict(SCAN_THRESHOLDS)
    assert "digest" in ambiguity_agrees(scanned_probe(live), base)
    assert ambiguity_agrees(scanned_probe(make_candidates((10, 11))), base) is None


def test_a_baseline_whose_digest_disagrees_with_its_own_candidates_is_rejected():
    """The digest alone would be enough to compare; checking the list too catches a baseline that was
    hand-edited on one side only — which would otherwise pass review looking like it says something
    other than what it enforces."""
    live = make_candidates((10, 11))
    base = {"scan_algorithm": SCAN_ALGORITHM, "thresholds": dict(SCAN_THRESHOLDS),
            "candidates": make_candidates((10, 11, 12)), "digest": candidates_digest(live)}
    assert ambiguity_agrees(scanned_probe(live), base) == \
        "baseline candidates disagree with the baseline digest"


def test_the_digest_is_stable_under_key_order_and_int_typing():
    a = [{"cell": 10, "nonzero_count": 5, "valid_count": 5, "distinct_ids": 3}]
    b = [{"distinct_ids": 3, "valid_count": 5, "nonzero_count": 5, "cell": 10}]
    assert candidates_digest(a) == candidates_digest(b)


def test_the_recorded_thresholds_are_integers_only():
    # Floats in a hashed structure digest differently across platforms and across Python/Node.
    assert all(isinstance(v, int) and not isinstance(v, bool) for v in SCAN_THRESHOLDS.values())
    assert set(SCAN_THRESHOLDS) == {"min_support", "min_distinct", "valid_num", "valid_den"}


# --- the baseline is validated where it is AUTHORED, not only where it is used ---

def _policy_with_baseline(block):
    """The committed policy plus an ambiguity_baseline, rehashed so the load reaches the new check."""
    import copy
    import json as _json
    from pathlib import Path as _Path

    from coa_client_extract.spell_layout import compute_policy_sha256

    doc = copy.deepcopy(_json.loads(
        (_Path(__file__).resolve().parents[1] / "coa_client_extract/data/spell_layout_v2.json")
        .read_text(encoding="utf-8")))
    doc["ambiguity_baseline"] = block
    doc.pop("sha256", None)
    doc["sha256"] = compute_policy_sha256(doc)
    return doc


def test_a_well_formed_baseline_loads():
    from coa_client_extract.spell_layout import load_spell_policy
    pol = load_spell_policy(_policy_with_baseline(make_baseline({_FIELD: make_candidates((10, 11))})))
    assert pol.doc["ambiguity_baseline"]["joins"][_FIELD]["digest"]


def test_a_baseline_whose_digest_does_not_match_its_candidates_is_rejected_at_load():
    from coa_client_extract.spell_layout import SpellPolicyError, load_spell_policy
    block = make_baseline({_FIELD: make_candidates((10, 11))})
    block["joins"][_FIELD]["digest"] = "0" * 64
    with pytest.raises(SpellPolicyError, match="does not match its own candidates"):
        load_spell_policy(_policy_with_baseline(block))


def test_a_baseline_naming_a_field_that_is_not_a_join_index_is_rejected():
    from coa_client_extract.spell_layout import SpellPolicyError, load_spell_policy
    block = make_baseline({"not_an_index_field": make_candidates((10, 11))})
    with pytest.raises(SpellPolicyError, match="not an index field"):
        load_spell_policy(_policy_with_baseline(block))


def test_a_baseline_with_float_metrics_is_rejected():
    from coa_client_extract.spell_layout import SpellPolicyError, load_spell_policy
    block = make_baseline({_FIELD: make_candidates((10, 11))})
    block["joins"][_FIELD]["candidates"][0]["distinct_ids"] = 41.0
    block["joins"][_FIELD]["digest"] = candidates_digest(block["joins"][_FIELD]["candidates"])
    with pytest.raises(SpellPolicyError, match="must be a non-negative int"):
        load_spell_policy(_policy_with_baseline(block))


def test_a_baseline_with_unsorted_candidates_is_rejected():
    from coa_client_extract.spell_layout import SpellPolicyError, load_spell_policy
    block = make_baseline({_FIELD: make_candidates((10, 11))})
    block["joins"][_FIELD]["candidates"].reverse()
    block["joins"][_FIELD]["digest"] = candidates_digest(block["joins"][_FIELD]["candidates"])
    with pytest.raises(SpellPolicyError, match="sorted by cell"):
        load_spell_policy(_policy_with_baseline(block))


def test_a_baseline_with_float_thresholds_is_rejected():
    from coa_client_extract.spell_layout import SpellPolicyError, load_spell_policy
    block = make_baseline({_FIELD: make_candidates((10, 11))})
    block["thresholds"]["valid_num"] = 99.0
    with pytest.raises(SpellPolicyError, match="thresholds.valid_num must be a positive int"):
        load_spell_policy(_policy_with_baseline(block))


# --- end to end: policy -> thresholds -> live scan -> status ---

def test_recon_compares_the_policy_baseline_against_a_live_client_scan():
    """The integration the unit tests cannot prove: `recon_spell_mechanics` reads the baseline out of
    the policy, scans the CLIENT under the baseline's own thresholds, and records whether the two agree.

    The verdict COUPLING (disagreement => review_required) is `_recon_status`'s job and is tested
    directly above; this stub client has other blocking findings, and `blocked` outranks everything."""
    from coa_client_extract.recordview import open_view as _open
    from coa_client_extract.spell_mechanics import recon_spell_mechanics, scan_index_candidates
    from tests._e0r2_recon_fixtures import Backend, _wdbc

    # A 3-cell Spell table whose cells 1 and 2 both hold valid SpellCastTimes ids: ambiguous by
    # construction, and the anchors sit at the cells the stub policy declares.
    rows = [(5, 5, 71), (71, 71, 5), (3, 3, 3)]
    spell_bytes = _wdbc(rows, 3)
    side_bytes = _wdbc([(5, 500), (71, 7100), (3, 300)], 2)
    backend = Backend({"DBFilesClient\\Spell.dbc": [(Path("patch-T.MPQ"), spell_bytes)],
                       "DBFilesClient\\SpellCastTimes.dbc": [(Path("patch-T.MPQ"), side_bytes)]})
    observed = scan_index_candidates(_open(spell_bytes), _open(side_bytes), side_id_cell=0)
    assert len(observed) >= 2, "the fixture must actually be ambiguous"

    def run(block):
        policy = SimpleNamespace(
            sha256="p", reviewed=True, bound=None,
            columns={"power_type": 1, "school_mask": 2, "name": None},
            enum_policy={"power_types": {0, 3, 5, 71}, "school_bits": {1, 2, 4, 8, 16, 32, 64}},
            required_tables=["Spell", "SpellCastTimes"], expected_absent=[],
            tables={"Spell": {"key_cell": 0, "unique": True, "expected_field_count": 3},
                    "SpellCastTimes": {"key_cell": 0, "unique": True, "expected_field_count": 2}},
            index_fields={_FIELD: "SpellCastTimes"}, doc={"ambiguity_baseline": block})
        return recon_spell_mechanics(
            backend, Path("c.MPQ"), (Path("patch-T.MPQ"),), spell_policy=policy,
            anchors=[{"id": 5, "power_type": 5, "school_mask": 71, "name": None}],
            budget={"artifact_size_mb": 4096, "peak_rss_mb": 16384, "elapsed_s": 3600},
            extractor_commit="e0r2", client_build="fixture",
            join_value_anchors={_FIELD: {"side_table": "SpellCastTimes", "side_id_cell": 0,
                                         "adjudication": "reviewed_ambiguous", "evidence": "fixture"}})

    matching = run(make_baseline({_FIELD: observed}))
    assert matching["join_pairs"][_FIELD]["candidates"] == observed
    assert matching["ambiguity_agreement"] == {_FIELD: None}

    drifted = run(make_baseline({_FIELD: make_candidates((90, 91))}))
    assert "digest" in drifted["ambiguity_agreement"][_FIELD]

    # The thresholds the scan ran under came from the POLICY, not from the module defaults: a baseline
    # declaring a stricter min_distinct changes what the same client yields.
    strict = run(make_baseline({_FIELD: observed}, thresholds={**SCAN_THRESHOLDS, "min_distinct": 99}))
    assert strict["join_pairs"][_FIELD]["candidates"] == []
    assert strict["join_pairs"][_FIELD]["scan_thresholds"]["min_distinct"] == 99


# --- the committed policy's baseline, and the prose that describes it ---

def _committed_policy():
    import json as _json
    from pathlib import Path as _Path
    return _json.loads((_Path(__file__).resolve().parents[1]
                        / "coa_client_extract/data/spell_layout_v2.json").read_text(encoding="utf-8"))


def test_the_committed_policy_carries_a_baseline_for_every_ambiguous_join():
    doc = _committed_policy()
    ambiguous = {name for name, spec in doc["anchor_set"]["joins"].items()
                 if spec.get("adjudication") == "reviewed_ambiguous"}
    assert ambiguous, "the fixture assumption changed: no join is adjudicated ambiguous"
    assert set(doc["ambiguity_baseline"]["joins"]) == ambiguous


def test_the_reviewed_prose_agrees_with_the_machine_authored_baseline():
    """The bug this task's baseline caught on the real client: the reviewed evidence for
    `duration_index` claimed 33 candidate columns where the client yields 34 — under BOTH the old float
    predicate and the new integer one, with zero difference between them. A count written into prose is
    not a baseline, and nothing was checking it. Now the two must agree."""
    doc = _committed_policy()
    for field, entry in doc["ambiguity_baseline"]["joins"].items():
        prose = doc["anchor_set"]["joins"][field]["evidence"]
        assert f"yields {len(entry['candidates'])} candidate columns" in prose, field


def test_the_committed_baseline_digests_match_its_own_candidates():
    doc = _committed_policy()
    for field, entry in doc["ambiguity_baseline"]["joins"].items():
        assert entry["digest"] == candidates_digest(entry["candidates"]), field


def test_the_committed_baseline_was_produced_by_the_shipped_scan():
    doc = _committed_policy()
    assert doc["ambiguity_baseline"]["scan_algorithm"] == SCAN_ALGORITHM
    assert doc["ambiguity_baseline"]["thresholds"] == SCAN_THRESHOLDS


def test_the_committed_lock_matches_the_committed_policy():
    import json as _json
    from pathlib import Path as _Path
    lock = _json.loads((_Path(__file__).resolve().parents[1]
                        / "coa_scraper/config/spell_layout.lock.json").read_text(encoding="utf-8"))
    assert lock["sha256"] == _committed_policy()["sha256"]
