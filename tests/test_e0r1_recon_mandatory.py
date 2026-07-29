# tests/test_e0r1_recon_mandatory.py
"""E0R.1 Task 1.1: the recon `verified` state machine is self-consistent — every required join is probed,
a unique discovery must be adopted at the authored cell, an ambiguous join may stay null WITH evidence,
and power_type signedness is required for `verified` ONLY if the policy claims a verified interpretation.

E0R.2 T3.2 tightened what "ambiguous" has to show for itself: a bare `pair: None` is no longer enough,
because a join that was never scanned looked identical to one whose ambiguity genuinely persisted. The
helpers below therefore stage a live scan plus the reviewed baseline it agrees with, so these tests keep
exercising the OTHER legs of the state machine. The ambiguity rule itself is tested in
tests/test_e0r2_recon_live_joins.py.
"""
from coa_client_extract.spell_mechanics import _recon_status
from tests._e0r2_recon_fixtures import baseline as make_baseline
from tests._e0r2_recon_fixtures import candidates as make_candidates
from tests._e0r2_recon_fixtures import scanned_probe

_REQUIRED_JOINS = ("casting_time_index", "duration_index", "range_index", "spell_icon_id")
_GOOD_LAYOUT = {"power_type": {"matches_policy": True}, "school_mask": {"matches_policy": True},
                "name": {"matches_policy": True}}
_CANDIDATES = make_candidates((10, 11))
_BASELINE = make_baseline({f: _CANDIDATES for f in _REQUIRED_JOINS})


def _joins_all_ambiguous():
    return {f: scanned_probe(_CANDIDATES) for f in _REQUIRED_JOINS}


def _status(**over):
    base = dict(blocking=[], bound_mismatch=[], layout_proof=_GOOD_LAYOUT, reviewed=True,
                required_joins=_REQUIRED_JOINS, join_pairs=_joins_all_ambiguous(),
                authored_join_cells={}, power_type_interpretation="raw_only", power_type_signed=None,
                ambiguity_baseline=_BASELINE)
    base.update(over)
    return _recon_status(**base)


def test_blocking_is_blocked():
    assert _status(blocking=[{"field": "x"}]) == "blocked"


def test_bound_mismatch_is_review_required():
    assert _status(bound_mismatch=[{"table": "Spell", "field": "sha256"}]) == "review_required"


def test_unmatched_scalar_anchor_is_review_required():
    bad = {**_GOOD_LAYOUT, "power_type": {"matches_policy": False}}
    assert _status(layout_proof=bad) == "review_required"


def test_a_required_join_not_probed_is_review_required():
    jp = _joins_all_ambiguous()
    del jp["spell_icon_id"]                       # icon join never probed
    assert _status(join_pairs=jp) == "review_required"


def test_unique_discovery_not_adopted_is_review_required():
    # a uniquely-discovered join cell the policy has NOT adopted must NOT verify.
    jp = _joins_all_ambiguous()
    jp["casting_time_index"] = {"pair": (12, 1), "winners": [(12, 1)]}   # unique at index cell 12
    assert _status(join_pairs=jp, authored_join_cells={}) == "review_required"


def test_unique_discovery_at_a_different_cell_than_authored_is_review_required():
    jp = _joins_all_ambiguous()
    jp["casting_time_index"] = {"pair": (12, 1), "winners": [(12, 1)]}
    assert _status(join_pairs=jp, authored_join_cells={"casting_time_index": 99}) == "review_required"


def test_ambiguous_joins_with_evidence_can_verify():
    # every join probed + ambiguous (recorded) + power_type raw_only -> verified (no signedness needed).
    assert _status() == "verified"


def test_unique_adopted_joins_verify():
    jp = _joins_all_ambiguous()
    jp["casting_time_index"] = {"pair": (12, 1), "winners": [(12, 1)]}
    assert _status(join_pairs=jp, authored_join_cells={"casting_time_index": 12}) == "verified"


def test_power_type_verified_interpretation_requires_signedness():
    assert _status(power_type_interpretation="verified", power_type_signed=None) == "review_required"
    assert _status(power_type_interpretation="verified", power_type_signed=False) == "review_required"
    assert _status(power_type_interpretation="verified", power_type_signed=True) == "verified"


def test_power_type_rawonly_verifies_without_signedness():
    # no_static_anchor is acceptable when the policy declares power_type raw_only/unproven.
    assert _status(power_type_interpretation="raw_only", power_type_signed=None) == "verified"
