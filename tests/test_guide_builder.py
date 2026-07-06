from __future__ import annotations

import json
from pathlib import Path

from coa_meta.guide_builder import build_guide_site
from coa_meta.guide_models import GuideSpec
from coa_meta.reporting import MetaReportRunner, MetaRunConfig


FIXTURES = Path(__file__).parent / "fixtures"
BUILDER_LAYOUT_FIXTURE = FIXTURES / "builder_tree_layout_fixture.json"


def _report():
    return MetaReportRunner(
        MetaRunConfig(
            entries_path=FIXTURES / "meta_report_fixture.jsonl",
            classes_path=FIXTURES / "meta_classes.json",
            class_names=("Testclass",),
            top=1,
            beam_width=2,
            branch_width=2,
            require_budget_fraction=0.0,
        )
    ).run()


def _write_testclass_builder_layout(tmp_path, *, omit_entry_ids=()):
    raw = json.loads(BUILDER_LAYOUT_FIXTURE.read_text(encoding="utf-8"))
    raw["class_name"] = "Testclass"
    raw["source_spec_name"] = "Damage"
    raw["display_spec_name"] = "Damage"
    raw["trees"][0]["nodes"] = [
        {"entry_id": 101, "spell_id": 1001, "name": "Shared Strike", "x": 410, "y": 80, "width": 64, "height": 64},
        {"entry_id": 102, "spell_id": 1002, "name": "Shared Veteran Strike", "x": 410, "y": 190, "width": 64, "height": 64},
    ]
    raw["trees"][0]["edges"] = [{"source_entry_id": 101, "target_entry_id": 102, "kind": "requires"}]
    raw["trees"][1]["nodes"] = [
        {"entry_id": 201, "spell_id": 2001, "name": "Damage Talent", "x": 925, "y": 70, "width": 64, "height": 64},
        {"entry_id": 202, "spell_id": 2002, "name": "Deep Damage", "x": 1040, "y": 170, "width": 64, "height": 64},
    ]
    raw["trees"][1]["edges"] = [{"source_entry_id": 201, "target_entry_id": 202, "kind": "requires"}]
    raw["trees"][2]["nodes"] = [
        {"entry_id": 100, "spell_id": 1000, "name": "Shared Free", "x": 40, "y": 20, "width": 64, "height": 64}
    ]
    raw["trees"][2]["edges"] = []
    omit = set(omit_entry_ids)
    for tree in raw["trees"]:
        tree["nodes"] = [node for node in tree["nodes"] if node["entry_id"] not in omit]
        tree["edges"] = [
            edge for edge in tree["edges"]
            if edge["source_entry_id"] not in omit and edge["target_entry_id"] not in omit
        ]
    path = tmp_path / "testclass-damage-layout.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return tmp_path


def test_build_guide_site_creates_index_and_spec_routes():
    site = build_guide_site(
        _report(),
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        db_tooltips_path=FIXTURES / "guide_db_tooltips.jsonl",
    )

    assert site.index_path == "index.html"
    assert site.legacy_index_path == "meta-report.html"
    assert [spec.slug for spec in site.specs] == ["testclass-damage", "testclass-support"]
    assert site.specs[0].href == "specs/testclass-damage.html"


def test_guide_site_has_metric_definitions_and_player_facing_sections():
    site = build_guide_site(_report(), entries_path=FIXTURES / "meta_report_fixture.jsonl")

    assert "primary_index" in site.metric_definitions
    assert "projected_dps_index" in site.metric_definitions
    assert "confidence" in site.metric_definitions
    assert "Overview" in site.specs[0].sections
    assert "Abilities and Talents" in site.specs[0].sections


def test_guide_nodes_include_links_tooltips_and_icons():
    site = build_guide_site(
        _report(),
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        db_tooltips_path=FIXTURES / "guide_db_tooltips.jsonl",
    )
    damage = site.specs[0]
    node = next(item for item in damage.nodes if item.entry_id == 201)

    assert node.db_url == "https://db.ascension.gg/?spell=2001"
    assert node.tooltip_id == "spell:2001"
    assert node.asset.asset_id.startswith("icon:")


