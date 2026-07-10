from __future__ import annotations

import html
import json
from typing import Any

from .guide_models import GuideSite, GuideSpec

ROLE_DISPLAY_ORDER = ("tank", "healer", "support", "caster_dps", "ranged_dps", "melee_dps")
REPO_URL = "https://github.com/plowsters/coacodex"
ISSUES_URL = "https://github.com/plowsters/coacodex/issues"
FRONT_PAGE_DISCLAIMER = (
    "Theorycrafting projections based on CoA Builder and Ascension data. "
    "Further accuracy tuning through combat logs/simming may be added if CoA stays online "
    "and pending CoA compatibility with AscensionLogs."
)
GITHUB_MARK_SVG = (
    '<svg viewBox="0 0 16 16" width="19" height="19" aria-hidden="true" fill="currentColor">'
    '<path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 '
    "0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01"
    "1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 "
    "0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 "
    "1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 "
    '3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"/>'
    "</svg>"
)
DIAMOND = '<span class="diamond" aria-hidden="true"></span>'
HEAD_RULE = '<span class="head-rule" aria-hidden="true"></span>'

GUIDE_CSS = """
@font-face { font-family: "Cinzel"; font-weight: 600; font-display: swap; src: url("fonts/Cinzel-600.woff2") format("woff2"); }
@font-face { font-family: "Cinzel"; font-weight: 700; font-display: swap; src: url("fonts/Cinzel-700.woff2") format("woff2"); }
@font-face { font-family: "Cinzel"; font-weight: 900; font-display: swap; src: url("fonts/Cinzel-900.woff2") format("woff2"); }
@font-face { font-family: "Barlow"; font-weight: 400; font-display: swap; src: url("fonts/Barlow-400.woff2") format("woff2"); }
@font-face { font-family: "Barlow"; font-weight: 500; font-display: swap; src: url("fonts/Barlow-500.woff2") format("woff2"); }
@font-face { font-family: "Barlow"; font-weight: 600; font-display: swap; src: url("fonts/Barlow-600.woff2") format("woff2"); }
@font-face { font-family: "Barlow"; font-weight: 700; font-display: swap; src: url("fonts/Barlow-700.woff2") format("woff2"); }
@font-face { font-family: "JetBrains Mono"; font-weight: 500; font-display: swap; src: url("fonts/JetBrainsMono-500.woff2") format("woff2"); }
@font-face { font-family: "JetBrains Mono"; font-weight: 700; font-display: swap; src: url("fonts/JetBrainsMono-700.woff2") format("woff2"); }
:root {
  --bg: #08060f;
  --panel: rgba(17,11,28,.72);
  --panel-solid: rgba(14,10,23,.92);
  --panel-2: rgba(9,6,16,.85);
  --text: #f4f1fb;
  --muted: #a99fc4;
  --dim: #8b81a6;
  --gold: #ffcf5c;
  --gold-rgb: 255,207,92;
  --gold-text: #ffe6a6;
  --lead: #6cf06b;
  --lead-bright: #b7ff6a;
  --lead-rgb: 108,240,107;
  --accent: #9a6bff;
  --accent-rgb: 154,107,255;
  --line: rgba(108,240,107,.24);
  --bevel: polygon(0 13px,13px 0,calc(100% - 13px) 0,100% 13px,100% calc(100% - 13px),calc(100% - 13px) 100%,13px 100%,0 calc(100% - 13px));
  --bevel-sm: polygon(0 7px,7px 0,calc(100% - 7px) 0,100% 7px,100% calc(100% - 7px),calc(100% - 7px) 100%,7px 100%,0 calc(100% - 7px));
}
:root[data-theme="void"] {
  --lead: #a879ff;
  --lead-bright: #cbb0ff;
  --lead-rgb: 168,121,255;
  --accent: #6cf06b;
  --accent-rgb: 108,240,107;
  --line: rgba(168,121,255,.30);
}
* { box-sizing: border-box; }
body {
  margin: 0; font-family: Barlow, system-ui, sans-serif; font-size: 16px; line-height: 1.55; color: var(--text);
  background:
    radial-gradient(1300px 640px at 50% -8%, rgba(var(--lead-rgb),.14), transparent 60%),
    radial-gradient(1000px 560px at 90% 2%, rgba(var(--accent-rgb),.12), transparent 62%),
    radial-gradient(900px 700px at 6% 34%, rgba(var(--accent-rgb),.08), transparent 60%),
    var(--bg);
}
body::before { content: ""; position: fixed; inset: 0; z-index: -1; pointer-events: none; background: radial-gradient(circle at 50% 42%, transparent 58%, rgba(0,0,0,.55) 100%); mix-blend-mode: multiply; }
h1, h2, h3, h4, h5, h6 { font-family: Cinzel, serif; }
.mono, .tree-rank { font-family: "JetBrains Mono", monospace; }
a { color: var(--lead); text-decoration: none; }
a:hover { color: var(--lead-bright); }
button { font: inherit; color: inherit; background: none; border: none; cursor: pointer; }
::selection { background: rgba(var(--lead-rgb),.32); color: #fff; }
:focus-visible { outline: 2px solid var(--gold); outline-offset: 3px; }
::-webkit-scrollbar { width: 12px; height: 12px; }
::-webkit-scrollbar-track { background: rgba(0,0,0,.3); }
::-webkit-scrollbar-thumb { background: rgba(var(--lead-rgb),.35); border: 3px solid transparent; background-clip: padding-box; }
::-webkit-scrollbar-thumb:hover { background: rgba(var(--lead-rgb),.6); border: 3px solid transparent; background-clip: padding-box; }
@keyframes coaPulse { 0%,100% { box-shadow: 0 0 0 1px rgba(var(--lead-rgb),.55), 0 0 14px rgba(var(--lead-rgb),.45), inset 0 0 12px rgba(var(--lead-rgb),.22); } 50% { box-shadow: 0 0 0 1px rgba(var(--lead-rgb),.8), 0 0 26px rgba(var(--lead-rgb),.75), inset 0 0 16px rgba(var(--lead-rgb),.34); } }
@keyframes coaFlow { to { stroke-dashoffset: -28; } }
@keyframes coaDrift { 0%,100% { transform: translate3d(0,0,0) scale(1); opacity: .8; } 50% { transform: translate3d(2%,-3%,0) scale(1.08); opacity: 1; } }
.site-shell { position: relative; z-index: 2; }
.site-header { position: sticky; top: 0; z-index: 40; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px clamp(16px,4vw,40px); background: linear-gradient(180deg, rgba(8,6,15,.94), rgba(8,6,15,.72)); backdrop-filter: blur(10px); border-bottom: 1px solid var(--line); }
.site-brand { display: inline-flex; align-items: center; gap: 11px; color: var(--text); }
.site-brand:hover { color: var(--text); }
.brand-sigil { width: 30px; height: 30px; display: grid; place-items: center; clip-path: polygon(50% 0,100% 25%,100% 75%,50% 100%,0 75%,0 25%); background: linear-gradient(135deg, var(--lead), var(--accent)); box-shadow: 0 0 16px rgba(var(--lead-rgb),.5); }
.brand-sigil > span { width: 22px; height: 22px; display: grid; place-items: center; clip-path: polygon(50% 0,100% 25%,100% 75%,50% 100%,0 75%,0 25%); background: var(--bg); color: var(--lead); font-family: Cinzel, serif; font-weight: 900; font-size: 13px; }
.brand-word { font-family: Cinzel, serif; font-weight: 700; letter-spacing: .14em; font-size: 14px; text-transform: uppercase; }
.brand-word span { color: var(--lead); }
.site-nav { display: flex; align-items: center; gap: 18px; }
.all-guides { color: var(--muted); font-size: 13px; font-weight: 600; letter-spacing: .04em; }
.all-guides:hover { color: var(--lead); }
.github-link { color: var(--muted); display: inline-flex; transition: color .15s ease; }
.github-link:hover { color: var(--lead); }
.theme-toggle { display: inline-flex; align-items: center; gap: 0; padding: 3px; background: var(--panel-2); clip-path: var(--bevel-sm); border: 1px solid var(--line); }
.theme-btn { display: inline-flex; align-items: center; gap: 7px; padding: 6px 14px; font-size: 13px; font-weight: 700; letter-spacing: .04em; clip-path: var(--bevel-sm); color: var(--muted); background: transparent; transition: all .18s; }
.theme-btn[aria-pressed="true"] { color: #0a0614; background: linear-gradient(135deg, var(--lead), var(--lead-bright)); box-shadow: 0 0 14px rgba(var(--lead-rgb),.4); }
.theme-dot { width: 9px; height: 9px; display: inline-block; clip-path: polygon(50% 0,100% 50%,50% 100%,0 50%); }
.theme-dot-fel { background: #6cf06b; box-shadow: 0 0 8px #6cf06b; }
.theme-dot-void { background: #a879ff; box-shadow: 0 0 8px #a879ff; }
.hero { position: relative; overflow: hidden; max-width: 1320px; margin: 0 auto; padding: clamp(34px,6vw,72px) clamp(16px,4vw,40px) clamp(20px,3vw,30px); }
.hero > * { position: relative; z-index: 1; }
.hero-glow { position: absolute; top: -30px; left: 38%; width: min(560px,70%); height: 460px; z-index: 0; pointer-events: none; background: radial-gradient(circle at 50% 40%, rgba(var(--lead-rgb),.2), transparent 62%); filter: blur(8px); animation: coaDrift 12s ease-in-out infinite; }
.hero-kicker { margin: 0 0 12px; font-family: "JetBrains Mono", monospace; font-size: 12.5px; letter-spacing: .34em; text-transform: uppercase; color: var(--lead); }
.hero-title { margin: 0; font-weight: 900; font-size: clamp(40px,7vw,80px); line-height: .94; letter-spacing: .01em; text-shadow: 0 0 34px rgba(var(--lead-rgb),.4); }
.hero-title span { color: var(--lead); }
.hero-sub { margin: 16px 0 0; max-width: 60ch; font-size: 18px; color: var(--muted); }
.front-disclaimer { margin: 18px 0 0; max-width: 80ch; padding: 12px 16px; background: rgba(var(--gold-rgb),.08); border: 1px solid rgba(var(--gold-rgb),.4); clip-path: var(--bevel-sm); color: var(--gold-text); font-size: 13.5px; }
.stat-line { margin: 16px 0 0; font-family: "JetBrains Mono", monospace; font-size: 12.5px; letter-spacing: .02em; color: var(--dim); }
.role-filter-bar { position: sticky; top: 56px; z-index: 35; background: linear-gradient(180deg, rgba(8,6,15,.96), rgba(8,6,15,.8)); backdrop-filter: blur(9px); border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.role-filter-row { max-width: 1320px; margin: 0 auto; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 12px clamp(16px,4vw,40px); }
.role-filter-label { font-family: "JetBrains Mono", monospace; font-size: 11px; letter-spacing: .16em; text-transform: uppercase; color: var(--dim); margin-right: 4px; }
.role-filter { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; font-size: 13px; font-weight: 600; letter-spacing: .02em; clip-path: var(--bevel-sm); border: 1px solid var(--line); color: var(--muted); background: var(--panel-2); transition: all .16s; }
.role-filter:hover { border-color: var(--lead); color: var(--text); }
.role-filter.is-active, .role-filter[aria-pressed="true"] { border-color: var(--lead); color: #0a0614; background: linear-gradient(135deg, var(--lead), var(--lead-bright)); box-shadow: 0 0 14px rgba(var(--lead-rgb),.3); }
.site-main { max-width: 1320px; margin: 0 auto; padding: clamp(22px,3vw,40px) clamp(16px,4vw,40px) 30px; display: grid; gap: clamp(30px,4vw,48px); grid-template-columns: minmax(0,1fr); }
.role-section { scroll-margin-top: 128px; min-width: 0; }
.role-section[hidden] { display: none; }
.section-head { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
.section-head h2 { margin: 0; font-weight: 800; font-size: clamp(21px,2.8vw,29px); letter-spacing: .05em; color: var(--text); }
.section-count { font-family: "JetBrains Mono", monospace; font-size: 12px; color: var(--dim); }
.diamond { flex: 0 0 auto; width: 11px; height: 11px; clip-path: polygon(50% 0,100% 50%,50% 100%,0 50%); background: var(--lead); box-shadow: 0 0 10px var(--lead); }
.head-rule { flex: 1; height: 1px; background: linear-gradient(90deg, var(--lead), transparent); }
.head-rule-dim { background: linear-gradient(90deg, var(--line), transparent); }
.empty-role { color: var(--muted); margin: 0; }
.guide-grid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fill, minmax(min(300px,100%),1fr)); }
.guide-card { position: relative; clip-path: var(--bevel); background: linear-gradient(150deg, rgba(var(--lead-rgb),.4), rgba(var(--accent-rgb),.28)); padding: 1.5px; transition: transform .16s ease; }
.guide-card[hidden] { display: none; }
.frame-gold { background: linear-gradient(150deg, rgba(var(--gold-rgb),.45), rgba(var(--accent-rgb),.35)); }
.card-inner { position: relative; display: flex; flex-direction: column; clip-path: var(--bevel); background: linear-gradient(165deg, var(--panel-solid), var(--panel-2)); padding: 18px 20px; height: 100%; color: var(--text); overflow: hidden; }
a.card-inner:hover { color: var(--text); }
.spec-card:hover { transform: translateY(-2px); }
.spec-card-head { display: flex; align-items: center; gap: 13px; }
.spec-icon, .spec-hero-icon { flex: 0 0 auto; display: grid; place-items: center; clip-path: polygon(50% 0,100% 25%,100% 75%,50% 100%,0 75%,0 25%); background: linear-gradient(150deg, var(--lead), var(--accent)); }
.spec-icon { width: 52px; height: 58px; box-shadow: 0 0 16px rgba(var(--lead-rgb),.35); }
.spec-icon-core { display: grid; place-items: center; clip-path: polygon(50% 0,100% 25%,100% 75%,50% 100%,0 75%,0 25%); background: var(--panel-2); overflow: hidden; }
.spec-icon .spec-icon-core { width: 46px; height: 51px; }
.spec-icon-core img { width: 100%; height: 100%; object-fit: cover; }
.spec-icon-mono { color: var(--text); font-family: Cinzel, serif; font-weight: 700; font-size: 13px; }
.spec-card-title { min-width: 0; }
.spec-card-title h3 { margin: 0; font-weight: 700; font-size: 18px; color: var(--text); line-height: 1.15; }
.spec-card-class { margin: 2px 0 0; font-family: "JetBrains Mono", monospace; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--lead); }
.spec-card-summary { margin: 14px 0 0; font-size: 13.5px; color: var(--muted); flex: 1; }
.spec-card .chip-row { margin: 14px 0 0; }
.spec-card-cta { display: flex; align-items: center; justify-content: space-between; margin-top: 16px; padding-top: 13px; border-top: 1px solid var(--line); }
.cta-label { font-family: "JetBrains Mono", monospace; font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: var(--lead); font-weight: 700; }
.cta-arrow { color: var(--lead); font-size: 18px; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border: 1px solid var(--line); clip-path: var(--bevel-sm); background: var(--panel-2); color: var(--muted); font-size: 12.5px; font-weight: 600; letter-spacing: .02em; }
.chip-primary { border-color: rgba(var(--lead-rgb),.5); color: var(--lead); background: rgba(var(--lead-rgb),.08); cursor: help; }
.chip-dot { width: 8px; height: 8px; flex: 0 0 auto; clip-path: polygon(50% 0,100% 50%,50% 100%,0 50%); background: var(--lead); }
.chip.warning { border-color: rgba(var(--gold-rgb),.55); color: var(--gold-text); background: rgba(var(--gold-rgb),.09); }
.weapon-chip { font-family: "JetBrains Mono", monospace; font-size: 12px; }
.chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; align-items: center; }
.spec-hero .hero-kicker { letter-spacing: .32em; margin-bottom: 14px; }
.spec-hero-row { display: flex; flex-wrap: wrap; align-items: center; gap: clamp(18px,3vw,34px); }
.spec-hero-icon { width: 112px; height: 124px; box-shadow: 0 0 40px rgba(var(--lead-rgb),.5); }
.spec-hero-icon .spec-icon-core { width: 102px; height: 113px; }
.spec-hero-icon img { opacity: .92; }
.spec-hero-text { flex: 1 1 340px; min-width: 280px; }
.spec-hero-text h1 { margin: 0; font-weight: 900; font-size: clamp(44px,7.5vw,86px); line-height: .92; letter-spacing: .01em; color: var(--text); text-shadow: 0 0 34px rgba(var(--lead-rgb),.42); }
.spec-hero-class { margin: 6px 0 0; font-family: Cinzel, serif; font-weight: 600; font-size: clamp(17px,2.4vw,24px); letter-spacing: .16em; text-transform: uppercase; color: var(--muted); }
.spec-hero .chip-row { margin: 16px 0 0; gap: 10px; }
.spec-hero .chip-primary { padding: 6px 14px 6px 12px; font-size: 13px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; border-color: var(--lead); background: rgba(var(--lead-rgb),.12); }
.spec-hero .weapon-chip { padding: 6px 13px; }
.spec-hero-summary { margin: 18px 0 0; max-width: 56ch; font-size: 17px; color: var(--muted); }
.spec-hero-summary strong { color: var(--text); font-weight: 600; }
.guide-nav { position: sticky; top: 56px; z-index: 35; margin-top: 8px; background: linear-gradient(180deg, rgba(8,6,15,.95), rgba(8,6,15,.78)); backdrop-filter: blur(9px); border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.guide-nav-row { max-width: 1320px; margin: 0 auto; display: flex; gap: 2px; overflow-x: auto; padding: 0 clamp(10px,3vw,32px); }
.guide-nav a { display: inline-block; white-space: nowrap; padding: 13px 15px; font-size: 13px; font-weight: 600; letter-spacing: .03em; color: var(--muted); border-bottom: 2px solid transparent; transition: color .15s; }
.guide-nav a:hover { color: var(--lead-bright); }
.guide-nav a.is-active { color: var(--lead); border-bottom-color: var(--lead); text-shadow: 0 0 12px rgba(var(--lead-rgb),.5); }
.spec-main { max-width: 1320px; margin: 0 auto; padding: clamp(22px,4vw,44px) clamp(16px,4vw,40px); display: grid; gap: clamp(26px,4vw,48px); grid-template-columns: minmax(0,1fr); }
.panel-section { scroll-margin-top: 132px; min-width: 0; }
.frame { position: relative; clip-path: var(--bevel); background: linear-gradient(150deg, rgba(var(--lead-rgb),.4), rgba(var(--accent-rgb),.3)); padding: 1.5px; }
.frame-inner { clip-path: var(--bevel); background: linear-gradient(160deg, var(--panel-solid), var(--panel-2)); padding: clamp(16px,2.4vw,26px); height: 100%; }
.sub-panel { clip-path: var(--bevel-sm); border: 1px solid var(--line); background: var(--panel); padding: 18px 20px; }
.section-note { padding: 11px 15px; background: rgba(var(--gold-rgb),.08); border: 1px solid rgba(var(--gold-rgb),.4); clip-path: var(--bevel-sm); color: var(--gold-text); font-size: 13.5px; }
.stats-note { margin: -6px 0 18px; max-width: 74ch; }
.builds-grid { display: grid; gap: 22px; grid-template-columns: repeat(auto-fit, minmax(min(300px,100%),1fr)); }
.build-card .card-inner, .glance-card .card-inner { padding: 22px 24px; }
.build-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.build-tier { font-family: "JetBrains Mono", monospace; font-size: 11px; color: var(--gold); letter-spacing: .18em; }
.build-head h3 { margin: 0; font-weight: 700; font-size: 23px; color: var(--text); }
.build-reason { margin: 10px 0 16px; color: var(--muted); font-size: 15px; }
.build-cta { margin: 4px 0 0; }
.cta-btn { display: inline-flex; align-items: center; gap: 8px; padding: 10px 18px; background: linear-gradient(135deg, var(--lead), var(--lead-bright)); color: #07160a; font-weight: 700; letter-spacing: .04em; clip-path: var(--bevel-sm); text-transform: uppercase; font-size: 13px; }
.cta-btn:hover { color: #07160a; }
.glance-label { margin: 0 0 16px; font-family: "JetBrains Mono", monospace; font-size: 11px; letter-spacing: .2em; text-transform: uppercase; color: var(--muted); }
.glance-metric { display: flex; align-items: flex-end; gap: 12px; }
.glance-value { font-family: Cinzel, serif; font-weight: 900; font-size: 54px; line-height: 1; color: var(--gold); text-shadow: 0 0 26px rgba(var(--gold-rgb),.45); cursor: help; }
.glance-metric-label { padding-bottom: 8px; font-size: 13px; color: var(--muted); max-width: 15ch; }
.essence-bars { display: grid; gap: 12px; margin-top: 20px; }
.essence-bar-head { display: flex; justify-content: space-between; font-size: 12px; font-family: "JetBrains Mono", monospace; color: var(--muted); margin-bottom: 5px; }
.essence-bar-head .ae-value { color: var(--lead); }
.essence-bar-head .te-value { color: var(--accent); }
.essence-track { height: 9px; background: var(--panel-2); border: 1px solid var(--line); clip-path: polygon(0 0,100% 0,calc(100% - 4px) 100%,0 100%); }
.essence-fill { height: 100%; }
.essence-fill.ae { background: linear-gradient(90deg, var(--lead), var(--lead-bright)); box-shadow: 0 0 10px rgba(var(--lead-rgb),.6); }
.essence-fill.te { background: linear-gradient(90deg, var(--accent), var(--lead)); box-shadow: 0 0 10px rgba(var(--accent-rgb),.6); }
.glance-facts { margin-top: 18px; padding-top: 16px; border-top: 1px solid var(--line); display: flex; gap: 18px; flex-wrap: wrap; }
.glance-fact-label { font-family: "JetBrains Mono", monospace; font-size: 11px; color: var(--dim); letter-spacing: .1em; text-transform: uppercase; }
.glance-fact-value { color: var(--lead); font-weight: 700; text-transform: capitalize; }
.glance-fact-value.band { color: var(--text); font-weight: 600; }
.tree-toolbar { display: flex; flex-wrap: wrap; gap: 22px; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.tree-toolbar label { display: inline-flex; align-items: center; gap: 8px; font-family: "JetBrains Mono", monospace; font-size: 12px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }
.tree-toolbar select { background: var(--panel-2); color: var(--text); border: 1px solid var(--line); padding: 7px 9px; font: inherit; font-size: 14px; letter-spacing: normal; text-transform: none; }
.scrub-wrap { flex: 1 1 320px; min-width: 260px; }
.scrub-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.scrub-title { font-family: "JetBrains Mono", monospace; font-size: 12px; letter-spacing: .16em; text-transform: uppercase; color: var(--muted); }
.scrub-level { font-family: Cinzel, serif; font-weight: 800; font-size: 26px; color: var(--gold); text-shadow: 0 0 16px rgba(var(--gold-rgb),.5); }
input[type="range"].level-scrub { -webkit-appearance: none; appearance: none; width: 100%; height: 8px; background: transparent; cursor: pointer; }
input[type="range"].level-scrub::-webkit-slider-runnable-track { height: 8px; background: linear-gradient(90deg, var(--lead), var(--accent)); clip-path: polygon(0 40%,100% 0,100% 100%,0 60%); }
input[type="range"].level-scrub::-moz-range-track { height: 8px; background: linear-gradient(90deg, var(--lead), var(--accent)); }
input[type="range"].level-scrub::-webkit-slider-thumb { -webkit-appearance: none; width: 20px; height: 20px; margin-top: -6px; background: var(--gold); box-shadow: 0 0 12px rgba(var(--gold-rgb),.8); clip-path: polygon(50% 0,100% 50%,50% 100%,0 50%); }
input[type="range"].level-scrub::-moz-range-thumb { width: 20px; height: 20px; border: none; background: var(--gold); clip-path: polygon(50% 0,100% 50%,50% 100%,0 50%); }
.scrub-ticks { display: flex; justify-content: space-between; margin-top: 6px; font-family: "JetBrains Mono", monospace; font-size: 10.5px; color: var(--dim); }
.scrub-ticks .is-active { color: var(--gold); font-weight: 700; }
.tree-legend { display: flex; flex-wrap: wrap; gap: 16px; margin: 16px 0 4px; padding: 11px 15px; background: var(--panel-2); border: 1px solid var(--line); clip-path: var(--bevel-sm); font-size: 12.5px; color: var(--muted); }
.tree-legend > span { display: inline-flex; align-items: center; gap: 7px; }
.legend-dot { width: 14px; height: 14px; border: 2px solid; border-radius: 50%; }
.legend-selected { border-color: var(--lead); box-shadow: 0 0 8px rgba(var(--lead-rgb),.6); }
.legend-free { border-color: var(--gold); }
.legend-available { border-color: var(--accent); }
.legend-locked { border-color: rgba(var(--accent-rgb),.3); opacity: .6; }
.legend-hint { margin-left: auto; font-family: "JetBrains Mono", monospace; font-size: 11px; color: var(--dim); }
.tree-scroll { overflow-x: auto; padding: 4px 4px 8px; }
.tree-build-panel[hidden] { display: none; }
.tree-groups { display: grid; gap: 26px; margin-top: 18px; min-width: max-content; }
.tree-group, .passive-lane { min-width: max-content; }
.tree-group-head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.tree-group-head .diamond { width: 9px; height: 9px; box-shadow: 0 0 8px var(--lead); }
.tree-group-head h3 { margin: 0; font-weight: 700; font-size: 18px; letter-spacing: .05em; color: var(--lead); }
.talent-tree { position: relative; display: grid; grid-template-columns: repeat(var(--tree-cols), 58px); grid-template-rows: repeat(var(--tree-rows), 58px); gap: 34px; min-width: max-content; padding: 20px; border: 1px solid var(--line); clip-path: var(--bevel-sm); background: radial-gradient(circle at 50% 38%, rgba(var(--lead-rgb),.07), rgba(8,6,15,.5)); }
.talent-tree.is-captured-layout { display: block; min-width: var(--tree-width); height: var(--tree-height); }
.talent-tree[hidden] { display: none; }
.passive-lane .talent-tree { display: flex; gap: 34px; align-items: center; min-height: 98px; }
.passive-lane .talent-tree.is-captured-layout { display: block; }
.tree-links { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; overflow: visible; }
.tree-links line { stroke: rgba(var(--accent-rgb),.28); stroke-width: 2; }
.tree-links line.is-selected { stroke: var(--lead); stroke-width: 3; stroke-linecap: round; stroke-dasharray: 5 9; filter: drop-shadow(0 0 4px rgba(var(--lead-rgb),.7)); animation: coaFlow 1.1s linear infinite; }
.tree-links line.is-available { stroke: var(--accent); stroke-width: 2.4; opacity: .8; stroke-dasharray: 4 6; }
.tree-node { position: relative; z-index: 1; width: 58px; height: 58px; display: grid; place-items: center; padding: 0; border: 2px solid rgba(var(--accent-rgb),.28); border-radius: 50%; color: var(--text); background: rgba(10,7,18,.94); overflow: visible; transition: transform .16s ease, box-shadow .2s ease; cursor: help; }
.tree-node img { width: 100%; height: 100%; object-fit: cover; border-radius: inherit; clip-path: inherit; }
.is-captured-layout .tree-node { position: absolute; }
.tree-node.shape-square, .passive-lane .tree-node { border-radius: 11px; }
.tree-node.shape-hex { clip-path: polygon(25% 4%,75% 4%,100% 50%,75% 96%,25% 96%,0 50%); border-radius: 0; }
.tree-node.is-selected { border-color: var(--lead); box-shadow: 0 0 0 1px rgba(var(--lead-rgb),.55), 0 0 15px rgba(var(--lead-rgb),.5), inset 0 0 12px rgba(var(--lead-rgb),.24); animation: coaPulse 2.6s ease-in-out infinite; }
.tree-node.is-free { border-color: var(--gold); box-shadow: 0 0 0 1px rgba(var(--gold-rgb),.5), 0 0 14px rgba(var(--gold-rgb),.45); }
.tree-node.is-available { border-color: var(--accent); box-shadow: 0 0 12px rgba(var(--accent-rgb),.4); }
.tree-node.is-gated, .tree-node.is-inactive { opacity: .46; filter: grayscale(.55); }
.tree-node.is-gated img, .tree-node.is-inactive img { opacity: .7; }
.tree-node.is-over-budget { border-color: var(--gold); box-shadow: 0 0 16px rgba(var(--gold-rgb),.28); }
.tree-rank { position: absolute; right: -6px; bottom: -6px; min-width: 18px; height: 18px; padding: 0 3px; display: grid; place-items: center; font-size: 10px; font-weight: 700; color: var(--text); background: var(--bg); border: 1px solid var(--line); border-radius: 9px; z-index: 2; }
.leveling-path { margin-top: 22px; border: 1px solid var(--line); clip-path: var(--bevel-sm); background: var(--panel-2); }
.leveling-path summary { padding: 14px 18px; cursor: pointer; }
.leveling-heading { display: inline-block; margin-right: 8px; font-family: Cinzel, serif; font-weight: 600; font-size: 15px; letter-spacing: .04em; color: var(--text); }
.leveling-path summary .mono { font-size: 11px; color: var(--dim); }
.leveling-list { columns: 240px auto; column-gap: 24px; padding: 4px 20px 20px 44px; margin: 0; }
.leveling-path li { margin-bottom: 8px; color: var(--muted); font-size: 13.5px; }
.leveling-list li { break-inside: avoid; }
.leveling-list strong { font-family: "JetBrains Mono", monospace; font-size: 11.5px; font-weight: 700; letter-spacing: .04em; color: var(--gold); }
.leveling-list .chip { padding: 2px 8px; border: none; background: none; font-family: "JetBrains Mono", monospace; font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: var(--dim); }
.leveling-path > ul { margin: 0; padding: 0 20px 16px 38px; color: var(--gold-text); font-size: 13px; }
.rotation-grid { display: grid; gap: 20px; grid-template-columns: repeat(auto-fit, minmax(min(320px,100%),1fr)); }
.rotation-card { background: linear-gradient(150deg, rgba(var(--lead-rgb),.32), rgba(var(--accent-rgb),.24)); }
.rotation-card .card-inner { padding: 20px 22px; }
.rotation-card h3 { margin: 0 0 14px; font-weight: 700; font-size: 17px; letter-spacing: .04em; color: var(--lead); display: flex; align-items: center; gap: 9px; }
.rotation-card h3 .diamond { width: 8px; height: 8px; box-shadow: none; }
.step-list { margin: 0; padding: 0; list-style-type: none; display: grid; gap: 10px; }
.step-list li { display: flex; gap: 12px; align-items: flex-start; font-size: 14.5px; color: var(--muted); }
.step-num { flex: 0 0 auto; width: 24px; height: 24px; display: grid; place-items: center; font-family: "JetBrains Mono", monospace; font-size: 11px; font-weight: 700; color: var(--lead); border: 1px solid rgba(var(--lead-rgb),.45); clip-path: polygon(50% 0,100% 50%,50% 100%,0 50%); }
.step-text { padding-top: 2px; min-width: 0; }
.step-text .muted { color: var(--dim); }
.rotation-extras { margin-top: 20px; }
.stat-groups, .gear-groups { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(min(260px,100%),1fr)); }
.stat-group h3 { margin: 0 0 14px; font-family: "JetBrains Mono", monospace; font-size: 12px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); }
.stat-chips { display: flex; flex-direction: column; gap: 9px; align-items: flex-start; }
.stat-chip { display: inline-flex; align-items: center; gap: 10px; padding: 9px 13px; background: var(--panel-2); border: 1px solid var(--line); clip-path: var(--bevel-sm); font-size: 14px; font-weight: 600; color: var(--text); cursor: help; }
.stat-rank { flex: 0 0 auto; width: 20px; height: 20px; display: grid; place-items: center; font-family: "JetBrains Mono", monospace; font-size: 10px; font-weight: 700; color: var(--gold); border: 1px solid rgba(var(--gold-rgb),.4); border-radius: 50%; }
.gear-group h3 { margin: 0 0 13px; font-weight: 700; font-size: 16px; color: var(--lead); }
.gear-group .chip { color: var(--text); font-size: 13px; font-weight: 400; padding: 6px 13px; }
.gear-note { margin: 14px 0 0; font-family: "JetBrains Mono", monospace; font-size: 11.5px; color: var(--dim); }
.ability-note { margin: 0 0 16px; font-size: 13.5px; color: var(--dim); }
.node-list { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(min(240px,100%),1fr)); }
.node-card { display: flex; align-items: center; gap: 12px; padding: 9px 12px; background: var(--panel); border: 1px solid var(--line); clip-path: var(--bevel-sm); color: var(--text); }
a.node-card:hover { border-color: rgba(var(--lead-rgb),.5); color: var(--text); }
.icon-frame { flex: 0 0 auto; width: 40px; height: 40px; display: grid; place-items: center; clip-path: var(--bevel-sm); border: 1px solid rgba(var(--lead-rgb),.4); overflow: hidden; background: var(--panel-2); color: var(--lead); font-size: 12px; }
.icon-frame img { width: 100%; height: 100%; object-fit: cover; }
.node-text { min-width: 0; }
.node-name { display: block; font-weight: 600; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.node-meta { display: block; font-family: "JetBrains Mono", monospace; font-size: 10.5px; color: var(--dim); text-transform: uppercase; letter-spacing: .05em; }
.warnings-panel { clip-path: var(--bevel-sm); border: 1px solid rgba(var(--gold-rgb),.5); background: rgba(var(--gold-rgb),.07); padding: 18px 22px; color: var(--gold-text); }
.warnings-panel h2 { margin: 0 0 10px; font-size: 17px; color: var(--gold-text); }
.warnings-panel ul { margin: 0; padding-left: 1.2rem; font-size: 13.5px; }
.data-notes-panel { clip-path: var(--bevel-sm); border: 1px solid var(--line); background: var(--panel); padding: 18px 22px; display: flex; flex-wrap: wrap; gap: 20px; align-items: center; justify-content: space-between; }
.data-notes-panel h2 { margin: 0 0 4px; font-weight: 700; font-size: 17px; color: var(--text); }
.data-notes-panel p { margin: 0; font-size: 13px; color: var(--muted); max-width: 70ch; }
.generated-stamp { font-family: "JetBrains Mono", monospace; font-size: 11px; color: var(--dim); white-space: nowrap; }
.tooltip { position: fixed; z-index: 70; width: 320px; max-width: 92vw; padding: 13px 15px; background: linear-gradient(160deg, rgba(12,8,20,.98), rgba(9,6,15,.98)); border: 1px solid var(--accent); clip-path: var(--bevel-sm); box-shadow: 0 0 30px rgba(var(--accent-rgb),.35), 0 14px 40px rgba(0,0,0,.6); font-size: 13.5px; line-height: 1.5; color: var(--text); }
.tooltip.is-pinned { border-color: var(--gold); box-shadow: 0 0 24px rgba(var(--gold-rgb),.32), 0 14px 40px rgba(0,0,0,.6); }
.tooltip strong { font-family: Cinzel, serif; font-weight: 700; font-size: 15px; color: var(--gold); line-height: 1.2; }
.tooltip table { width: 100%; border-collapse: collapse; margin-top: 8px; }
.tooltip th, .tooltip td { border: 1px solid rgba(var(--accent-rgb),.3); padding: 4px 6px; text-align: left; vertical-align: top; font-size: 12px; }
.tooltip .pin-hint { margin-top: 9px; font-family: "JetBrains Mono", monospace; font-size: 10px; color: var(--dim); }
.site-footer { border-top: 1px solid var(--line); background: rgba(8,6,15,.7); padding: 26px clamp(16px,4vw,40px); margin-top: 20px; }
.footer-row { max-width: 1320px; margin: 0 auto; display: flex; flex-wrap: wrap; gap: 14px; justify-content: space-between; align-items: center; font-size: 12.5px; color: var(--dim); }
.site-footer a { color: var(--muted); }
.site-footer a:hover { color: var(--lead); }
.footer-links { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; }
@media (max-width: 720px) { .spec-hero-icon { width: 84px; height: 93px; } .spec-hero-icon .spec-icon-core { width: 76px; height: 84px; } .legend-hint { margin-left: 0; } }
@media (prefers-reduced-motion: reduce) { * { animation-duration: .001ms !important; animation-iteration-count: 1 !important; } }
"""

