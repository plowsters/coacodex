from coa_client_extract.parity import build_parity_report, flip_gate_inputs
from coa_client_extract.advancement import AdvancementNode
from coa_client_extract.class_types import ClassType


def _node(node_id, spell_id, display, tab, etype="Ability", *, legality=None):
    return AdvancementNode(
        node_id=node_id, spell_id=spell_id, class_type_id=33, class_internal=display,
        class_display=display, class_kind="coa_class", tab_type_id=1, tab_name=tab,
        entry_type=etype, essence_kind="ability", legality=legality or {},
        field_confidence={}, raw={},
    )


def _builder(entry_id, spell_id, display, tab, etype="Ability", *,
             connected=None, required=None, **legality):
    b = {"entry_id": entry_id, "spell_id": spell_id, "class_name": display,
         "tab_name": tab, "entry_type": etype,
         "connected_node_ids": connected or [], "required_ids": required or []}
    b.update(legality)      # ae_cost, te_cost, required_level, ...
    return b


def _clean_pair():
    # one Witch Doctor node, identical on both sides; adjacency + legality decoded high and matching
    nodes = [_node(7131, 503748, "Witch Doctor", "Brewing", "Talent",
                   legality={"ae_cost": 1, "connected_node_ids": [7132], "required_ids": []})]
    builder = [_builder(7131, 503748, "Witch Doctor", "Brewing", "Talent",
                        connected=[7132], required=[], ae_cost=1)]
    return nodes, builder


def test_exact_node_id_ownership_and_per_tab_counts():
    nodes = [
        _node(7131, 503748, "Witch Doctor", "Brewing", "Talent"),
        _node(12264, 503748, "Witch Doctor", "Class", "Ability"),
    ]
    builder = [
        _builder(7131, 503748, "Witch Doctor", "Brewing", "Talent"),
        _builder(12264, 503748, "Witch Doctor", "Class", "Ability"),
    ]
    rep = build_parity_report(nodes, builder)
    assert rep["builder_records"] == 2 and rep["client_nodes"] == 2
    assert rep["builder_only_records"] == 0 and rep["client_only_records"] == 0
    assert rep["identity_mismatches"] == 0
    assert rep["ownership_recall"] == 1.0 and rep["ownership_precision"] == 1.0
    assert rep["per_class"]["Witch Doctor"]["client_nodes"] == 2
    brewing = next(x for x in rep["per_tab"]
                   if x["class"] == "Witch Doctor" and x["tab"] == "Brewing")
    assert brewing["client_nodes"] == 1 and brewing["builder_records"] == 1
    # clean synthetic case with nothing withheld -> every readiness dimension earns true
    assert rep["blockers"] == []
    assert rep["readiness"]["ownership_ready"] is True
    assert rep["readiness"]["attribution_ready"] is True
    assert rep["readiness"]["full_builder_retirement_ready"] is True
    assert rep["readiness"]["leveling_progression_ready"] is False   # essence undecoded, separate, never blocks


def test_builder_only_node_breaks_ownership_not_attribution():
    nodes = [_node(7131, 503748, "Witch Doctor", "Brewing", "Talent")]   # missing 12264
    builder = [
        _builder(7131, 503748, "Witch Doctor", "Brewing", "Talent"),
        _builder(12264, 503748, "Witch Doctor", "Class", "Ability"),
    ]
    rep = build_parity_report(nodes, builder)
    assert rep["builder_only_records"] == 1 and 12264 in rep["builder_only_sample"]
    assert rep["ownership_recall"] < 1.0
    assert "builder_only_node_instances" in rep["blockers"]
    assert rep["readiness"]["ownership_ready"] is False
    assert rep["readiness"]["attribution_ready"] is True   # attribution is anchor-based, independent
    assert rep["readiness"]["full_builder_retirement_ready"] is False


def test_client_only_node_breaks_ownership_precision():
    # client covers every Builder node (recall 1.0) but adds an extra wrongly-attributed CoA node
    nodes = [
        _node(7131, 503748, "Witch Doctor", "Brewing", "Talent"),
        _node(99999, 999999, "Witch Doctor", "Class", "Ability"),   # not in Builder
    ]
    builder = [_builder(7131, 503748, "Witch Doctor", "Brewing", "Talent")]
    rep = build_parity_report(nodes, builder)
    assert rep["ownership_recall"] == 1.0 and rep["ownership_precision"] < 1.0
    assert rep["client_only_records"] == 1 and 99999 in rep["client_only_sample"]
    assert "client_only_node_instances" in rep["blockers"]
    assert rep["readiness"]["ownership_ready"] is False


def test_identity_mismatch_same_id_different_anchor_breaks_ownership():
    # node_id matches an entry_id but the anchored (spell_id, class) disagrees -> decode/attribution
    # defect. tab/entry_type are deliberately NOT part of the identity tuple (they are decode-gated).
    nodes = [_node(7131, 503748, "Witch Doctor", "Brewing", "Talent")]
    builder = [_builder(7131, 888888, "Witch Doctor", "Brewing", "Talent")]   # spell_id differs
    rep = build_parity_report(nodes, builder)
    assert rep["builder_only_records"] == 0 and rep["client_only_records"] == 0
    assert rep["identity_mismatches"] == 1
    assert "identity_mismatch" in rep["blockers"]
    assert rep["readiness"]["ownership_ready"] is False


