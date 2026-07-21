# tests/test_e0r1_join_adjudication.py
"""E0R.1 Task 1.2 — all-four-join adjudication.

The reviewed spell-layout policy must record a definite verdict for every join: the icon join is adopted
at the cell that independent Builder-payload icon evidence uniquely pins (cell 133 on the real client),
while the three numeric joins (cast time / duration / range) — for which no admissible independent value
evidence exists — are recorded reviewed_ambiguous with a null cell and recorded evidence, never silently
left unprobed or deferred. The recon machinery must (a) probe a reviewed_ambiguous join WITHOUT reading its
side table, and (b) NOT let the deliberately-ambiguous bare FK-validity scan block a join the stronger
value-anchor discovery has already resolved.
"""
import json
import struct
from pathlib import Path
from types import SimpleNamespace

from coa_client_extract.archive_backend import FakeArchiveBackend
from coa_client_extract.recordview import open_view
from coa_client_extract.spell_mechanics import probe_joins, recon_spell_mechanics, DEFAULT_BUDGET
from coa_client_extract.spell_layout import load_default_policy, load_spell_policy

_POLICY_PATH = Path("coa_client_extract/data/spell_layout_v2.json")
_BUILDER_PATH = Path("coa_scraper/dist/coa_entries.jsonl")


# --- tiny view/backend builders -------------------------------------------------------------------
def _view(rows, field_count):
    body = b"".join(struct.pack("<%dI" % field_count, *r) for r in rows)
    return open_view(struct.pack("<4sIIII", b"WDBC", len(rows), field_count, field_count * 4, 0) + body)


def _side_bytes(pairs):  # 2-col WDBC: id@0, value@1
    body = b"".join(struct.pack("<II", i, v) for i, v in pairs)
    return struct.pack("<4sIIII", b"WDBC", len(pairs), 2, 8, 0) + body


class _ExplodingBackend:
    def read_effective_file(self, *a, **k):
        raise AssertionError("a reviewed_ambiguous join must not read its side table")


# --- Part A: probe_joins -------------------------------------------------------------------------
def test_reviewed_ambiguous_join_is_probed_without_reading_side_table():
    spell = _view([[133, 5], [116, 7], [400, 0]], field_count=2)
    id_to_rec = {r.u32(0): r for r in spell.records()}
    jva = {"casting_time_index": {"side_table": "SpellCastTimes", "adjudication": "reviewed_ambiguous",
                                  "evidence": "no admissible independent value evidence disambiguates the FK"}}
    jp = probe_joins(_ExplodingBackend(), Path("c.MPQ"), (Path("p.MPQ"),), spell, id_to_rec,
                     SimpleNamespace(), jva)
    # probed (present) but ambiguous (pair=None), with the recorded marker — NOT omitted.
    assert jp["casting_time_index"]["pair"] is None
    assert jp["casting_time_index"]["adjudication"] == "reviewed_ambiguous"
    assert jp["casting_time_index"]["evidence"]


def test_value_anchor_join_discovers_unique_index_cell():
    # icon-shaped: FK in spell-cell 2, verified against the side id itself (value_cell 0).
    spell = _view([[133, 0, 28001], [116, 0, 8625], [400, 0, 0]], field_count=3)
    id_to_rec = {r.u32(0): r for r in spell.records()}
    backend = FakeArchiveBackend({"DBFilesClient\\SpellIcon.dbc":
                                  [(Path("p.MPQ"), _side_bytes([(28001, 1), (8625, 1)]))]})
    jva = {"spell_icon_id": {"side_table": "SpellIcon", "side_id_cell": 0, "side_value_cells": [0],
                             "side_value_kind": "uint32",
                             "anchors": [{"spell_id": 133, "expected_state": "resolved", "expected_value": 28001},
                                         {"spell_id": 116, "expected_state": "resolved", "expected_value": 8625}]}}
    jp = probe_joins(backend, Path("c.MPQ"), (Path("p.MPQ"),), spell, id_to_rec, SimpleNamespace(), jva)
    assert jp["spell_icon_id"]["pair"] == (2, 0)
    assert jp["spell_icon_id"]["winners"] == [(2, 0)]


# --- Part B: recon does not let the ambiguous bare FK scan block an adjudicated join --------------
# Spell.dbc (234 fields to mirror the real record): scalar anchors at 41/225/136; the casting_time FK sits
# in cell 28, with a DECOY in cell 29 that also holds valid SpellCastTimes ids (so the bare validity scan
# is ambiguous) but resolves the anchors to the WRONG base_ms (so value-anchor discovery still picks 28).
_ANCHOR_ROWS = [(133, 0, 4, "Fireball", 5, 71), (116, 0, 16, "Frostbolt", 71, 5),
                (78, 1, 1, "Heroic Strike", 0, 0), (585, 0, 2, "Smite", 5, 71)]
_ANCHORS = [{"id": i, "power_type": pt, "school_mask": sm, "name": nm}
            for (i, pt, sm, nm, _c, _d) in _ANCHOR_ROWS]


def _spell_dbc(rows):
    bodies, strings, off = [], b"\x00", 1
    for sid, pt, sm, name, ct, decoy in rows:
        cells = [0] * 234
        cells[0], cells[41], cells[225], cells[136] = sid, pt & 0xFFFFFFFF, sm, off
        cells[28], cells[29] = ct, decoy
        strings += name.encode() + b"\x00"
        off += len(name) + 1
        bodies.append(struct.pack("<234I", *cells))
    return struct.pack("<4sIIII", b"WDBC", len(rows), 234, 936, len(strings)) + b"".join(bodies) + strings


