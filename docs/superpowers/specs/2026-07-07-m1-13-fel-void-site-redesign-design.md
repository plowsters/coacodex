# M1.13 Fel/Void Site Redesign Design

## Purpose

M1.13 restyles the M1.12 guide site into the externally sourced Claude Design **fel/void**
redesign. It is scoped to **presentation**: CSS, HTML structure, and client JS emitted by the Python
guide generator, self-hosted web fonts, and two small render-time data derivations (a hero
weapon/armor chip and an index stat line) that read from data already present in the report. No
engine, data, legality, scoring, simulation, or tree-geometry changes. All correctness items
(essence full-spend, leveling level-skips, mutually exclusive nodes, level slider) remain in M1.15;
asset localization remains in M1.14; deploy/CI remains in M1.20.

M1.12 was deliberately built as durable behavior/content so this milestone **inherits the wiring and
only restyles it** — icon resolution, role-filter semantics, footer/disclaimer copy, and the header
link all remain functional through the reskin.

### Source of truth (the settled architecture)

The `design/` directory holds Claude Design **canvas** deliverables (`*.dc.html` React + `<sc-for>`/
`{{ }}` DC runtime, plus `extract.js`, `tips-catalog.js`, and per-spec `specs/*.js`). These are a
**visual reference only**. `design/` stays uncommitted and is never shipped.

The redesign is implemented by porting the design's visual language into the existing Python
generator (`coa_meta/guide_rendering.py`, with a small `guide_writer.py` change for fonts). The whole
site — index plus all 70 spec pages — is then regenerated from the single source of truth with the
existing command:

```
python -m coa_meta meta --format html --out reports/meta \
  --entries coa_scraper/dist/coa_entries.jsonl --classes coa_scraper/dist/coa_classes.json
```

**Rejected alternative:** Claude Design's plan to parse the 70+ rendered spec HTML files into
per-spec `specs/*.js` data and serve them through a parameterized `Spec Guide.dc.html`. This is a
lossy round-trip that reverse-engineers data back out of the very HTML the generator produced, and it
creates a second data pipeline that drifts from the real analysis and must be re-run whenever the
numbers change. The generator already emits every spec page from `spec_results` (70 entries), so
editing the templates covers all specs automatically with no per-spec files, no `extract.js`, and no
`.dc.html` runtime.

## Current State

All rendering lives in `coa_meta/guide_rendering.py`:

- **`GUIDE_CSS`** (line ~28): dark, single-look theme. `Inter, system-ui`. Fel/void appear only as
  static accent variables (`--fel`, `--void`); there is no theme toggle and no self-hosted fonts.
- **`GUIDE_JS`** (line ~111): a **single** transient tooltip (`showTooltip`/`removeTooltip` on
  `mouseover`/`mouseout`, keyed by `data-tooltip-id` → `window.COA_TOOLTIPS`), the role-filter click
  handler (multi-select, already select-to-include), and the tree snapshot/level/build logic with SVG
  edge drawing. No pinning, no theme toggle, no ambient canvas.
- **`_render_header`** (line ~247): brand text `CoA Meta Guides`; inline GitHub SVG linking to
  `plowsters/coa_meta_analyzer` (`REPO_URL`, line ~10).
- **`_render_footer`** (line ~257): `© 2026 CoA Meta Analyzer …`; issues/source links to
  `coa_meta_analyzer`; optional `· Generated {generated_at}`.
- **`render_index_html`** (line ~271): hero `<h1>CoA Meta Guides</h1>`, tagline
  `Player-facing class and specialization guides for Conquest of Azeroth.`; role-filter bar + role
  sections; **no** spec/role count. Cards via `_render_spec_card` (line ~338).
- **`render_spec_html`** (line ~298): hero shows role chips only (`_role_chips`) — **no** weapon/armor
  chip. Sections: Recommended Builds, Talents (tree), Rotation, Stats, Weapons and Armor, Abilities,
  Data Notes.
- **`_render_leveling_path_for_build`** (line ~707): renders `.leveling-path <ol>`; `.leveling-path`
  CSS (line ~103) is a plain block list — items flow top-to-bottom in one column. The design intent
  is a multi-column layout, and the requested reading order is **column-major**.
