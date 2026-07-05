# M1.9 Combat Engine and Theorycraft Completion Plan

## Objective

Implement the foundation for a full CoA combat engine while finishing the report features that make the theorycraft output complete and usable. The plan follows the design in:

- `docs/superpowers/specs/2026-07-05-m1-9-combat-engine-and-theorycraft-completion-design.md`

## Checkpoint 0: Report Runner Hardening

Status: started in the M1.8 follow-up.

Tasks:

- Add dynamic zero-cost node closure so free nodes unlock after paid prerequisites are selected.
- Fall back to legal partial builds when the configured budget floor is unreachable.
- Add auto role resolution for reportable specs.
- Pass resolved roles into scoring and APL profile loaders.
- Serialize resolved role in spec results and build provenance.
- Add a root `package.json` wrapper so `npm run pipeline:m1.8` works from the repository root.

Verification:

```bash
python -m pytest tests/test_build_rules.py::test_zero_cost_nodes_unlock_after_paid_prerequisites_are_selected -q
python -m pytest tests/test_meta_report_runner.py tests/test_cli.py tests/test_package_metadata.py -q
python -m coa_meta meta --entries coa_scraper/dist/coa_entries.jsonl --classes coa_scraper/dist/coa_classes.json --out /tmp/coa-meta-role-check --format json
```

Expected smoke result:

- 70 spec result rows.
- 0 empty top-build rows.
- Role counts are serialized in JSON.
- Specs with unreachable budget floors have `budget_floor_unreachable_with_current_gates`.

## Checkpoint 1: Mechanics Schema and Repository

Goal: define the mechanics corpus before parsing or simulating.

Tasks:

- Add `coa_meta/mechanics.py` with dataclasses for:
  - `MechanicRecord`
  - `MechanicEffect`
  - `ProcRule`
  - `ScalingRule`
  - `MechanicProvenance`
- Add `coa_meta/mechanics_repository.py` for spell/effect lookup by `spell_id`, node id, and name.
- Define JSON validation helpers for `coa-mechanics-v1`.
- Add a small fixture covering:
  - direct damage
  - DoT
  - cooldown
  - passive buff
  - pet summon
  - healing/support effect
- Document `coa-mechanics-v1` under `docs/data/`.

Tests first:

```bash
python -m pytest tests/test_mechanics_schema.py -q
```

Expected initial failure:

- Import or validation failures until the mechanics module exists.

Implementation notes:

- Keep the schema permissive enough for low-confidence inferred mechanics.
- Store unknown fields under provenance or raw source, not as silent omissions.
- Do not make simulation depend on perfect coefficients.

## Checkpoint 2: AscensionDB Mechanics and Item Enrichment

Goal: expand M1.8 enrichment beyond spell tooltips into mechanics and gear-ready data.

Tasks:

- Extend or add scraper scripts for:
  - spell registration payloads
  - buff/effect tooltip pages
  - item records
  - weapon type, armor type, slot, stats, use/equip/proc text
  - icons/assets
- Prefer AscensionDB for canonical spells/effects/items when builder fields are absent.
- Write artifacts:
  - `coa_scraper/dist/coa_mechanics.jsonl`
  - `coa_scraper/dist/coa_items.jsonl`
  - `coa_scraper/reports/coa_mechanics_enrichment_summary.json`
  - `coa_scraper/reports/coa_item_enrichment_summary.json`
- Update artifact manifest.

Tests first:

```bash
npm --prefix coa_scraper run unit-test
python -m pytest tests/test_mechanics_schema.py -q
```

Implementation notes:

- Network-backed enrichment should remain an explicit pipeline step.
- Package tests must not require network.
- Cache raw payloads for audit and reproducibility.

## Checkpoint 3: Tooltip Mechanics Inference

Goal: convert canonical tooltips into usable low/medium-confidence mechanics records.

Tasks:

- Add `coa_meta/mechanics_inference.py`.
- Parse common tooltip patterns:
  - direct damage/healing
  - damage/healing over time
  - duration and tick interval
  - cooldown and charges
  - resource cost/generation
  - target count and radius
  - aura stacks
  - weapon damage scaling text
  - chance/proc/PPM/internal cooldown language when present
- Emit confidence per field.
- Add override support for spell-specific fixes.

Tests first:

```bash
python -m pytest tests/test_mechanics_inference.py -q
```

Implementation notes:

- Use structured regexes with named captures and clear provenance.
- Avoid one giant parser function. Each pattern family should be independently tested.
- Keep raw tooltip text attached to inferred records.

## Checkpoint 4: Stats, Gear, and Item Scoring

Goal: create enough stat and gear infrastructure for recommendations and later simulation.

Tasks:

- Add `coa_meta/stats.py` for primary stats, secondary ratings, AP/RAP/SP, crit, haste, hit, resource-relevant stats, and role weights.
- Add `coa_meta/gear.py` for item, slot, weapon profile, armor profile, and gear profile models.
- Add gear aggregation from `coa-item-v1`.
- Add role-aware weapon/armor recommendation helpers.
- Add report placeholders when item data is missing.

Tests first:

```bash
python -m pytest tests/test_stats.py tests/test_gear.py -q
```

Implementation notes:

- Do not invent exact WotLK/Ascension formulas without source or calibration.
- Keep formulas versioned and confidence-labeled.
- Let role profiles influence stat recommendations but keep final outputs traceable.

