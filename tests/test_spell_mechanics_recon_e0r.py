# tests/test_spell_mechanics_recon_e0r.py
import struct
import pytest
from coa_client_extract.recordview import open_view
from coa_client_extract.spell_mechanics import (
    discover_join_pair, discover_power_type_signedness, recon_budget,
)


def _spell(rows: list[list[int]], field_count: int):
    rs = field_count * 4
    body = b"".join(struct.pack("<%dI" % field_count, *r) for r in rows)
    return open_view(struct.pack("<4sIIII", b"WDBC", len(rows), field_count, rs, 0) + body)


def _side(rows: list[tuple[int, int]]):
    body = b"".join(struct.pack("<II", i, v) for i, v in rows)
    return open_view(struct.pack("<4sIIII", b"WDBC", len(rows), 2, 8, 0) + body)


def test_joined_pair_discovers_both_cells_uniquely():
    # index FK in spell-cell 2, side value in side-cell 1; decoy spell-cell 1 also holds ids but resolves
    # to the WRONG values, so only the (2, 1) pair satisfies every anchor.
    spell = _spell([[133, 3, 2], [116, 2, 3], [400, 0, 0]], field_count=3)
    id_to_rec = {r.u32(0): r for r in spell.records()}
    side = _side([(2, 1500), (3, 3000)])
    anchors = [{"spell_id": 133, "expected_state": "resolved", "expected_value": 1500},
               {"spell_id": 116, "expected_state": "resolved", "expected_value": 3000},
               {"spell_id": 400, "expected_state": "not_applicable", "expected_value": None}]
    pair, winners = discover_join_pair(spell, id_to_rec, side, side_id_cell=0, side_value_cells=[1],
                                       anchors=anchors)
    assert pair == (2, 1) and winners == [(2, 1)]


def test_resolved_zero_is_distinguished_from_not_applicable():
    # spell 133 & 200 -> side id 1 whose value is 0 (a RESOLVED zero); spell 400 has fk 0 (not_applicable).
    # 200 is present only to give the FK column enough non-zero support to qualify as a candidate.
    spell = _spell([[133, 1], [200, 1], [400, 0]], field_count=2)
    id_to_rec = {r.u32(0): r for r in spell.records()}
    side = _side([(1, 0)])
    correct = [{"spell_id": 133, "expected_state": "resolved", "expected_value": 0},
               {"spell_id": 400, "expected_state": "not_applicable", "expected_value": None}]
    pair, _ = discover_join_pair(spell, id_to_rec, side, side_id_cell=0, side_value_cells=[1], anchors=correct)
    assert pair == (1, 1)
    # Mislabelling the resolved-zero as not_applicable must FAIL to match (its fk is non-zero).
    mislabelled = [{"spell_id": 133, "expected_state": "not_applicable", "expected_value": None},
                   {"spell_id": 400, "expected_state": "not_applicable", "expected_value": None}]
    pair2, _ = discover_join_pair(spell, id_to_rec, side, side_id_cell=0, side_value_cells=[1], anchors=mislabelled)
    assert pair2 is None


def test_joined_pair_ambiguous_returns_none():
    spell = _spell([[133, 2, 2], [116, 3, 3], [400, 0, 0]], field_count=3)  # spell-cells 1 and 2 identical
    id_to_rec = {r.u32(0): r for r in spell.records()}
    side = _side([(2, 1500), (3, 3000)])
    anchors = [{"spell_id": 133, "expected_state": "resolved", "expected_value": 1500},
               {"spell_id": 116, "expected_state": "resolved", "expected_value": 3000}]
    pair, winners = discover_join_pair(spell, id_to_rec, side, side_id_cell=0, side_value_cells=[1],
                                       anchors=anchors)
    assert pair is None and winners == [(1, 1), (2, 1)]


def test_power_type_signedness_requires_static_negative_anchor():
    spell = _spell([[5, 0xFFFFFFFE]], field_count=2)   # health cost reads -2 unsigned
    id_to_rec = {r.u32(0): r for r in spell.records()}
    assert discover_power_type_signedness(spell, id_to_rec, cell=1,
                                          anchors=[{"spell_id": 5, "expected_signed": -2}]) is True
    assert discover_power_type_signedness(spell, id_to_rec, cell=1, anchors=[]) is False


def test_recon_budget_gates_what_a_recon_measures():
    # E0R.2 T3.3 retired the three-part budget: its `serialized_bytes` leg was record_count*record_size,
    # the raw DBC size of the SOURCE table, gated as though it forecast the serialized artifact.
    ceilings = {"python_peak_rss_mb": 4096, "python_elapsed_s": 600,
                "node_peak_rss_mb": 4096, "node_elapsed_s": 600,
                "max_serialized_bytes_per_child": 1 << 30, "max_whole_generation_bytes": 1 << 31}
    ok = recon_budget(peak_rss_mb=100, elapsed_s=5, ceilings=ceilings)
    assert ok["within_budget"] is True
    over_rss = recon_budget(peak_rss_mb=9000, elapsed_s=5, ceilings=ceilings)
    assert over_rss["within_budget"] is False and len(over_rss["breach"]) == 1
    assert "python_peak_rss_mb" in over_rss["breach"][0]
