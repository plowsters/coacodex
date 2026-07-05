# M1.9 Combat Engine and Theorycraft Completion Design

## Scope

M1.9 turns the Phase 1 theorycraft stack into the foundation for a real combat simulator and richer reports. It does not replace the M1.8 builder/source pipeline. It adds the missing mechanics layer that can consume builder nodes, AscensionDB spell/effect/item data, generated APLs, and eventually log calibration.

This spec also captures deferred Phase 1 report work that should land before or alongside the simulator:

- role-aware report generation for DPS, tank, healer, and support specs
- readable rotations in the main report, not only JSON APL payloads
- stat priorities
- ideal weapon and armor type recommendations
- class/spec summaries
- image/icon-backed static HTML, GitHub Pages publishing, and later frontend UX

## Research Notes

Primary references:

- AscensionDB is the preferred canonical source for spell, effect, item, weapon, armor, and tooltip data when the builder does not expose a field. The public site exposes spells, items, tools, and the official builder entry point: <https://db.ascension.gg/>.
- SimulationCraft's ActionLists documentation models rotations as priority lists scanned until an available action is found, with sublists and conditions. M1.9 should keep this APL shape rather than embedding rotation logic in Python branches: <https://github.com/simulationcraft/simc/wiki/ActionLists>.
- The existing `docs/ARCHITECTURE.md` already separates builder scraping, build legality, scoring, APL generation, reports, logs, calibration, and the future simulator. M1.9 should keep that boundary.

Source priority for mechanics:

1. Builder payload: class/spec ownership, node identity, AE/TE costs, prerequisites, gates, level availability, and selected build state.
2. AscensionDB: spell registrations, effect text, buff/debuff names, item stats, weapon/armor metadata, icons, cooldown text, and canonical tooltip descriptions.
3. Addon/combat logs: observed timings, proc rates, pet attribution, resource behavior, aura uptime, and empirical coefficients.
4. Local override data: hand-curated mechanics only when source data is missing or ambiguous, with provenance and review notes.

## Goals

- Add a versioned mechanics corpus that can describe abilities, passives, buffs, debuffs, pets, cooldowns, resources, damage/healing events, item stats, and role outputs.
- Add a deterministic event-driven combat engine with seeded RNG and repeatable outputs.
- Interpret generated APL JSON against combat state instead of treating rotations as static report text.
- Produce role-appropriate simulated metrics:
  - DPS specs: damage per second, damage breakdown, cooldown contribution, resource waste, uptime.
  - Tank specs: damage taken per second, mitigation uptime, effective health, self-healing, threat/damage contribution.
  - Healer/support specs: HPS/effective healing proxy, overheal proxy when possible, buff uptime, group utility uptime, damage contribution.
- Generate stat priorities by perturbing stat profiles and rerunning scoring/simulation.
- Recommend weapons and armor by slot/type from item data and the resolved role.
- Upgrade HTML reports from basic tables to a GitHub Pages-friendly static guide site with filters, icons, role badges, build cards, rotation panels, stat priority panels, and class/spec summaries.

## Non-Goals

- No claim that simulated DPS is observed DPS.
- No full empirical calibration until log/addon ingestion has stable sample data.
- No attempt to perfectly parse every tooltip on first pass.
- No browser-dependent report generation.
- No direct copy of SimulationCraft or other GPL/AGPL engine code.

## Architecture

Recommended package layout:

```text
coa_meta/
  mechanics.py             # versioned mechanics DTOs and validation
  mechanics_repository.py  # spell/effect/item lookup APIs
  mechanics_inference.py   # tooltip and DB payload inference rules
  stats.py                 # primary/secondary/combat rating model
  gear.py                  # item, slot, weapon, armor, and gear profile model
  combat/
    state.py               # actor, target, aura, resource, cooldown state
    events.py              # event queue and event records
    engine.py              # deterministic simulation loop
    formulas.py            # damage/healing/mitigation/resource formulas
    rng.py                 # seeded RNG helpers
  apl_interpreter.py       # execute APL JSON against combat state
  simulation.py            # batch runner and result schema
  report_frontend.py       # richer static HTML model/assets
```

The current modules remain:

- `repository.py`, `builds.py`, and `search.py` own legality.
- `profiles.py` and `scoring.py` own pre-sim theory weights.
- `apl.py` owns APL generation/export.
- `reporting.py` owns report orchestration.

M1.9 should add the simulator as an optional path under the report runner, not as a prerequisite for all reports. Theorycraft reports must still work when mechanics data is incomplete.

## Data Contracts

### `coa-mechanics-v1`

One record per spell or passive effect:

- `spell_id`, `name`, `source_node_ids`, `source_urls`
- `kind`: ability, passive, buff, debuff, pet_action, item_effect, proc
- `school`, `power_type`, `range`, `cast_time_ms`, `gcd_ms`
- `cooldown_ms`, `charges`, `duration_ms`, `tick_interval_ms`
- `costs`, `generates`, `spends`, `max_targets`
- `effects[]`: damage, heal, absorb, aura_apply, aura_refresh, resource_delta, summon, cooldown_modify, stat_modify, trigger_spell
- `proc`: chance, ppm, internal_cooldown_ms, trigger_conditions
- `scaling`: flat_amount, coefficient, weapon_damage_pct, ap_pct, sp_pct, stat_modifiers
- `provenance`: builder, AscensionDB, tooltip_parser, override, log_calibration
- `confidence`