def _cast_side():  # id -> base_ms: 5->500, 71->7100
    return _side_bytes([(5, 500), (71, 7100)])


def _recon_backend():
    return FakeArchiveBackend({
        "DBFilesClient\\Spell.dbc": [(Path("patch-T.MPQ"), _spell_dbc(_ANCHOR_ROWS))],
        "DBFilesClient\\SpellCastTimes.dbc": [(Path("patch-T.MPQ"), _cast_side())]})


def _recon_policy():
    return SimpleNamespace(
        sha256="policyhash", reviewed=False, bound=None,
        columns={"power_type": 41, "school_mask": 225, "name": 136, "casting_time_index": 28},
        enum_policy={"power_types": {-2, 0, 1, 2, 3, 4, 5, 6}, "school_bits": {1, 2, 4, 8, 16, 32, 64}},
        required_tables=["Spell", "SpellCastTimes"], expected_absent=["SpellEffect"],
        tables={"Spell": {"key_cell": 0, "unique": True, "expected_field_count": 234},
                "SpellCastTimes": {"key_cell": 0, "unique": True, "expected_field_count": 2}},
        index_fields={"casting_time_index": "SpellCastTimes"})


_CAST_ANCHORS = {"casting_time_index": {
    "side_table": "SpellCastTimes", "side_id_cell": 0, "side_value_cells": [1], "side_value_kind": "int32",
    "anchors": [{"spell_id": 133, "expected_state": "resolved", "expected_value": 500},
                {"spell_id": 116, "expected_state": "resolved", "expected_value": 7100},
                {"spell_id": 78, "expected_state": "not_applicable"}]}}


def _run(**over):
    return recon_spell_mechanics(_recon_backend(), Path("c.MPQ"), (Path("patch-T.MPQ"),),
                                 spell_policy=_recon_policy(), anchors=_ANCHORS, budget=DEFAULT_BUDGET,
                                 extractor_commit="abc", client_build="3.3.5a+T", **over)


def _has_block(r, field, reason):
    return any(f.get("field") == field and f.get("reason") == reason for f in r["blocking_findings"])


def test_ambiguous_bare_fk_blocks_without_value_anchors():
    # Baseline: with two valid-FK candidate cells (28 + decoy 29) and no value anchors, the bare scan is
    # ambiguous and recon HARD-BLOCKS — this is the failure the skip must prevent for adjudicated joins.
    r = _run()
    assert _has_block(r, "casting_time_index", "no_unique_index_cell")


def test_adjudicated_join_not_blocked_by_ambiguous_bare_fk():
    r = _run(join_value_anchors=_CAST_ANCHORS)
    assert not _has_block(r, "casting_time_index", "no_unique_index_cell")
    assert r["join_pairs"]["casting_time_index"]["pair"] == (28, 1)   # value-anchor discovery wins


# --- Part C: the real reviewed policy adjudicates all four joins ----------------------------------
def _policy_doc():
    return json.loads(_POLICY_PATH.read_text(encoding="utf-8"))


def _builder_icon_spells():
    spells = {}
    with open(_BUILDER_PATH, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("spell_id") and d.get("icon"):
                spells[d["spell_id"]] = d["icon"]
    return spells


def test_policy_adopts_icon_join_at_cell_133():
    doc = _policy_doc()
    fields = doc["tables"]["Spell"]["fields"]
    icon = fields["spell_icon_id"]
    assert icon["cell"] == 133                       # uniquely discovered via Builder icon anchors
    assert icon["layout"] == "verified"              # the column identity is proven
    # T2.3 PROMOTED the adjudicated icon string-join: verified interpretation + normalized, like Spell.name.
    assert icon["interpretation"] == "verified"
    assert icon["promotion"] == "normalized"
    assert doc["joins"]["spell_icon_id"]["promotion"] == "normalized"
    assert doc["tables"]["SpellIcon"]["fields"]["path"]["promotion"] == "normalized"


def test_policy_records_numeric_joins_reviewed_ambiguous():
    fields = _policy_doc()["tables"]["Spell"]["fields"]
    for f in ("casting_time_index", "duration_index", "range_index"):
        assert fields[f]["cell"] is None, f
        assert fields[f]["promotion"] == "raw_only", f
        assert "reviewed_ambiguous" in fields[f]["evidence"], f


def test_anchor_set_covers_all_four_joins_with_verdicts():
    joins = _policy_doc()["anchor_set"]["joins"]
    assert set(joins) == {"casting_time_index", "duration_index", "range_index", "spell_icon_id"}
    for f in ("casting_time_index", "duration_index", "range_index"):
        assert joins[f]["adjudication"] == "reviewed_ambiguous"
        assert joins[f]["evidence"]
    icon = joins["spell_icon_id"]
    assert icon["side_table"] == "SpellIcon" and icon["side_value_cells"] == [0]
    assert icon.get("adjudication") != "reviewed_ambiguous"
    assert all(a["expected_state"] == "resolved" for a in icon["anchors"])
    assert len(icon["anchors"]) >= 8


def test_icon_anchors_are_genuine_builder_payload_spells():
    # provenance: every icon anchor must be a real Builder-payload CoA spell carrying an icon path (evidence
    # precedence #2), never an invented or remembered value.
    builder = _builder_icon_spells()
    for a in _policy_doc()["anchor_set"]["joins"]["spell_icon_id"]["anchors"]:
        assert a["spell_id"] in builder, a["spell_id"]
        assert isinstance(a["expected_value"], int) and a["expected_value"] > 0


def test_policy_still_loads_and_hashes_consistently():
    load_spell_policy(_policy_doc())        # re-validates every embedded digest (policy + anchor_set + enum)
    load_default_policy()
