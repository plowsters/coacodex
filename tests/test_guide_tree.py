from __future__ import annotations

import json
from pathlib import Path

from coa_meta.builds import BuildConfig
from coa_meta.guide_models import (
    GuideBuildCard,
    GuideNodeGate,
    GuideTree,
    GuideTreeEdge,
    GuideTreePanel,
    GuideTreeSnapshot,
)
from coa_meta.guide_tree import build_guide_tree, build_guide_tree_panel, default_tree_levels
from coa_meta.repository import TalentRepository


FIXTURES = Path(__file__).parent / "fixtures"


def test_guide_tree_serializes_snapshots_and_edges():
    tree = GuideTree(
        tree_id="testclass-damage-1",
        class_name="Testclass",
        spec_name="Damage",
        build_rank=1,
        build_label="Direct damage loop",
        level=60,
        max_ae=26,
        max_te=25,
        ae_spent=3,
        te_spent=2,
        rows=10,
        cols=11,
        nodes=tuple(),
        edges=(GuideTreeEdge(source_id=201, target_id=202, kind="connection", state="selected"),),
        snapshots=(
            GuideTreeSnapshot(
                level=60,
                max_ae=26,
                max_te=25,
                ae_spent=3,
                te_spent=2,
                selected_node_ids=(201, 202),
                free_node_ids=tuple(),
                available_node_ids=(203,),
                gated_nodes=(
                    GuideNodeGate(
                        node_id=204,
                        state="gated_required_node",
                        reasons=("Requires Damage Talent",),
                        issue_codes=("required_node_missing",),
                    ),
                ),
            ),
        ),
        warnings=tuple(),
    )

    payload = tree.to_dict()

    assert payload["schema_version"] == "coa-guide-tree-v1"
    assert payload["edges"][0]["source_id"] == 201
    assert payload["snapshots"][0]["gated_nodes"][0]["state"] == "gated_required_node"


def test_default_tree_levels_include_report_level_and_key_breakpoints():
    assert default_tree_levels(13) == (10, 13, 20, 30, 40, 50, 60)


def test_build_guide_tree_uses_coordinates_edges_and_snapshots():
    repo = TalentRepository.from_entries(FIXTURES / "meta_report_fixture.jsonl")
    nodes = tuple(
        node for node in repo.nodes_for_class("Testclass")
        if node.tab_name in {"Class", "Damage"}
    )

    tree = build_guide_tree(
        repository=repo,
        class_name="Testclass",
        spec_name="Damage",
        build_rank=1,
        build_label="Direct damage loop",
        selected_node_ids=(201, 202),
        config=BuildConfig(class_name="Testclass", level=60, max_ae=26, max_te=25),
        spec_nodes=nodes,
    )

    assert tree.rows >= 3
    assert tree.cols >= 2
    assert any(edge.source_id == 201 and edge.target_id == 202 for edge in tree.edges)
    assert any(snapshot.level == 60 for snapshot in tree.snapshots)
    assert {node.entry_id for node in tree.nodes if node.selected} >= {201, 202}


def test_guide_tree_panel_splits_ability_talent_and_passive_groups():
    repo = TalentRepository.from_entries(FIXTURES / "meta_report_fixture.jsonl")
    nodes = tuple(
        node for node in repo.nodes_for_class("Testclass")
        if node.tab_name in {"Class", "Damage"}
    )

    panel = build_guide_tree_panel(
        repository=repo,
        class_name="Testclass",
        source_spec_name="Damage",
        display_spec_name="Damage",
        build_rank=1,
        build_label="Direct damage loop",
        selected_node_ids=(201, 202),
        config=BuildConfig(class_name="Testclass", level=60, max_ae=26, max_te=25),
        spec_nodes=nodes,
    )

    assert isinstance(panel, GuideTreePanel)
    assert {tree.tree_kind for tree in panel.trees} == {
        "ability_essence",
        "talent_essence",
        "level_passives",
    }
    ability_tree = next(tree for tree in panel.trees if tree.tree_kind == "ability_essence")
    talent_tree = next(tree for tree in panel.trees if tree.tree_kind == "talent_essence")
    passive_lane = next(tree for tree in panel.trees if tree.tree_kind == "level_passives")

    assert ability_tree.layout_source == "normalized_fallback"
    assert {node.entry_id for node in ability_tree.nodes} == {100, 101, 102}
    assert {node.entry_id for node in talent_tree.nodes} == {201, 202}
    assert {node.entry_id for node in passive_lane.nodes} == set()
    assert all(node.tab_name == "Class" for node in ability_tree.nodes)
    assert all(node.te_cost > 0 and node.essence_kind == "talent" for node in talent_tree.nodes)
    assert all(node.ae_cost == 0 and node.te_cost == 0 for node in passive_lane.nodes)