- **`write_guide_site`** (`guide_writer.py`, line ~29): writes `assets/guide.css` and
  `assets/guide.js` from the module constants, plus `tooltip-catalog.json` and the manifest. No font
  assets are copied.

The committed reports already hotlink `db.ascension.gg` icons, so the pages are not offline-self-
contained today; self-hosting fonts (below) is an intentional, independent robustness choice.

## Scope

M1.13 includes:

- A dual **Fel / Void** theme with a header segmented toggle, `localStorage` persistence across
  index↔spec navigation, and default **Fel**.
- Self-hosted **Cinzel / Barlow / JetBrains Mono** WOFF2 fonts vendored into the repo, copied into
  the output `assets/fonts/`, and referenced via `@font-face`.
- An ambient ember-particle canvas background, recolored by theme and disabled under
  `prefers-reduced-motion`.
- Beveled `clip-path` frames, gold accents, and radial-gradient backdrops per the design.
- Rebrand: header brand, page titles, and hero to **CoA Codex** / **Meta Codex**; footer copyright to
  **CoA Codex**; GitHub repo/issue links to `plowsters/coacodex`.
- Index: drop "Player-facing" from the tagline; add a **stat line** of the unique-spec count
  (`N specs · M roles`); restyled cards (hex spec icon, role chip with role-source tooltip, flagship
  badge on `felsworn-tyrant`, warnings chip). Existing multi-select role-filter semantics preserved.
- Spec page: restyled hero with hex icon, role chip, and a **new weapon/armor chip**; sticky section
  nav; restyled Recommended Builds / Rotation / Stats / Weapons & Armor / Abilities panels; reskinned
  talent tree; **multi-pin tooltips**; collapsible leveling path reordered **column-major**
  (top-to-bottom, then left-to-right).
- Test updates asserting the new intended behavior.

M1.13 does not include:

- **Deferred to M1.15:** full AE/TE essence spend; removing `deferred` leveling skips at the source;
  mutually exclusive shared-node handling; the granular 10–60 level slider. The leveling **reorder**
  here is presentation only and does not change which levels appear.
- **Deferred to M1.14:** localizing the hotlinked AscensionDB spell/talent icons.
- **Deferred to M1.20:** GitHub Pages deploy pipeline and CI.
- Any change to tree geometry, snapshots, scoring, rotation data, or gear data. Only presentation and
  the two read-only derivations (weapon chip, stat line) change.
- The "remove Copy build string button" item from the Claude Design notes: the current generator has
  no copy button (it was added and removed inside the Claude Design fork). No-op.

## Design

### 1. Theme system (Fel / Void)

Restructure `GUIDE_CSS` `:root` variables around the design tokens (`--lead`, `--lead-bright`,
`--lead-rgb`, `--accent`, `--accent-rgb`, `--gold`, `--gold-rgb`, `--line`, panel/text/muted tokens,
plus `--bevel`/`--bevel-sm` clip-path polygons). Fel is the default `:root` palette (green lead /
violet accent). Add a `:root[data-theme="void"]` block that overrides the lead/accent tokens to the
Void palette (violet lead / green accent). All component CSS references the tokens, so a single
`data-theme` attribute on `<html>` reskins everything.

A segmented **Fel · Void** control lives in the shared header (`data-theme-toggle`, two
`aria-pressed` buttons). In `GUIDE_JS`: on load, read `localStorage["coa-theme"]` (default `fel`),
set `document.documentElement.dataset.theme`, and reflect `aria-pressed`; on click, swap the value,
persist it, and recolor the ember palette. Persistence makes the choice survive navigation between
the statically generated index and spec pages. Fel/Void are brand palettes, not light/dark, so OS
`prefers-color-scheme` is not consulted for theme selection (it is only consulted for motion, §3).

### 2. Self-hosted fonts

Vendor WOFF2 files into `coa_meta/assets/fonts/` (checked into the repo). Weights: Cinzel 600/700/900;
Barlow 400/500/600/700 (+ italic 500 if used); JetBrains Mono 500/700. `GUIDE_CSS` gains `@font-face`
blocks with `font-display: swap` and `src: url("fonts/<file>.woff2")` — URLs are relative to
`assets/guide.css`, so they resolve identically for the index (`assets/guide.css`) and spec pages
(`../assets/guide.css`). `write_guide_site` copies every file from the vendored font directory into
`output_dir/assets/fonts/` alongside the CSS/JS writes. A module constant lists the font directory so
the copy step and tests share one source. Body text uses Barlow; display headings Cinzel; labels/mono
JetBrains Mono; the existing `system-ui, sans-serif` chain remains the fallback.

