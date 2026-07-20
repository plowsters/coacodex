import struct

from coa_client_extract.recordview import open_view
from coa_client_extract.spell_layout import compute_policy_sha256, load_spell_policy
from coa_client_extract.spell_record import build_spell_v2_records

# Synthetic Spell record: 9 uint32 cells.
#  0 id | 1 power_type | 2 school_mask | 3 name_off | 4 desc_off
#  5 casting_time_index | 6 duration_index | 7 range_index | 8 spell_icon_id
SPELL_FC = 9
SPELL_RS = SPELL_FC * 4


def _spell_dbc(rows):
    strings, off, bodies = b"\x00", 1, []
    for (sid, pt, sm, name, desc, ct, du, rg, ic) in rows:
        n_off = off
        strings += name.encode() + b"\x00"; off += len(name) + 1
        d_off = off
        strings += desc.encode() + b"\x00"; off += len(desc) + 1
        cells = [sid, pt & 0xFFFFFFFF, sm, n_off, d_off, ct, du, rg, ic]
        bodies.append(struct.pack("<9I", *cells))
    return struct.pack("<4sIIII", b"WDBC", len(rows), SPELL_FC, SPELL_RS, len(strings)) + b"".join(bodies) + strings


def _int_side(rows):   # id@0, base_ms@1
    body = b"".join(struct.pack("<ii", i, v) for i, v in rows)
    return struct.pack("<4sIIII", b"WDBC", len(rows), 2, 8, 1) + body + b"\x00"


def _range_side(rows):  # id@0(uint), min_yd@1(float), max_yd@2(float)
    body = b"".join(struct.pack("<Iff", i, mn, mx) for i, mn, mx in rows)
    return struct.pack("<4sIIII", b"WDBC", len(rows), 3, 12, 1) + body + b"\x00"


def _icon_side(ids):    # id@0
    body = b"".join(struct.pack("<II", i, 0) for i in ids)
    return struct.pack("<4sIIII", b"WDBC", len(ids), 2, 8, 1) + body + b"\x00"


def _f(cell, kind, layout, interp, promo):
    return {"cell": cell, "kind": kind, "layout": layout, "interpretation": interp,
            "promotion": promo, "evidence": "fixture"}


def _policy(*, reviewed=True, bound=None):
    V = ("verified", "verified")
    spell_fields = {
        "id": _f(0, "uint32", *V, "normalized"),
        "power_type": _f(1, "int32", *V, "normalized"),
        "school_mask": _f(2, "uint32", *V, "normalized"),
        "name": _f(3, "string", *V, "normalized"),
        "description": _f(4, "string", "verified", "reference", "raw_only"),
        "casting_time_index": _f(5, "uint32", *V, "raw_only"),
        "duration_index": _f(6, "uint32", *V, "raw_only"),
        "range_index": _f(7, "uint32", *V, "raw_only"),
        "spell_icon_id": _f(8, "uint32", *V, "raw_only"),
    }
    tables = {
        "Spell": {"expected_field_count": SPELL_FC, "fields": spell_fields},
        "SpellCastTimes": {"expected_field_count": 2, "fields": {
            "id": _f(0, "uint32", *V, "raw_only"), "base_ms": _f(1, "int32", *V, "raw_only")}},
        "SpellDuration": {"expected_field_count": 2, "fields": {
            "id": _f(0, "uint32", *V, "raw_only"), "base_ms": _f(1, "int32", *V, "raw_only")}},
        "SpellRange": {"expected_field_count": 3, "fields": {
            "id": _f(0, "uint32", *V, "raw_only"), "min_yd": _f(1, "float", *V, "raw_only"),
            "max_yd": _f(2, "float", *V, "raw_only")}},
        "SpellIcon": {"expected_field_count": 2, "fields": {"id": _f(0, "uint32", *V, "raw_only")}},
    }
    joins = {
        "cast_time_ms": {"index_field": "casting_time_index", "side_table": "SpellCastTimes", "side_value_field": "base_ms"},
        "duration_ms": {"index_field": "duration_index", "side_table": "SpellDuration", "side_value_field": "base_ms"},
        "range_min_yd": {"index_field": "range_index", "side_table": "SpellRange", "side_value_field": "min_yd"},
        "range_max_yd": {"index_field": "range_index", "side_table": "SpellRange", "side_value_field": "max_yd"},
        "spell_icon_id": {"index_field": "spell_icon_id", "side_table": "SpellIcon", "side_value_field": "id"},
    }
    for _t in tables.values():                      # v2: every table declares its key cell + uniqueness
        _t.setdefault("key_cell", 0); _t.setdefault("unique", True)
    for _j in joins.values():                        # v2: joins carry explicit promotion (all un-adjudicated)
        _j.setdefault("promotion", "raw_only")
    enum = {"power_types": [-2, 0, 1, 2, 3, 4, 5, 6], "school_bits": [1, 2, 4, 8, 16, 32, 64]}
    enum["sha256"] = compute_policy_sha256(enum)
    anchor_set = {"spells": [{"id": 133, "name": "Fireball", "power_type": 0, "school_mask": 4}]}
    anchor_set["sha256"] = compute_policy_sha256(anchor_set)
    p = {"schema_version": "coa-spell-layout-v2", "reviewed": reviewed, "bound": bound,
         "required_tables": ["Spell"], "expected_absent": [], "enum_policy": enum,
         "anchor_set": anchor_set, "tables": tables, "joins": joins}
    p["sha256"] = compute_policy_sha256(p)
    return load_spell_policy(p)


