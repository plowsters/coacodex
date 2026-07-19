import struct
from pathlib import Path
from types import SimpleNamespace

from coa_client_extract.archive_backend import FakeArchiveBackend
from coa_client_extract.spell_mechanics import recon_spell_mechanics, DEFAULT_BUDGET

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
        index_fields={"casting_time_index": "SpellCastTimes"}, reviewed=reviewed, bound=bound)


def _kwargs(policy):
    return dict(spell_policy=policy, anchors=ANCHORS, budget=DEFAULT_BUDGET,
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


def test_verified_when_reviewed_and_bound_matches():
    b = _backend()
    spell_sha = __import__("hashlib").sha256(
        b.read_effective_file(Path("c.MPQ"), (Path("patch-T.MPQ"),), "DBFilesClient\\Spell.dbc").data).hexdigest()
    bound = {"client_build": "3.3.5a+T", "source_dbc_sha256": {"Spell": spell_sha}}
    r = recon_spell_mechanics(b, Path("c.MPQ"), (Path("patch-T.MPQ"),),
                              **_kwargs(_policy(reviewed=True, bound=bound)))
    assert r["status"] == "verified" and r["blocking_findings"] == []


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
