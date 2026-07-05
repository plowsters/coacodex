# M1.11 Report Correctness and Data Parity Implementation Plan

> **For agentic workers:** Use test-driven changes for code tasks. Commit after each checkpoint. Do not regenerate large scraper artifacts unless the task explicitly requires it.

**Goal:** Correct the M1.10 report defects that are safe to fix immediately, then implement the deeper data/simulation work behind explicit schemas, tests, and cache policies.

**Architecture:** Preserve the existing package boundaries. Scraper code owns external data collection and assets. `coa_meta` owns role resolution, legality, scoring, APLs, simulation, and report rendering. Static guide pages consume local artifacts only.

**Tech Stack:** Python 3.14, Node.js scraper scripts, Playwright only for builder parity captures, pytest, Node test scripts where existing, static HTML/CSS/JS, JSON/JSONL artifacts.

---

## Checkpoint 1: M1.11A Quick Fixes

Status: implemented.

Files changed:

- `coa_meta/guide_rendering.py`
- `coa_meta/guide_tooltips.py`
- `coa_meta/display_names.py`
- `coa_meta/reporting.py`
- `coa_meta/guide_builder.py`
- `coa_meta/roles.py`
- `coa_meta/data/role_overrides.json`
- `coa_meta/stats.py`
- `coa_meta/gear.py`
- `coa_meta/rotation_loops.py`
- Tests for rendering, tooltips, display names, roles, stats, and gear.

Verification:

```bash
PYTHONPATH=. pytest
PYTHONPATH=. python -m coa_meta meta \
  --entries tests/fixtures/meta_report_fixture.jsonl \
  --classes tests/fixtures/meta_classes.json \
  --out /tmp/coa-m1-11-smoke \
  --format json --format html
```

Expected:

- All tests pass.
- Index contains six role headers.
- Role filters are multi-select.
- Front-page disclaimer is visible.
- Tooltip tables render.
- No visible "medium confidence" guide badges.

---

## Checkpoint 2: Role Authority and Role-Specific Index Schema

Purpose: stop explaining non-DPS roles through DPS labels.

### Step 1: Add role objective tests

Create or extend tests:

- `tests/test_roles.py`
- `tests/test_scoring_engine.py`
- `tests/test_meta_report_runner.py`
- `tests/test_guide_rendering.py`

Assertions:

- `GUIDE_ROLES == ("melee_dps", "caster_dps", "ranged_dps", "tank", "healer", "support")`.
- Role map records serialize source, confidence, evidence, and optional authority URL.
- Tank/healer/support builds expose a `primary_index_label` that is not "Projected DPS Index".
- DPS specs can still expose backward-compatible `projected_dps_index`.
- Report cards and metric tooltips use role-specific labels.

Run:

```bash
PYTHONPATH=. pytest tests/test_roles.py tests/test_scoring_engine.py tests/test_meta_report_runner.py tests/test_guide_rendering.py
```

Expected: RED until implementation.

### Step 2: Add role map schema and data

Create:

- `docs/data/role-map-schema.md`
- `coa_meta/data/spec_roles.json`

Schema fields:

- `schema_version`
- `class_name`
- `source_spec_name`
- `display_spec_name`
- `role`
- `engine_role`
- `source`: `authoritative`, `curated`, `inferred`
- `confidence`
- `evidence`
- `source_urls`
- `notes`

Migrate current role overrides into this richer file. Keep `role_overrides.json` as a compatibility input for one release or replace the loader with backward-compatible parsing.

### Step 3: Add role objective payload

Add a data object, likely in `coa_meta/scoring.py` or a new `coa_meta/objectives.py`:

```text
RoleObjectiveResult
  objective_id
  label
  primary_index
  primary_index_label
  objective_breakdown
  warnings
```

Map:

- `melee_dps`, `ranged_dps`, `caster_dps` -> damage objective.
- `healer` -> healing objective.
- `tank` -> survival/threat objective.
- `support` -> support objective.

Keep old fields during transition:

- `projected_dps_index`: still numeric for compatibility.
- `primary_index`: preferred for guide rendering.
- `primary_index_label`: preferred display label.

### Step 4: Render role-specific metric names

Modify:

- `coa_meta/guide_builder.py`
- `coa_meta/guide_rendering.py`
- `coa_meta/reporting.py`
- `docs/data/meta-report-schema.md`

Expected guide copy:

- Damage specs: "Projected Damage Index"
- Healers: "Projected Healing Index"
- Tanks: "Projected Survival/Threat Index"
- Support: "Projected Support Index"

### Step 5: Verify and commit