def _build():
    rows = [
        # id, pt, school, name, desc, cast_idx, dur_idx, range_idx, icon
        (805775, 3, 8, "Adrenal Venom", "Venom desc", 1, 1, 1, 100),
        (133, 7, 20, "Fireball", "Fire desc", 0, 99, 0, 0),   # pt 7 OOD; school 20=4|16 ok; joins edge cases
    ]
    spell = open_view(_spell_dbc(rows))
    side = {
        "SpellCastTimes": open_view(_int_side([(1, 1500)])),
        "SpellDuration": open_view(_int_side([(1, 18000)])),   # id 99 absent -> side_row_missing
        "SpellRange": open_view(_range_side([(1, 0.0, 30.0)])),
        "SpellIcon": open_view(_icon_side([100])),
    }
    return build_spell_v2_records(spell, side, policy=_policy(), provenance={"effective_archive": "patch-CA.MPQ"})


def test_v2_schema_and_verified_scalars():
    records, _inv = _build()
    a = records[0]
    assert a["schema_version"] == "coa-client-spell-v2"
    assert a["spell_id"] == 805775 and a["name"] == "Adrenal Venom"
    assert a["mechanics"]["power_type"] == 3
    assert a["mechanics"]["school_mask"] == 8
    assert a["coa_attribution"]["archive_family"] == "coa" and a["coa_attribution"]["id_range"] == "high"
    # observation carries raw + proof; normalized copied from it
    obs = a["field_observations"]["power_type"]
    assert obs["raw_u32"] == 3 and obs["decoded"]["value"] == 3 and obs["proof"]["interpretation"] == "verified"


def test_v2_join_resolutions():
    records, _inv = _build()
    a, b = records
    # resolved join: cast idx 1 -> base_ms 1500
    assert a["mechanics"]["cast_time_ms"] == 1500
    assert a["field_observations"]["cast_time_ms"]["state"] == "resolved"
    assert a["mechanics"]["range_max_yd"] == 30.0 and a["mechanics"]["range_min_yd"] == 0.0
    assert a["mechanics"]["spell_icon_id"] == 100
    # index_zero: cast idx 0 -> not_applicable, null
    assert b["mechanics"]["cast_time_ms"] is None
    assert b["field_observations"]["cast_time_ms"]["state"] == "not_applicable"
    # side_row_missing: dur idx 99 absent -> unresolved, null
    assert b["mechanics"]["duration_ms"] is None
    assert b["field_observations"]["duration_ms"]["state"] == "unresolved"


def test_v2_per_value_domain_gate_and_inventory():
    records, inv = _build()
    b = records[1]   # Fireball: power_type 7 (unknown), school_mask 20 = 4|16 (valid combo)
    assert b["mechanics"]["power_type"] is None
    assert b["field_observations"]["power_type"]["decoded_reason"] == "value_out_of_domain"
    assert b["field_observations"]["power_type"]["raw_u32"] == 7      # raw retained
    assert b["mechanics"]["school_mask"] == 20                        # 4|16 accepted
    assert inv["power_type"] == [7]
    assert inv["school_bits"] == []


def test_v2_description_raw_only_not_promoted():
    records, _inv = _build()
    d = records[0]["field_observations"]["description"]
    assert d["decoded_reason"] == "proof_withheld" and d["resolved"] is None   # reference => withheld
    assert d["raw_offset"] > 0
    assert "description" not in records[0]["mechanics"]                          # not an emitted mechanic


def test_v2_raw_signals_base_family_and_low_id():
    rows = [(133, 0, 4, "Fireball", "d", 0, 0, 0, 0)]   # low id, base archive
    spell = open_view(_spell_dbc(rows))
    records, _inv = build_spell_v2_records(spell, {}, policy=_policy(),
                                           provenance={"effective_archive": "common.MPQ"})
    assert records[0]["coa_attribution"]["archive_family"] == "base"
    assert records[0]["coa_attribution"]["id_range"] == "base"


def test_v2_unknown_school_bit_withheld():
    rows = [(1, 0, 128, "X", "d", 0, 0, 0, 0)]   # bit 128 (0x80) not an allowed school bit
    spell = open_view(_spell_dbc(rows))
    records, inv = build_spell_v2_records(spell, {}, policy=_policy(), provenance={})
    assert records[0]["mechanics"]["school_mask"] is None
    assert records[0]["field_observations"]["school_mask"]["decoded_reason"] == "value_out_of_domain"
    assert inv["school_bits"] == [128]