## Checkpoint 5: Combat Engine Skeleton

Goal: run a deterministic event loop for a minimal actor/action profile.

Tasks:

- Add `coa_meta/combat/state.py`.
- Add `coa_meta/combat/events.py`.
- Add `coa_meta/combat/engine.py`.
- Add `coa_meta/combat/rng.py`.
- Model:
  - simulation clock
  - actor resources
  - cooldowns and GCD
  - target health
  - auras
  - scheduled events
  - direct damage/heal events
  - periodic ticks
- Emit an event trace and summary metrics.

Tests first:

```bash
python -m pytest tests/test_combat_engine.py -q
```

Implementation notes:

- Start deterministic. Add Monte Carlo batch execution after a single run is reliable.
- Use seeded RNG even for deterministic fixtures.
- Keep engine inputs as DTOs, not repository globals.

## Checkpoint 6: APL Interpreter

Goal: execute generated APL JSON against combat state.

Tasks:

- Add `coa_meta/apl_interpreter.py`.
- Convert generated APL steps into executable conditions:
  - cooldown ready
  - buff/debuff up/down/remains
  - resource thresholds
  - target count
  - execute window
  - role utility/defensive thresholds
- Add unsupported-condition warnings.
- Add a SimC-like text import/export compatibility layer only after JSON execution works.

Tests first:

```bash
python -m pytest tests/test_apl_interpreter.py tests/test_apl_generation.py -q
```

Implementation notes:

- APL interpretation should return "no action" explicitly when nothing is usable.
- Avoid embedding spell-specific behavior in the interpreter.
- Conditions should be data-driven and inspectable.

## Checkpoint 7: Simulation Runner and Report Integration

Goal: let the report runner optionally simulate top builds.

Tasks:

- Add `coa_meta/simulation.py`.
- Define `SimulationConfig` and `SimulationResult`.
- Run simulation for selected top builds only by default.
- Add CLI flags:
  - `--simulate`
  - `--simulation-duration`
  - `--simulation-iterations`
  - `--simulation-seed`
  - `--gear-profile`
- Add simulation result blocks to JSON and HTML.
- Keep theory scoring as the default when `--simulate` is absent.

Tests first:

```bash
python -m pytest tests/test_simulation_runner.py tests/test_meta_report_runner.py -q
```

Implementation notes:

- Use low iteration defaults for local usability.
- Report simulation warnings separately from theory warnings.
- Never relabel simulated metrics as observed.

## Checkpoint 8: Rotation, Stat, Gear, and Summary Report UX

Goal: make reports useful without manually reading JSON.

Tasks:

- Add rotation summary renderer:
  - opener
  - maintenance
  - cooldowns
  - builder/spender
  - defensive/support
- Add stat priority renderer:
  - theory-mode placeholder or weighted estimate
  - simulation-mode perturbation result
- Add weapon/armor recommendation renderer.
- Add class/spec summary fields:
  - inferred role
  - major mechanics
  - strengths
  - constraints/warnings
  - data confidence
- Upgrade static HTML:
  - GitHub Pages-compatible relative links and assets
  - per-spec guide pages inspired by retail WoW guide structure without copying any site design
  - role filters
  - class/spec filters
  - class/spec navigation menus
  - icons
  - build cards
  - expandable rotation/stat/gear panels

Tests first:

```bash
python -m pytest tests/test_report_writers.py tests/test_meta_report_runner.py -q
```

Implementation notes:

- Static HTML should remain a file output from the CLI.
- Use captured icons when available, but do not require assets.
- Preserve canonical JSON as the source of truth.

## Checkpoint 9: Validation and Calibration Hooks

Goal: prepare for Phase 2/3 calibration without blocking M1.9.

Tasks:

- Add comparison helpers between simulated spell breakdowns and log-derived spell summaries.
- Add placeholder calibration records for:
  - coefficient correction
  - proc rate correction
  - tick interval correction
  - uptime correction
- Add confidence calculation stubs based on source quality and sample size.

Tests first:

```bash
python -m pytest tests/test_calibration_hooks.py -q
```

Implementation notes:

- Calibration should be additive. Theory and simulation must still run with no logs.
- Keep empirical data source labels explicit.

## Full Verification

Run before marking M1.9 complete:

```bash
python -m pytest -q
npm --prefix coa_scraper run unit-test
python -m coa_meta meta --entries coa_scraper/dist/coa_entries.jsonl --classes coa_scraper/dist/coa_classes.json --out /tmp/coa-meta-full-check --format json --format md --format html
python -m coa_meta meta --entries coa_scraper/dist/coa_entries.jsonl --classes coa_scraper/dist/coa_classes.json --out /tmp/coa-meta-sim-check --format json --simulate --simulation-duration 60 --simulation-iterations 1
```

If the network pipeline changes:

```bash
npm run pipeline:m1.8
```

The root command should delegate to `coa_scraper`.

## Commit Strategy

Commit after each checkpoint:

- `fix: harden meta report build search`
- `feat: add mechanics schema`
- `feat: enrich mechanics from ascension db`
- `feat: infer mechanics from tooltips`
- `feat: model gear and stat profiles`
- `feat: add combat engine skeleton`
- `feat: execute apls in combat simulation`
- `feat: integrate simulation into meta reports`
- `feat: enhance static meta report ux`
- `feat: add calibration hooks`
