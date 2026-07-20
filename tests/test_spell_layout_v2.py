# tests/test_spell_layout_v2.py
import pytest
from coa_client_extract.spell_layout import load_spell_policy, SpellPolicyError, compute_policy_sha256


def _f(cell, kind, promo="normalized", layout="verified", interp="verified"):
    return {"cell": cell, "kind": kind, "layout": layout, "interpretation": interp,
            "promotion": promo, "evidence": "fixture"}


def _v2():
    tables = {
        "Spell": {"expected_field_count": 234, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32"), "power_type": _f(41, "int32"),
            "casting_time_index": _f(28, "uint32", promo="normalized")}},
        "SpellCastTimes": {"expected_field_count": 4, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32", promo="normalized"),
            "base_ms": _f(1, "int32", promo="normalized")}},
    }
    joins = {"cast_time_ms": {"index_field": "casting_time_index", "side_table": "SpellCastTimes",
                              "side_value_field": "base_ms", "promotion": "normalized"}}
    enum = {"power_types": [-2, 0, 1, 2, 3, 4, 5, 6], "school_bits": [1, 2, 4, 8, 16, 32, 64]}
    enum["sha256"] = compute_policy_sha256(enum)
    anchor = {"spells": [{"id": 133, "name": "Fireball", "power_type": 0, "school_mask": 4}]}
    anchor["sha256"] = compute_policy_sha256(anchor)
    bound = {"client_build": "3.3.5a+patch-CZZ", "expected_absent": ["SpellEffect"], "tables": {
        "Spell": {"sha256": "a" * 64, "header": {"magic": "WDBC", "record_count": 1, "field_count": 234,
                  "record_size": 936, "string_block_size": 10},
                  "source": {"member": "DBFilesClient\\Spell.dbc", "effective_archive": "patch-T.MPQ",
                             "patch_chain": []}},
        "SpellCastTimes": {"sha256": "b" * 64, "header": {"magic": "WDBC", "record_count": 1, "field_count": 4,
                           "record_size": 16, "string_block_size": 0},
                           "source": {"member": "DBFilesClient\\SpellCastTimes.dbc",
                                      "effective_archive": "patch-T.MPQ", "patch_chain": []}}}}
    p = {"schema_version": "coa-spell-layout-v2", "reviewed": True, "bound": bound,
         "required_tables": ["Spell", "SpellCastTimes"], "expected_absent": ["SpellEffect"],
         "enum_policy": enum, "anchor_set": anchor, "tables": tables, "joins": joins}
    p["sha256"] = compute_policy_sha256(p)
    return p


def test_v2_loads_join_promotion_and_key_uniqueness():
    pol = load_spell_policy(_v2())
    assert pol.schema_version == "coa-spell-layout-v2"
    assert pol.joins["cast_time_ms"].promotion == "normalized"
    assert pol.tables["Spell"]["key_cell"] == 0 and pol.tables["Spell"]["unique"] is True
    assert pol.bound["tables"]["Spell"]["header"]["field_count"] == 234


def test_v2_rejects_flat_bound_shape():
    p = _v2(); p["bound"] = {"client_build": "x", "source_dbc_sha256": {"Spell": "a" * 64}}
    p["sha256"] = compute_policy_sha256(p)
    with pytest.raises(SpellPolicyError, match="bound.tables"):
        load_spell_policy(p)


def test_v2_rejects_normalized_join_with_raw_only_component():
    p = _v2()
    p["tables"]["SpellCastTimes"]["fields"]["base_ms"]["promotion"] = "raw_only"
    p["sha256"] = compute_policy_sha256(p)
    with pytest.raises(SpellPolicyError, match="raw_only component"):
        load_spell_policy(p)


def test_v2_rejects_bound_table_set_mismatch():
    p = _v2(); del p["bound"]["tables"]["SpellCastTimes"]   # bound no longer covers every required table
    p["sha256"] = compute_policy_sha256(p)
    with pytest.raises(SpellPolicyError, match="bound.tables"):
        load_spell_policy(p)


def test_v1_schema_is_rejected():
    p = _v2(); p["schema_version"] = "coa-spell-layout-v1"; p["sha256"] = compute_policy_sha256(p)
    with pytest.raises(SpellPolicyError, match="coa-spell-layout-v2"):
        load_spell_policy(p)