GUIDE_JS = """
(() => {
  const THEME_KEY = "coa-theme";
  function applyTheme(value) {
    const theme = value === "void" ? "void" : "fel";
    document.documentElement.setAttribute("data-theme", theme);
    document.querySelectorAll("[data-theme-btn]").forEach(btn => {
      btn.setAttribute("aria-pressed", String(btn.getAttribute("data-theme-value") === theme));
    });
    window.__coaTheme = theme;
    if (typeof window.__coaEmberRecolor === "function") window.__coaEmberRecolor(theme);
  }
  function initTheme() {
    let stored = "fel";
    try { stored = localStorage.getItem(THEME_KEY) || "fel"; } catch (_e) {}
    applyTheme(stored);
    document.addEventListener("click", event => {
      const btn = event.target.closest("[data-theme-btn]");
      if (!btn) return;
      const value = btn.getAttribute("data-theme-value");
      try { localStorage.setItem(THEME_KEY, value); } catch (_e) {}
      applyTheme(value);
    });
  }
  document.addEventListener("DOMContentLoaded", initTheme);
  const FEL_PAL = [[108,240,107],[154,107,255],[255,207,92]];
  const VOID_PAL = [[168,121,255],[108,240,107],[255,207,92]];
  let emberPalette = FEL_PAL, emberParts = [], emberCanvas, emberCtx, emberRaf, emberW, emberH;
  window.__coaEmberRecolor = theme => { emberPalette = theme === "void" ? VOID_PAL : FEL_PAL; };
  function sizeEmberCanvas() {
    if (!emberCanvas) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    emberW = window.innerWidth; emberH = window.innerHeight;
    emberCanvas.width = emberW * dpr; emberCanvas.height = emberH * dpr;
    emberCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function startEmbers() {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    emberCanvas = document.createElement("canvas");
    emberCanvas.setAttribute("data-embers", "");
    emberCanvas.setAttribute("aria-hidden", "true");
    emberCanvas.style.cssText = "position:fixed;inset:0;width:100%;height:100%;z-index:-2;pointer-events:none;";
    document.body.insertBefore(emberCanvas, document.body.firstChild);
    emberCtx = emberCanvas.getContext("2d");
    sizeEmberCanvas();
    const rnd = (a, b) => a + Math.random() * (b - a);
    const n = Math.min(74, Math.round(emberW / 17));
    emberParts = Array.from({ length: n }, () => ({ x: rnd(0, emberW), y: rnd(0, emberH), r: rnd(0.7, 2.5), vy: rnd(-0.5, -0.13), vx: rnd(-0.15, 0.15), a: rnd(0.14, 0.66), tw: rnd(0.004, 0.02), ph: rnd(0, 6.28), ci: Math.random() < 0.12 ? 2 : (Math.random() < 0.4 ? 1 : 0) }));
    const loop = () => {
      emberCtx.clearRect(0, 0, emberW, emberH); emberCtx.globalCompositeOperation = "lighter";
      for (const p of emberParts) {
        p.y += p.vy; p.x += p.vx; p.ph += p.tw;
        if (p.y < -10) { p.y = emberH + 10; p.x = rnd(0, emberW); }
        if (p.x < -10) p.x = emberW + 10; if (p.x > emberW + 10) p.x = -10;
        const c = emberPalette[p.ci], al = p.a * (0.55 + 0.45 * Math.sin(p.ph));
        const g = emberCtx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 4.5);
        g.addColorStop(0, "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + al + ")");
        g.addColorStop(1, "rgba(" + c[0] + "," + c[1] + "," + c[2] + ",0)");
        emberCtx.fillStyle = g; emberCtx.beginPath(); emberCtx.arc(p.x, p.y, p.r * 4.5, 0, 6.2832); emberCtx.fill();
      }
      emberCtx.globalCompositeOperation = "source-over"; emberRaf = requestAnimationFrame(loop);
    };
    loop();
    window.addEventListener("resize", sizeEmberCanvas);
  }
  document.addEventListener("DOMContentLoaded", startEmbers);
  const tooltipData = window.COA_TOOLTIPS || {};
  const pins = new Map();
  let hoverEl = null, hoverAnchor = null;
  function makeTip(id, pinned) {
    const tip = tooltipData[id];
    if (!tip) return null;
    const el = document.createElement("div");
    el.className = "tooltip" + (pinned ? " is-pinned" : "");
    el.innerHTML = tip.html || tip.text || "";
    if (pinned) {
      const hint = document.createElement("div");
      hint.className = "pin-hint";
      hint.textContent = "pinned · click again or press Esc to clear all";
      el.appendChild(hint);
    }
    document.body.appendChild(el);
    return el;
  }
  function placeTip(el, anchor) {
    const rect = anchor.getBoundingClientRect();
    const width = el.offsetWidth || 320;
    const left = Math.max(12, Math.min(rect.left + rect.width / 2 - width / 2, window.innerWidth - width - 12));
    el.style.left = left + "px";
    const below = rect.bottom + 12;
    if (below + el.offsetHeight < window.innerHeight - 16) {
      el.style.top = below + "px"; el.style.bottom = "auto";
    } else {
      el.style.top = "auto"; el.style.bottom = (window.innerHeight - rect.top + 12) + "px";
    }
  }
  function clearHover() {
    if (hoverEl) hoverEl.remove();
    hoverEl = null; hoverAnchor = null;
  }
  function showHover(anchor) {
    const id = anchor.getAttribute("data-tooltip-id");
    if (!id || pins.has(anchor)) return;
    clearHover();
    hoverEl = makeTip(id, false); hoverAnchor = anchor;
    if (hoverEl) placeTip(hoverEl, anchor);
  }
  function togglePin(anchor) {
    const id = anchor.getAttribute("data-tooltip-id");
    if (!id) return;
    if (pins.has(anchor)) {
      pins.get(anchor).el.remove(); pins.delete(anchor);
      return;
    }
    clearHover();
    const el = makeTip(id, true);
    if (!el) return;
    pins.set(anchor, { el, anchor }); placeTip(el, anchor);
  }
  function repositionPins() {
    pins.forEach(pin => placeTip(pin.el, pin.anchor));
    if (hoverEl && hoverAnchor) placeTip(hoverEl, hoverAnchor);
  }
  document.addEventListener("mouseover", event => {
    const target = event.target.closest("[data-tooltip-id]");
    if (target) showHover(target);
  });
  document.addEventListener("focusin", event => {
    const target = event.target.closest("[data-tooltip-id]");
    if (target) showHover(target);
  });
  document.addEventListener("mouseout", event => {
    const target = event.target.closest("[data-tooltip-id]");
    if (!target) return;
    const related = event.relatedTarget;
    if (related && target.contains(related)) return;
    clearHover();
  });
  document.addEventListener("focusout", event => {
    const target = event.target.closest("[data-tooltip-id]");
    if (!target || target !== hoverAnchor) return;
    const related = event.relatedTarget;
    if (related && target.contains(related)) return;
    clearHover();
  });
  document.addEventListener("click", event => {
    const target = event.target.closest("[data-tooltip-id]");
    if (!target) return;
    event.preventDefault();
    togglePin(target);
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      clearHover();
      pins.forEach(pin => pin.el.remove());
      pins.clear();
    }
  });
  window.addEventListener("scroll", repositionPins, true);
  window.addEventListener("resize", repositionPins);
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
      const levelLabel = panel.querySelector("[data-tree-level-label]");
      const levels = levelSelector ? parseJson(levelSelector.getAttribute("data-tree-levels"), []) : [];
      function currentLevel() {
        if (!levelSelector) return null;
        if (levels.length) {
          const index = Math.max(0, Math.min(parseInt(levelSelector.value, 10) || 0, levels.length - 1));
          return levels[index];
        }
        return levelSelector.value;
      }
      function currentBuildPanel() {
        const id = buildSelector ? buildSelector.value : panel.querySelector("[data-tree-build-panel]")?.getAttribute("data-tree-build-panel");
        return panel.querySelector(`[data-tree-build-panel="${id}"]`) || panel.querySelector("[data-tree-build-panel]");
      }
      function refresh() {
        const level = currentLevel();
        if (levelLabel && level != null) levelLabel.textContent = "Lv " + level;
        panel.querySelectorAll("[data-level-tick]").forEach(tick => {
          tick.classList.toggle("is-active", tick.getAttribute("data-level-tick") === String(level));
        });
        const activePanel = currentBuildPanel();
        panel.querySelectorAll("[data-tree-build-panel]").forEach(buildPanel => { buildPanel.hidden = buildPanel !== activePanel; });
        if (!activePanel) return;
        activePanel.querySelectorAll("[data-tree-kind]").forEach(tree => {
          applySnapshot(panel, tree, level != null ? level : tree.getAttribute("data-tree-level"));
        });
      }
      if (buildSelector) buildSelector.addEventListener("change", refresh);
      if (levelSelector) {
        levelSelector.addEventListener("change", refresh);
        levelSelector.addEventListener("input", refresh);
      }
      refresh();
    });
  }
  function initSectionNav() {
    const links = Array.from(document.querySelectorAll(".guide-nav a[href^='#']"));
    if (!links.length || typeof IntersectionObserver === "undefined") return;
    const byId = new Map(links.map(link => [link.getAttribute("href").slice(1), link]));
    const sections = Array.from(byId.keys()).map(id => document.getElementById(id)).filter(Boolean);
    if (!sections.length) return;
    const io = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        links.forEach(link => link.classList.remove("is-active"));
        const link = byId.get(entry.target.id);
        if (link) link.classList.add("is-active");
      });
    }, { rootMargin: "-140px 0px -62% 0px", threshold: 0 });
    sections.forEach(section => io.observe(section));
  }
  window.addEventListener("resize", () => document.querySelectorAll("[data-tree-kind]").forEach(drawTreeLinks));
  document.addEventListener("DOMContentLoaded", initTrees);
  document.addEventListener("DOMContentLoaded", initSectionNav);
})();
"""


