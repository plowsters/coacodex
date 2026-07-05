# M1.11C CoA Builder Talent Tree Parity Design

Date: 2026-07-05

Status: ready for implementation

## Goal

M1.11C makes the generated guide talent trees match the official CoA Builder structure instead of approximating a single mixed tree from normalized row/column values.

The guide must represent the same conceptual layout players see in game and in the CoA Builder:

- Ability Essence class tree.
- Talent Essence spec tree.
- Automatic level-gated passive lane.

Stalking Venomancer is the first parity target because it has already been called out as visibly wrong and it exercises class-wide ability essence plus spec-specific talent essence.

The talent tree is intentionally desktop-focused. M1.11C should make it clean on 1080p, 2K, and 4K desktop or laptop screens. It should not implement a mobile-responsive tree reflow because that adds high layout complexity and does not match how most WoW talent tools are used.

## Current Problem

The M1.10 tree renderer builds one mixed tree from normalized nodes, row/column fields, and inferred connections. That is useful for legality debugging but not faithful enough for a player guide.

Observed issues:

- Class-wide Ability Essence and spec Talent Essence nodes are visually mixed.
- Level-gated passives are treated like normal nodes instead of a separate straight progression lane.
- Calculated connections do not match the CoA Builder.
- Relative spacing is not preserved.
- The selected build and level snapshots are useful, but they are drawn on top of the wrong structure.

## Source Priority

Tree parity should use sources in this order:

1. CoA Builder runtime layout data, if it exposes computed node positions, groups, and connector paths.
2. CoA Builder DOM measurements, captured after selecting a class/spec.
3. Normalized builder payload row/column/connection data, only when verified against Builder screenshots.
4. Inference as a warning-producing fallback, not as the default for guide output.

## Layout Artifact

Create a builder layout artifact:

```text
coa-builder-tree-layout-v1
```

File location:

```text
coa_scraper/reports/tree_layout/<class_key>/<spec_key>.json
```

Important fields:

- `schema_version`
- `capture_id`
- `captured_at`
- `source_url`
- `builder_slug`
- `class_name`
- `source_spec_name`
- `display_spec_name`
- `viewport`
- `trees`
- `screenshots`
- `warnings`

Each tree:

- `tree_kind`: `ability_essence`, `talent_essence`, or `level_passives`
- `title`
- `coordinate_system`: `builder_pixels`, `builder_grid`, or `normalized_grid`
- `bounds`
- `nodes`
- `edges`
- `warnings`

Each node:

- `entry_id`
- `spell_id`
- `name`
- `source_tab_name`
- `essence_kind`
- `required_level`
- `rank`
- `max_rank`
- `node_type`
- `x`
- `y`
- `width`
- `height`
- `row`
- `col`
- `source_coordinates`
- `tooltip_id`

Each edge:

- `source_entry_id`
- `target_entry_id`
- `edge_kind`
- `path`
- `source_anchor`
- `target_anchor`

## Capture Strategy

Add a Playwright script:

```text
coa_scraper/scripts/capture-builder-tree-layout.mjs
```

Responsibilities:

1. Load the official CoA Builder URL or a local captured builder page when supported.
2. Select class and spec.
3. Wait for the builder to finish rendering.
4. Capture runtime layout data if available.
5. Capture DOM node boxes and SVG/canvas connector data if runtime layout is not exposed.
6. Save full-page and tree-container screenshots.
7. Emit `coa-builder-tree-layout-v1`.

The script should be able to run unattended once the page is loaded. If the live builder requires manual interaction, the script should pause with clear terminal instructions and then resume capture.

## Renderer Architecture

M1.11C should move from one mixed tree per build to a tree panel with multiple groups:

```text
GuideTreePanel
  build_rank
  build_label
  level
  max_ae
  max_te
  trees:
    - ability_essence
    - talent_essence
    - level_passives
  snapshots
  warnings
```

Rendering:

- Use absolute positioning when the layout artifact provides pixel coordinates.
- Use grid positioning only when the source artifact is grid-based and verified.
- Render edges as SVG paths or segments from the layout artifact.
- Render passives as a horizontal or vertical lane exactly as captured.
- Target desktop widths first; allow horizontal scrolling on narrow containers rather than resizing or reflowing the tree.
- Preserve the existing level selector and legality state overlays.

Guide behavior:

- Build selector changes all tree groups together.
- Level selector updates selected/available/gated state across all groups.
- Hover/focus tooltips and `db.ascension.gg` links continue to work.

## Legality and State

M1.11C should not invent new legality rules. It should reuse:

- `BuildRules`
- `EligibilityPolicy`
- Existing AE/TE budgets
- Existing prerequisites and tab gates

The layout artifact decides where nodes are drawn. The legality engine decides node state.

State labels:

- `selected`
- `free`
- `available`
- `gated_level`
- `gated_prerequisite`
- `gated_tab_essence`
- `over_budget`
- `inactive`

## Visual Parity Workflow

Add a manual checklist:

```text
docs/tree-parity-checklist.md
```

First target:

```text
Venomancer / Stalking
```

Checklist:

- Capture CoA Builder screenshot for Stalking Venomancer.
- Generate local guide screenshot for Stalking Venomancer.
- Compare Ability Essence tree node positions and connections.
- Compare Talent Essence tree node positions and connections.
- Compare level passive lane.
- Compare selected build highlights at level 60.
- Record screenshot paths, capture date, viewport, and known differences.

Automated screenshot diff can be added later, but manual parity is acceptable for M1.11C because external Builder rendering may drift and screenshots can be noisy.

## Testing Strategy

Unit tests:

- Layout artifact parser accepts a fixture with three tree kinds.
- Guide tree builder keeps class AE nodes, spec TE nodes, and level passives separate.
- Renderer outputs separate tree containers with stable `data-tree-kind` attributes.
- Tree state snapshots still apply selected/available/gated classes.
- Missing layout artifact falls back to normalized layout with a visible warning.

Integration tests:

- Fixture report can render a multi-tree guide page.
- The generated HTML has no network calls.
- `db.ascension.gg` tooltip links remain intact.

Browser-gated checks:

- Capture Stalking Venomancer layout.
- Screenshot generated guide.
- Manually compare to CoA Builder and update checklist.

## Non-Goals

- Do not implement exact level-by-level talent order in M1.11C. That belongs to M1.11F.
- Do not scrape all class/spec layouts before the Stalking Venomancer capture path is stable.
- Do not require live builder access to run package tests.
- Do not use generated screenshots as required unit-test fixtures.
- Do not implement mobile-responsive tree resizing or mobile-specific reflow.

## Risks

- Builder runtime may not expose stable layout data. Mitigation: fall back to DOM measurements and record parser warnings.
- Canvas-rendered connectors may be hard to recover. Mitigation: prefer runtime graph data; otherwise use normalized edges with captured node coordinates and mark edge path source.
- Live Builder UI can change. Mitigation: store capture metadata, parser version, and screenshot evidence.
- Pixel-perfect parity can overfit one viewport. Mitigation: capture a standard desktop viewport first, then add responsive rules only after desktop parity is correct.
