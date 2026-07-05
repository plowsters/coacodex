from __future__ import annotations

from pathlib import Path

from coa_meta.guide_tooltips import (
    ascension_spell_url,
    build_node_tooltip,
    load_db_tooltip_rows,
    sanitize_tooltip_html,
)
from coa_meta.repository import TalentRepository


FIXTURES = Path(__file__).parent / "fixtures"


def test_ascension_spell_url_uses_public_spell_page():
    assert ascension_spell_url(2001) == "https://db.ascension.gg/?spell=2001"


def test_load_db_tooltip_rows_indexes_matched_spells():
    rows = load_db_tooltip_rows(FIXTURES / "guide_db_tooltips.jsonl")

    assert rows[2001]["name"] == "Damage Talent"
    assert rows[2001]["status"] == "matched"


def test_build_node_tooltip_prefers_db_tooltip_html():
    repo = TalentRepository.from_entries(FIXTURES / "meta_report_fixture.jsonl")
    node = repo.node_by_id(201)
    rows = load_db_tooltip_rows(FIXTURES / "guide_db_tooltips.jsonl")

    tooltip = build_node_tooltip(node, rows)

    assert tooltip.tooltip_id == "spell:2001"
    assert tooltip.db_url == "https://db.ascension.gg/?spell=2001"
    assert "Deals bonus Nature damage." in tooltip.text
    assert tooltip.source == "ascension_db"


def test_build_node_tooltip_falls_back_to_normalized_text():
    repo = TalentRepository.from_entries(FIXTURES / "meta_report_fixture.jsonl")
    node = repo.node_by_id(202)

    tooltip = build_node_tooltip(node, {})

    assert tooltip.tooltip_id == "spell:2002"
    assert tooltip.source == "normalized"
    assert "Requires investment in Damage." in tooltip.text


def test_sanitize_tooltip_html_removes_script_and_event_attributes():
    html = sanitize_tooltip_html('<span onclick="bad()">Safe</span><script>bad()</script>')

    assert "Safe" in html
    assert "onclick" not in html
    assert "script" not in html


def test_sanitize_tooltip_html_preserves_db_tables_without_event_attributes():
    html = sanitize_tooltip_html(
        '<table onclick="bad()"><tr><th>Effect</th><td>Deals <strong>Nature</strong> damage.</td></tr></table>'
    )

    assert "<table>" in html
    assert "<tr>" in html
    assert "<th>Effect</th>" in html
    assert "<td>Deals <strong>Nature</strong> damage.</td>" in html
    assert "onclick" not in html
