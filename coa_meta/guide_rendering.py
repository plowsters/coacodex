from __future__ import annotations

import html
import json
from typing import Any

from .guide_models import GuideSite, GuideSpec

ROLE_DISPLAY_ORDER = ("tank", "healer", "support", "caster_dps", "ranged_dps", "melee_dps")
REPO_URL = "https://github.com/plowsters/coa_meta_analyzer"
ISSUES_URL = "https://github.com/plowsters/coa_meta_analyzer/issues"
FRONT_PAGE_DISCLAIMER = (
    "Theorycrafting projections based on CoA Builder and Ascension data. "
    "Further accuracy tuning through combat logs/simming may be added if CoA stays online "
    "and pending CoA compatibility with AscensionLogs."
)
GITHUB_MARK_SVG = (
    '<svg viewBox="0 0 16 16" width="20" height="20" aria-hidden="true" fill="currentColor">'
    '<path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 '
    "0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01"
    "1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 "
    "0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 "
    "1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 "
    '3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"/>'
    "</svg>"
)

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
.front-disclaimer { margin-top: 16px; border: 1px solid rgba(245,197,66,.55); color: #ffe8a3; border-radius: 8px; padding: 12px 14px; background: rgba(245,197,66,.08); }
.role-filter-bar { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
.role-filter { appearance: none; border: 1px solid rgba(143,92,255,.45); border-radius: 999px; background: rgba(28,16,44,.9); color: var(--text); padding: 8px 13px; font: inherit; cursor: pointer; box-shadow: inset 0 0 12px rgba(143,92,255,.1); }
.role-filter:hover { border-color: var(--fel); box-shadow: 0 0 16px rgba(101,240,107,.18), inset 0 0 12px rgba(143,92,255,.1); }
.role-filter.is-active, .role-filter[aria-pressed="true"] { border-color: var(--fel); color: #061109; background: linear-gradient(135deg, var(--fel), #b6ff5f); box-shadow: 0 0 18px rgba(101,240,107,.28); }
.role-section { margin-top: 26px; }
.role-section[hidden] { display: none; }
.role-section-title { display: flex; align-items: center; gap: 10px; margin: 0 0 12px; color: var(--text); text-shadow: 0 0 14px rgba(143,92,255,.42); }
.empty-role { color: var(--muted); margin: 0; }
.guide-grid { display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); margin-top: 22px; }
.guide-card, .panel { border: 1px solid var(--border); background: rgba(19,11,30,.92); border-radius: 8px; padding: 18px; }
.spec-icon { display: inline-flex; width: 28px; height: 28px; vertical-align: middle; margin-right: 8px; border-radius: 6px; overflow: hidden; }
.spec-icon img { width: 100%; height: 100%; object-fit: cover; }
.spec-icon-mono { align-items: center; justify-content: center; background: rgba(143,92,255,.18); color: var(--text); font-size: 12px; }
.site-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 4px; }
.site-brand { font-weight: 600; color: var(--text); text-decoration: none; }
.github-link { color: var(--muted); display: inline-flex; transition: color .15s ease; }
.github-link:hover { color: var(--fel); }
.site-footer { margin-top: 32px; padding: 18px 4px; border-top: 1px solid rgba(143,92,255,.25); color: var(--muted); font-size: 13px; }
.site-footer a { color: var(--muted); }
.site-footer a:hover { color: var(--fel); }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px; border: 1px solid var(--border); border-radius: 999px; color: var(--muted); font-size: .85rem; }
.warning { border-color: rgba(245,197,66,.55); color: var(--warning); }
.chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }
.section-note { border: 1px solid rgba(245,197,66,.55); color: var(--warning); border-radius: 8px; padding: 10px; background: rgba(245,197,66,.08); }
.guide-nav { display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0; position: sticky; top: 0; padding: 10px 0; background: rgba(9,5,15,.9); backdrop-filter: blur(8px); }
.node-list { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.node-card { display: grid; grid-template-columns: 42px 1fr; gap: 10px; align-items: center; border: 1px solid rgba(101,240,107,.18); border-radius: 8px; padding: 10px; background: rgba(255,255,255,.03); }
.icon-frame { width: 42px; height: 42px; border-radius: 6px; border: 1px solid var(--fel); display: grid; place-items: center; color: var(--fel); background: rgba(101,240,107,.09); box-shadow: inset 0 0 12px rgba(101,240,107,.12); }
.icon-frame img { width: 100%; height: 100%; object-fit: cover; border-radius: 5px; }
.tree-toolbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 14px 0; }
.tree-toolbar select { background: var(--panel-2); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 7px 9px; }
.tree-scroll { overflow-x: auto; padding-bottom: 8px; }
.tree-build-panel[hidden] { display: none; }
.tree-groups { display: grid; gap: 18px; min-width: max-content; }
.tree-group, .passive-lane { min-width: max-content; }
.tree-group h3, .passive-lane h3 { margin: 0 0 8px; color: var(--fel); }
.talent-tree { position: relative; display: grid; grid-template-columns: repeat(var(--tree-cols), 72px); grid-template-rows: repeat(var(--tree-rows), 72px); gap: 22px; min-width: max-content; padding: 18px; border: 1px solid rgba(143,92,255,.28); border-radius: 8px; background: radial-gradient(circle at center, rgba(143,92,255,.10), rgba(9,5,15,.45)); }
.talent-tree.is-captured-layout { display: block; min-width: var(--tree-width); height: var(--tree-height); }
.talent-tree[hidden] { display: none; }
.passive-lane .talent-tree { display: flex; gap: 24px; align-items: center; min-height: 112px; }
.passive-lane .talent-tree.is-captured-layout { display: block; }
.tree-links { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; overflow: visible; }
.tree-links line { stroke: rgba(143,92,255,.45); stroke-width: 3; filter: drop-shadow(0 0 5px rgba(143,92,255,.35)); }
.tree-links line.is-selected { stroke: var(--fel); filter: drop-shadow(0 0 7px rgba(101,240,107,.55)); }
.tree-links line.is-available { stroke: var(--void); }
.tree-node { position: relative; z-index: 1; width: 64px; height: 64px; display: grid; place-items: center; border: 1px solid rgba(143,92,255,.5); border-radius: 50%; color: var(--text); background: rgba(19,11,30,.94); box-shadow: inset 0 0 16px rgba(143,92,255,.16); cursor: help; }
.tree-node img { width: 100%; height: 100%; object-fit: cover; border-radius: inherit; }
.is-captured-layout .tree-node { position: absolute; }
.passive-lane .tree-node { border-radius: 12px; }
.tree-node.shape-square { border-radius: 12px; }
.tree-node.shape-hex { clip-path: polygon(25% 4%, 75% 4%, 100% 50%, 75% 96%, 25% 96%, 0 50%); }
.tree-node.is-selected { border-color: var(--fel); box-shadow: 0 0 18px rgba(101,240,107,.42), inset 0 0 18px rgba(101,240,107,.16); }
.tree-node.is-free { border-color: rgba(101,240,107,.6); color: var(--fel); }
.tree-node.is-available { border-color: var(--void); box-shadow: 0 0 14px rgba(143,92,255,.34); }
.tree-node.is-gated, .tree-node.is-inactive { opacity: .54; filter: grayscale(.35); }
.tree-node.is-over-budget { border-color: var(--warning); box-shadow: 0 0 16px rgba(245,197,66,.28); }
.tree-rank { position: absolute; right: -7px; bottom: -7px; min-width: 22px; height: 22px; display: grid; place-items: center; border: 1px solid var(--border); border-radius: 999px; background: #09050f; font-size: .72rem; }
.leveling-path { margin-top: 14px; display: grid; gap: 8px; }
.leveling-path li { margin-bottom: 4px; color: var(--muted); }
.tooltip { position: fixed; z-index: 20; max-width: 360px; padding: 12px; border: 1px solid var(--void); border-radius: 8px; background: #09050f; box-shadow: 0 0 28px rgba(143,92,255,.25); }
.tooltip table { width: 100%; border-collapse: collapse; margin-top: 8px; }
.tooltip th, .tooltip td { border: 1px solid rgba(143,92,255,.3); padding: 4px 6px; text-align: left; vertical-align: top; }
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
    const buttons = Array.from(document.querySelectorAll("[data-role-filter]"));
    const roleButtons = buttons.filter(button => button.getAttribute("data-role-filter") !== "all");
    const allButton = buttons.find(button => button.getAttribute("data-role-filter") === "all");
    const selected = new Set(roleButtons.filter(button => button.getAttribute("aria-pressed") === "true").map(button => button.getAttribute("data-role-filter")));
    const clicked = filter.getAttribute("data-role-filter");
    if (clicked === "all") selected.clear();
    else if (selected.has(clicked)) selected.delete(clicked);
    else selected.add(clicked);
    const showAll = selected.size === 0;
    roleButtons.forEach(button => {
      const active = selected.has(button.getAttribute("data-role-filter"));
      button.setAttribute("aria-pressed", String(active));
      button.classList.toggle("is-active", active);
    });
    if (allButton) {
      allButton.setAttribute("aria-pressed", String(showAll));
      allButton.classList.toggle("is-active", showAll);
    }
    document.querySelectorAll("[data-role]").forEach(card => {
      const roles = (card.getAttribute("data-role") || "").split(/\\s+/).filter(Boolean);
      card.hidden = showAll ? false : !roles.some(role => selected.has(role));
    });
    document.querySelectorAll("[data-role-section]").forEach(section => {
      section.hidden = showAll ? false : !selected.has(section.getAttribute("data-role-section"));
    });
  });
  function parseJson(value, fallback) {
    try { return JSON.parse(value || ""); } catch (_error) { return fallback; }
  }
  function stateClass(state) {
    if (state === "selected" || state === "free" || state === "available" || state === "over_budget") return "is-" + state.replace("_", "-");
    if ((state || "").startsWith("gated_")) return "is-gated";
    return "is-inactive";
  }
  function applySnapshot(panel, tree, level) {
    const snapshots = parseJson(tree.getAttribute("data-tree-snapshots"), []);
    const snapshot = snapshots.find(item => String(item.level) === String(level)) || snapshots[snapshots.length - 1] || {};
    const selected = new Set((snapshot.selected_node_ids || []).map(String));
    const free = new Set((snapshot.free_node_ids || []).map(String));
    const available = new Set((snapshot.available_node_ids || []).map(String));
    const gated = new Map((snapshot.gated_nodes || []).map(item => [String(item.node_id), item.state]));
    tree.querySelectorAll("[data-tree-node-id]").forEach(node => {
      const id = node.getAttribute("data-tree-node-id");
      node.classList.remove("is-selected", "is-free", "is-available", "is-gated", "is-inactive", "is-over-budget");
      let state = "inactive";
      if (free.has(id)) state = "free";
      else if (selected.has(id)) state = "selected";
      else if (available.has(id)) state = "available";
      else if (gated.has(id)) state = gated.get(id);
      node.classList.add(stateClass(state));
      node.setAttribute("data-state", state);
    });
    const summary = panel.querySelector("[data-tree-budget-summary]");
    if (summary) summary.textContent = `AE ${snapshot.ae_spent || 0}/${snapshot.max_ae || 0} - TE ${snapshot.te_spent || 0}/${snapshot.max_te || 0}`;
    drawTreeLinks(tree);
  }
  function drawTreeLinks(tree) {
    const svg = tree.querySelector(".tree-links");
    if (!svg) return;
    const edges = parseJson(svg.getAttribute("data-tree-edges"), []);
    const canvas = svg.closest(".talent-tree") || tree;
    const treeRect = canvas.getBoundingClientRect();
    svg.innerHTML = "";
    edges.forEach(edge => {
      const source = canvas.querySelector(`[data-tree-node-id="${edge.source_id}"]`);
      const target = canvas.querySelector(`[data-tree-node-id="${edge.target_id}"]`);
      if (!source || !target) return;
      const a = source.getBoundingClientRect();
      const b = target.getBoundingClientRect();
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", String(a.left + a.width / 2 - treeRect.left));
      line.setAttribute("y1", String(a.top + a.height / 2 - treeRect.top));
      line.setAttribute("x2", String(b.left + b.width / 2 - treeRect.left));
      line.setAttribute("y2", String(b.top + b.height / 2 - treeRect.top));
      line.classList.add("is-" + (edge.state || "inactive"));
      svg.appendChild(line);
    });
  }
  function initTrees() {
    document.querySelectorAll("[data-guide-tree-panel]").forEach(panel => {
      const buildSelector = panel.querySelector("[data-tree-build-selector]");
      const levelSelector = panel.querySelector("[data-tree-level-selector]");
      function currentBuildPanel() {
        const id = buildSelector ? buildSelector.value : panel.querySelector("[data-tree-build-panel]")?.getAttribute("data-tree-build-panel");
        return panel.querySelector(`[data-tree-build-panel="${id}"]`) || panel.querySelector("[data-tree-build-panel]");
      }
      function refresh() {
        const activePanel = currentBuildPanel();
        panel.querySelectorAll("[data-tree-build-panel]").forEach(buildPanel => { buildPanel.hidden = buildPanel !== activePanel; });
        if (!activePanel) return;
        activePanel.querySelectorAll("[data-tree-kind]").forEach(tree => {
          applySnapshot(panel, tree, levelSelector ? levelSelector.value : tree.getAttribute("data-tree-level"));
        });
      }
      if (buildSelector) buildSelector.addEventListener("change", refresh);
      if (levelSelector) levelSelector.addEventListener("change", refresh);
      refresh();
    });
  }
  window.addEventListener("resize", () => document.querySelectorAll("[data-tree-kind]").forEach(drawTreeLinks));
  document.addEventListener("DOMContentLoaded", initTrees);
})();
"""


def _render_header(home_href: str = "index.html") -> str:
    return (
        '<header class="site-header">'
        f'<a class="site-brand" href="{_e(home_href)}">CoA Meta Guides</a>'
        f'<a class="github-link" href="{REPO_URL}" target="_blank" rel="noopener" '
        f'aria-label="View source on GitHub">{GITHUB_MARK_SVG}</a>'
        "</header>"
    )


def _render_footer(site: GuideSite) -> str:
    generated = _e(getattr(site, "generated_at", "") or "")
    generated_html = f" · Generated {generated}" if generated else ""
    return (
        '<footer class="site-footer">'
        "<p>© 2026 CoA Meta Analyzer · Fan-made theorycraft tool. "
        "Not affiliated with or endorsed by Project Ascension.</p>"
        f'<p><a href="{ISSUES_URL}" target="_blank" rel="noopener">Submit an issue</a> · '
        f'<a href="{REPO_URL}" target="_blank" rel="noopener">Source on GitHub</a>'
        f"{generated_html}</p>"
        "</footer>"
    )


def render_index_html(site: GuideSite) -> str:
    roles = _ordered_roles(site)
    filters = '<div class="role-filter-bar" aria-label="Filter guides by role">'
    filters += '<button class="role-filter is-active" data-role-filter="all" aria-pressed="true">All Roles</button>'
    filters += "".join(
        f'<button class="role-filter" data-role-filter="{_e(role)}" aria-pressed="false">{_e(_label(role))}</button>'
        for role in roles
    )
    filters += "</div>"
    role_sections = "".join(_render_role_section(role, [spec for spec in site.specs if role in _spec_roles(spec)]) for role in roles)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>CoA Meta Guides</title><link rel=\"stylesheet\" href=\"assets/guide.css\">"
        "</head><body><main class=\"site-shell\">"
        f"{_render_header()}"
        "<section class=\"hero\"><h1>CoA Meta Guides</h1>"
        "<p>Player-facing class and specialization guides for Conquest of Azeroth.</p>"
        f'<p class="front-disclaimer">{_e(FRONT_PAGE_DISCLAIMER)}</p></section>'
        f"<section class=\"panel\"><h2>Find Your Guide</h2>{filters}</section>"
        f"{role_sections}"
        f"{_render_footer(site)}"
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
        f"{_render_header(home_href='../index.html')}"
        f'<p><a href="../index.html">Back to guides</a></p><section class="hero" id="overview">'
        f"<h1>{_e(spec.class_name)} - {_e(spec.spec_name)}</h1><p>{_e(spec.summary)}</p>"
        f'{_role_chips(spec, tooltip_id=f"role:{spec.slug}")}</section>'
        f'<nav class="guide-nav">{nav}</nav>'
        f'<section class="panel" id="recommended-builds"><h2>Recommended Builds</h2>{builds}</section>'
        f"{_render_talent_tree_section(spec)}"
        f"{_render_rotation_section(spec)}"
        f"{_render_stats_section(spec)}"
        f"{_render_gear_section(spec)}"
        f'<section class="panel" id="abilities-and-talents"><h2>Abilities and Talents</h2><div class="node-list">{nodes}</div></section>'
        f"{warnings}<section class=\"panel\" id=\"data-notes\"><h2>Data Notes</h2><p>Generated: {_e(site.generated_at)}</p></section>"
        f"{_render_footer(site)}"
        f"{_tooltip_script(site)}<script src=\"../assets/guide.js\"></script>"
        "</main></body></html>"
    )


def _render_spec_icon(spec: GuideSpec, asset_prefix: str = "assets") -> str:
    asset = getattr(spec, "icon_asset", None)
    if asset and asset.href and not asset.missing:
        src = _asset_src(asset.href, asset_prefix)
        return f'<span class="spec-icon"><img src="{_e(src)}" alt="" loading="lazy"></span>'
    initials = "".join(word[:1] for word in spec.class_name.split()[:2]).upper() or spec.class_name[:2].upper()
    return f'<span class="spec-icon spec-icon-mono">{_e(initials)}</span>'


def _render_spec_card(spec: GuideSpec) -> str:
    warning = '<span class="chip warning">Warnings</span>' if spec.warning_count else ""
    role_values = " ".join(_spec_roles(spec))
    return (
        f'<article class="guide-card" data-role="{_e(role_values)}">'
        f"<h2>{_render_spec_icon(spec)} {_e(spec.class_name)} - {_e(spec.spec_name)}</h2>"
        f"<p>{_e(spec.summary)}</p><p>{_role_chips(spec)} {warning}</p>"
        f'<p><a href="{_e(spec.href)}">Open guide</a></p></article>'
    )


def _render_role_section(role: str, specs: list[GuideSpec]) -> str:
    if specs:
        cards = "".join(_render_spec_card(spec) for spec in sorted(specs, key=lambda item: (item.class_name, item.spec_name)))
        body = f'<div class="guide-grid">{cards}</div>'
    else:
        body = f'<p class="empty-role">No {_e(_label(role))} guides are available in the current report.</p>'
    return (
        f'<section class="role-section" data-role-section="{_e(role)}">'
        f'<h2 class="role-section-title">{_e(_label(role))}</h2>{body}</section>'
    )


def _ordered_roles(site: GuideSite) -> tuple[str, ...]:
    site_roles = {role for spec in site.specs for role in _spec_roles(spec)}
    extras = sorted(role for role in site_roles if role not in ROLE_DISPLAY_ORDER)
    return ROLE_DISPLAY_ORDER + tuple(extras)


def _render_build(build: Any) -> str:
    warning = '<span class="chip warning">Warnings</span>' if build.warnings else ""
    primary_index = build.primary_index if build.primary_index is not None else build.projected_dps_index
    primary_index_label = build.primary_index_label or "Projected Damage Index"
    return (
        '<article class="guide-card">'
        f"<h3>{_e(build.playstyle_label or build.label)}</h3>"
        f"<p>{_e(build.selection_reason or 'Strong current theorycraft result for this spec.')}</p>"
        f"<p><span class=\"chip\">{_e(build.reliability_label or build.confidence_label)} reliability</span> "
        f"<span class=\"chip\">{_e(build.performance_band or 'top theorycraft band')}</span> "
        f"<span class=\"chip\" data-tooltip-id=\"metric:primary_index\">{_e(primary_index_label)} {primary_index:.1f}</span> {warning}</p>"
        '<p><a href="#talents">View tree</a></p>'
        "</article>"
    )


def _spec_roles(spec: GuideSpec) -> tuple[str, ...]:
    primary_role = spec.primary_role or spec.role
    roles = spec.roles or tuple(dict.fromkeys((primary_role, *spec.secondary_roles)))
    if roles:
        return tuple(dict.fromkeys(str(role) for role in roles if role))
    return (spec.role,)


def _role_chips(spec: GuideSpec, *, tooltip_id: str = "") -> str:
    primary_role = spec.primary_role or spec.role
    chips: list[str] = []
    tooltip = f' data-tooltip-id="{_e(tooltip_id)}"' if tooltip_id else ""
    chips.append(f'<span class="chip" data-role-chip="{_e(primary_role)}"{tooltip}>{_e(_label(primary_role))}</span>')
    for role in spec.secondary_roles:
        if role == primary_role:
            continue
        chips.append(f'<span class="chip" data-role-chip="{_e(role)}">Secondary: {_e(_label(role))}</span>')
    return " ".join(chips)


def _render_rotation_section(spec: GuideSpec) -> str:
    build = spec.builds[0] if spec.builds else None
    guide = dict(build.rotation_guide or {}) if build else {}
    if guide:
        sections = []
        quick_priority = [
            *guide.get("priority_rules", []),
            *guide.get("core_loop", []),
        ]
        sections.append(_render_guide_rule_list("Quick Priority", quick_priority))
        sections.append(_render_guide_rule_list("Opener", guide.get("opener", [])))
        sections.append(_render_guide_rule_list("Core Loop", guide.get("core_loop", [])))
        sections.append(_render_guide_rule_list("Cooldowns", guide.get("cooldown_rules", [])))
        sections.append(_render_guide_rule_list("Procs and Statuses", guide.get("proc_rules", [])))
        role_rules = [
            *guide.get("defensive_rules", []),
            *guide.get("healing_rules", []),
            *guide.get("support_rules", []),
        ]
        sections.append(_render_guide_rule_list("Role Tools", role_rules))
        sections.append(_render_guide_rule_list("AoE Adjustments", guide.get("aoe_adjustments", [])))
        reliability = guide.get("reliability")
        summary = dict(guide.get("simulation_summary") or {})
        if reliability:
            sections.append(
                f'<p><span class="chip">{_e(reliability)} rotation reliability</span> '
                f'<span class="chip">{_e(str(summary.get("action_count", 0)))} simulated actions</span></p>'
            )
        warnings = guide.get("warnings") or []
        if warnings:
            sections.append(_render_loop_list("Rotation Warnings", warnings))
        body = "".join(section for section in sections if section)
        return f'<section class="panel" id="rotation"><h2>Rotation</h2>{body}</section>'

    loop = dict(build.rotation_loop or {}) if build else {}
    if not loop:
        return '<section class="panel" id="rotation"><h2>Rotation</h2><p>Use the generated priority notes as an early rotation scaffold.</p></section>'
    sections = [f'<p>{_e(loop.get("objective", ""))}</p>']
    sections.append(_render_loop_list("Core Loop", loop.get("core_loop", [])))
    sections.append(_render_loop_list("Opener and Setup", loop.get("opener", [])))
    sections.append(_render_loop_list("Cooldowns", loop.get("cooldowns", [])))
    role_steps = loop.get("defensive_or_support", [])
    if role_steps:
        sections.append(_render_loop_list("Defensive, Healing, or Support Priorities", role_steps))
    if loop.get("resource_rule"):
        sections.append(f'<p><strong>Resource Rule:</strong> {_e(loop["resource_rule"])}</p>')
    if loop.get("maintenance_rule"):
        sections.append(f'<p><strong>Maintenance Rule:</strong> {_e(loop["maintenance_rule"])}</p>')
    reliability = loop.get("reliability_label")
    if reliability:
        sections.append(f'<p><span class="chip">{_e(reliability)} rotation reliability</span></p>')
    return f'<section class="panel" id="rotation"><h2>Rotation</h2>{"".join(sections)}</section>'


def _render_guide_rule_list(title: str, rules: Any) -> str:
    values = [dict(rule) for rule in rules or [] if isinstance(rule, dict)]
    if not values:
        return ""
    rows = []
    for rule in values[:12]:
        ability = str(rule.get("ability_name") or "Ability")
        url = str(rule.get("db_url") or "")
        label = f'<a href="{_e(url)}">{_e(ability)}</a>' if url else _e(ability)
        text = str(rule.get("text") or f"Use {ability}.")
        condition = str(rule.get("condition") or "")
        condition_html = f' <span class="muted">({_e(condition)})</span>' if condition else ""
        rows.append(f"<li><strong>{label}</strong>: {_e(text)}{condition_html}</li>")
    return f"<h3>{_e(title)}</h3><ol>{''.join(rows)}</ol>"


def _render_stats_section(spec: GuideSpec) -> str:
    build = spec.builds[0] if spec.builds else None
    report = dict(build.stat_priority_report or {}) if build else {}
    if not report:
        return '<section class="panel warning" id="stats"><h2>Stats</h2><p>Stat priority is unavailable.</p></section>'
    disclaimer = report.get("disclaimer")
    warning = f'<p class="section-note">{_e(disclaimer)}</p>' if disclaimer else ""
    groups = []
    for group in report.get("groups", []):
        entries = "".join(
            f'<span class="chip" title="{_e(entry.get("reason", ""))}">'
            f'{_e(str(entry.get("stat", "")).replace("_", " ").title())}</span>'
            for entry in group.get("entries", [])
        )
        if entries:
            groups.append(
                f'<div><h3>{_e(group.get("label") or group.get("group_id") or "Stats")}</h3>'
                f'<div class="chip-row">{entries}</div></div>'
            )
    if not groups:
        groups.append("<p>Stat priority is unavailable.</p>")
    return f'<section class="panel" id="stats"><h2>Stats</h2>{warning}{"".join(groups)}</section>'


def _render_gear_section(spec: GuideSpec) -> str:
    build = spec.builds[0] if spec.builds else None
    report = dict(build.gear_recommendation_report or {}) if build else {}
    if not report:
        return '<section class="panel" id="weapons-and-armor"><h2>Weapons and Armor</h2><p>Gear targeting is unavailable.</p></section>'
    best = _render_type_group(
        "Best targets for this spec",
        tuple(report.get("best_weapon_types", [])) + tuple(report.get("best_armor_types", [])),
    )
    available = _render_type_group(
        "Available to this class",
        tuple(report.get("available_weapon_types", [])) + tuple(report.get("available_armor_types", [])),
    )
    warning_items = "".join(f"<li>{_e(warning)}</li>" for warning in report.get("warnings", []))
    warnings = f'<div class="section-note"><ul>{warning_items}</ul></div>' if warning_items else ""
    return (
        '<section class="panel" id="weapons-and-armor"><h2>Weapons and Armor</h2>'
        f"{best}{available}{warnings}</section>"
    )


def _render_type_group(title: str, values: tuple[str, ...]) -> str:
    unique_values = tuple(dict.fromkeys(value for value in values if value))
    if not unique_values:
        return f"<h3>{_e(title)}</h3><p>Unknown.</p>"
    chips = "".join(f'<span class="chip">{_e(value.replace("_", " ").title())}</span>' for value in unique_values)
    return f'<h3>{_e(title)}</h3><div class="chip-row">{chips}</div>'


def _render_loop_list(title: str, items: Any) -> str:
    values = [str(item) for item in items or [] if str(item)]
    if not values:
        return ""
    body = "".join(f"<li>{_e(item)}</li>" for item in values)
    return f"<h3>{_e(title)}</h3><ol>{body}</ol>"


def _render_talent_tree_section(spec: GuideSpec) -> str:
    tree_builds = [build for build in spec.builds if build.tree_panel or build.tree]
    if not tree_builds:
        return '<section class="panel" id="talents"><h2>Talents</h2><p>No talent tree data is available for this build.</p></section>'
    first_panel = tree_builds[0].tree_panel
    first_tree = _first_panel_tree(first_panel) if first_panel else tree_builds[0].tree
    assert first_tree is not None
    build_options = "".join(
        f'<option value="{_e(_build_tree_panel_id(build))}">{_e(build.label)}</option>'
        for build in tree_builds
    )
    levels = sorted(
        {
            snapshot.level
            for build in tree_builds
            for snapshot in _build_tree_snapshots(build)
        }
    )
    level_options = "".join(
        f'<option value="{level}"{" selected" if level == first_tree.level else ""}>Level {level}</option>'
        for level in levels
    )
    panels = "".join(
        _render_build_tree_panel(build, hidden=index > 0)
        for index, build in enumerate(tree_builds)
    )
    return (
        '<section class="panel" id="talents" data-guide-tree-panel>'
        "<h2>Talents</h2>"
        '<div class="tree-toolbar">'
        f'<label>Build <select data-tree-build-selector>{build_options}</select></label>'
        f'<label>Level <select data-tree-level-selector>{level_options}</select></label>'
        f'<span class="chip" data-tree-budget-summary>AE {first_tree.ae_spent}/{first_tree.max_ae} - TE {first_tree.te_spent}/{first_tree.max_te}</span>'
        "</div>"
        f'<div class="tree-scroll">{panels}</div>'
        "</section>"
    )


def _build_tree_panel_id(build: Any) -> str:
    if build.tree_panel:
        return build.tree_panel.tree_panel_id
    if build.tree:
        return build.tree.tree_id
    return ""


def _build_tree_snapshots(build: Any) -> tuple[Any, ...]:
    if build.tree_panel:
        return tuple(build.tree_panel.snapshots)
    if build.tree:
        return tuple(build.tree.snapshots)
    return tuple()


def _first_panel_tree(panel: Any) -> Any:
    for tree in panel.trees:
        if tree.nodes:
            return tree
    return panel.trees[0] if panel.trees else None


def _render_build_tree_panel(build: Any, *, hidden: bool) -> str:
    leveling_path = _render_leveling_path_for_build(build)
    if build.tree_panel:
        groups = "".join(_render_tree_group(tree) for tree in build.tree_panel.trees)
        warnings = "".join(f"<li>{_e(warning)}</li>" for warning in build.tree_panel.warnings)
        warning_html = f'<div class="section-note"><ul>{warnings}</ul></div>' if warnings else ""
        return (
            f'<div class="tree-build-panel" data-tree-build-panel="{_e(build.tree_panel.tree_panel_id)}"'
            f'{" hidden" if hidden else ""}>'
            f'<div class="tree-groups">{groups}</div>{leveling_path}{warning_html}</div>'
        )
    if build.tree:
        leveling_path = leveling_path or _render_leveling_path(build.tree)
        return (
            f'<div class="tree-build-panel" data-tree-build-panel="{_e(build.tree.tree_id)}"'
            f'{" hidden" if hidden else ""}>'
            f'{_render_tree(build.tree, hidden=False)}{leveling_path}</div>'
        )
    return ""


def _render_tree_group(tree: Any) -> str:
    group_class = "passive-lane" if tree.tree_kind == "level_passives" else "tree-group"
    return (
        f'<div class="{group_class}" data-tree-kind="{_e(tree.tree_kind)}" data-tree-id="{_e(tree.tree_id)}" '
        f'data-tree-level="{tree.level}" data-tree-snapshots="{_json_attr([snapshot.to_dict() for snapshot in tree.snapshots])}">'
        f'<h3>{_e(_tree_group_label(tree.tree_kind))}</h3>'
        f'{_render_tree_canvas(tree)}</div>'
    )


def _render_tree(tree: Any, *, hidden: bool) -> str:
    group = (
        f'<div class="tree-group" data-tree-kind="{_e(tree.tree_kind)}" data-tree-id="{_e(tree.tree_id)}" '
        f'data-tree-level="{tree.level}" data-tree-snapshots="{_json_attr([snapshot.to_dict() for snapshot in tree.snapshots])}">'
        f'{_render_tree_canvas(tree)}</div>'
    )
    return f'<div class="legacy-tree-wrapper"{" hidden" if hidden else ""}>{group}</div>'


def _render_tree_canvas(tree: Any) -> str:
    edges = _json_attr([edge.to_dict() for edge in tree.edges])
    nodes = "".join(_render_tree_node(node) for node in tree.nodes)
    captured = bool(tree.bounds)
    if captured:
        width = int(float(tree.bounds.get("width", 0) or max((node.x or 0) + (node.width or 64) for node in tree.nodes)))
        height = int(float(tree.bounds.get("height", 0) or max((node.y or 0) + (node.height or 64) for node in tree.nodes)))
        style = f"--tree-width: {width}px; --tree-height: {height}px"
        css_class = "talent-tree is-captured-layout"
    else:
        style = f"--tree-cols: {tree.cols}; --tree-rows: {tree.rows}"
        css_class = "talent-tree"
    return (
        f'<div class="{css_class}" style="{style}">'
        f'<svg class="tree-links" data-tree-edges="{edges}" aria-hidden="true"></svg>'
        f"{nodes}</div>"
    )


def _render_tree_node(node: Any) -> str:
    shape = "shape-square" if "square" in node.node_type.lower() else "shape-hex" if "hex" in node.node_type.lower() else "shape-circle"
    state_class = _tree_state_class(node.tree_state)
    label = _render_icon_content(node, "../assets")
    rank = f"{node.rank}/{node.max_rank}" if node.max_rank > 1 else str(node.rank or 1)
    style = _tree_node_style(node)
    return (
        f'<button class="tree-node {shape} {state_class}" data-tree-node-id="{node.entry_id}" '
        f'data-tooltip-id="{_e(node.tooltip_id)}" data-state="{_e(node.tree_state)}" '
        f'data-rank="{node.rank}" data-max-rank="{node.max_rank}" '
        f'style="{style}" '
        f'aria-label="{_e(node.name)}">'
        f'{label}<span class="tree-rank">{_e(rank)}</span></button>'
    )


def _tree_node_style(node: Any) -> str:
    if node.x is not None and node.y is not None:
        width = node.width if node.width is not None else 64
        height = node.height if node.height is not None else 64
        return f"left: {node.x}px; top: {node.y}px; width: {width}px; height: {height}px"
    return f"grid-column: {node.col + 1 if node.col is not None else 1}; grid-row: {node.row + 1 if node.row is not None else 1}"


def _tree_group_label(tree_kind: str) -> str:
    labels = {
        "ability_essence": "Ability Essence",
        "talent_essence": "Talent Essence",
        "level_passives": "Level Passives",
        "combined": "Talent Tree",
    }
    return labels.get(tree_kind, tree_kind.replace("_", " ").title())


def _render_leveling_path(tree_or_panel: Any) -> str:
    if hasattr(tree_or_panel, "trees"):
        candidate_nodes = [node for tree in tree_or_panel.trees for node in tree.nodes]
    else:
        candidate_nodes = list(tree_or_panel.nodes)
    selected = sorted(
        (node for node in candidate_nodes if node.selected or node.free),
        key=lambda item: (item.required_level, item.row or 0, item.col or 0, item.name),
    )
    if not selected:
        return ""
    items = "".join(
        f"<li><strong>{_e(node.name)}</strong> <span class=\"chip\">Level {node.required_level or 'when available'}</span></li>"
        for node in selected[:12]
    )
    return f'<div class="leveling-path"><h3>Leveling Path</h3><ol>{items}</ol></div>'


def _render_leveling_path_for_build(build: Any) -> str:
    path = dict(getattr(build, "leveling_path", None) or {})
    steps = [dict(step) for step in path.get("steps", []) if isinstance(step, dict)]
    if not steps:
        return ""
    items = []
    for step in steps:
        if step.get("event_type") == "deferred":
            continue
        level = step.get("level")
        essence = str(step.get("essence_kind", "")).replace("_", " ").title()
        name = step.get("name", "")
        reason = step.get("reason", "")
        items.append(
            f"<li><strong>Level {_e(level)}</strong> "
            f"<span class=\"chip\">{_e(essence)}</span> "
            f"{_e(name)}<br><span class=\"muted\">{_e(reason)}</span></li>"
        )
    if not items:
        return ""
    warnings = [
        warning
        for warning in path.get("warnings", [])
        if warning
    ]
    warning_html = ""
    if warnings:
        warning_html = "<ul>" + "".join(f"<li>{_e(warning)}</li>" for warning in warnings) + "</ul>"
    return f'<div class="leveling-path"><h3>Leveling Path</h3><ol>{"".join(items)}</ol>{warning_html}</div>'


def _render_node(node: Any) -> str:
    icon = _render_icon_content(node, "../assets")
    link = f'<a href="{_e(node.db_url)}" data-tooltip-id="{_e(node.tooltip_id)}">{_e(node.name)}</a>' if node.db_url else _e(node.name)
    return (
        '<article class="node-card">'
        f'<span class="icon-frame">{icon}</span><span>{link}<br>'
        f'<small>{_e(node.tab_name)} - {_e(node.essence_kind)} - Level {node.required_level}</small></span></article>'
    )


def _render_icon_content(node: Any, asset_prefix: str) -> str:
    asset = getattr(node, "asset", None)
    href = getattr(asset, "href", None)
    missing = bool(getattr(asset, "missing", True))
    if href and not missing:
        src = _asset_src(href, asset_prefix)
        return f'<img src="{_e(src)}" alt="" loading="lazy">'
    return f"<span>{_e(node.name[:2].upper())}</span>"


def _asset_src(href: str, asset_prefix: str) -> str:
    if href.startswith(("http://", "https://", "/", "../")):
        return href
    return f"{asset_prefix.rstrip('/')}/{href.lstrip('/')}"


def _tooltip_script(site: GuideSite) -> str:
    payload = {key: value.to_dict() for key, value in site.tooltips.items()}
    for spec in site.specs:
        provenance = dict(spec.role_provenance or {})
        evidence = ", ".join(str(item) for item in provenance.get("evidence", [])) or "No detailed evidence recorded."
        source = provenance.get("source", "unknown")
        confidence = provenance.get("confidence", "unknown")
        engine_role = provenance.get("engine_role", "unknown")
        payload[f"role:{spec.slug}"] = {
            "html": (
                "<strong>Role Source</strong>"
                f"<div>Source: {_e(source)}</div>"
                f"<div>Confidence: {_e(confidence)}</div>"
                f"<div>Engine profile: {_e(engine_role)}</div>"
                f"<div>Evidence: {_e(evidence)}</div>"
            ),
            "text": f"Role source {source}; confidence {confidence}; engine profile {engine_role}; evidence {evidence}",
        }
    payload["metric:projected_dps_index"] = {
        "html": "<strong>Projected DPS Index</strong><div>A relative theorycraft score, not observed DPS.</div>",
        "text": "A relative theorycraft score, not observed DPS.",
    }
    payload["metric:primary_index"] = {
        "html": (
            "<strong>Role-Specific Projected Index</strong>"
            "<div>A relative theorycraft score labeled for this spec's primary role. "
            "It is not observed logs or simulated output.</div>"
        ),
        "text": "A relative theorycraft score labeled for this spec's primary role; not observed logs or simulated output.",
    }
    return f"<script>window.COA_TOOLTIPS = {json.dumps(payload, sort_keys=True)};</script>"


def _anchor(value: str) -> str:
    return value.lower().replace(" ", "-")


def _label(value: str) -> str:
    labels = {
        "caster_dps": "Caster DPS",
        "melee_dps": "Melee DPS",
        "ranged_dps": "Ranged DPS",
    }
    if value in labels:
        return labels[value]
    return value.replace("_", " ").title()


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _json_attr(value: Any) -> str:
    return _e(json.dumps(value, sort_keys=True))


def _tree_state_class(state: str) -> str:
    if state in {"selected", "free", "available", "over_budget"}:
        return f"is-{state.replace('_', '-')}"
    if state.startswith("gated_"):
        return "is-gated"
    return "is-inactive"