### 3. Ember canvas ambient background

Port the design's ember particle field into `GUIDE_JS`: a single fixed, `pointer-events:none`,
`aria-hidden` `<canvas>` injected behind content on each page, sized to the viewport (DPR-capped),
animating upward-drifting particles colored from the active theme palette. It is **not started** when
`window.matchMedia('(prefers-reduced-motion: reduce)').matches`; the static radial-gradient backdrop
is always present so reduced-motion users still get the look. The particle palette updates when the
theme toggles.

### 4. Header, footer, and naming

A shared header fragment (used by index and spec pages) renders, left to right: the **CoA Codex**
brand (hex glyph + wordmark), the **Fel · Void** segmented toggle, and the light-gray inline GitHub
mark. `_render_header` keeps its `home_href` parameter. `REPO_URL` and `ISSUES_URL` become
`https://github.com/plowsters/coacodex` and `.../coacodex/issues`. The shared footer renders
`© 2026 CoA Codex · Fan-made theorycraft tool. Not affiliated with or endorsed by Project Ascension.`,
the issues/source links, and the optional generated/data-capture date from `site.generated_at`. Page
`<title>`s become `CoA Codex` (index) and `<Class> <Spec> Guide · CoA Codex` (spec).

### 5. Index page

- Hero `<h1>` → **Meta Codex**; tagline → `Class and specialization guides for Conquest of Azeroth.`
  (drop "Player-facing"); keep the front-page disclaimer.
- Add a **stat line**: the count of **unique** spec slugs across all role sections and the role
  count, e.g. `70 specs · 6 roles`. Computed in `render_index_html` from `site.specs` (dedupe by
  `slug`) so specs that appear under multiple role sections count once, matching the design's
  `new Set(...).size` behavior.
- Restyle `_render_spec_card`: beveled card, hex spec icon (existing `icon_asset`, monogram
  fallback), class/spec typography, summary, role chip carrying the existing `role:<slug>` tooltip,
  a warnings chip when `warning_count`, and a flagship badge when `slug == "felsworn-tyrant"`. The
  `data-role` attribute and `_render_role_section` grouping are unchanged so the role filter keeps
  working.

### 6. Spec page hero + weapon/armor chip

Restyle the hero (hex icon frame, Cinzel name, uppercase class eyebrow, role chip with the
`role:<slug>` provenance tooltip). Add a **weapon/armor chip** summarizing the spec's gear
recommendation, e.g. `Melee · 1H + Shield · Plate`, built from data already in
`build.gear_recommendation_report` (best/available weapon and armor types) plus an attack-posture
token derived from the spec's role family (caster → `Caster`, ranged_dps → `Ranged`, otherwise
`Melee`). A small helper condenses weapon types into a compact combo descriptor and title-cases the
armor class. The chip degrades gracefully — it omits any token it cannot derive and is skipped
entirely when the gear report is empty. No gear data is recomputed; this is a read-only summary.

### 7. Section nav and panel reskin

Add a sticky in-page section nav (anchors to the existing section ids). Reskin Recommended Builds,
Rotation, Stats, Weapons & Armor, and Abilities panels to the beveled/gold design. All underlying
data and section ids are unchanged; `_render_build`, `_render_rotation_section`,
`_render_stats_section`, `_render_gear_section`, and `_render_node` keep their data contracts and only
change markup/classes.

### 8. Talent tree reskin (behavior preserved)

The tree keeps **all** current behavior: build selector, level selector, per-snapshot node states
(`selected`/`free`/`available`/`gated`/`over_budget`), the budget summary, captured-pixel vs. grid
layouts, and SVG edge drawing. Only node/edge/frame styling changes to match the design. The tree
data attributes (`data-tree-*`, `data-tree-node-id`, `data-tooltip-id`) are retained because both the
snapshot JS and the tooltip JS depend on them.

### 9. Multi-pin tooltips