def test_adjacency_mismatch_breaks_adjacency_not_ownership():
    nodes = [_node(7131, 503748, "Witch Doctor", "Brewing", "Talent",
                   legality={"connected_node_ids": [7132, 7133], "required_ids": []})]
    builder = [_builder(7131, 503748, "Witch Doctor", "Brewing", "Talent",
                        connected=[7132], required=[])]        # client has an extra edge
    rep = build_parity_report(nodes, builder)
    assert rep["adjacency_mismatches"] == 1 and 7131 in rep["adjacency_mismatch_sample"]
    assert "adjacency_mismatch" in rep["blockers"]
    assert rep["readiness"]["adjacency_ready"] is False
    assert rep["readiness"]["ownership_ready"] is True     # ownership is independent of adjacency
    assert rep["readiness"]["full_builder_retirement_ready"] is False


def test_legality_class_b_difference_recorded_but_field_stays_ready():
    # client decoded ae_cost high; value differs from Builder -> client wins offline (class b)
    nodes = [_node(7131, 503748, "Witch Doctor", "Brewing", "Talent",
                   legality={"ae_cost": 2, "connected_node_ids": [], "required_ids": []})]
    builder = [_builder(7131, 503748, "Witch Doctor", "Brewing", "Talent",
                        connected=[], required=[], ae_cost=1)]
    rep = build_parity_report(nodes, builder)
    diffs = [d for d in rep["legality_diffs"] if d["field"] == "ae_cost"]
    assert diffs and diffs[0]["class"] == "b" and diffs[0]["client"] == 2 and diffs[0]["builder"] == 1
    # ae_cost decoded high (nothing withheld) -> stays ready despite the client-wins value diff
    assert rep["readiness"]["legality"]["ae_cost"] == "ready"


def test_undecoded_legality_blocks_retirement_not_ownership():
    # THE scoped-readiness invariant: an unresolved legality field blocks flipping THAT field and
    # full_builder_retirement, but never ownership or attribution.
    nodes, builder = _clean_pair()
    rep = build_parity_report(nodes, builder,
                              low_confidence_fields=["te_cost"],
                              unresolved_layout_columns=["max_rank"])
    assert "low_confidence:te_cost" in rep["blockers"]
    assert "unresolved_layout_column:max_rank" in rep["blockers"]
    assert rep["readiness"]["legality"]["te_cost"] == "unresolved"
    assert rep["readiness"]["legality"]["max_rank"] == "unresolved"
    assert rep["readiness"]["legality"]["required_level"] == "ready"   # not withheld -> ready
    assert rep["readiness"]["full_builder_retirement_ready"] is False
    assert rep["readiness"]["ownership_ready"] is True                 # unaffected by legality
    assert rep["readiness"]["attribution_ready"] is True


def test_cosmetic_layout_fields_never_block():
    nodes, builder = _clean_pair()
    rep = build_parity_report(nodes, builder, unresolved_layout_columns=["row"])
    assert rep["readiness"]["layout"]["row"] == "unresolved"
    # row is cosmetic: it must not drag down retirement (all required legality here is ready)
    assert rep["readiness"]["full_builder_retirement_ready"] is True


def test_cardinality_and_expected_count_gates():
    nodes, builder = _clean_pair()
    cts = {i: ClassType(i, f"C{i}", f"C{i}", "coa_class") for i in range(14, 34)}  # only 20 playable
    cts[35] = ClassType(35, "ConquestOfAzeroth", "ConquestOfAzeroth", "coa_system")
    rep = build_parity_report(nodes, builder, class_types=cts, expected_builder_records=3612)
    assert "playable_class_count" in rep["blockers"]      # 20 != 21
    assert "builder_record_count" in rep["blockers"]      # 1 != 3612
    assert rep["readiness"]["attribution_ready"] is False  # taxonomy broken
    assert rep["readiness"]["ownership_ready"] is False


def test_empty_inputs_block():
    rep = build_parity_report([], [], provenance={"client_build": "3.3.5a+patch-CZZ"})
    assert "empty_client_input" in rep["blockers"]
    assert "empty_builder_input" in rep["blockers"]
    assert rep["provenance"]["client_build"] == "3.3.5a+patch-CZZ"
    assert rep["readiness"]["ownership_ready"] is False
    assert rep["readiness"]["attribution_ready"] is False   # no coa_nodes


def test_flip_gate_inputs_splits_unresolved_from_low_confidence():
    from coa_client_extract.dbc_layouts import CharacterAdvancementLayout
    layout = CharacterAdvancementLayout(
        tab_type_col=3, entry_type_col=4,
        ae_cost_col=5,                       # resolved but not proven high -> low_confidence
        required_level_col=None,             # never resolved -> unresolved
        connected_node_cols=(7, 8),          # resolved but not proven high -> low_confidence
        required_id_cols=(),                 # never resolved -> unresolved
        confidence={"ae_cost": "medium", "connected_node_ids": "low",
                    "tab_type": "high", "entry_type": "high"},
    )
    low, unresolved = flip_gate_inputs(layout)
    assert "ae_cost" in low and "connected_node_ids" in low
    assert "required_level" in unresolved and "required_ids" in unresolved
