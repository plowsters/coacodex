# M1.11C CoA Builder Talent Tree Parity Implementation Plan

> **For agentic workers:** Use TDD for parser/model/rendering work. Commit after each checkpoint. Browser capture is allowed only for the capture checkpoint and should not be required by unit tests.

**Goal:** Render guide talent trees with the same structure as the CoA Builder: separate Ability Essence tree, Talent Essence tree, and automatic level-passive lane.

**Architecture:** Introduce a builder layout artifact produced by the scraper/capture side. The guide renderer consumes the artifact when available and falls back to normalized layout with warnings when it is not available. Build legality remains owned by `BuildRules`. Talent trees are desktop-first; do not implement mobile-responsive resizing or reflow.

---

## Checkpoint 1: Layout Artifact Schema and Parser

Files:

- Create `docs/data/builder-tree-layout-schema.md`
- Create `coa_meta/builder_tree_layout.py`
- Create `tests/fixtures/builder_tree_layout_fixture.json`
- Create `tests/test_builder_tree_layout.py`

### Step 1: Add failing parser tests

Fixture should include:

- `schema_version: "coa-builder-tree-layout-v1"`
- class `Venomancer`
- source spec `Stalking`
- three trees:
  - `ability_essence`
  - `talent_essence`
  - `level_passives`
- at least two nodes and one edge in AE and TE trees
- at least three level passive nodes in the passive lane

Assertions:

- Parser returns three tree groups.
- Each node keeps `entry_id`, `spell_id`, `x`, `y`, `width`, `height`, `tree_kind`.
- Edges preserve source and target IDs.
- Invalid tree kind raises a clear error.

Run:

```bash
PYTHONPATH=. pytest tests/test_builder_tree_layout.py
```

Expected: RED.

### Step 2: Implement parser dataclasses

Create dataclasses:

```text
BuilderTreeLayout
BuilderLayoutTree
BuilderLayoutNode
BuilderLayoutEdge
BuilderLayoutBounds
```

Parser functions:

```text
load_builder_tree_layout(path)
load_builder_tree_layouts(root)
layout_for(class_name, source_spec_name)
```

### Step 3: Document schema

Write `docs/data/builder-tree-layout-schema.md` from the M1.11C design.

### Step 4: Verify and commit

Run:

```bash
PYTHONPATH=. pytest tests/test_builder_tree_layout.py
```

Commit:

```bash
git add coa_meta tests docs/data/builder-tree-layout-schema.md
git commit -m "Add builder tree layout artifact parser"
```

---

## Checkpoint 2: Guide Model Supports Multiple Tree Groups

Files:

- Modify `coa_meta/guide_models.py`
- Modify `coa_meta/guide_tree.py`
- Extend `tests/test_guide_tree.py`

### Step 1: Add failing model tests

Assert:

- A guide build can carry a `GuideTreePanel` with multiple `GuideTree` groups.
- AE nodes are only in the `ability_essence` tree.
- TE nodes are only in the `talent_essence` tree.
- Passive nodes are only in `level_passives` and have zero essence cost.
- Existing single-tree consumers still have a compatibility path during migration.

### Step 2: Add model types

Add:

```text
GuideTreePanel
  tree_panel_id
  class_name
  source_spec_name
  display_spec_name
  build_rank
  build_label
  level
  max_ae
  max_te
  trees
  snapshots
  warnings

GuideTree.tree_kind
GuideTree.layout_source
GuideTree.bounds
```

Keep `GuideBuildCard.tree` temporarily for compatibility, but add `tree_panel` as preferred.

### Step 3: Update serialization

Every new model should have `to_dict()` output with schema versions where appropriate.

### Step 4: Verify and commit

Run:

```bash
PYTHONPATH=. pytest tests/test_guide_tree.py tests/test_guide_builder.py
```

Commit:

```bash
git add coa_meta tests
git commit -m "Add multi-tree guide model"
```

---

## Checkpoint 3: Build Tree Panels from Layout Artifacts

Files:

- Modify `coa_meta/guide_tree.py`
- Modify `coa_meta/guide_builder.py`
- Extend `tests/test_guide_tree.py`
- Extend `tests/test_guide_builder.py`

### Step 1: Add failing builder tests

Assertions:

- Given a layout fixture, guide builder uses source coordinates from the layout artifact.
- Without a layout fixture, guide builder falls back to normalized layout and emits `builder_layout_missing`.
- Nodes absent from layout but present in selected build emit `layout_node_missing:<entry_id>` warnings.
- Existing selected/free/available/gated snapshots still apply by entry ID.

### Step 2: Add optional layout root

Extend `build_guide_site()`:

```text
builder_layout_root: Path | str | None = None
```

CLI/report writer can pass it later; tests can call builder directly.

### Step 3: Split nodes by tree kind

Rules:

- `essence_kind == "ability"` -> `ability_essence`
- `essence_kind == "talent"` -> `talent_essence`
- zero-cost automatic level passives -> `level_passives`

When layout artifact specifies a tree kind, trust artifact kind and warn if it conflicts with normalized essence kind.

### Step 4: Verify and commit

Run:

```bash
PYTHONPATH=. pytest tests/test_guide_tree.py tests/test_guide_builder.py
```

Commit:

```bash
git add coa_meta tests
git commit -m "Build guide tree panels from builder layouts"
```

---

## Checkpoint 4: Render Multi-Tree Panels

Files:

