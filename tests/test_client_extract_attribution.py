# tests/test_client_extract_attribution.py
from coa_client_extract.attribution import attribute, AttributionResult
from coa_client_extract.advancement import AdvancementNode


def _node(node_id, spell_id, cid, kind, display, tab_id=1, tab="Class", etype="Ability"):
    return AdvancementNode(
        node_id=node_id, spell_id=spell_id, class_type_id=cid, class_internal=display,
        class_display=display, class_kind=kind, tab_type_id=tab_id, tab_name=tab,
        entry_type=etype, essence_kind="ability", legality={}, field_confidence={}, raw={},
    )


def test_coa_membership_is_high_confidence_coa():
    nodes = [_node(1, 805775, 33, "coa_class", "Venomancer")]
    res = attribute(nodes, {})
    a = res[805775].result
    assert a.is_coa is True and a.modes == ("coa",) and a.exclusive_mode == "coa"
    assert a.confidence == "high"


def test_unknown_kind_contributes_no_mode_not_stock():
    # a node on an out-of-band (unknown) class must NOT be silently attributed as stock.
    nodes = [_node(1, 960, 999, "unknown", "???")]
    a = attribute(nodes, {})[960].result
    assert a.is_coa is False and a.modes == () and a.exclusive_mode is None
    assert a.confidence == "low"


def test_derive_and_build_skill_line_index_from_proven_lines():
    from coa_client_extract.attribution import derive_coa_skill_lines, build_skill_line_index
    # spell 900 is a known CoA graph spell attached to spec SkillLine 512 (NOT the 475-495 band);
    # 7777 is a graph-ABSENT spell on that same proven line -> medium-confidence coa fallback.
    rows = [
        {0: 1, 1: 512, 2: 900},    # proven CoA spell 900 on line 512 -> line 512 is a CoA line
        {0: 2, 1: 512, 2: 7777},   # graph-absent spell on the proven CoA line 512 -> coa (medium)
        {0: 3, 1: 44, 2: 1234},    # stock line -> ignored
        {0: 4, 1: 512, 2: 0},      # no spell -> ignored
    ]
    coa_lines = derive_coa_skill_lines(rows, coa_spell_ids={900})
    assert coa_lines == {512}                       # derived, not the hard-coded 475-495 range
    assert build_skill_line_index(rows, coa_lines) == {900: "coa", 7777: "coa"}


def test_shared_spell_aggregates_memberships():
    nodes = [
        _node(7131, 503748, 15, "coa_class", "Witch Doctor", 49, "Brewing", "Talent"),
        _node(12264, 503748, 15, "coa_class", "Witch Doctor", 1, "Class", "Ability"),
    ]
    res = attribute(nodes, {})
    assert len(res[503748].memberships) == 2
    assert {m["tab_name"] for m in res[503748].memberships} == {"Brewing", "Class"}


def test_coa_plus_reborn_is_multimode_not_conflict():
    nodes = [
        _node(1, 900, 33, "coa_class", "Venomancer"),
        _node(2, 900, 36, "reborn", "RebornHunter"),
    ]
    a = attribute(nodes, {})[900].result
    assert a.is_coa is True
    assert a.modes == ("coa", "reborn") and a.exclusive_mode is None


def test_stock_membership_does_not_overwrite_coa():
    nodes = [
        _node(1, 950, 33, "coa_class", "Venomancer"),
        _node(2, 950, 2, "stock", "Hunter"),
    ]
    a = attribute(nodes, {})[950].result
    assert a.is_coa is True
    assert set(a.modes) == {"coa", "stock"}


def test_skill_line_fallback_for_graph_absent_spell():
    res = attribute([], {}, skill_line_index={7777: "coa"})
    a = res[7777].result
    assert a.is_coa is True and a.confidence == "medium"


def test_id_only_is_unknown_low():
    # a spell with no advancement node and no skill line is simply absent from the result;
    # callers treat absence as is_coa: false / low. Assert it is not present.
    res = attribute([], {}, skill_line_index={})
    assert 123456 not in res
