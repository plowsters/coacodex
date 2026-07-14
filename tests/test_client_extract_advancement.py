import pytest

from coa_client_extract.class_types import resolve_class_types, resolve_tab_types
from coa_client_extract.dbc_layouts import CharacterAdvancementLayout
from coa_client_extract.advancement import AdvancementNode, read_advancement, validate_semantics
from coa_client_extract.errors import DbcSemanticError


class _Table:
    def __init__(self, rows): self.rows = rows


def _class_types():
    rows = [{"id": i, "name": n} for i, n in {
        2: "Hunter", 15: "WitchDoctor", 33: "Venomancer", 35: "ConquestOfAzeroth", 36: "RebornHunter",
    }.items()]
    return resolve_class_types(_Table(rows))


def _tab_types():
    return resolve_tab_types(_Table([{"id": 1, "name": "Class"}, {"id": 49, "name": "Brewing"}]))


def _layout(confidence=None):
    return CharacterAdvancementLayout(
        node_id_col=0, spell_id_col=5, class_type_col=32, tab_type_col=6, entry_type_col=7,
        ae_cost_col=8, required_level_col=9, connected_node_cols=(10, 11), required_id_cols=(12,),
        max_rank_col=13, entry_type_map={"0": "Ability", "1": "Talent"},
        confidence=confidence if confidence is not None else {
            "tab_type": "high", "entry_type": "high",
            "ae_cost": "high", "required_level": "high",
            "connected_node_ids": "high", "required_ids": "high", "max_rank": "high",
        },
    )


def _ca(rows):
    # rows are dicts keyed by column index (decoded raw), the shape parse_positional produces.
    return _Table(rows)


def _row(node_id, spell, cls, tab=1, entry=0, ae=1, lvl=0, c1=0, c2=0, req=0, rank=1):
    return {0: node_id, 5: spell, 32: cls, 6: tab, 7: entry, 8: ae, 9: lvl,
            10: c1, 11: c2, 12: req, 13: rank}


def test_reads_node_with_ownership_and_confidence_gated_legality():
    ca = _ca([_row(6086, 805775, 33, tab=1, entry=0, ae=1, c1=0, c2=0)])
    n = read_advancement(ca, _class_types(), _tab_types(), _layout())[0]
    assert isinstance(n, AdvancementNode)
    assert n.node_id == 6086 and n.spell_id == 805775
    assert n.class_type_id == 33 and n.class_display == "Venomancer"
    assert n.tab_name == "Class" and n.entry_type == "Ability"
    assert n.legality["ae_cost"] == 1 and n.field_confidence["ae_cost"] == "high"
    assert n.legality["required_ids"] == []            # 0 padding dropped


def test_unproven_legality_field_is_withheld():
    # confidence lacks ae_cost -> it must NOT appear in legality even though the column is set
    layout = _layout(confidence={"required_level": "high"})
    n = read_advancement(_ca([_row(1, 100, 33)]), _class_types(), _tab_types(), layout)[0]
    assert "ae_cost" not in n.legality
    assert "required_level" in n.legality


def test_shared_spell_yields_two_nodes():
    ca = _ca([_row(7131, 503748, 15, tab=49, entry=1), _row(12264, 503748, 15, tab=1, entry=0)])
    nodes = read_advancement(ca, _class_types(), _tab_types(), _layout())
    assert {n.node_id for n in nodes} == {7131, 12264}
    assert {n.tab_name for n in nodes} == {"Brewing", "Class"}