Run:

```bash
PYTHONPATH=. pytest
PYTHONPATH=. python -m coa_meta meta \
  --entries tests/fixtures/meta_report_fixture.jsonl \
  --classes tests/fixtures/meta_classes.json \
  --out /tmp/coa-m1-11-role-index-smoke \
  --format json --format html
```

Commit:

```bash
git add coa_meta tests docs
git commit -m "Add role-specific report indexes"
```

---

## Checkpoint 3: CoA Builder Tree Parity Capture

Purpose: stop approximating talent trees when the Builder has a canonical layout.

### Step 1: Define parity fixture contract

Create:

- `docs/data/builder-tree-layout-schema.md`
- `tests/fixtures/builder_tree_layout_stalking_venomancer.json`

Schema:

- `class_name`
- `source_spec_name`
- `display_spec_name`
- `capture_url`
- `capture_date`
- `trees`
  - `tree_kind`: `ability_essence`, `talent_essence`, `level_passives`
  - `nodes`
  - `edges`
  - `layout`
  - `source_coordinates`
  - `warnings`

Tests should assert the renderer can keep trees separate:

- Class-wide Ability Essence nodes appear only in the AE tree.
- Spec Talent Essence nodes appear only in the TE tree.
- Level passives appear in a straight lane and have zero cost.

### Step 2: Add capture script

Create:

- `coa_scraper/scripts/capture-builder-tree-layout.mjs`

Behavior:

- Accept builder URL, class/spec selector, output directory, and screenshot directory.
- Use existing Playwright/browser utilities where possible.
- Capture runtime layout JSON before screenshot comparison.
- Save Stalking Venomancer as the first fixture target.
- Do not hard-code browser interactions that only work on one viewport.

Command shape:

```bash
npm --prefix coa_scraper run capture:tree-layout -- \
  --class Venomancer \
  --spec Stalking \
  --out coa_scraper/reports/tree_layout \
  --screenshots coa_scraper/reports/tree_layout/screenshots
```

### Step 3: Rework guide tree model

Modify:

- `coa_meta/guide_models.py`
- `coa_meta/guide_tree.py`
- `coa_meta/guide_builder.py`
- `coa_meta/guide_rendering.py`

Add:

- Multiple trees per build instead of one mixed tree.
- `tree_kind`.
- Passive lane rendering.
- Source-layout provenance and warnings.

### Step 4: Add screenshot parity workflow

Create:

- `docs/tree-parity-checklist.md`

Checklist:

- Open generated Stalking Venomancer report.
- Open CoA Builder Stalker Venomancer.
- Compare AE tree node order.
- Compare TE tree node order.
- Compare connections.
- Compare passive lane.
- Record screenshot paths and capture date.

### Step 5: Verify and commit

Run:

```bash
PYTHONPATH=. pytest tests/test_guide_tree.py tests/test_guide_builder.py tests/test_guide_rendering.py
npm --prefix coa_scraper test
```

Only run browser capture when network/browser access is available.

Commit:

```bash
git add coa_meta coa_scraper tests docs
git commit -m "Add CoA builder tree parity layout support"
```

---

## Checkpoint 4: AscensionDB Asset and Canonical Data Cache

Purpose: add icons/images and richer DB records without hammering AscensionDB.

### Step 1: Add cache manifest tests

Create tests under `coa_scraper/test/` or the existing Node test location:

- Manifest skips unchanged URLs when ETag/Last-Modified matches.
- Missing headers fall back to content hash.
- Parser writes stable asset paths.
- Large unchanged records are not rewritten.
- Concurrency default is conservative.

### Step 2: Add scraper manifest schema

Create:

- `docs/data/ascensiondb-cache-schema.md`

Fields:

- `schema_version`
- `parser_version`
- `url`
- `kind`
- `id`
- `status`
- `etag`
- `last_modified`
- `content_sha256`
- `parsed_sha256`
- `fetched_at`
- `checked_at`
- `asset_paths`
- `warnings`

### Step 3: Extend scraper script

Modify or create:

- `coa_scraper/scripts/enrich-ascensiondb-assets.mjs`
- `coa_scraper/package.json`

Options:

- `--entries`
- `--items`
- `--out`
- `--asset-root`
- `--manifest`
- `--stale-days`
- `--force`
- `--limit`
- `--concurrency`

Default behavior:

- Use conditional requests when headers exist.
- Parse without rewriting unchanged outputs.
- Download icon/image files only when missing or changed.
- Keep logs stage-based and concise.

### Step 4: Connect assets to guide renderer

Modify:

