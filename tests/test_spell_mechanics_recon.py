import struct
from pathlib import Path
from types import SimpleNamespace

from coa_client_extract.archive_backend import FakeArchiveBackend
from coa_client_extract.spell_mechanics import recon_spell_mechanics

RECON_CEILINGS = {          # E0R.2 T3.3: policy-shaped ceilings; a recon gates only the python_* pair
    "max_serialized_bytes_per_child": 1 << 30, "max_whole_generation_bytes": 1 << 31,
    "python_peak_rss_mb": 16384, "python_elapsed_s": 3600,
    "node_peak_rss_mb": 16384, "node_elapsed_s": 3600,
}

# Column anchors: (id, power_type, school_mask, name, casting_time_index)
ANCHOR_ROWS = [(133, 0, 4, "Fireball", 5), (116, 0, 16, "Frostbolt", 71),
               (78, 1, 1, "Heroic Strike", 0), (585, 0, 2, "Smite", 5)]
ANCHORS = [{"id": i, "power_type": pt, "school_mask": sm, "name": nm}
           for (i, pt, sm, nm, _ct) in ANCHOR_ROWS]


def _spell_dbc(rows):
    bodies, strings, off = [], b"\x00", 1
    for spell_id, pt, sm, name, ct in rows:
        cells = [0] * 234
        cells[0], cells[41], cells[225], cells[136], cells[28] = spell_id, pt & 0xFFFFFFFF, sm, off, ct
        strings += name.encode() + b"\x00"
        off += len(name) + 1
        bodies.append(struct.pack("<234I", *cells))
    return struct.pack("<4sIIII", b"WDBC", len(rows), 234, 936, len(strings)) + b"".join(bodies) + strings


def _side(ids):   # SpellCastTimes-shaped: id@0, base_ms@1
    body = b"".join(struct.pack("<II", i, i * 100) for i in ids)
    return struct.pack("<4sIIII", b"WDBC", len(ids), 2, 8, 1) + body + b"\x00"


def _backend(spell_rows=ANCHOR_ROWS, cast_ids=(0, 5, 71), extra=None):
    e = {"DBFilesClient\\Spell.dbc": [(Path("patch-T.MPQ"), _spell_dbc(spell_rows))],
         "DBFilesClient\\SpellCastTimes.dbc": [(Path("patch-T.MPQ"), _side(cast_ids))]}
    for k, v in (extra or {}).items():
        e[f"DBFilesClient\\{k}.dbc"] = [(Path("patch-T.MPQ"), v)]
    return FakeArchiveBackend(e)


def _policy(*, reviewed, bound=None):
    return SimpleNamespace(
        sha256="policyhash",
        columns={"power_type": 41, "school_mask": 225, "name": 136, "casting_time_index": 28},
        enum_policy={"power_types": {-2, 0, 1, 2, 3, 4, 5, 6}, "school_bits": {1, 2, 4, 8, 16, 32, 64}},
        required_tables=["Spell", "SpellCastTimes"], expected_absent=["SpellEffect"],
        tables={"Spell": {"key_cell": 0, "unique": True, "expected_field_count": 234},
                "SpellCastTimes": {"key_cell": 0, "unique": True, "expected_field_count": 2}},
        index_fields={"casting_time_index": "SpellCastTimes"}, reviewed=reviewed, bound=bound)


def _kwargs(policy):
    return dict(spell_policy=policy, anchors=ANCHORS, budget=RECON_CEILINGS,
                extractor_commit="abc123", client_build="3.3.5a+T")


def test_review_required_when_unbound_and_delta_names_discovered_cells():
    r = recon_spell_mechanics(_backend(), Path("c.MPQ"), (Path("patch-T.MPQ"),),
                              **_kwargs(_policy(reviewed=False)))
    assert r["schema_version"] == "coa-spell-mechanics-recon-v1"
    assert r["status"] == "review_required" and r["blocking_findings"] == []
    assert r["layout_proof"]["power_type"] == {"discovered_cell": 41, "coverage": "4/4",
                                               "unique": True, "matches_policy": True}
    assert r["layout_proof"]["school_mask"]["discovered_cell"] == 225
    assert r["index_fk"]["casting_time_index"]["discovered_cell"] == 28
    assert r["index_fk"]["casting_time_index"]["distinct"] >= 2
    assert r["proposed_policy_delta"]["casting_time_index"] == 28
    assert r["source_pins"]["dbc"]["SpellCastTimes"]["sha256"]
    assert r["source_pins"]["policy_sha256"] == "policyhash"