def test_validate_semantics_rejects_dangling_adjacency():
    nodes = read_advancement(_ca([_row(1, 100, 33, c1=999)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="dangling"):
        validate_semantics(nodes, _class_types(), _tab_types())


def test_validate_semantics_rejects_out_of_range_level():
    nodes = read_advancement(_ca([_row(1, 100, 33, lvl=999)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="required_level"):
        validate_semantics(nodes, _class_types(), _tab_types())


def test_validate_semantics_rejects_unknown_class_band():
    ct = resolve_class_types(_Table([{"id": 99, "name": "Mystery"}]))
    nodes = read_advancement(_ca([_row(1, 100, 99)]), ct, _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="unknown class"):
        validate_semantics(nodes, ct, _tab_types())


def test_validate_semantics_rejects_duplicate_and_zero_node_ids():
    dup = read_advancement(_ca([_row(1, 100, 33), _row(1, 101, 33)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="duplicate node"):
        validate_semantics(dup, _class_types(), _tab_types())
    zero = read_advancement(_ca([_row(0, 100, 33)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="node id 0"):
        validate_semantics(zero, _class_types(), _tab_types())


def test_validate_semantics_rejects_decoded_unknown_tab_but_allows_unresolved_entry():
    # a DECODED tab_type_id outside the tab-types domain is real drift -> raises
    bad_tab = read_advancement(_ca([_row(1, 100, 33, tab=777)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="unknown tab"):
        validate_semantics(bad_tab, _class_types(), _tab_types())
    # an entry value outside the proven map yields entry_type="" (honestly unresolved for that node);
    # under the scoped-readiness model that is NOT a semantic error -> must NOT raise.
    unresolved = read_advancement(_ca([_row(1, 100, 33, entry=99)]), _class_types(), _tab_types(), _layout())
    assert unresolved[0].entry_type == ""
    validate_semantics(unresolved, _class_types(), _tab_types())   # no raise


def test_validate_semantics_rejects_self_reference_and_excessive_cost():
    self_ref = read_advancement(_ca([_row(5, 100, 33, c1=5)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="self-reference"):
        validate_semantics(self_ref, _class_types(), _tab_types())
    huge = read_advancement(_ca([_row(1, 100, 33, ae=100000)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="ae_cost"):
        validate_semantics(huge, _class_types(), _tab_types())


def test_tab_type_and_entry_type_are_confidence_gated():
    # a layout that did NOT prove tab_type/entry_type high must withhold them (ownership is gated
    # exactly like legality) -> tab withheld, entry_type "". A withheld field is honestly unresolved
    # (reported by the parity readiness gate), NOT a semantic error -> validate_semantics must NOT raise.
    layout = _layout(confidence={"ae_cost": "high"})   # tab_type/entry_type absent -> not high
    n = read_advancement(_ca([_row(1, 100, 33, tab=1, entry=0)]),
                         _class_types(), _tab_types(), layout)[0]
    assert n.tab_type_id == 0 and n.tab_name == ""     # withheld, not shipped as ownership
    assert n.entry_type == ""
    validate_semantics([n], _class_types(), _tab_types())   # withheld metadata does not block


def test_withheld_entry_type_alone_does_not_block_extraction():
    # the real-decode-plausible ASYMMETRIC case: tab_type proves high but entry_type does not. Under
    # the scoped-readiness model an unresolved entry_type must NOT fail-close the whole extraction
    # (it is reported per-field by the readiness gate); only a DECODED-but-invalid value would.
    layout = _layout(confidence={"tab_type": "high"})   # entry_type not high -> withheld
    nodes = read_advancement(_ca([_row(1, 100, 33, tab=1, entry=0)]), _class_types(), _tab_types(), layout)
    assert nodes[0].tab_name == "Class" and nodes[0].entry_type == ""
    validate_semantics(nodes, _class_types(), _tab_types())   # no raise on unresolved metadata


def test_graph_invariants_reject_missing_root():
    # two connected nodes in one tab, each requiring the other -> no root
    rows = [_row(1, 100, 33, tab=1, c1=2, req=2), _row(2, 101, 33, tab=1, c1=1, req=1)]
    nodes = read_advancement(_ca(rows), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="no root"):
        validate_semantics(nodes, _class_types(), _tab_types())


def test_graph_invariants_reject_orphan_node():
    # node 1 is an isolated root; node 2 has a prerequisite (not a root) but NO connected edge,
    # so it is unreachable from the roots over the visual tree -> orphan.
    rows = [_row(1, 100, 33, tab=1, c1=0, req=0), _row(2, 101, 33, tab=1, c1=0, req=1)]
    nodes = read_advancement(_ca(rows), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="orphan"):
        validate_semantics(nodes, _class_types(), _tab_types())


def test_graph_invariants_reject_prerequisite_cycle():
    # node 1 is a root connected to 2 and 3; nodes 2 and 3 require each other -> prerequisite cycle
    # (all three are reachable and a root exists, so only the acyclicity check fires)
    rows = [_row(1, 100, 33, tab=1, c1=2, c2=3, req=0), _row(2, 101, 33, tab=1, c1=1, req=3),
            _row(3, 102, 33, tab=1, c1=1, req=2)]
    nodes = read_advancement(_ca(rows), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="cycle"):
        validate_semantics(nodes, _class_types(), _tab_types())


def test_graph_invariants_accept_valid_tree():
    # 1 (root) -> 2 -> 3, a clean chain: root exists, all reachable via connected edges, acyclic
    rows = [_row(1, 100, 33, tab=1, c1=2, req=0), _row(2, 101, 33, tab=1, c1=3, req=1),
            _row(3, 102, 33, tab=1, c1=0, req=2)]
    nodes = read_advancement(_ca(rows), _class_types(), _tab_types(), _layout())
    validate_semantics(nodes, _class_types(), _tab_types())   # must not raise