def _render_header(home_href: str = "index.html", *, show_all_guides: bool = False) -> str:
    all_guides = (
        f'<a class="all-guides" href="{_e(home_href)}">All Guides</a>' if show_all_guides else ""
    )
    return (
        '<header class="site-header">'
        f'<a class="site-brand" href="{_e(home_href)}">'
        '<span class="brand-sigil" aria-hidden="true"><span>C</span></span>'
        '<span class="brand-word">CoA <span>Codex</span></span></a>'
        '<div class="theme-toggle" role="group" aria-label="Theme" data-theme-toggle>'
        '<button type="button" class="theme-btn" data-theme-btn data-theme-value="fel" aria-pressed="true">'
        '<span class="theme-dot theme-dot-fel" aria-hidden="true"></span>Fel</button>'
        '<button type="button" class="theme-btn" data-theme-btn data-theme-value="void" aria-pressed="false">'
        '<span class="theme-dot theme-dot-void" aria-hidden="true"></span>Void</button>'
        "</div>"
        f'<nav class="site-nav">{all_guides}'
        f'<a class="github-link" href="{REPO_URL}" target="_blank" rel="noopener" '
        f'aria-label="View source on GitHub">{GITHUB_MARK_SVG}</a></nav>'
        "</header>"
    )


def _render_footer(site: GuideSite) -> str:
    generated = _e(getattr(site, "generated_at", "") or "")
    generated_html = f'<span class="generated-stamp">Generated {generated}</span>' if generated else ""
    return (
        '<footer class="site-footer"><div class="footer-row">'
        "<span>© 2026 CoA Codex · Fan-made theorycraft tool. "
        "Not affiliated with or endorsed by Project Ascension.</span>"
        '<span class="footer-links">'
        f'<a href="{ISSUES_URL}" target="_blank" rel="noopener">Submit an issue</a>'
        f'<a href="{REPO_URL}" target="_blank" rel="noopener">Source on GitHub</a>'
        f"{generated_html}</span>"
        "</div></footer>"
    )