def test_verified_when_reviewed_and_structured_bound_matches():
    # E0R verified status requires the reviewed policy's STRUCTURED bound to match the opened topology
    # facet-for-facet (sha256 + full header + member/archive/patch chain) across every required table.
    from coa_client_extract.topology import verify_source_topology
    b = _backend()
    topo = verify_source_topology(_policy(reviewed=True), b, Path("c.MPQ"), (Path("patch-T.MPQ"),))
    tables = {t: {"sha256": s["sha256"], "header": s["header"],
                  "source": {"member": s["member"], "effective_archive": s["effective_archive"],
                             "patch_chain": s["patch_chain"]}} for t, s in topo["tables"].items()}
    bound = {"client_build": "3.3.5a+T", "expected_absent": ["SpellEffect"], "tables": tables}
    # E0R.1: `verified` now requires the join to be PROBED and adopted at the authored cell (28). Supply a
    # state-bearing value anchor that resolves uniquely through (casting_time_index@28 -> base_ms@1).
    join_anchors = {"casting_time_index": {
        "side_table": "SpellCastTimes", "side_id_cell": 0, "side_value_cells": [1], "side_value_kind": "int32",
        "anchors": [{"spell_id": 133, "expected_state": "resolved", "expected_value": 500},
                    {"spell_id": 116, "expected_state": "resolved", "expected_value": 7100},
                    {"spell_id": 78, "expected_state": "not_applicable"}]}}
    r = recon_spell_mechanics(b, Path("c.MPQ"), (Path("patch-T.MPQ"),),
                              **_kwargs(_policy(reviewed=True, bound=bound)), join_value_anchors=join_anchors)
    assert r["status"] == "verified", (r["status"], r["join_pairs"], r["blocking_findings"])
    assert r["blocking_findings"] == []
    assert r["join_pairs"]["casting_time_index"]["pair"][0] == 28    # index cell discovered + adopted


def test_blocked_when_expected_absent_table_present():
    present = struct.pack("<4sIIII", b"WDBC", 0, 1, 4, 1) + b"\x00"
    r = recon_spell_mechanics(_backend(extra={"SpellEffect": present}), Path("c.MPQ"),
                              (Path("patch-T.MPQ"),), **_kwargs(_policy(reviewed=False)))
    assert r["status"] == "blocked"
    assert any(f["field"] == "SpellEffect" for f in r["blocking_findings"])


def test_blocked_when_anchor_not_uniquely_discoverable():
    # scramble one anchor's school value so no single cell holds all four expected school masks
    rows = [(133, 0, 999, "Fireball", 5), (116, 0, 16, "Frostbolt", 71),
            (78, 1, 1, "Heroic Strike", 0), (585, 0, 2, "Smite", 5)]
    r = recon_spell_mechanics(_backend(spell_rows=rows), Path("c.MPQ"), (Path("patch-T.MPQ"),),
                              **_kwargs(_policy(reviewed=False)))
    assert r["status"] == "blocked"
    assert any(f["field"] == "school_mask" for f in r["blocking_findings"])


def test_index_discovery_rejects_zero_heavy_decoy():
    # all rows share casting_time_index cell 28; the recon must pick 28, not the all-zero cells
    r = recon_spell_mechanics(_backend(), Path("c.MPQ"), (Path("patch-T.MPQ"),),
                              **_kwargs(_policy(reviewed=False)))
    assert r["index_fk"]["casting_time_index"]["discovered_cell"] == 28
    assert r["index_fk"]["casting_time_index"]["valid_fraction"] == 1.0
