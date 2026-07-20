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


def test_ascension_spell_url_is_removed_no_remote_link():
    # E0R AscensionDB sunset: guide nodes no longer link out to db.ascension.gg.
    assert ascension_spell_url(2001) is None


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
    assert tooltip.db_url is None                       # no remote AscensionDB link (E0R)
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


def test_sanitize_tooltip_html_strips_disallowed_inline_tags_to_readable_text():
    raw = (
        "Javelin Toss now lodges into enemies."
        "<span class='iconsmall'>"
        "<ins style='background-image: url(\"https://db.ascension.gg/x.jpg\");'></ins>"
        "<del></del></span>"
        "<a style='color: white !important' href='?spell=802591'> Lodged Spear </a>"
    )

    out = sanitize_tooltip_html(raw)

    assert "Lodged Spear" in out  # inner link text preserved
    assert "&lt;" not in out  # nothing rendered as literal markup
    assert "<ins" not in out  # disallowed tags stripped, not escaped
    assert "<del" not in out
    assert "<a" not in out
    assert "background-image" not in out  # disallowed-tag attributes dropped
    assert "href" not in out
    assert '<span class="iconsmall">' in out  # allowed span preserved


def test_sanitize_tooltip_html_strips_ascensiondb_placeholder_pseudo_tags():
    out = sanitize_tooltip_html(
        "Deals 4+<UNK: $ppl1> Plague damage and 437*$<scalingbp> Frost damage."
    )

    assert "&lt;" not in out
    assert "UNK" not in out
    assert "scalingbp" not in out
    assert "Plague damage" in out
    assert "Frost damage" in out