- `coa_meta/guide_assets.py`
- `coa_meta/guide_builder.py`
- `coa_meta/guide_rendering.py`

Expected:

- Spell/talent node cards and tree nodes can show local icon images.
- Gear chips can use icon assets when item/armor/weapon data exists.
- Missing images use deterministic placeholders.

### Step 5: Verify and commit

Run:

```bash
npm --prefix coa_scraper test
PYTHONPATH=. pytest tests/test_guide_assets.py tests/test_guide_builder.py tests/test_guide_rendering.py
```

If network access is available, run a tiny bounded scrape:

```bash
npm --prefix coa_scraper run enrich-assets -- --limit 5 --concurrency 2
```

Commit:

```bash
git add coa_scraper coa_meta tests docs
git commit -m "Add cache-aware AscensionDB asset enrichment"
```

---

## Checkpoint 5: Exact Leveling Path

Purpose: produce actionable level-by-level talent choices.

### Step 1: Add tests for essence awards

Create:

- `tests/test_leveling_path.py`

Assertions:

- Level 10 grants Ability Essence.
- Levels alternate AE/TE through 60.
- Level passives unlock automatically and do not spend essence.
- Chosen path never violates prerequisites, tab gates, or budgets.
- The final path reconstructs the selected level-60 build when possible.

### Step 2: Add path generator

Create:

- `coa_meta/leveling_path.py`

Algorithm:

1. Build target node set from selected build.
2. Iterate levels 10 through 60.
3. Add automatic passives at their source level.
4. Award AE on level 10 and every other level; TE on alternate levels.
5. Among legal target nodes of the awarded essence kind, pick the node with highest marginal role objective value.
6. If no target node is legal, pick the prerequisite or gate-unlocking node that best advances the target build.
7. Emit warnings when the target build cannot be reconstructed exactly.

### Step 3: Render path per selected build

Modify:

- `coa_meta/guide_tree.py`
- `coa_meta/guide_models.py`
- `coa_meta/guide_rendering.py`

Expected:

- The leveling path changes when the build selector changes.
- The path shows level, essence type, node, reason, and automatic passive unlocks.

### Step 4: Verify and commit

Run:

```bash
PYTHONPATH=. pytest tests/test_leveling_path.py tests/test_guide_tree.py tests/test_guide_rendering.py
```

Commit:

```bash
git add coa_meta tests docs
git commit -m "Generate exact level-by-level build paths"
```

---

## Checkpoint 6: Rotation Simulation and Guide Output

Purpose: move from category summaries to compact guide-ready rotations.

### Step 1: Add rotation candidate tests

Create or extend:

- `tests/test_apl_interpreter.py`
- `tests/test_combat_engine.py`
- `tests/test_rotation_optimizer.py`
- `tests/test_rotation_loops.py`

Assertions:

- APL priority list executes the first ready action.
- Buff/debuff/cooldown/resource state changes affect available actions.
- Candidate generator can produce alternate opener/priority sequences.
- Rotation guide output is 4-12 entries for normal builds.
- Healer/tank/support rotations optimize role objectives, not DPS only.

### Step 2: Extend combat state and APL execution

Modify:

- `coa_meta/combat/engine.py`
- `coa_meta/combat/events.py`
- `coa_meta/apl_interpreter.py`
- `coa_meta/mechanics.py`

Add:

- Buff/debuff aura state.
- Cooldown state.
- Resource state.
- Proc state.
- GCD windows.
- Target count.
- Role objective event aggregation.

### Step 3: Add rotation candidate generator

Create:

- `coa_meta/rotation_optimizer.py`

Inputs:

- Selected build.
- Mechanics repository.
- APL document.
- Encounter profile.
- Role objective.
- Iteration/beam config.

Outputs:

- Best candidate.
- Candidate score distribution.
- Chosen guide steps.
- Reliability warnings.

### Step 4: Render guide-ready rotation

Modify:

- `coa_meta/reporting.py`
- `coa_meta/guide_models.py`
- `coa_meta/guide_rendering.py`
- `docs/data/meta-report-schema.md`

Add payload:

```text
rotation_guide:
  schema_version: "coa-rotation-guide-v1"
  source: "simulated_apl" | "heuristic_apl"
  role
  objective_id
  opener
  core_priority
  cooldowns
  conditions
  defensive_or_support
  reliability_label
  warnings
```

### Step 5: Verify and commit

Run:

```bash
PYTHONPATH=. pytest tests/test_apl_interpreter.py tests/test_combat_engine.py tests/test_rotation_optimizer.py tests/test_rotation_loops.py tests/test_meta_report_runner.py
```

