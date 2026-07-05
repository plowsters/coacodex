from __future__ import annotations

import html
import json
from typing import Any

from .guide_models import GuideSite, GuideSpec

GUIDE_CSS = """
:root {
  --bg: #09050f;
  --panel: #130b1e;
  --panel-2: #1c102c;
  --fel: #65f06b;
  --void: #8f5cff;
  --warning: #f5c542;
  --text: #f5f1ff;
  --muted: #bdb4d3;
  --border: rgba(143, 92, 255, 0.35);
}
* { box-sizing: border-box; }
body { margin: 0; font-family: Inter, system-ui, sans-serif; background: radial-gradient(circle at top, #24113b 0, var(--bg) 42rem); color: var(--text); }
a { color: var(--fel); }
.site-shell { max-width: 1280px; margin: 0 auto; padding: 28px; }
.hero { padding: 28px; border: 1px solid var(--border); background: linear-gradient(135deg, rgba(101,240,107,.12), rgba(143,92,255,.13)); border-radius: 10px; box-shadow: 0 0 32px rgba(101,240,107,.08); }
.guide-grid { display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); margin-top: 22px; }
.guide-card, .panel { border: 1px solid var(--border); background: rgba(19,11,30,.92); border-radius: 8px; padding: 18px; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px; border: 1px solid var(--border); border-radius: 999px; color: var(--muted); font-size: .85rem; }
.warning { border-color: rgba(245,197,66,.55); color: var(--warning); }
.guide-nav { display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0; position: sticky; top: 0; padding: 10px 0; background: rgba(9,5,15,.9); backdrop-filter: blur(8px); }
.node-list { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.node-card { display: grid; grid-template-columns: 42px 1fr; gap: 10px; align-items: center; border: 1px solid rgba(101,240,107,.18); border-radius: 8px; padding: 10px; background: rgba(255,255,255,.03); }
.icon-frame { width: 42px; height: 42px; border-radius: 6px; border: 1px solid var(--fel); display: grid; place-items: center; color: var(--fel); background: rgba(101,240,107,.09); box-shadow: inset 0 0 12px rgba(101,240,107,.12); }
.tooltip { position: fixed; z-index: 20; max-width: 360px; padding: 12px; border: 1px solid var(--void); border-radius: 8px; background: #09050f; box-shadow: 0 0 28px rgba(143,92,255,.25); }
@media (max-width: 720px) { .site-shell { padding: 16px; } .hero { padding: 20px; } }
"""

GUIDE_JS = """
(() => {
  const tooltipData = window.COA_TOOLTIPS || {};
  let active;
  function removeTooltip() {
    if (active) active.remove();
    active = null;
  }
  function showTooltip(target) {
    const id = target.getAttribute("data-tooltip-id");
    const tip = tooltipData[id];
    if (!tip) return;
    removeTooltip();
    active = document.createElement("div");
    active.className = "tooltip";
    active.innerHTML = tip.html || tip.text || "";
    document.body.appendChild(active);
    const rect = target.getBoundingClientRect();
    active.style.left = Math.min(rect.left, window.innerWidth - active.offsetWidth - 16) + "px";
    active.style.top = Math.min(rect.bottom + 8, window.innerHeight - active.offsetHeight - 16) + "px";
  }
  document.addEventListener("mouseover", event => {
    const target = event.target.closest("[data-tooltip-id]");
    if (target) showTooltip(target);
  });
  document.addEventListener("mouseout", event => {
    if (event.target.closest("[data-tooltip-id]")) removeTooltip();
  });
  document.addEventListener("click", event => {
    const filter = event.target.closest("[data-role-filter]");
    if (!filter) return;
    const role = filter.getAttribute("data-role-filter");
    document.querySelectorAll("[data-role]").forEach(card => {
      card.hidden = role !== "all" && card.getAttribute("data-role") !== role;
    });
  });
})();
"""


def render_index_html(site: GuideSite) -> str:
    roles = sorted({spec.role for spec in site.specs})
    filters = '<button data-role-filter="all">All</button>' + "".join(
        f'<button data-role-filter="{_e(role)}">{_e(_label(role))}</button>' for role in roles
    )
    cards = "".join(_render_spec_card(spec) for spec in site.specs)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>CoA Meta Guides</title><link rel=\"stylesheet\" href=\"assets/guide.css\">"
        "</head><body><main class=\"site-shell\">"
        "<section class=\"hero\"><h1>CoA Meta Guides</h1>"
        "<p>Player-facing theorycraft guides generated from normalized Conquest of Azeroth builder data.</p></section>"
        f"<section class=\"panel\"><h2>Find Your Guide</h2>{filters}</section>"
        f"<section class=\"guide-grid\">{cards}</section>"
        f"{_tooltip_script(site)}<script src=\"assets/guide.js\"></script>"
        "</main></body></html>"
    )