def _section_head(title: str, extra: str = "") -> str:
    return f'<div class="section-head"><h2>{_e(title)}</h2>{extra}{HEAD_RULE}</div>'


def render_index_html(site: GuideSite) -> str:
    roles = _ordered_roles(site)
    unique_specs = len({spec.slug for spec in site.specs})
    role_count = len(roles)
    stat_line = (
        f'<p class="stat-line" data-stat-line>'
        f'{unique_specs} spec{"" if unique_specs == 1 else "s"} · '
        f'{role_count} role{"" if role_count == 1 else "s"}</p>'
    )
    filters = (
        '<div class="role-filter-bar" id="guides">'
        '<div class="role-filter-row" role="group" aria-label="Filter guides by role">'
        '<span class="role-filter-label">Filter</span>'
        '<button class="role-filter is-active" data-role-filter="all" aria-pressed="true">All Roles</button>'
    )
    filters += "".join(
        f'<button class="role-filter" data-role-filter="{_e(role)}" aria-pressed="false">{_e(_label(role))}</button>'
        for role in roles
    )
    filters += "</div></div>"
    role_sections = "".join(_render_role_section(role, [spec for spec in site.specs if role in _spec_roles(spec)]) for role in roles)
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>CoA Codex</title><link rel=\"stylesheet\" href=\"assets/guide.css\">"
        "</head><body><main class=\"site-shell\">"
        f"{_render_header()}"
        '<section class="hero"><div class="hero-glow" aria-hidden="true"></div>'
        '<p class="hero-kicker">Conquest of Azeroth</p>'
        '<h1 class="hero-title">Meta <span>Codex</span></h1>'
        '<p class="hero-sub">Class and specialization guides for Conquest of Azeroth.</p>'
        f'<p class="front-disclaimer">{_e(FRONT_PAGE_DISCLAIMER)}</p>'
        f"{stat_line}</section>"
        f"{filters}"
        f'<div class="site-main">{role_sections}</div>'
        f"{_render_footer(site)}"
        f"{_tooltip_script(site)}<script src=\"assets/guide.js\"></script>"
        "</main></body></html>"
    )