- Modify `coa_meta/guide_rendering.py`
- Modify static `GUIDE_CSS` and `GUIDE_JS`
- Extend `tests/test_guide_rendering.py`

### Step 1: Add failing rendering tests

Assert:

- Spec HTML includes separate containers:
  - `data-tree-kind="ability_essence"`
  - `data-tree-kind="talent_essence"`
  - `data-tree-kind="level_passives"`
- Passive lane renders as a lane, not as a normal circular tree.
- Tree nodes still include tooltip IDs.
- JS still has no network calls.
- Level selector updates all groups in a panel.
- CSS does not introduce mobile-specific tree reflow rules; narrow containers should scroll horizontally instead of resizing the tree.

### Step 2: Implement renderer

Preferred structure:

```html
section#talents
  div[data-guide-tree-panel]
    div.tree-group[data-tree-kind="ability_essence"]
    div.tree-group[data-tree-kind="talent_essence"]
    div.passive-lane[data-tree-kind="level_passives"]
```

Use absolute positioning when `layout_source` is `builder_runtime` or `builder_dom`.

Do not add mobile breakpoints that change tree geometry. The guide shell can remain responsive, but the tree component should keep its captured desktop geometry.

### Step 3: Preserve old fallback

If only `build.tree` exists, render the old tree and emit a warning. If `build.tree_panel` exists, prefer it.

### Step 4: Verify and commit

Run:

```bash
PYTHONPATH=. pytest tests/test_guide_rendering.py tests/test_guide_builder.py
```

Commit:

```bash
git add coa_meta tests
git commit -m "Render separate AE TE and passive trees"
```

---

## Checkpoint 5: Capture Script for Builder Layouts

Files:

- Create `coa_scraper/scripts/capture-builder-tree-layout.mjs`
- Modify `coa_scraper/package.json`
- Create Node tests if a parser utility is factored out
- Create `docs/tree-parity-checklist.md`

### Step 1: Add capture command skeleton

Package script:

```json
"capture:tree-layout": "node scripts/capture-builder-tree-layout.mjs"
```

CLI options:

- `--url`
- `--class`
- `--spec`
- `--out`
- `--screenshots`
- `--headless`
- `--viewport`
- `--pause-for-manual-selection`

### Step 2: Implement capture stages

Stages:

1. Load page.
2. Select class/spec or pause for manual selection.
3. Detect tree containers.
4. Extract runtime layout if exposed.
5. Fall back to DOM boxes.
6. Extract or infer edges.
7. Save layout JSON.
8. Save screenshots.

Logs should clearly state which source was used:

- `builder_runtime`
- `builder_dom`
- `normalized_fallback`

### Step 3: Add checklist

Create `docs/tree-parity-checklist.md` with Stalking Venomancer as the first target.

### Step 4: Verify and commit

Run non-browser tests:

```bash
npm --prefix coa_scraper test
PYTHONPATH=. pytest tests/test_builder_tree_layout.py
```

Browser-gated smoke when available:

```bash
npm --prefix coa_scraper run capture:tree-layout -- \
  --class Venomancer \
  --spec Stalking \
  --out coa_scraper/reports/tree_layout \
  --screenshots coa_scraper/reports/tree_layout/screenshots \
  --headless
```

Commit:

```bash
git add coa_scraper docs tests coa_meta
git commit -m "Add CoA builder tree layout capture"
```

---

## Checkpoint 6: CLI and Report Writer Integration

Files:

- Modify `coa_meta/cli.py`
- Modify `coa_meta/report_writers.py` or `guide_writer` path if applicable
- Extend `tests/test_cli.py`
- Extend `tests/test_report_writers.py`

### Step 1: Add failing CLI tests

Add `--builder-layout-root` to `python -m coa_meta meta`.

Assert writer receives the path and guide builder uses it for HTML output.

### Step 2: Implement CLI option

Command example:

```bash
python -m coa_meta meta \
  --entries coa_scraper/dist/coa_entries.jsonl \
  --classes coa_scraper/dist/coa_classes.json \
  --builder-layout-root coa_scraper/reports/tree_layout \
  --out reports/meta \
  --format html
```

### Step 3: Verify and commit

Run:

```bash
PYTHONPATH=. pytest tests/test_cli.py tests/test_report_writers.py tests/test_guide_builder.py
```

Commit:

```bash
git add coa_meta tests docs
git commit -m "Wire builder layouts into guide generation"
```

---

## Final M1.11C Verification

Run:

```bash
PYTHONPATH=. pytest
npm --prefix coa_scraper test
PYTHONPATH=. python -m coa_meta meta \
  --entries tests/fixtures/meta_report_fixture.jsonl \
  --classes tests/fixtures/meta_classes.json \
  --out /tmp/coa-m1-11-c-smoke \
  --format json --format html
```

Browser-gated parity:

```bash
npm --prefix coa_scraper run capture:tree-layout -- \
  --class Venomancer \
  --spec Stalking \
  --out coa_scraper/reports/tree_layout \
  --screenshots coa_scraper/reports/tree_layout/screenshots
```

Then generate a real report with `--builder-layout-root`, screenshot the generated Stalking Venomancer page, and fill out `docs/tree-parity-checklist.md`.

## Completion Criteria

- Guide model supports AE tree, TE tree, and passive lane separately.
- Renderer outputs separate visual tree groups.
- Layout artifacts can be parsed and consumed.
- Missing layouts degrade with visible warnings.
- Stalking Venomancer has a documented screenshot parity workflow.
- Unit tests remain browser-independent.
