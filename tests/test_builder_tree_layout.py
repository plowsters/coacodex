from __future__ import annotations

import json
from pathlib import Path

import pytest

from coa_meta.builder_tree_layout import load_builder_tree_layout, load_builder_tree_layouts


FIXTURE = Path(__file__).parent / "fixtures" / "builder_tree_layout_fixture.json"


def test_load_builder_tree_layout_preserves_groups_nodes_and_edges():
    layout = load_builder_tree_layout(FIXTURE)

    assert layout.schema_version == "coa-builder-tree-layout-v1"
    assert layout.class_name == "Venomancer"
    assert layout.source_spec_name == "Stalking"
    assert {tree.tree_kind for tree in layout.trees} == {
        "ability_essence",
        "talent_essence",
        "level_passives",
    }

    ability_tree = layout.tree_by_kind("ability_essence")
    assert ability_tree is not None
    assert ability_tree.bounds.width == 760
    assert ability_tree.nodes[0].entry_id == 101
    assert ability_tree.nodes[0].spell_id == 1001
    assert ability_tree.nodes[0].x == 120
    assert ability_tree.nodes[0].y == 80
    assert ability_tree.nodes[0].width == 64
    assert ability_tree.nodes[0].height == 64
    assert ability_tree.nodes[0].tree_kind == "ability_essence"
    assert ability_tree.edges[0].source_entry_id == 101
    assert ability_tree.edges[0].target_entry_id == 102

    talent_tree = layout.tree_by_kind("talent_essence")
    assert talent_tree is not None
    assert talent_tree.nodes[0].tree_kind == "talent_essence"
    assert talent_tree.edges[0].kind == "requires"

    passive_lane = layout.tree_by_kind("level_passives")
    assert passive_lane is not None
    assert len(passive_lane.nodes) == 3
    assert all(node.tree_kind == "level_passives" for node in passive_lane.nodes)


def test_load_builder_tree_layouts_resolves_by_class_and_source_spec():
    layouts = load_builder_tree_layouts(FIXTURE.parent)

    layout = layouts.layout_for("Venomancer", "Stalking")

    assert layout is not None
    assert layout.display_spec_name == "Stalking"
    assert layouts.layout_for("Venomancer", "Rot") is None


def test_invalid_tree_kind_raises_clear_error(tmp_path):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["trees"][0]["tree_kind"] = "mobile_reflow"
    path = tmp_path / "invalid-layout.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported builder tree kind"):
        load_builder_tree_layout(path)