def render_spec_html(site: GuideSite, spec: GuideSpec) -> str:
    nav_links = "".join(f'<a href="#{_anchor(section)}">{_e(section)}</a>' for section in spec.sections)
    nav = f'<nav class="guide-nav" aria-label="Guide sections"><div class="guide-nav-row">{nav_links}</div></nav>'
    warnings = ""
    if spec.warnings:
        items = "".join(f"<li>{_e(warning)}</li>" for warning in spec.warnings)
        warnings = (
            '<section class="panel-section" id="warnings">'
            f'<div class="warnings-panel"><h2>Warnings</h2><ul>{items}</ul></div></section>'
        )
    nodes = "".join(_render_node(node) for node in spec.nodes)
    node_count = len(spec.nodes)
    hero = (
        '<section class="hero spec-hero" id="overview">'
        '<div class="hero-glow" aria-hidden="true"></div>'
        f'<p class="hero-kicker">Conquest of Azeroth · {_e(spec.class_name)}</p>'
        '<div class="spec-hero-row">'
        f"{_render_spec_icon(spec, '../assets', css_class='spec-hero-icon')}"
        '<div class="spec-hero-text">'
        f"<h1>{_e(spec.spec_name)}</h1>"
        f'<p class="spec-hero-class">{_e(spec.class_name)}</p>'
        f'<div class="chip-row">{_role_chips(spec, tooltip_id=f"role:{spec.slug}")} {_weapon_armor_chip(spec)}</div>'
        f'<p class="spec-hero-summary">{_e(spec.summary)}</p>'
        "</div></div></section>"
    )
    abilities_section = (
        '<section class="panel-section" id="abilities-and-talents">'
        + _section_head(
            "Abilities and Talents",
            f'<span class="section-count">{node_count} entr{"y" if node_count == 1 else "ies"}</span>',
        )
        + '<p class="ability-note">Hover or focus any entry for its full in-game tooltip.</p>'
        + f'<div class="node-list">{nodes}</div></section>'
    )
    data_notes = (
        '<section class="panel-section" id="data-notes">'
        '<div class="data-notes-panel"><div>'
        "<h2>Data Notes</h2>"
        "<p>Theorycraft projections from CoA Builder and Ascension data — not observed logs "
        "or simulated output. Accuracy tuning via combat logs / simming pending.</p></div>"
        f'<span class="generated-stamp">Generated {_e(site.generated_at)}</span>'
        "</div></section>"
    )
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{_e(spec.class_name)} {_e(spec.spec_name)} Guide · CoA Codex</title>"
        "<link rel=\"stylesheet\" href=\"../assets/guide.css\"></head><body><main class=\"site-shell\">"
        f"{_render_header(home_href='../index.html', show_all_guides=True)}"
        f"{hero}"
        f"{nav}"
        '<div class="spec-main">'
        f"{_render_builds_section(spec)}"
        f"{_render_talent_tree_section(spec)}"
        f"{_render_rotation_section(spec)}"
        f"{_render_stats_section(spec)}"
        f"{_render_gear_section(spec)}"
        f"{abilities_section}"
        f"{warnings}{data_notes}"
        "</div>"
        f"{_render_footer(site)}"
        f"{_tooltip_script(site)}<script src=\"../assets/guide.js\"></script>"
        "</main></body></html>"
    )


