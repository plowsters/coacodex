# tests/_spell_fixtures.py
"""Shared synthetic v2 policy + DBC fixtures for the E0R streaming producer and icon-catalog tests."""
import struct

from coa_client_extract.recordview import open_view
from coa_client_extract.spell_layout import compute_policy_sha256, derive_artifact_contract, load_spell_policy

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


def icon_side_views(*, empty_paths=()):
    """SpellIcon: id@0, path@1 (string offset). Icons 100 and 200.

    `empty_paths` points the named icon ids at string offset 0 — the real client's SpellIcon row 1 does
    exactly this, and it is the case that proved E0R.2 T6.3's model incomplete (T8.1)."""
    block, off = _strings("Interface/Icons/Ability_Fireball.blp", "Interface/Icons/Spell_Frost_Frostbolt.blp")
    rows = [(100, off["Interface/Icons/Ability_Fireball.blp"]),
            (200, off["Interface/Icons/Spell_Frost_Frostbolt.blp"])]
    rows = [(icon_id, 0 if icon_id in empty_paths else path) for icon_id, path in rows]
    return {"SpellIcon": open_view(_wdbc(rows, 2, block))}


def _f(cell, kind, promo="normalized", layout="verified", interp="verified"):
    return {"cell": cell, "kind": kind, "layout": layout, "interpretation": interp,
            "promotion": promo, "evidence": "fixture"}


# E0R.2 T0.2: the Content JSON binding is part of a reviewed policy, so every policy — synthetic
# included — must declare one.
#
# E0R.2 T2.1: this now binds the REAL bytes the synthetic client fixture writes
# (tests/test_client_extract_cli.py::_client), because `declared_content_derivation` roots the Content
# child's expected count in `content_sources[*].source_entries`. A placeholder digest would make the
# synthetic regenerate path unable to satisfy its own accounting identity — and the point of the rule
# is that the count comes from the reviewed policy rather than from the candidate.
SYNTHETIC_CONTENT_ENTRIES = 1
SYNTHETIC_CONTENT_BODY = '[{"Spell":805775,"Rank":1}]'
SYNTHETIC_CONTENT_SOURCES = {
    "directory": "Content",
    "required_files": {
        "SpellRankData.json": {
            "kind": "spell_rank",
            "sha256": "3f5e5f31f0d6af8b78e5bb3151a26c6eac5a79fb9821ae79938b518ca6c72190",
            "source_entries": SYNTHETIC_CONTENT_ENTRIES,
        },
    },
}


def _base(tables, joins):
    enum = {"power_types": [-2, 0, 1, 2, 3, 4, 5, 6], "school_bits": [1, 2, 4, 8, 16, 32, 64]}
    enum["sha256"] = compute_policy_sha256(enum)
    anchor = {"spells": [{"id": 133, "name": "Fireball", "power_type": 3, "school_mask": 4}]}
    anchor["sha256"] = compute_policy_sha256(anchor)
    p = {"schema_version": "coa-spell-layout-v2", "reviewed": True, "bound": None,
         "required_tables": list(tables), "expected_absent": [], "enum_policy": enum,
         "anchor_set": anchor, "tables": tables, "joins": joins,
         "content_sources": SYNTHETIC_CONTENT_SOURCES}
    # E0R.2 T2.3: the observation domain is a REVIEWED block the loader checks against the layout, so a
    # fixture derives it from the tables/joins it just declared rather than restating it by hand.
    p["artifact_contract"] = derive_artifact_contract(p)
    p["sha256"] = compute_policy_sha256(p)
    return load_spell_policy(p)