def test_guide_builder_prefers_db_icon_asset_path(tmp_path: Path):
    db_path = tmp_path / "db_tooltips.jsonl"
    db_path.write_text(
        json.dumps(
            {
                "kind": "spell",
                "id": 2001,
                "status": "matched",
                "name": "Damage Talent",
                "icon": "spell_nature_poison",
                "icon_asset_path": "dist/assets/icons/spell_nature_poison.png",
                "tooltip_html": "<table><tr><td>Deals bonus Nature damage.</td></tr></table>",
                "tooltip_text": "Deals bonus Nature damage.",
                "linked_spell_ids": [],
                "linked_item_ids": [],
                "name_match": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    site = build_guide_site(
        _report(),
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        db_tooltips_path=db_path,
    )
    damage = site.specs[0]
    node = next(item for item in damage.nodes if item.entry_id == 201)

    assert node.asset.href == "icons/spell_nature_poison.png"
    assert node.asset.source == "ascension_db_asset"
    assert node.asset.missing is False


def test_guide_build_cards_include_static_tree_payloads():
    site = build_guide_site(_report(), entries_path=FIXTURES / "meta_report_fixture.jsonl")
    damage = site.specs[0]
    build = damage.builds[0]

    assert build.tree is not None
    assert build.tree.class_name == "Testclass"
    assert any(node.entry_id == 201 for node in build.tree.nodes)
    assert any(snapshot.level == 60 for snapshot in build.tree.snapshots)


def test_guide_builder_uses_builder_layout_coordinates(tmp_path):
    layout_root = _write_testclass_builder_layout(tmp_path)
    site = build_guide_site(
        _report(),
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        builder_layout_root=layout_root,
    )
    damage = site.specs[0]
    panel = damage.builds[0].tree_panel

    assert panel is not None
    talent_tree = next(tree for tree in panel.trees if tree.tree_kind == "talent_essence")
    node = next(node for node in talent_tree.nodes if node.entry_id == 201)

    assert talent_tree.layout_source == "builder_dom"
    assert talent_tree.bounds["x"] == 860
    assert node.x == 925
    assert node.y == 70
    assert node.width == 64
    assert node.height == 64


def test_guide_builder_warns_when_builder_layout_is_missing(tmp_path):
    site = build_guide_site(
        _report(),
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        builder_layout_root=tmp_path,
    )
    damage = site.specs[0]

    assert damage.builds[0].tree_panel is not None
    assert "builder_layout_missing" in damage.builds[0].tree_panel.warnings


def test_guide_builder_warns_when_selected_node_is_missing_from_layout(tmp_path):
    layout_root = _write_testclass_builder_layout(tmp_path, omit_entry_ids=(202,))
    site = build_guide_site(
        _report(),
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        builder_layout_root=layout_root,
    )
    damage = site.specs[0]

    assert "layout_node_missing:202" in damage.builds[0].tree_panel.warnings


def test_guide_build_cards_include_playstyle_metadata():
    site = build_guide_site(_report(), entries_path=FIXTURES / "meta_report_fixture.jsonl")
    build = site.specs[0].builds[0]

    assert build.playstyle_label
    assert build.selection_reason
    assert build.rotation_loop


def test_guide_build_cards_include_role_specific_objective_labels():
    site = build_guide_site(_report(), entries_path=FIXTURES / "meta_report_fixture.jsonl")
    support = next(spec for spec in site.specs if spec.spec_name == "Support")
    build = support.builds[0]

    assert build.primary_index == build.projected_dps_index
    assert build.primary_index_label == "Projected Healing Index"
    assert build.objective_id == "healing"

    payload = build.to_dict()
    assert payload["primary_index"] == payload["projected_dps_index"]
    assert payload["primary_index_label"] == "Projected Healing Index"


def test_guide_specs_include_role_provenance():
    site = build_guide_site(_report(), entries_path=FIXTURES / "meta_report_fixture.jsonl")
    support = next(spec for spec in site.specs if spec.spec_name == "Support")

    assert support.role == "healer"
    assert support.role_provenance["source"] == "curated"


def test_guide_spec_serializes_primary_and_secondary_roles():
    spec = GuideSpec(
        slug="guardian-inspiration",
        href="specs/guardian-inspiration.html",
        class_name="Guardian",
        spec_name="Inspiration",
        role="melee_dps",
        primary_role="melee_dps",
        secondary_roles=("support",),
        roles=("melee_dps", "support"),
        confidence_label="high",
        warning_count=0,
        summary="Hybrid role guide.",
        sections=("Overview",),
        builds=tuple(),
        nodes=tuple(),
        warnings=tuple(),
        role_provenance={"source": "authoritative_video"},
    )

    payload = spec.to_dict()

    assert payload["role"] == "melee_dps"
    assert payload["primary_role"] == "melee_dps"
    assert payload["secondary_roles"] == ["support"]
    assert payload["roles"] == ["melee_dps", "support"]