Replace the single-tooltip logic in `GUIDE_JS` with a model of one transient **hover** tooltip plus a
stack of **pins**, preserving `data-tooltip-id` → tooltip-catalog lookup:

- **Hover / focus** a `[data-tooltip-id]` element → show a transient tooltip with an **accent**
  border, positioned near the element. Skipped if that element is already pinned.
- **Mouse-out / blur** → clear only the transient hover; pins remain.
- **Click** a pinnable node/chip → toggle a pin: if already pinned, remove just that pin; otherwise
  add a pin (rendered with a **gold** border) and clear the transient hover. Multiple pins stack and
  stay visible together.
- **Escape** → clear all pins and the hover.
- **Scroll (capture) / resize** → reposition every pin so it stays glued to its node; drop the
  transient hover.

Pins are keyed by tooltip id and hold a reference to their anchor element for repositioning. Tooltip
DOM is created/removed imperatively (no framework), consistent with the current vanilla JS.

### 10. Leveling path (collapsible, column-major)

Wrap the leveling path in a collapsible `<details>` (summary: `Leveling Path — order to spend your
essence`). Render the steps as a **multi-column** list (CSS `columns` / column-flow) so items read
**top-to-bottom within a column, then left-to-right across columns** — the requested order, and the
inverse of a row-major grid. Each item keeps its `Level N · essence · node name` content from
`_render_leveling_path_for_build`; the step data and `deferred`-skip behavior are unchanged (the
skip fix is M1.15).

## Testing

Update `tests/test_guide_rendering.py` (and touch `tests/test_report_writers.py` /
`tests/test_guide_assets.py` where they assert asset output), asserting **intended behavior** rather
than snapshotting markup (per the M1.14 test-integrity principle):

- **Naming:** rendered index/spec contain brand `CoA Codex`, footer `© 2026 CoA Codex`, and GitHub
  links to `plowsters/coacodex`; the old `CoA Meta Analyzer` / `coa_meta_analyzer` strings are gone.
- **Tagline:** the index tagline no longer contains "Player-facing".
- **Theme:** the header renders the `data-theme-toggle` control; `GUIDE_JS` reads/writes
  `coa-theme` and sets `data-theme`; `GUIDE_CSS` defines a `:root[data-theme="void"]` block.
- **Fonts:** `GUIDE_CSS` contains `@font-face` rules with `fonts/…woff2` URLs; `write_guide_site`
  copies the vendored font files into `assets/fonts/` (assert the files exist in a temp output).
- **Stat line:** the index stat line equals the unique-slug count (e.g. one spec listed under two
  roles counts once).
- **Weapon chip:** a spec with a populated gear report renders a weapon/armor chip; a spec with an
  empty gear report renders no chip and does not error.
- **Leveling path:** the rendered leveling path uses the column-flow container (assert the multicolumn
  CSS/markup) and remains inside a `<details>`.
- **Multi-pin tooltips:** `GUIDE_JS` contains the pin/Escape/scroll-reposition logic and pinnable
  nodes expose the required data attributes; the tooltip-catalog lookup path is retained.
- **Reduced motion:** the ember canvas init is guarded by a `prefers-reduced-motion` check.

Then run the full suite (`pytest`) and the HTML smoke regeneration (the `python -m coa_meta meta
--format html` command) and confirm the index and all spec pages regenerate.

## Exit Criteria

- The generated site renders in the fel/void design: dual-theme toggle works and persists across
  index↔spec navigation, defaulting to Fel; beveled frames, gold accents, and self-hosted Cinzel/
  Barlow/JetBrains Mono fonts load from `assets/fonts/`; the ember canvas animates and is disabled
  under `prefers-reduced-motion`.
- Every page shows the **CoA Codex** brand, the `coacodex` GitHub links, and the footer with
  `© 2026 CoA Codex` and the non-affiliation notice.
- The index tagline omits "Player-facing" and shows the unique-spec stat line (70 specs).
- Spec heroes show the weapon/armor chip; the talent tree retains build/level/snapshot behavior;
  tooltips support multi-pin (hover, click-to-pin stacking, click-to-unpin, Escape-clear, scroll
  re-glue); the leveling path reads column-major inside a collapsible section.
- `design/` remains uncommitted and unreferenced by shipped output.
- The full test suite passes and the HTML report command regenerates the index and all 70 spec pages.