def render_spec_html(site: GuideSite, spec: GuideSpec) -> str:
    nav = "".join(f'<a href="#{_anchor(section)}">{_e(section)}</a>' for section in spec.sections)
    warnings = ""
    if spec.warnings:
        items = "".join(f"<li>{_e(warning)}</li>" for warning in spec.warnings)
        warnings = f'<section class="panel warning" id="warnings"><h2>Warnings</h2><ul>{items}</ul></section>'
    nodes = "".join(_render_node(node) for node in spec.nodes)
    builds = "".join(_render_build(build) for build in spec.builds)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{_e(spec.class_name)} {_e(spec.spec_name)} Guide</title>"
        "<link rel=\"stylesheet\" href=\"../assets/guide.css\"></head><body><main class=\"site-shell\">"
        f'<p><a href="../index.html">Back to guides</a></p><section class="hero" id="overview">'
        f"<h1>{_e(spec.class_name)} - {_e(spec.spec_name)}</h1><p>{_e(spec.summary)}</p>"
        f'<span class="chip">{_e(_label(spec.role))}</span> <span class="chip">{_e(spec.confidence_label)} confidence</span></section>'
        f'<nav class="guide-nav">{nav}</nav>'
        f'<section class="panel" id="recommended-builds"><h2>Recommended Builds</h2><p>Early theorycraft picks.</p>{builds}</section>'
        '<section class="panel" id="talents"><h2>Talents</h2><p>Interactive tree view arrives in M1.10C.</p></section>'
        '<section class="panel" id="rotation"><h2>Rotation</h2><p>Use the generated priority notes as an early rotation scaffold.</p></section>'
        '<section class="panel warning" id="stats"><h2>Stats</h2><p>Stat priorities are early theorycraft until simulations or combat logs are available.</p></section>'
        '<section class="panel" id="weapons-and-armor"><h2>Weapons and Armor</h2><p>Gear targeting is low confidence until item data is complete.</p></section>'
        f'<section class="panel" id="abilities-and-talents"><h2>Abilities and Talents</h2><div class="node-list">{nodes}</div></section>'
        f"{warnings}<section class=\"panel\" id=\"data-notes\"><h2>Data Notes</h2><p>Generated: {_e(site.generated_at)}</p></section>"
        f"{_tooltip_script(site)}<script src=\"../assets/guide.js\"></script>"
        "</main></body></html>"
    )


def _render_spec_card(spec: GuideSpec) -> str:
    warning = '<span class="chip warning">Warnings</span>' if spec.warning_count else ""
    return (
        f'<article class="guide-card" data-role="{_e(spec.role)}">'
        f"<h2>{_e(spec.class_name)} - {_e(spec.spec_name)}</h2>"
        f"<p>{_e(spec.summary)}</p><p><span class=\"chip\">{_e(_label(spec.role))}</span> "
        f"<span class=\"chip\">{_e(spec.confidence_label)} confidence</span> {warning}</p>"
        f'<p><a href="{_e(spec.href)}">Open guide</a></p></article>'
    )


def _render_build(build: Any) -> str:
    return (
        '<article class="guide-card">'
        f"<h3>{_e(build.label)}</h3><p><span class=\"chip\">{_e(build.confidence_label)} confidence</span> "
        f"<span class=\"chip\" data-tooltip-id=\"metric:projected_dps_index\">Projected Index {build.projected_dps_index:.1f}</span></p>"
        "</article>"
    )


def _render_node(node: Any) -> str:
    icon = node.name[:2].upper()
    link = f'<a href="{_e(node.db_url)}" data-tooltip-id="{_e(node.tooltip_id)}">{_e(node.name)}</a>' if node.db_url else _e(node.name)
    return (
        '<article class="node-card">'
        f'<span class="icon-frame">{_e(icon)}</span><span>{link}<br>'
        f'<small>{_e(node.tab_name)} - {_e(node.essence_kind)} - Level {node.required_level}</small></span></article>'
    )


def _tooltip_script(site: GuideSite) -> str:
    payload = {key: value.to_dict() for key, value in site.tooltips.items()}
    payload["metric:projected_dps_index"] = {
        "html": "<strong>Projected DPS Index</strong><div>A relative theorycraft score, not observed DPS.</div>",
        "text": "A relative theorycraft score, not observed DPS.",
    }
    return f"<script>window.COA_TOOLTIPS = {json.dumps(payload, sort_keys=True)};</script>"


def _anchor(value: str) -> str:
    return value.lower().replace(" ", "-")


def _label(value: str) -> str:
    return value.replace("_", " ").title()


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)
