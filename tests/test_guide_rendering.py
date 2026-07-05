from __future__ import annotations

from pathlib import Path

from coa_meta.guide_builder import build_guide_site
from coa_meta.guide_rendering import GUIDE_CSS, GUIDE_JS, render_index_html, render_spec_html
from coa_meta.reporting import MetaReportRunner, MetaRunConfig


FIXTURES = Path(__file__).parent / "fixtures"


def _site():
    report = MetaReportRunner(
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
    return build_guide_site(report, entries_path=FIXTURES / "meta_report_fixture.jsonl")


def test_render_index_html_uses_player_facing_guide_shell():
    html = render_index_html(_site())

    assert "<!doctype html>" in html
    assert "CoA Meta Guides" in html
    assert "Open guide" in html
    assert "data-role=" in html
    assert "beam search" not in html.lower()


def test_render_spec_html_includes_sections_and_omits_empty_warnings():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")

    html = render_spec_html(site, spec)

    assert "Overview" in html
    assert "Abilities and Talents" in html
    assert "Stat priorities are early theorycraft" in html
    assert 'id="warnings"' not in html


def test_render_spec_html_links_spell_and_tooltip_ids():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")

    html = render_spec_html(site, spec)

    assert "https://db.ascension.gg/?spell=2001" in html
    assert 'data-tooltip-id="spell:2001"' in html


def test_static_assets_have_fel_void_theme_and_no_network_fetch():
    assert "#65f06b" in GUIDE_CSS
    assert "#8f5cff" in GUIDE_CSS
    assert "fetch(" not in GUIDE_JS
