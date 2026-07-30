from __future__ import annotations

import html
import re

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


def build_node_tooltip(node: TalentNode) -> GuideTooltip:
    # E0R.1 T5.1 AscensionDB sunset: a tooltip is always `normalized` from the client/Builder
    # description — no scraped-DB preference, no remote DB URL, no name-match confidence boost.
    text = node.description_text or node.name
    header = f"<strong>{html.escape(node.name)}</strong>"
    body = html.escape(text)
    return GuideTooltip(
        tooltip_id=f"spell:{node.spell_id}" if node.spell_id is not None else f"entry:{node.entry_id}",
        entry_id=node.entry_id,
        spell_id=node.spell_id,
        name=node.name,
        html=f"{header}<div>{body}</div>",
        text=text,
        db_url=None,
        source="normalized",
        source_confidence="medium" if node.description_text else "low",
        warnings=(),
    )


def sanitize_tooltip_html(value: str) -> str:
    text = re.sub(r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>", "", value, flags=re.I | re.S)
    text = re.sub(r"\s+on[a-zA-Z]+\s*=\s*(['\"]).*?\1", "", text)
    text = re.sub(r"\s+on[a-zA-Z]+\s*=\s*[^\s>]+", "", text)

    def replace_tag(match: re.Match[str]) -> str:
        slash, tag_name, attrs = match.group(1), match.group(2).lower(), match.group(3) or ""
        if tag_name not in _ALLOWED_TAGS:
            # Drop unknown/disallowed markup (e.g. legacy <ins>/<del>/<a> icon and spell-link tags,
            # and <UNK>/<scalingbp> scaling placeholders) rather than escaping it, which would
            # surface raw HTML as literal tooltip text.
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
