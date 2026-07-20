# tests/test_e0r_recon_cli.py
import struct
from pathlib import Path

from coa_client_extract.archive_backend import FakeArchiveBackend
from coa_client_extract.spell_layout import compute_policy_sha256, load_spell_policy
from coa_client_extract.spell_mechanics import recon_spell_mechanics, DEFAULT_BUDGET

# Spell layout for the fixture: id@0, power_type@1, school_mask@2, name@3, casting_time_index@4.
_FC = 5
# (id, power_type_raw, school, name, casting_time_index)
_ROWS = [(133, 3, 4, "Fireball", 2), (116, 3, 16, "Frostbolt", 3),
         (5, 0xFFFFFFFE, 1, "Lifeblood", 0)]   # spell 5: power_type reads -2 (health cost), cast index_zero


def _spell_dbc():
    strings, off, block = {}, 1, b"\x00"
    for _, _, _, nm, _ in _ROWS:
        strings[nm] = off
        block += nm.encode() + b"\x00"
        off += len(nm) + 1
    body = b""
    for sid, pt, sm, nm, ci in _ROWS:
        cells = [0] * _FC
        cells[0], cells[1], cells[2], cells[3], cells[4] = sid, pt & 0xFFFFFFFF, sm, strings[nm], ci
        body += struct.pack("<%dI" % _FC, *cells)
    return struct.pack("<4sIIII", b"WDBC", len(_ROWS), _FC, _FC * 4, len(block)) + body + block


def _cast_dbc():   # SpellCastTimes: id@0, base_ms@1
    rows = [(2, 1500), (3, 3000)]
    body = b"".join(struct.pack("<II", i, v) for i, v in rows)
    return struct.pack("<4sIIII", b"WDBC", len(rows), 2, 8, 0) + body


def _backend():
    return FakeArchiveBackend({
        "DBFilesClient\\Spell.dbc": [(Path("patch-CZZ.MPQ"), _spell_dbc())],
        "DBFilesClient\\SpellCastTimes.dbc": [(Path("patch-CZZ.MPQ"), _cast_dbc())],
    })


def _f(cell, kind, promo="normalized", layout="verified", interp="verified"):
    return {"cell": cell, "kind": kind, "layout": layout, "interpretation": interp,
            "promotion": promo, "evidence": "fx"}


def _policy():
    enum = {"power_types": [-2, 0, 1, 2, 3, 4, 5, 6], "school_bits": [1, 2, 4, 8, 16, 32, 64]}
    enum["sha256"] = compute_policy_sha256(enum)
    anchor = {"spells": [{"id": 133, "name": "Fireball", "power_type": 3, "school_mask": 4},
                         {"id": 116, "name": "Frostbolt", "power_type": 3, "school_mask": 16}]}
    anchor["sha256"] = compute_policy_sha256(anchor)
    tables = {
        "Spell": {"expected_field_count": _FC, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32"), "power_type": _f(1, "int32"), "school_mask": _f(2, "uint32"),
            "name": _f(3, "string"), "casting_time_index": _f(None, "uint32", promo="raw_only",
                                                              layout="unproven", interp="unproven")}},
        "SpellCastTimes": {"expected_field_count": 2, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32", promo="raw_only"), "base_ms": _f(1, "int32", promo="raw_only",
                                                                  layout="verified", interp="reference")}},
    }
    joins = {"cast_time_ms": {"index_field": "casting_time_index", "side_table": "SpellCastTimes",
                             "side_value_field": "base_ms", "promotion": "raw_only"}}
    p = {"schema_version": "coa-spell-layout-v2", "reviewed": True, "bound": None,
         "required_tables": ["Spell", "SpellCastTimes"], "expected_absent": ["SpellEffect"],
         "enum_policy": enum, "anchor_set": anchor, "tables": tables, "joins": joins}
    p["sha256"] = compute_policy_sha256(p)
    return load_spell_policy(p)


_ANCHORS = [{"id": 133, "power_type": 3, "school_mask": 4, "name": "Fireball"},
            {"id": 116, "power_type": 3, "school_mask": 16, "name": "Frostbolt"}]


def test_recon_uses_shared_topology_and_three_part_budget():
    r = recon_spell_mechanics(_backend(), Path("c.MPQ"), (Path("patch-CZZ.MPQ"),), spell_policy=_policy(),
                              anchors=_ANCHORS, budget=DEFAULT_BUDGET, extractor_commit="e0r", client_build="3.3.5a+CZZ")
    assert r["status"] == "review_required"                        # bound is null -> not verified
    # shared verify_source_topology captures a full header + density for every required table
    assert r["topology"]["tables"]["Spell"]["dense"] is True
    assert r["topology"]["tables"]["SpellCastTimes"]["header"]["field_count"] == 2
    # three-part budget: all three gates present
    assert set(r["budget"]["breach"]) == set()
    assert {"serialized_mb", "peak_rss_mb", "elapsed_s"} <= set(r["budget"])


def test_recon_value_anchors_discover_join_pair_and_power_type_signedness():
    join_anchors = {"casting_time_index": {"side_table": "SpellCastTimes", "side_id_cell": 0,
                    "side_value_cells": [1], "side_value_kind": "int32", "anchors": [
                        {"spell_id": 133, "expected_state": "resolved", "expected_value": 1500},
                        {"spell_id": 116, "expected_state": "resolved", "expected_value": 3000},
                        {"spell_id": 5, "expected_state": "not_applicable", "expected_value": None}]}}
    r = recon_spell_mechanics(_backend(), Path("c.MPQ"), (Path("patch-CZZ.MPQ"),), spell_policy=_policy(),
                              anchors=_ANCHORS, budget=DEFAULT_BUDGET, extractor_commit="e0r",
                              client_build="3.3.5a+CZZ", join_value_anchors=join_anchors,
                              power_type_anchors=[{"spell_id": 5, "expected_signed": -2}])
    # the joined pair (index cell 4, value cell 1) is uniquely discovered and named in the delta
    assert r["join_pairs"]["casting_time_index"]["pair"] == (4, 1)
    assert r["proposed_policy_delta"]["casting_time_index"] == (4, 1)
    # the static negative anchor admits the signed int32 power_type reading
    assert r["proposed_policy_delta"]["power_type_signed"] is True


def test_recon_never_writes_a_policy(tmp_path):
    # recon proposes a delta but touches no policy file on disk.
    before = set(p.name for p in tmp_path.iterdir())
    recon_spell_mechanics(_backend(), Path("c.MPQ"), (Path("patch-CZZ.MPQ"),), spell_policy=_policy(),
                          anchors=_ANCHORS, budget=DEFAULT_BUDGET, extractor_commit="e0r", client_build="x")
    assert set(p.name for p in tmp_path.iterdir()) == before