def _render_spec_icon(spec: GuideSpec, asset_prefix: str = "assets", *, css_class: str = "spec-icon") -> str:
    asset = getattr(spec, "icon_asset", None)
    if asset and asset.href and not asset.missing:
        src = _asset_src(asset.href, asset_prefix)
        core = f'<span class="spec-icon-core"><img src="{_e(src)}" alt="" loading="lazy"></span>'
    else:
        initials = "".join(word[:1] for word in spec.class_name.split()[:2]).upper() or spec.class_name[:2].upper()
        core = f'<span class="spec-icon-core spec-icon-mono">{_e(initials)}</span>'
    return f'<span class="{css_class}" aria-hidden="true">{core}</span>'


def _render_spec_card(spec: GuideSpec) -> str:
    warning = '<span class="chip warning">⚠ Warnings</span>' if spec.warning_count else ""
    role_values = " ".join(_spec_roles(spec))
    return (
        f'<article class="guide-card spec-card" data-role="{_e(role_values)}">'
        f'<a class="card-inner spec-card-inner" href="{_e(spec.href)}">'
        '<div class="spec-card-head">'
        f"{_render_spec_icon(spec)}"
        f'<div class="spec-card-title"><h3>{_e(spec.spec_name)}</h3>'
        f'<p class="spec-card-class">{_e(spec.class_name)}</p></div></div>'
        f'<p class="spec-card-summary">{_e(spec.summary)}</p>'
        f'<div class="chip-row">{_role_chips(spec)} {warning}</div>'
        '<div class="spec-card-cta"><span class="cta-label">Open guide</span>'
        '<span class="cta-arrow" aria-hidden="true">→</span></div>'
        "</a></article>"
    )


def _render_role_section(role: str, specs: list[GuideSpec]) -> str:
    count = len(specs)
    if specs:
        cards = "".join(_render_spec_card(spec) for spec in sorted(specs, key=lambda item: (item.class_name, item.spec_name)))
        body = f'<div class="guide-grid">{cards}</div>'
    else:
        body = f'<p class="empty-role">No {_e(_label(role))} guides are available in the current report.</p>'
    return (
        f'<section class="role-section" data-role-section="{_e(role)}">'
        '<div class="section-head">'
        f"{DIAMOND}"
        f'<h2 class="role-section-title">{_e(_label(role))}</h2>'
        f'<span class="section-count">{count} spec{"" if count == 1 else "s"}</span>'
        f"{HEAD_RULE}</div>{body}</section>"
    )


def _ordered_roles(site: GuideSite) -> tuple[str, ...]:
    site_roles = {role for spec in site.specs for role in _spec_roles(spec)}
    extras = sorted(role for role in site_roles if role not in ROLE_DISPLAY_ORDER)
    return ROLE_DISPLAY_ORDER + tuple(extras)


def _render_builds_section(spec: GuideSpec) -> str:
    builds = "".join(_render_build(build) for build in spec.builds)
    glance = _render_glance_panel(spec)
    if not builds and not glance:
        body = "<p>No recommended builds are available in the current report.</p>"
    else:
        body = f'<div class="builds-grid">{builds}{glance}</div>'
    return (
        '<section class="panel-section" id="recommended-builds">'
        + _section_head("Recommended Builds")
        + body
        + "</section>"
    )