def v2_policy(raw_only_cast=False, raw_only_power_type=False):
    cast_promo = "raw_only" if raw_only_cast else "normalized"
    # E0R.1 T1.3: a demoted power_type is raw_only with a non-verified interpretation, so the streaming
    # producer withholds the decode (decoded_reason='proof_withheld') and emits no normalized value.
    pt = _f(1, "int32", promo="raw_only", interp="reference") if raw_only_power_type else _f(1, "int32")
    tables = {
        "Spell": {"expected_field_count": _SPELL_FC, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32"), "power_type": pt, "school_mask": _f(2, "uint32"),
            "name": _f(3, "string"), "casting_time_index": _f(4, "uint32", promo=cast_promo)}},
        "SpellCastTimes": {"expected_field_count": 2, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32", promo=cast_promo), "base_ms": _f(1, "int32", promo=cast_promo)}},
    }
    joins = {"cast_time_ms": {"index_field": "casting_time_index", "side_table": "SpellCastTimes",
                             "side_value_field": "base_ms", "promotion": cast_promo}}
    return _base(tables, joins)


def spell_dbc_desc():
    # id@0, power_type@1, school_mask@2, name@3, description@4 (five 4-byte cells)
    block, off = _strings("Fireball", "Hurls a fiery ball that causes Fire damage.")
    rows = [(133, 3, 4, off["Fireball"], off["Hurls a fiery ball that causes Fire damage."])]
    return open_view(_wdbc(rows, 5, block))


def v2_desc_policy():
    tables = {"Spell": {"expected_field_count": 5, "key_cell": 0, "unique": True, "fields": {
        "id": _f(0, "uint32"), "power_type": _f(1, "int32"), "school_mask": _f(2, "uint32"),
        "name": _f(3, "string"),
        "description": _f(4, "string", promo="raw_only", interp="reference")}}}
    return _base(tables, {})


def v2_icon_policy():
    # E0R.1 T2.3: the icon string-join is PROMOTED — WS1 (T1.2) adjudicated the FK cell, so the join and
    # every component are normalized/verified and make_string_join resolves real client paths. A resolved
    # path with no client asset is `missing`; an unresolved join (fk 0 / no side row) is a `placeholder`.
    tables = {
        "Spell": {"expected_field_count": _SPELL_FC, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32"), "spell_icon_id": _f(5, "uint32")}},
        "SpellIcon": {"expected_field_count": 2, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32"), "path": _f(1, "string")}},
    }
    joins = {"spell_icon_id": {"index_field": "spell_icon_id", "side_table": "SpellIcon",
                              "side_value_field": "path", "promotion": "normalized"}}
    return _base(tables, joins)


def v2_icon_policy_ambiguous():
    # The counterfactual where WS1 did NOT adjudicate the icon index: the FK cell is null, so the join stays
    # raw_only/reference and the catalog can only emit placeholders (zero resolved-path coverage).
    null_fk = {"cell": None, "kind": "uint32", "layout": "unproven", "interpretation": "reference",
               "promotion": "raw_only", "evidence": "fixture: icon index unadjudicated"}
    tables = {
        "Spell": {"expected_field_count": _SPELL_FC, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32"), "spell_icon_id": null_fk}},
        "SpellIcon": {"expected_field_count": 2, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32", promo="raw_only"),
            "path": _f(1, "string", promo="raw_only", interp="reference")}},
    }
    joins = {"spell_icon_id": {"index_field": "spell_icon_id", "side_table": "SpellIcon",
                              "side_value_field": "path", "promotion": "raw_only"}}
    return _base(tables, joins)


def spell_dbc_icon_edges():
    # Icon join edge cases at spell_icon_id@5: a resolved path (100), an index_zero FK (0), a nonzero FK with
    # no SpellIcon side row (999 -> side_row_missing), and a second resolved path (200). Reuse icon_side_views().
    rows = [(133, 0, 0, 0, 0, 100),      # resolves -> Ability_Fireball.blp
            (300, 0, 0, 0, 0, 0),        # index_zero -> placeholder
            (400, 0, 0, 0, 0, 999),      # side_row_missing -> placeholder
            (500, 0, 0, 0, 0, 200)]      # resolves -> Spell_Frost_Frostbolt.blp
    return open_view(_wdbc(rows, _SPELL_FC, b"\x00"))
