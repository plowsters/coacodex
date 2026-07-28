from __future__ import annotations

from pathlib import Path

from coa_meta.guide_tooltips import build_node_tooltip, sanitize_tooltip_html
from coa_meta.repository import TalentRepository


FIXTURES = Path(__file__).parent / "fixtures"


def test_build_node_tooltip_is_normalized_from_the_description():
    # E0R.1 T5.1 AscensionDB sunset: every tooltip is client-native — `normalized` from the node's
    # description, never a scraped-DB preference and never a remote DB URL.
    repo = TalentRepository.from_entries(FIXTURES / "meta_report_fixture.jsonl")
    node = repo.node_by_id(201)

    tooltip = build_node_tooltip(node)

    assert tooltip.tooltip_id == "spell:2001"
    assert tooltip.source == "normalized"
    assert tooltip.db_url is None
    assert node.description_text in tooltip.text
    assert tooltip.source_confidence == "medium"


def test_build_node_tooltip_without_description_falls_back_to_name_low_confidence():
    repo = TalentRepository.from_entries(FIXTURES / "meta_report_fixture.jsonl")
    node = repo.node_by_id(202)

    tooltip = build_node_tooltip(node)

    assert tooltip.tooltip_id == "spell:2002"
    assert tooltip.source == "normalized"
    assert tooltip.text  # description if present, else the node name — never empty


def test_sanitize_tooltip_html_removes_script_and_event_attributes():
    html = sanitize_tooltip_html('<span onclick="bad()">Safe</span><script>bad()</script>')

    assert "Safe" in html
    assert "onclick" not in html
    assert "script" not in html


def test_sanitize_tooltip_html_preserves_tables_without_event_attributes():
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


def test_sanitize_tooltip_html_strips_legacy_placeholder_pseudo_tags():
    out = sanitize_tooltip_html(
        "Deals 4+<UNK: $ppl1> Plague damage and 437*$<scalingbp> Frost damage."
    )

    assert "&lt;" not in out
    assert "UNK" not in out
    assert "scalingbp" not in out
    assert "Plague damage" in out
    assert "Frost damage" in out