def _render_build(build: Any) -> str:
    warning = '<span class="chip warning">⚠ Warnings</span>' if build.warnings else ""
    primary_index = build.primary_index if build.primary_index is not None else build.projected_dps_index
    primary_index_label = build.primary_index_label or "Projected Damage Index"
    tier = "S-TIER" if build.rank == 1 else f"RANK {build.rank}"
    return (
        '<article class="guide-card build-card"><div class="card-inner">'
        '<div class="build-head">'
        f'<span class="build-tier">{_e(tier)}</span>'
        f"<h3>{_e(build.playstyle_label or build.label)}</h3></div>"
        f'<p class="build-reason">{_e(build.selection_reason or "Strong current theorycraft result for this spec.")}</p>'
        '<div class="chip-row">'
        f'<span class="chip">{_e(build.reliability_label or build.confidence_label)} reliability</span> '
        f'<span class="chip">{_e(build.performance_band or "top theorycraft band")}</span> '
        f'<span class="chip chip-primary" data-tooltip-id="metric:primary_index">{_e(primary_index_label)} {primary_index:.1f}</span> '
        f"{warning}</div>"
        '<p class="build-cta"><a class="cta-btn" href="#talents">View talent tree ↓</a></p>'
        "</div></article>"
    )


def _render_glance_panel(spec: GuideSpec) -> str:
    build = spec.builds[0] if spec.builds else None
    if build is None:
        return ""
    primary_index = build.primary_index if build.primary_index is not None else build.projected_dps_index
    label = build.primary_index_label or "Projected Damage Index"
    snapshots = _build_tree_snapshots(build)
    bars = ""
    if snapshots:
        snapshot = max(snapshots, key=lambda item: item.level)
        ae_pct = round(snapshot.ae_spent / snapshot.max_ae * 100) if snapshot.max_ae else 0
        te_pct = round(snapshot.te_spent / snapshot.max_te * 100) if snapshot.max_te else 0
        bars = (
            '<div class="essence-bars">'
            '<div><div class="essence-bar-head"><span>Ability Essence</span>'
            f'<span class="ae-value">{snapshot.ae_spent} / {snapshot.max_ae}</span></div>'
            f'<div class="essence-track"><div class="essence-fill ae" style="width: {ae_pct}%"></div></div></div>'
            '<div><div class="essence-bar-head"><span>Talent Essence</span>'
            f'<span class="te-value">{snapshot.te_spent} / {snapshot.max_te}</span></div>'
            f'<div class="essence-track"><div class="essence-fill te" style="width: {te_pct}%"></div></div></div>'
            "</div>"
        )
    reliability = build.reliability_label or build.confidence_label
    band = build.performance_band or "top theorycraft"
    return (
        '<article class="guide-card frame-gold glance-card"><div class="card-inner">'
        '<p class="glance-label">At a Glance</p>'
        '<div class="glance-metric">'
        f'<span class="glance-value" data-tooltip-id="metric:primary_index" tabindex="0">{primary_index:.1f}</span>'
        f'<span class="glance-metric-label">{_e(label)}</span></div>'
        f"{bars}"
        '<div class="glance-facts">'
        f'<div><div class="glance-fact-label">Reliability</div><div class="glance-fact-value">{_e(reliability)}</div></div>'
        f'<div><div class="glance-fact-label">Band</div><div class="glance-fact-value band">{_e(band)}</div></div>'
        "</div></div></article>"
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
    tooltip = f' data-tooltip-id="{_e(tooltip_id)}" tabindex="0"' if tooltip_id else ""
    dot = '<span class="chip-dot" aria-hidden="true"></span>' if tooltip_id else ""
    chips.append(
        f'<span class="chip chip-primary" data-role-chip="{_e(primary_role)}"{tooltip}>{dot}{_e(_label(primary_role))}</span>'
    )
    for role in spec.secondary_roles:
        if role == primary_role:
            continue
        chips.append(f'<span class="chip" data-role-chip="{_e(role)}">Secondary: {_e(_label(role))}</span>')
    return " ".join(chips)


def _attack_posture(spec: GuideSpec) -> str:
    role = (spec.primary_role or spec.role or "").lower()
    if role in {"caster_dps", "healer", "support"}:
        return "Caster"
    if role == "ranged_dps":
        return "Ranged"
    return "Melee"


def _weapon_armor_chip(spec: GuideSpec) -> str:
    build = spec.builds[0] if spec.builds else None
    report = dict(build.gear_recommendation_report or {}) if build else {}
    if not report:
        return ""
    weapons = tuple(report.get("best_weapon_types") or report.get("available_weapon_types") or ())
    armor = tuple(report.get("best_armor_types") or report.get("available_armor_types") or ())
    tokens = [_attack_posture(spec)]
    if weapons:
        tokens.append(" + ".join(dict.fromkeys(w.replace("_", " ").title() for w in weapons if w)))
    if armor:
        tokens.append(next(iter(dict.fromkeys(a.replace("_", " ").title() for a in armor if a))))
    tokens = [token for token in tokens if token]
    if len(tokens) <= 1:
        return ""
    return f'<span class="chip weapon-chip">{_e(" · ".join(tokens))}</span>'


def _render_rotation_section(spec: GuideSpec) -> str:
    build = spec.builds[0] if spec.builds else None
    guide = dict(build.rotation_guide or {}) if build else {}
    head = _section_head("Rotation")
    if guide:
        cards = []
        quick_priority = [
            *guide.get("priority_rules", []),
            *guide.get("core_loop", []),
        ]
        cards.append(_render_guide_rule_card("Quick Priority", quick_priority))
        cards.append(_render_guide_rule_card("Opener", guide.get("opener", [])))
        cards.append(_render_guide_rule_card("Core Loop", guide.get("core_loop", [])))
        cards.append(_render_guide_rule_card("Cooldowns", guide.get("cooldown_rules", [])))
        cards.append(_render_guide_rule_card("Procs and Statuses", guide.get("proc_rules", [])))
        role_rules = [
            *guide.get("defensive_rules", []),
            *guide.get("healing_rules", []),
            *guide.get("support_rules", []),
        ]
        cards.append(_render_guide_rule_card("Role Tools", role_rules))
        cards.append(_render_guide_rule_card("AoE Adjustments", guide.get("aoe_adjustments", [])))
        extras = []
        reliability = guide.get("reliability")
        summary = dict(guide.get("simulation_summary") or {})
        if reliability:
            extras.append(
                f'<div class="chip-row"><span class="chip">{_e(reliability)} rotation reliability</span> '
                f'<span class="chip">{_e(str(summary.get("action_count", 0)))} simulated actions</span></div>'
            )
        warnings = guide.get("warnings") or []
        if warnings:
            warning_items = "".join(f"<li>{_e(warning)}</li>" for warning in warnings)
            extras.append(f'<div class="section-note"><strong>Rotation Warnings</strong><ul>{warning_items}</ul></div>')
        body = f'<div class="rotation-grid">{"".join(card for card in cards if card)}</div>'
        if extras:
            body += f'<div class="rotation-extras">{"".join(extras)}</div>'
        return f'<section class="panel-section" id="rotation">{head}{body}</section>'

    loop = dict(build.rotation_loop or {}) if build else {}
    if not loop:
        return (
            f'<section class="panel-section" id="rotation">{head}'
            '<div class="sub-panel"><p>Use the generated priority notes as an early rotation scaffold.</p></div></section>'
        )
    cards = [
        _render_loop_card("Core Loop", loop.get("core_loop", [])),
        _render_loop_card("Opener and Setup", loop.get("opener", [])),
        _render_loop_card("Cooldowns", loop.get("cooldowns", [])),
    ]
    role_steps = loop.get("defensive_or_support", [])
    if role_steps:
        cards.append(_render_loop_card("Defensive, Healing, or Support Priorities", role_steps))
    extras = []
    if loop.get("objective"):
        extras.append(f"<p>{_e(loop['objective'])}</p>")
    if loop.get("resource_rule"):
        extras.append(f'<p><strong>Resource Rule:</strong> {_e(loop["resource_rule"])}</p>')
    if loop.get("maintenance_rule"):
        extras.append(f'<p><strong>Maintenance Rule:</strong> {_e(loop["maintenance_rule"])}</p>')
    reliability = loop.get("reliability_label")
    if reliability:
        extras.append(f'<div class="chip-row"><span class="chip">{_e(reliability)} rotation reliability</span></div>')
    body = f'<div class="rotation-grid">{"".join(card for card in cards if card)}</div>'
    if extras:
        body += f'<div class="rotation-extras">{"".join(extras)}</div>'
    return f'<section class="panel-section" id="rotation">{head}{body}</section>'


def _rotation_card(title: str, rows: list[str]) -> str:
    if not rows:
        return ""
    return (
        '<div class="guide-card rotation-card"><div class="card-inner">'
        f'<h3>{DIAMOND}{_e(title)}</h3>'
        f'<ol class="step-list">{"".join(rows)}</ol></div></div>'
    )


def _render_guide_rule_card(title: str, rules: Any) -> str:
    values = [dict(rule) for rule in rules or [] if isinstance(rule, dict)]
    rows = []
    for index, rule in enumerate(values[:12], start=1):
        ability = str(rule.get("ability_name") or "Ability")
        url = str(rule.get("db_url") or "")
        label = f'<a href="{_e(url)}">{_e(ability)}</a>' if url else _e(ability)
        text = str(rule.get("text") or f"Use {ability}.")
        condition = str(rule.get("condition") or "")
        condition_html = f' <span class="muted">({_e(condition)})</span>' if condition else ""
        rows.append(
            f'<li><span class="step-num" aria-hidden="true">{index}</span>'
            f'<span class="step-text"><strong>{label}</strong>: {_e(text)}{condition_html}</span></li>'
        )
    return _rotation_card(title, rows)


def _render_loop_card(title: str, items: Any) -> str:
    values = [str(item) for item in items or [] if str(item)]
    rows = [
        f'<li><span class="step-num" aria-hidden="true">{index}</span>'
        f'<span class="step-text">{_e(item)}</span></li>'
        for index, item in enumerate(values, start=1)
    ]
    return _rotation_card(title, rows)


def _render_stats_section(spec: GuideSpec) -> str:
    build = spec.builds[0] if spec.builds else None
    report = dict(build.stat_priority_report or {}) if build else {}
    head = _section_head("Stats")
    if not report:
        return (
            f'<section class="panel-section" id="stats">{head}'
            '<div class="section-note">Stat priority is unavailable.</div></section>'
        )
    disclaimer = report.get("disclaimer")
    warning = f'<p class="section-note stats-note">{_e(disclaimer)}</p>' if disclaimer else ""
    groups = []
    for group in report.get("groups", []):
        entries = "".join(
            f'<span class="stat-chip" title="{_e(entry.get("reason", ""))}">'
            f'<span class="stat-rank" aria-hidden="true">{index}</span>'
            f'{_e(str(entry.get("stat", "")).replace("_", " ").title())}</span>'
            for index, entry in enumerate(group.get("entries", []), start=1)
        )
        if entries:
            groups.append(
                f'<div class="sub-panel stat-group"><h3>{_e(group.get("label") or group.get("group_id") or "Stats")}</h3>'
                f'<div class="stat-chips">{entries}</div></div>'
            )
    if groups:
        body = f'<div class="stat-groups">{"".join(groups)}</div>'
    else:
        body = '<div class="section-note">Stat priority is unavailable.</div>'
    return f'<section class="panel-section" id="stats">{head}{warning}{body}</section>'


def _render_gear_section(spec: GuideSpec) -> str:
    build = spec.builds[0] if spec.builds else None
    report = dict(build.gear_recommendation_report or {}) if build else {}
    head = _section_head("Weapons and Armor")
    if not report:
        return (
            f'<section class="panel-section" id="weapons-and-armor">{head}'
            '<div class="sub-panel"><p>Gear targeting is unavailable.</p></div></section>'
        )
    best = _render_type_group(
        "Best targets for this spec",
        tuple(report.get("best_weapon_types", [])) + tuple(report.get("best_armor_types", [])),
    )
    available = _render_type_group(
        "Available to this class",
        tuple(report.get("available_weapon_types", [])) + tuple(report.get("available_armor_types", [])),
    )
    warning_values = [str(warning) for warning in report.get("warnings", []) if warning]
    warnings = (
        f'<p class="gear-note">Notes: {_e(" · ".join(warning_values).replace("_", " "))}</p>'
        if warning_values
        else ""
    )
    return (
        f'<section class="panel-section" id="weapons-and-armor">{head}'
        f'<div class="gear-groups">{best}{available}</div>{warnings}</section>'
    )


def _render_type_group(title: str, values: tuple[str, ...]) -> str:
    unique_values = tuple(dict.fromkeys(value for value in values if value))
    if not unique_values:
        body = "<p>Unknown.</p>"
    else:
        chips = "".join(f'<span class="chip">{_e(value.replace("_", " ").title())}</span>' for value in unique_values)
        body = f'<div class="chip-row">{chips}</div>'
    return f'<div class="sub-panel gear-group"><h3>{_e(title)}</h3>{body}</div>'


def _render_talent_tree_section(spec: GuideSpec) -> str:
    head = _section_head("Talents")
    tree_builds = [build for build in spec.builds if build.tree_panel or build.tree]
    if not tree_builds:
        return (
            f'<section class="panel-section" id="talents">{head}'
            '<div class="sub-panel"><p>No talent tree data is available for this build.</p></div></section>'
        )
    first_panel = tree_builds[0].tree_panel
    first_tree = _first_panel_tree(first_panel) if first_panel else tree_builds[0].tree
    assert first_tree is not None
    levels = sorted(
        {
            snapshot.level
            for build in tree_builds
            for snapshot in _build_tree_snapshots(build)
        }
    )
    if not levels:
        levels = [first_tree.level]
    first_level = first_tree.level if first_tree.level in levels else levels[-1]
    level_index = levels.index(first_level)
    ticks = "".join(
        f'<span data-level-tick="{level}" class="is-active">{level}</span>'
        if level == first_level
        else f'<span data-level-tick="{level}">{level}</span>'
        for level in levels
    )
    scrub = (
        '<div class="scrub-wrap">'
        '<div class="scrub-head"><span class="scrub-title">Character Level</span>'
        f'<span class="scrub-level" data-tree-level-label>Lv {first_level}</span></div>'
        f'<input type="range" class="level-scrub" data-tree-level-selector min="0" max="{len(levels) - 1}" '
        f'step="1" value="{level_index}" data-tree-levels="{_json_attr(levels)}" aria-label="Character level">'
        f'<div class="scrub-ticks">{ticks}</div></div>'
    )
    build_selector = ""
    if len(tree_builds) > 1:
        build_options = "".join(
            f'<option value="{_e(_build_tree_panel_id(build))}">{_e(build.label)}</option>'
            for build in tree_builds
        )
        build_selector = f'<label>Build <select data-tree-build-selector>{build_options}</select></label>'
    legend = (
        '<div class="tree-legend">'
        '<span><span class="legend-dot legend-selected" aria-hidden="true"></span>Selected</span>'
        '<span><span class="legend-dot legend-free" aria-hidden="true"></span>Granted (free)</span>'
        '<span><span class="legend-dot legend-available" aria-hidden="true"></span>Available</span>'
        '<span><span class="legend-dot legend-locked" aria-hidden="true"></span>Locked</span>'
        '<span class="legend-hint">Hover or focus a node for its tooltip · click to pin — pins stack</span>'
        "</div>"
    )
    panels = "".join(
        _render_build_tree_panel(build, hidden=index > 0)
        for index, build in enumerate(tree_builds)
    )
    return (
        f'<section class="panel-section" id="talents" data-guide-tree-panel>{head}'
        '<div class="frame"><div class="frame-inner">'
        '<div class="tree-toolbar">'
        f"{scrub}{build_selector}"
        f'<span class="chip mono" data-tree-budget-summary>AE {first_tree.ae_spent}/{first_tree.max_ae} - TE {first_tree.te_spent}/{first_tree.max_te}</span>'
        "</div>"
        f"{legend}"
        f'<div class="tree-scroll">{panels}</div>'
        "</div></div></section>"
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
    node_count = len(tree.nodes)
    return (
        f'<div class="{group_class}" data-tree-kind="{_e(tree.tree_kind)}" data-tree-id="{_e(tree.tree_id)}" '
        f'data-tree-level="{tree.level}" data-tree-snapshots="{_json_attr([snapshot.to_dict() for snapshot in tree.snapshots])}">'
        '<div class="tree-group-head">'
        f"{DIAMOND}"
        f"<h3>{_e(_tree_group_label(tree.tree_kind))}</h3>"
        f'<span class="section-count">{node_count} node{"" if node_count == 1 else "s"}</span>'
        '<span class="head-rule head-rule-dim" aria-hidden="true"></span></div>'
        f"{_render_tree_canvas(tree)}</div>"
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
    rank_html = ""
    if node.max_rank > 1:
        rank_html = f'<span class="tree-rank">{_e(f"{node.rank}/{node.max_rank}")}</span>'
    style = _tree_node_style(node)
    return (
        f'<button class="tree-node {shape} {state_class}" data-tree-node-id="{node.entry_id}" '
        f'data-tooltip-id="{_e(node.tooltip_id)}" data-state="{_e(node.tree_state)}" '
        f'data-rank="{node.rank}" data-max-rank="{node.max_rank}" '
        f'style="{style}" '
        f'aria-label="{_e(node.name)}">'
        f"{label}{rank_html}</button>"
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
    return (
        '<details class="leveling-path" open><summary><span class="leveling-heading">Leveling Path</span>'
        '<span class="mono">order to spend your essence</span></summary>'
        f'<ol class="leveling-list">{items}</ol></details>'
    )


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
        items.append(
            f"<li><strong>Level {_e(level)}</strong> "
            f"<span class=\"chip\">{_e(essence)}</span> "
            f"{_e(name)}</li>"
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
    return (
        '<details class="leveling-path" open><summary><span class="leveling-heading">Leveling Path</span>'
        '<span class="mono">order to spend your essence</span></summary>'
        f'<ol class="leveling-list">{"".join(items)}</ol>{warning_html}</details>'
    )


def _render_node(node: Any) -> str:
    icon = _render_icon_content(node, "../assets")
    meta = f"{node.tab_name} · {node.essence_kind} · Lv {node.required_level}"
    inner = (
        f'<span class="icon-frame" aria-hidden="true">{icon}</span>'
        f'<span class="node-text"><span class="node-name">{_e(node.name)}</span>'
        f'<span class="node-meta">{_e(meta)}</span></span>'
    )
    if node.db_url:
        return (
            f'<a class="node-card" href="{_e(node.db_url)}" target="_blank" rel="noopener" '
            f'data-tooltip-id="{_e(node.tooltip_id)}">{inner}</a>'
        )
    return f'<article class="node-card" data-tooltip-id="{_e(node.tooltip_id)}">{inner}</article>'


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