def test_guide_tree_panel_keeps_spec_free_core_nodes_out_of_passive_lane(tmp_path):
    rows = [
        json.loads(line)
        for line in (FIXTURES / "meta_report_fixture.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    spec_free_core = {
        **rows[3],
        "entry_id": 203,
        "spell_id": 2003,
        "spell_ids": [2003],
        "name": "Free Core Ability",
        "entry_type": "Ability",
        "essence_kind": "ability",
        "ae_cost": 0,
        "te_cost": 0,
        "required_level": 0,
        "row": 0,
        "col": 4,
        "required_ids": [],
        "connected_node_ids": [],
    }
    level_passive = {
        **rows[3],
        "entry_id": 204,
        "spell_id": 2004,
        "spell_ids": [2004],
        "name": "Level Passive",
        "entry_type": "Talent",
        "essence_kind": "talent",
        "ae_cost": 0,
        "te_cost": 0,
        "required_level": 10,
        "row": 0,
        "col": 10,
        "required_ids": [],
        "connected_node_ids": [],
    }
    fixture = tmp_path / "entries.jsonl"
    fixture.write_text(
        "\n".join(json.dumps(row) for row in [*rows, spec_free_core, level_passive]) + "\n",
        encoding="utf-8",
    )
    repo = TalentRepository.from_entries(fixture)
    nodes = tuple(
        node for node in repo.nodes_for_class("Testclass")
        if node.tab_name in {"Class", "Damage"}
    )

    panel = build_guide_tree_panel(
        repository=repo,
        class_name="Testclass",
        source_spec_name="Damage",
        display_spec_name="Damage",
        build_rank=1,
        build_label="Direct damage loop",
        selected_node_ids=(201, 202),
        config=BuildConfig(class_name="Testclass", level=60, max_ae=26, max_te=25),
        spec_nodes=nodes,
    )

    talent_tree = next(tree for tree in panel.trees if tree.tree_kind == "talent_essence")
    passive_lane = next(tree for tree in panel.trees if tree.tree_kind == "level_passives")

    assert 203 in {node.entry_id for node in talent_tree.nodes}
    assert 203 not in {node.entry_id for node in passive_lane.nodes}
    assert {node.entry_id for node in passive_lane.nodes} == {204}


def test_build_card_serializes_tree_panel_and_legacy_tree():
    legacy_tree = GuideTree(
        tree_id="testclass-damage-1",
        class_name="Testclass",
        spec_name="Damage",
        build_rank=1,
        build_label="Direct damage loop",
        level=60,
        max_ae=26,
        max_te=25,
        ae_spent=0,
        te_spent=0,
        rows=1,
        cols=1,
        nodes=tuple(),
        edges=tuple(),
        snapshots=tuple(),
        warnings=tuple(),
    )
    panel = GuideTreePanel(
        tree_panel_id="testclass-damage-1",
        class_name="Testclass",
        source_spec_name="Damage",
        display_spec_name="Damage",
        build_rank=1,
        build_label="Direct damage loop",
        level=60,
        max_ae=26,
        max_te=25,
        trees=(legacy_tree,),
        snapshots=tuple(),
        warnings=tuple(),
    )
    card = GuideBuildCard(
        rank=1,
        label="Direct damage loop",
        confidence_label="medium",
        projected_dps_index=101.0,
        node_ids=tuple(),
        warnings=tuple(),
        tree=legacy_tree,
        tree_panel=panel,
    )

    payload = card.to_dict()

    assert payload["tree"]["schema_version"] == "coa-guide-tree-v1"
    assert payload["tree_panel"]["schema_version"] == "coa-guide-tree-panel-v1"
    assert payload["tree_panel"]["trees"][0]["tree_kind"] == "combined"
