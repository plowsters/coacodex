from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from .domain import TalentNode
from .guide_models import GuideTooltip

_ALLOWED_TAGS = {
    "b",
    "br",
    "div",
    "em",
    "i",
    "p",
    "small",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
}


def ascension_spell_url(spell_id: int | None) -> None:
    # E0R AscensionDB sunset: guide nodes no longer link out to db.ascension.gg. Kept as a no-op returning
    # None so callers (guide_tree, build_node_tooltip) keep a stable signature and produce no remote URL.
    return None


def load_db_tooltip_rows(path: Path | str | None) -> dict[int, dict[str, Any]]:
    if path is None:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}
    rows: dict[int, dict[str, Any]] = {}
    for line in file_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("kind") == "spell" and row.get("status") == "matched":
            spell_id = int(row.get("spell_id") or row["id"])
            rows[spell_id] = row
    return rows


def build_node_tooltip(node: TalentNode, db_rows: dict[int, dict[str, Any]]) -> GuideTooltip:
    db_row = db_rows.get(node.spell_id or -1)
    if db_row:
        text = str(db_row.get("tooltip_text") or node.description_text or node.name)
        tooltip_html = sanitize_tooltip_html(str(db_row.get("tooltip_html") or ""))
        source = "ascension_db"
        confidence = "high" if db_row.get("name_match") else "medium"
        warnings = () if db_row.get("name_match") else ("db_name_mismatch",)
    else:
        text = node.description_text or node.name
        tooltip_html = html.escape(text)
        source = "normalized"
        confidence = "medium" if node.description_text else "low"
        warnings = ()

    header = f"<strong>{html.escape(node.name)}</strong>"
    body = tooltip_html if tooltip_html else html.escape(text)
    return GuideTooltip(
        tooltip_id=f"spell:{node.spell_id}" if node.spell_id is not None else f"entry:{node.entry_id}",
        entry_id=node.entry_id,
        spell_id=node.spell_id,
        name=node.name,
        html=f"{header}<div>{body}</div>",
        text=text,
        db_url=ascension_spell_url(node.spell_id),
        source=source,
        source_confidence=confidence,
        warnings=warnings,
    )


def sanitize_tooltip_html(value: str) -> str:
    text = re.sub(r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>", "", value, flags=re.I | re.S)
    text = re.sub(r"\s+on[a-zA-Z]+\s*=\s*(['\"]).*?\1", "", text)
    text = re.sub(r"\s+on[a-zA-Z]+\s*=\s*[^\s>]+", "", text)

    def replace_tag(match: re.Match[str]) -> str:
        slash, tag_name, attrs = match.group(1), match.group(2).lower(), match.group(3) or ""
        if tag_name not in _ALLOWED_TAGS:
            # Drop unknown/disallowed markup (e.g. AscensionDB <ins>/<del>/<a> icon and
            # spell-link tags, and <UNK>/<scalingbp> scaling placeholders) rather than
            # escaping it, which would surface raw HTML as literal tooltip text.
            return ""
        if slash:
            return f"</{tag_name}>"
        if tag_name == "span":
            class_match = re.search(r"class\s*=\s*([\"'])(.*?)\1", attrs, flags=re.I)
            if class_match:
                safe_class = html.escape(class_match.group(2), quote=True)
                return f'<span class="{safe_class}">'
        return f"<{tag_name}>"

    return re.sub(r"<\s*(/?)\s*([a-zA-Z0-9]+)([^>]*)>", replace_tag, text)
