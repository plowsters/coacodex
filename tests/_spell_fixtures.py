# tests/_spell_fixtures.py
"""Shared synthetic v2 policy + DBC fixtures for the E0R streaming producer and icon-catalog tests."""
import struct

from coa_client_extract.recordview import open_view
from coa_client_extract.spell_layout import compute_policy_sha256, load_spell_policy

# Spell layout used by the fixtures: id@0, power_type@1, school_mask@2, name@3, casting_time_index@4,
# spell_icon_id@5 (six 4-byte cells).
_SPELL_FC = 6


def _wdbc(rows, field_count, strings=b"\x00"):
    body = b"".join(struct.pack("<%dI" % field_count, *r) for r in rows)
    return (struct.pack("<4sIIII", b"WDBC", len(rows), field_count, field_count * 4, len(strings))
            + body + strings)


def _strings(*values):
    """Build a string block + return (block_bytes, {value: offset}). Offset 0 is the empty string."""
    block = b"\x00"
    offsets = {}
    for v in values:
        offsets[v] = len(block)
        block += v.encode("utf-8") + b"\x00"
    return block, offsets


# spells: (id, power_type, school_mask, name, casting_time_index, spell_icon_id)
_SPELLS = [
    (133, 3, 4, "Fireball", 2, 100),
    (805775, 0, 8, "Adrenal Venom", 0, 100),     # custom id (is_coa); shares icon 100; cast index_zero
    (116, 0, 16, "Frostbolt", 2, 200),
]


def spell_dbc():
    block, off = _strings("Fireball", "Adrenal Venom", "Frostbolt")
    rows = [(sid, pt & 0xFFFFFFFF, sm, off[nm], ci, ico) for (sid, pt, sm, nm, ci, ico) in _SPELLS]
    return open_view(_wdbc(rows, _SPELL_FC, block))


def side_views():
    # SpellCastTimes: id@0, base_ms@1. Cast id 2 -> 1500 ms.
    cast = _wdbc([(2, 1500), (3, 3000)], 2)
    return {"SpellCastTimes": open_view(cast)}


def icon_side_views():
    # SpellIcon: id@0, path@1 (string offset). Icons 100 and 200.
    block, off = _strings("Interface/Icons/Ability_Fireball.blp", "Interface/Icons/Spell_Frost_Frostbolt.blp")
    rows = [(100, off["Interface/Icons/Ability_Fireball.blp"]),
            (200, off["Interface/Icons/Spell_Frost_Frostbolt.blp"])]
    return {"SpellIcon": open_view(_wdbc(rows, 2, block))}


def _f(cell, kind, promo="normalized", layout="verified", interp="verified"):
    return {"cell": cell, "kind": kind, "layout": layout, "interpretation": interp,
            "promotion": promo, "evidence": "fixture"}


def _base(tables, joins):
    enum = {"power_types": [-2, 0, 1, 2, 3, 4, 5, 6], "school_bits": [1, 2, 4, 8, 16, 32, 64]}
    enum["sha256"] = compute_policy_sha256(enum)
    anchor = {"spells": [{"id": 133, "name": "Fireball", "power_type": 3, "school_mask": 4}]}
    anchor["sha256"] = compute_policy_sha256(anchor)
    p = {"schema_version": "coa-spell-layout-v2", "reviewed": True, "bound": None,
         "required_tables": list(tables), "expected_absent": [], "enum_policy": enum,
         "anchor_set": anchor, "tables": tables, "joins": joins}
    p["sha256"] = compute_policy_sha256(p)
    return load_spell_policy(p)


def v2_policy(raw_only_cast=False):
    cast_promo = "raw_only" if raw_only_cast else "normalized"
    tables = {
        "Spell": {"expected_field_count": _SPELL_FC, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32"), "power_type": _f(1, "int32"), "school_mask": _f(2, "uint32"),
            "name": _f(3, "string"), "casting_time_index": _f(4, "uint32", promo=cast_promo)}},
        "SpellCastTimes": {"expected_field_count": 2, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32", promo=cast_promo), "base_ms": _f(1, "int32", promo=cast_promo)}},
    }
    joins = {"cast_time_ms": {"index_field": "casting_time_index", "side_table": "SpellCastTimes",
                             "side_value_field": "base_ms", "promotion": cast_promo}}
    return _base(tables, joins)


def v2_icon_policy():
    tables = {
        "Spell": {"expected_field_count": _SPELL_FC, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32"), "spell_icon_id": _f(5, "uint32", promo="raw_only")}},
        "SpellIcon": {"expected_field_count": 2, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32", promo="raw_only"),
            "path": _f(1, "string", promo="raw_only", interp="reference")}},
    }
    joins = {"spell_icon_id": {"index_field": "spell_icon_id", "side_table": "SpellIcon",
                              "side_value_field": "path", "promotion": "raw_only"}}
    return _base(tables, joins)
