import copy

import pytest

from coa_client_extract.spell_layout import (
    SCHEMA, SpellPolicyError, compute_policy_sha256, load_spell_policy, load_default_policy,
)


def _hdr(field_count, record_size):
    return {"magic": "WDBC", "record_count": 1, "field_count": field_count,
            "record_size": record_size, "string_block_size": 0}


def _src(member):
    return {"member": member, "effective_archive": "patch-CZZ.MPQ", "patch_chain": []}


def _valid_payload() -> dict:
    enum = {"power_types": [-2, 0, 1, 2, 3, 4, 5, 6], "school_bits": [1, 2, 4, 8, 16, 32, 64]}
    enum["sha256"] = compute_policy_sha256({"power_types": enum["power_types"],
                                            "school_bits": enum["school_bits"], "sha256": None})
    spells = [{"id": 133, "name": "Fireball", "power_type": 0, "school_mask": 4},
              {"id": 78, "name": "Heroic Strike", "power_type": 1, "school_mask": 1}]
    anchor_set = {"spells": spells}
    anchor_set["sha256"] = compute_policy_sha256({"spells": spells, "sha256": None})
    p = {
        "schema_version": SCHEMA,
        "reviewed": True,
        "bound": {"client_build": "3.3.5a+patch-CZZ", "expected_absent": ["SpellEffect"], "tables": {
            "Spell": {"sha256": "a" * 64, "header": _hdr(234, 936), "source": _src("DBFilesClient\\Spell.dbc")},
            "SpellCastTimes": {"sha256": "b" * 64, "header": _hdr(4, 16),
                               "source": _src("DBFilesClient\\SpellCastTimes.dbc")}}},
        "required_tables": ["Spell", "SpellCastTimes"],
        "expected_absent": ["SpellEffect"],
        "enum_policy": enum,
        "anchor_set": anchor_set,
        "tables": {
            "Spell": {"expected_field_count": 234, "key_cell": 0, "unique": True, "fields": {
                "id": {"cell": 0, "kind": "uint32", "layout": "verified",
                       "interpretation": "verified", "promotion": "normalized", "evidence": "id anchor"},
                "name": {"cell": 136, "kind": "string", "layout": "verified",
                         "interpretation": "verified", "promotion": "normalized", "evidence": "name anchor"},
                "power_type": {"cell": 41, "kind": "int32", "layout": "verified",
                               "interpretation": "verified", "promotion": "normalized", "evidence": "7-spell anchor"},
                "school_mask": {"cell": 225, "kind": "uint32", "layout": "verified",
                                "interpretation": "verified", "promotion": "normalized", "evidence": "7-spell anchor"},
                "description": {"cell": 170, "kind": "string", "layout": "verified",
                                "interpretation": "reference", "promotion": "raw_only", "evidence": "Eviscerate 2098"},
                "casting_time_index": {"cell": None, "kind": "uint32", "layout": "unproven",
                                       "interpretation": "unproven", "promotion": "raw_only", "evidence": "recon-pending"},
            }},
            "SpellCastTimes": {"expected_field_count": 4, "key_cell": 0, "unique": True, "fields": {
                "id": {"cell": 0, "kind": "uint32", "layout": "verified",
                       "interpretation": "verified", "promotion": "raw_only", "evidence": "id col"},
                "base_ms": {"cell": 1, "kind": "int32", "layout": "unproven",
                            "interpretation": "unproven", "promotion": "raw_only", "evidence": "recon-pending"},
            }},
        },
        "joins": {
            "cast_time_ms": {"index_field": "casting_time_index", "side_table": "SpellCastTimes",
                             "side_value_field": "base_ms", "promotion": "raw_only"},
        },
    }
    p["sha256"] = compute_policy_sha256(p)
    return p


def _rehash(p: dict) -> dict:
    p["sha256"] = compute_policy_sha256(p)
    return p


def test_valid_policy_exposes_recon_views():
    pol = load_spell_policy(_valid_payload())
    assert pol.schema_version == SCHEMA and pol.reviewed is True
    assert pol.columns["power_type"] == 41 and pol.columns["school_mask"] == 225
    assert "casting_time_index" not in pol.columns          # null cell omitted from columns
    assert pol.index_fields == {}                            # un-adjudicated join not re-checked by recon
    assert pol.enum_policy["power_types"] == frozenset({-2, 0, 1, 2, 3, 4, 5, 6})
    assert 20 not in pol.enum_policy["school_bits"] and 64 in pol.enum_policy["school_bits"]
    assert pol.bound["client_build"] == "3.3.5a+patch-CZZ"
    assert pol.tables["Spell"]["key_cell"] == 0 and pol.tables["Spell"]["unique"] is True
    assert pol.sha256 == compute_policy_sha256(_valid_payload())


