from __future__ import annotations

from pathlib import Path

from coa_meta.guide_builder import build_guide_site
from coa_meta.reporting import MetaReportRunner, MetaRunConfig


FIXTURES = Path(__file__).parent / "fixtures"


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