Commit:

```bash
git add coa_meta tests docs
git commit -m "Simulate APL rotations for guide output"
```

---

## Checkpoint 7: Build Diversity Clustering

Purpose: select genuinely different build playstyles, not tiny variations of the same loop.

### Step 1: Add clustering tests

Extend:

- `tests/test_build_diversity.py`
- `tests/test_meta_report_runner.py`

Scenarios:

- Two poison DoT loop builds with small node differences collapse into one representative.
- A stealth/burst build remains distinct from a DoT loop build.
- A build below the performance band is excluded even if distinct.
- A build with no consistent rotation is excluded unless explicitly experimental.

### Step 2: Upgrade fingerprints

Modify:

- `coa_meta/build_diversity.py`

Add features:

- Core rotation action set.
- Opener action set.
- Cooldown cadence.
- Stealth/burst markers.
- Pet/summon markers.
- DoT/maintenance markers.
- Role objective contribution vector.

### Step 3: Tune performance band

Use robust thresholds:

- Always consider the top build.
- Candidate band can be within max of configured percent from top and robust standard deviation from top group.
- Minimum reliability threshold.
- Maximum one representative per close cluster.

### Step 4: Verify and commit

Run:

```bash
PYTHONPATH=. pytest tests/test_build_diversity.py tests/test_meta_report_runner.py tests/test_guide_rendering.py
```

Commit:

```bash
git add coa_meta tests docs
git commit -m "Cluster recommended builds by playstyle"
```

---

## Checkpoint 8: Calibration and Confidence Sensitivity

Purpose: make confidence meaningful and prepare Phase 2 live tuning.

### Step 1: Add confidence model tests

Extend:

- `tests/test_calibration_hooks.py`
- `tests/test_scoring_engine.py`
- `tests/test_meta_report_runner.py`

Confidence should consider:

- Source completeness.
- Role-source quality.
- Mechanics coverage.
- DB tooltip match status.
- Simulation coverage.
- Empirical sample size and variance when available.

### Step 2: Add live sanity correction schema

Create:

- `docs/data/live-sanity-schema.md`
- `coa_meta/data/live_sanity_overrides.json`

Fields:

- `class_name`
- `source_spec_name`
- `metric`
- `direction`
- `magnitude`
- `confidence`
- `evidence`
- `source`
- `expires_at` or `builder_version`

This file should not hard-code anecdotal rankings as truth. It exists to flag severe known mismatches and down-rank overconfident theory output until logs are available.

### Step 3: Integrate with report warnings

Modify:

- `coa_meta/calibration.py`
- `coa_meta/scoring.py`
- `coa_meta/reporting.py`
- `coa_meta/guide_rendering.py`

Expected:

- A live sanity warning appears when a known mismatch is present.
- Confidence can be low, medium, or high in practice.
- The default guide still avoids showing confidence as a primary player-facing badge.

### Step 4: Verify and commit

Run:

```bash
PYTHONPATH=. pytest tests/test_calibration_hooks.py tests/test_scoring_engine.py tests/test_meta_report_runner.py tests/test_guide_rendering.py
```

Commit:

```bash
git add coa_meta tests docs
git commit -m "Make confidence sensitive to source quality"
```

---

## Final M1.11 Verification

Run unit tests:

```bash
PYTHONPATH=. pytest
```

Run package smoke:

```bash
PYTHONPATH=. python -m coa_meta meta \
  --entries tests/fixtures/meta_report_fixture.jsonl \
  --classes tests/fixtures/meta_classes.json \
  --out /tmp/coa-m1-11-final-smoke \
  --format json --format md --format html
```

Run real artifact smoke when artifacts are present:

```bash
PYTHONPATH=. python -m coa_meta meta \
  --entries coa_scraper/dist/coa_entries.jsonl \
  --classes coa_scraper/dist/coa_classes.json \
  --db-tooltips coa_scraper/dist/coa_db_spell_tooltips.jsonl \
  --out reports/meta \
  --format json --format md --format html
```

Run scraper tests:

```bash
npm --prefix coa_scraper test
```

Network/browser gated:

```bash
npm --prefix coa_scraper run capture:tree-layout -- --class Venomancer --spec Stalking
npm --prefix coa_scraper run enrich-assets -- --limit 20 --concurrency 2
```

Final docs:

- Update `docs/ROADMAP.md` with M1.11 completion status.
- Update `docs/README.md` current planning focus.
- Update `docs/data/meta-report-schema.md` for new payloads.
- Record remaining P2 gates for AscensionLogs and Vercel serverless upload.