def test_adjudicated_join_appears_in_index_fields():
    p = _valid_payload()
    p["tables"]["Spell"]["fields"]["casting_time_index"]["cell"] = 28   # adjudicated cell
    pol = load_spell_policy(_rehash(p))
    assert pol.index_fields == {"casting_time_index": "SpellCastTimes"}


def test_reject_out_of_bounds_cell():
    p = _valid_payload()
    p["tables"]["Spell"]["fields"]["power_type"]["cell"] = 999
    with pytest.raises(SpellPolicyError, match="out of"):
        load_spell_policy(_rehash(p))


def test_reject_duplicate_cell_in_table():
    p = _valid_payload()
    p["tables"]["Spell"]["fields"]["school_mask"]["cell"] = 41   # collide with power_type
    with pytest.raises(SpellPolicyError, match="reused"):
        load_spell_policy(_rehash(p))


def test_reject_bad_proof_state():
    p = _valid_payload()
    p["tables"]["Spell"]["fields"]["description"]["interpretation"] = "definitely"
    with pytest.raises(SpellPolicyError, match="proof state"):
        load_spell_policy(_rehash(p))


def test_reject_normalized_without_verified_facets():
    p = _valid_payload()
    p["tables"]["Spell"]["fields"]["power_type"]["interpretation"] = "reference"  # still promotion normalized
    with pytest.raises(SpellPolicyError, match="normalized"):
        load_spell_policy(_rehash(p))


def test_reject_school_bit_not_power_of_two():
    p = _valid_payload()
    p["enum_policy"]["school_bits"] = [1, 2, 3]  # 3 is not a power of two
    p["enum_policy"]["sha256"] = compute_policy_sha256(
        {"power_types": p["enum_policy"]["power_types"], "school_bits": [1, 2, 3], "sha256": None})
    with pytest.raises(SpellPolicyError, match="power of two"):
        load_spell_policy(_rehash(p))


def test_reject_wrong_schema_version():
    p = _valid_payload()
    p["schema_version"] = "coa-spell-layout-v1"   # the retired schema is now rejected
    with pytest.raises(SpellPolicyError, match="coa-spell-layout-v2"):
        load_spell_policy(_rehash(p))


def test_reject_key_cell_out_of_bounds():
    p = _valid_payload()
    p["tables"]["Spell"]["key_cell"] = 999
    with pytest.raises(SpellPolicyError, match="key_cell"):
        load_spell_policy(_rehash(p))


def test_reject_bound_table_set_mismatch():
    p = _valid_payload()
    del p["bound"]["tables"]["SpellCastTimes"]   # bound no longer covers every required table
    with pytest.raises(SpellPolicyError, match="bound.tables"):
        load_spell_policy(_rehash(p))


def test_reject_flat_bound_shape():
    p = _valid_payload()
    p["bound"] = {"client_build": "x", "source_dbc_sha256": {"Spell": "a" * 64}}
    with pytest.raises(SpellPolicyError, match="bound.tables"):
        load_spell_policy(_rehash(p))


def test_reject_top_level_hash_tamper():
    p = _valid_payload()
    p["reviewed"] = False   # edited without rehashing
    with pytest.raises(SpellPolicyError, match="sha256 mismatch"):
        load_spell_policy(p)


def test_reject_anchor_set_hash_tamper():
    p = _valid_payload()
    p["anchor_set"]["spells"].append({"id": 585, "name": "Smite", "power_type": 0, "school_mask": 2})
    with pytest.raises(SpellPolicyError, match="anchor_set.sha256"):
        load_spell_policy(_rehash(p))


def test_reject_join_with_unknown_side_value_field():
    p = _valid_payload()
    p["joins"]["cast_time_ms"]["side_value_field"] = "nonesuch"
    with pytest.raises(SpellPolicyError, match="side_value_field"):
        load_spell_policy(_rehash(p))


def test_committed_default_policy_is_client_bound():
    # The shipped v2 default carries the reviewed scalar substrate + the structured bound authored from
    # real-client recon (Task 8b). Joins stay un-adjudicated (raw_only) pending M1.14E1.
    pol = load_default_policy()
    assert pol.schema_version == "coa-spell-layout-v2"
    assert pol.columns["power_type"] == 41 and pol.columns["school_mask"] == 225
    assert pol.columns["name"] == 136
    assert pol.joins["cast_time_ms"].promotion == "raw_only"
    assert pol.bound is not None and pol.bound["client_build"] == "3.3.5a+patch-CZZ"
    assert set(pol.bound["tables"]) == set(pol.required_tables)   # every required table byte-bound
    assert len(pol.bound["tables"]["Spell"]["sha256"]) == 64
    assert pol.bound["tables"]["Spell"]["header"]["field_count"] == 234
