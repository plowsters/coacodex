import math

import pytest

from coa_client_extract.wow_constants import reference_comparison, build_snapshot


def test_reference_comparison_is_anchor_scoped_on_axes():
    entries = [{"rating_id": 10, "level": 60, "value": 14.0},
               {"rating_id": 10, "level": 80, "value": 40.0}]
    anchors = [{"table": "combat_ratings", "rating_id": 10, "level": 60, "expected": 14.0, "tolerance": 0.5},
               {"table": "combat_ratings", "rating_id": 10, "level": 80, "expected": 45.9, "tolerance": 0.5}]
    rc = reference_comparison(entries, anchors, axes=("rating_id", "level"),
                              anchor_set_version="v1", anchor_set_sha256="ab")
    assert rc["scope"] == "anchors" and rc["checked"] == 2 and rc["equal"] == 1 and rc["different"] == 1
    assert rc["status"] == "differs_on_checked_anchors"


def test_build_snapshot_shape_and_rejects_non_finite():
    ok = build_snapshot(client_build="3.3.5a+patch-M", provenance={"backend": "fake", "source_dbcs": {}},
        class_axis={"namespace": "chr_classes", "comparison": "exact", "observed_client_ids": [1]},
        game_tables={"combat_ratings": {"axes": ["rating_id", "level"], "class_indexed": False,
                     "entries": [{"rating_id": 0, "level": 1, "value": 1.0}]}},
        rules={"base_energy": {"value": 100}},
        rating_enum={"version": "cr-3.3.5a-v1", "supported": {"0": "weapon_skill"}},
        power_type_enum={"version": "m1.14c-power-v1", "map": {"0": "mana"}})
    assert ok["schema_version"] == "coa-wow-constants-v1"
    assert set(ok) >= {"schema_version", "client_build", "provenance", "class_axis", "enum_maps",
                       "game_tables", "rules"}
    with pytest.raises(ValueError):
        build_snapshot(client_build="t", provenance={}, class_axis={},
            game_tables={"t": {"axes": ["x"], "class_indexed": False,
                         "entries": [{"x": 0, "value": math.inf}]}},
            rules={}, rating_enum={}, power_type_enum={})
