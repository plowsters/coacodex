# tests/test_e0r1_projection_expansion.py
"""E0R.1 Task 2.2 — the CoA projection (coa-client-spell-projection-v3) is the RICH form: each compact
`raw` cell of the full child is expanded into a canonical field observation (substrate + re-derived decoded
+ proof/promotion claims), and the projection carries NO compact `raw`. The full child stays compact.
`_expand_compact(full.raw[f], policy)` MUST equal `projection.field_observations[f]` exactly, so the
compact child is provably lossless.
"""
from coa_client_extract.spell_layout import load_default_policy
from coa_client_extract.spell_record import (
    iter_spell_records, project_v3_row, _expand_compact, build_field_descriptors,
    PROJECTION_SCHEMA_V3)
from tests._spell_fixtures import spell_dbc, side_views, v2_policy


def _compact_by_id():
    return {r["spell_id"]: r for r in iter_spell_records(
        spell_dbc(), side_views(), policy=v2_policy(),
        provenance={"effective_archive": "patch-T.MPQ"})}


def test_projection_row_is_rich_and_carries_no_raw():
    policy = v2_policy()
    row = project_v3_row(_compact_by_id()[133], policy)
    assert row["schema_version"] == PROJECTION_SCHEMA_V3
    assert "raw" not in row and "field_observations" in row
    pt = row["field_observations"]["power_type"]
    assert pt["raw_u32"] == 3 and pt["decoded"] == {"kind": "int32", "value": 3}
    assert pt["proof"] == {"integrity": "verified", "layout": "verified", "interpretation": "verified"}
    assert pt["promotion"] == "normalized" and pt["policy_ref"].endswith("/power_type")
    assert row["field_observations"]["name"]["resolved"] == "Fireball"


def test_projection_preserves_identity_mechanics_attribution():
    compact = _compact_by_id()[133]
    row = project_v3_row(compact, v2_policy())
    assert row["spell_id"] == compact["spell_id"] and row["name"] == compact["name"]
    assert row["mechanics"] == compact["mechanics"]
    assert row["coa_attribution"] == compact["coa_attribution"]


def test_expand_compact_is_the_cross_child_inverse_for_every_field():
    """E0R.2 T6.2: a v4 cell no longer carries its own pointer, so expansion is handed the field name and
    the policy-derived descriptors — the same two the validators derive. The EQUALITY is unchanged, which
    is the point: the encoding moved, the contract did not."""
    policy = v2_policy()
    descriptors = build_field_descriptors(policy.doc)
    compact = _compact_by_id()[133]
    proj = project_v3_row(compact, policy)
    for f, cell in compact["raw"].items():
        assert _expand_compact(cell, policy, field=f, descriptors=descriptors,
                               row_schema=compact["schema_version"]) == proj["field_observations"][f], f


def test_resolved_join_expands_with_components_and_decoded():
    policy = v2_policy()               # cast_time_ms normalized; spell 133 cast index 2 -> base_ms 1500
    fobs = project_v3_row(_compact_by_id()[133], policy)["field_observations"]
    j = fobs["cast_time_ms"]
    assert j["state"] == "resolved" and j["decoded"] == 1500
    assert set(j["components"]) == {"index", "side_id", "side_value"}
    assert j["components"]["side_value"]["decoded"] == {"kind": "int32", "value": 1500}


def test_index_zero_join_expands_not_applicable():
    j = project_v3_row(_compact_by_id()[805775], v2_policy())["field_observations"]["cast_time_ms"]
    assert j["state"] == "not_applicable" and j["decoded_reason"] == "index_zero"
    assert set(j["components"]) == {"index"} and j["decoded"] is None


def test_absent_null_index_join_expands_without_components():
    # the real default policy has null-index numeric joins (reviewed_ambiguous) -> absent-marker compact.
    policy = load_default_policy()
    cell = {"join_name": "cast_time_ms", "state": "unresolved", "decoded_reason": "not_present",
            "policy_ref": "/tables/Spell/fields/casting_time_index"}
    obs = _expand_compact(cell, policy)
    assert obs["state"] == "unresolved" and "components" not in obs
    assert obs["promotion"] == "raw_only" and obs["proof"]["integrity"] == "verified"
