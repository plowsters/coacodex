from __future__ import annotations

import json
from pathlib import Path

from coa_meta.report_assets import AssetResolver
from coa_meta.reporting import (
    MetaReportRunner,
    MetaRunConfig,
    render_html_report,
    render_markdown_report,
    render_spec_guide_html,
    write_report_outputs,
)

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


def _write_testclass_layout(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    raw = json.loads(BUILDER_LAYOUT_FIXTURE.read_text(encoding="utf-8"))
    raw["class_name"] = "Testclass"
    raw["source_spec_name"] = "Damage"
    raw["display_spec_name"] = "Damage"
    raw["trees"][0]["nodes"] = [
        {"entry_id": 101, "spell_id": 1001, "name": "Shared Strike", "x": 410, "y": 80, "width": 64, "height": 64}
    ]
    raw["trees"][0]["edges"] = []
    raw["trees"][1]["nodes"] = [
        {"entry_id": 201, "spell_id": 2001, "name": "Damage Talent", "x": 925, "y": 70, "width": 64, "height": 64},
        {"entry_id": 202, "spell_id": 2002, "name": "Deep Damage", "x": 1040, "y": 170, "width": 64, "height": 64},
    ]
    raw["trees"][1]["edges"] = [{"source_entry_id": 201, "target_entry_id": 202, "kind": "requires"}]
    raw["trees"][2]["nodes"] = [
        {"entry_id": 100, "spell_id": 1000, "name": "Shared Free", "x": 40, "y": 20, "width": 64, "height": 64}
    ]
    raw["trees"][2]["edges"] = []
    path = root / "testclass-damage.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return root


def test_writes_json_markdown_and_html_outputs(tmp_path):
    report = _report()

    written = write_report_outputs(
        report,
        tmp_path,
        formats=("json", "md", "html"),
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        db_tooltips_path=FIXTURES / "guide_db_tooltips.jsonl",
    )

    names = {path.name for path in written}
    assert {"meta-report.json", "meta-report.md", "meta-report.html", "index.html"}.issubset(names)
    assert (tmp_path / "specs" / "testclass-damage.html").exists()
    assert (tmp_path / "assets" / "guide.css").exists()
    assert (tmp_path / "assets" / "guide.js").exists()
    assert (tmp_path / "assets" / "tooltip-catalog.json").exists()
    assert (tmp_path / "assets" / "guide-site-manifest.json").exists()
    data = json.loads((tmp_path / "meta-report.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == "coa-meta-report-v1"
    assert "Projected DPS Index" in (tmp_path / "meta-report.md").read_text(encoding="utf-8")
    assert "<html" in (tmp_path / "meta-report.html").read_text(encoding="utf-8")


def test_html_writer_passes_builder_layout_root_to_guide_site(tmp_path):
    report = _report()
    layout_root = _write_testclass_layout(tmp_path / "layouts")

    write_report_outputs(
        report,
        tmp_path / "out",
        formats=("html",),
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        builder_layout_root=layout_root,
    )

    manifest = json.loads((tmp_path / "out" / "assets" / "guide-site-manifest.json").read_text(encoding="utf-8"))
    damage = next(spec for spec in manifest["specs"] if spec["spec_name"] == "Damage")
    talent_tree = next(
        tree for tree in damage["builds"][0]["tree_panel"]["trees"]
        if tree["tree_kind"] == "talent_essence"
    )

    assert talent_tree["layout_source"] == "builder_dom"
    assert talent_tree["nodes"][0]["x"] == 925


def test_markdown_and_html_include_warnings_and_theorycraft_label():
    report = _report()

    markdown = render_markdown_report(report)
    html = render_html_report(report, entries_path=FIXTURES / "meta_report_fixture.jsonl")

    assert "theorycraft" in markdown.lower()
    assert "metadata_tab_has_no_nodes:Testclass:Empty" in markdown
    assert "Observed DPS" not in markdown
    assert "CoA Codex" in html
    assert "Open guide" in html
    assert "beam search" not in html.lower()


def test_spec_guide_html_has_rotation_stat_and_gear_sections():
    report = _report()
    result = report.spec_results[0]

    html = render_spec_guide_html(report, result)

    assert "spec-guide" in html
    assert "Rotation" in html
    assert "Stat Priority" in html
    assert "Weapon and Armor" in html
    assert "Best targets for this spec" in html
    assert "Best stats to target" in html
    assert "Icy" not in html


def test_asset_resolver_returns_none_for_missing_assets(tmp_path):
    resolver = AssetResolver(tmp_path)

    assert resolver.class_tree_image("Testclass") is None
    assert resolver.node_icon("Interface\\Icons\\Missing") is None