### `coa-item-v1`

One record per item:

- `item_id`, `name`, `icon`, `slot`, `item_class`, `subclass`, `weapon_type`, `armor_type`
- `stats`, `ratings`, `speed`, `min_damage`, `max_damage`, `spell_power`, `attack_power`
- `equip_effects`, `use_effects`, `proc_effects`
- `required_level`, `source_urls`, `provenance`, `confidence`

### `coa-gear-profile-v1`

A selected equipment set:

- actor identity fields
- slot to item mapping
- aggregated stats
- weapon profile
- role and encounter assumptions
- provenance

### `coa-simulation-result-v1`

A simulation output:

- build identity, role, encounter, gear profile, APL profile
- iterations, seed, duration settings
- DPS/HPS/tank/support metrics by role
- spell breakdown, aura uptime, resource timeline summary, cooldown usage
- warnings and confidence

## Combat Engine Model

The engine should be event-driven:

1. Initialize actor, target set, resources, gear stats, selected build, passive auras, and APL.
2. Schedule encounter start, auto attacks, periodic ticks, cooldown completions, aura expirations, and decision points.
3. At each decision point, evaluate the APL from highest priority to lowest priority and cast the first available action.
4. Resolve cast/GCD/cooldown/resource changes, immediate effects, scheduled future events, and proc triggers.
5. Stop at duration or encounter end and emit summarized metrics plus optional trace rows.

Minimum M1.9 mechanics:

- GCD, cast time, cooldowns, charges
- primary resources and overcap tracking
- direct damage/healing
- DoT/HoT periodic ticks
- buffs/debuffs with stacks and refresh rules
- weapon swings and weapon damage scaling
- pets/guardians as child actors with owner attribution
- seeded crit/hit/proc rolls
- target count and target cap handling

Later mechanics:

- movement windows
- interrupts/lockouts
- threat and enemy swing tables
- absorbs and shields
- snapshotting rules when verified by logs
- encounter-specific damage patterns for tank/healer valuation

## Report Completion Work

### Role-Aware Main Report

The default report role should be `auto`. Each reportable spec resolves to `dps`, `tank`, or `healer_support` before scoring and APL generation. Explicit `--role` still overrides auto detection. The resolved role must be serialized into JSON, Markdown, HTML, and build provenance.

### Rotation Presentation

Every top build already receives generated APL JSON. Reports should also include:

- compact opener list
- steady-state priority list
- cooldown section
- maintenance section for DoTs, HoTs, buffs, and debuffs
- role-specific utility or defensive section
- confidence notes for inferred conditions

### Stat Priorities

Before simulation, stat priorities can use weighted feature profiles. After M1.9 simulation exists, priorities should use perturbation:

1. Pick baseline gear/stat profile.
2. Add a fixed budget of one stat.
3. Rerun deterministic or Monte Carlo simulation.
4. Report normalized delta by role metric.

### Weapon and Armor Recommendations

Recommendations should come from item/gear data, not talent text alone. Until item data is complete, report only role-derived preferences with warnings. Once `coa-item-v1` exists, rank weapon and armor types by role score, supported spell/resource scaling, weapon damage scaling, armor type, and item stat budget.

### Static Guide Frontend

The first frontend step should remain a generated static site that can be published to GitHub Pages. Each spec should get a guide-like page with the practical structure players expect from retail WoW class/spec resources, while using distinct branding, layout, color, menus, and interaction patterns rather than copying Icy Veins or any other existing guide site.

Per-spec pages should include:

- overview and role identity
- recommended builds by encounter profile
- talent and ability selection cards with icons
- opener and steady-state rotation sections
- defensive/support sections for non-DPS roles
- stat priority panels
- weapon and armor recommendation panels
- strengths, weaknesses, and assumptions
- warnings and provenance visible without inspecting JSON

The index and comparison views should include:

- role/spec/class filters
- class and spec navigation menus
- build cards with icons and selected node groups
- expandable rotation/stat/gear panels
- static assets that work from relative GitHub Pages paths

Do not require a dev server for static report generation. A later web app can reuse the same JSON schema.

## Risks

- Tooltips alone will not produce trustworthy coefficients for every spell. Keep confidence explicit and support overrides.
- Tank and healer metrics need encounter damage assumptions; M1.9 should ship baseline synthetic encounters and label them.
- Gear recommendations are weak until item data is enriched from AscensionDB.
- Role inference can misclassify hybrid specs. Serialize the resolved role and allow CLI override.
- Search plus simulation can become expensive. Keep the first sim path top-build-only, then add batch controls.

## Exit Criteria

- Main report generation produces top builds for all reportable specs or emits actionable warnings.
- Every spec result records a resolved role and uses the matching generic or specific profile.
- A mechanics corpus can be generated and validated from current builder plus AscensionDB payloads.
- A deterministic simulator can execute at least one selected build/APL/gear profile and emit `coa-simulation-result-v1`.
- Reports include readable rotation summaries, role-aware summaries, stat priority placeholders or results, and weapon/armor recommendation placeholders or results with confidence.
