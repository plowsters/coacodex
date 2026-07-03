# M1.3/M1.4 Legal Build and Theory Scoring Design

## Scope

This spec covers Phase 1 Milestone 1.3 and Milestone 1.4 from [ROADMAP.md](../../ROADMAP.md):

- M1.3: Legal Build Engine
- M1.4: Theory Scoring Engine

M1.3 and M1.4 are designed together because scoring must operate only on legal, explainable build states. They should still be implemented as separate milestones with separate commits and verification gates.

## Current Context

M1.1/M1.2 made the builder artifacts reproducible and versioned:

- `coa_scraper/dist/coa_entries.jsonl` contains 3,612 `coa-normalized-v1` node records.
- `coa_scraper/dist/coa_classes.json` contains 21 normalized class records.
- `coa_scraper/dist/coa_essence_caps.json` contains builder-provided class essence caps.
- `coa_scraper/reports/coa_validation_summary.json` currently validates with zero missing class records, zero missing tab records, and zero unknown essence-kind records.

The optimizer prototype still centralizes domain loading, legality, search, scoring, and CLI behavior in `coa_optimizer_extensible.py`. M1.3/M1.4 should extract the durable parts into a package while keeping existing CLI behavior available during migration.

## Goals

M1.3 goals:

- Create a dedicated legal build engine module.
- Load `coa-normalized-v1` records through a domain repository layer.
- Validate selected builds and explain failures.
- Generate legal builds using the same rules used for direct validation.
- Model AE/TE budgets, required level, required node IDs, tab AE/TE gates, free starting/passive closure, class-tab ownership, and rank spending.
- Represent build states as serializable data.

M1.4 goals:

- Replace hard-coded Python scoring logic with data-driven scoring profiles.
- Support role and encounter templates: single-target DPS, 2-target cleave, 5-target AoE, solo, tank, healer/support.
- Score source features separately: tab investment, role tags, damage schools, resources, named synergies, inferred coefficients, cooldowns, DoTs, target count, summon/pet behavior, defensive value, and utility value.
- Emit projected DPS index, confidence, uncertainty, and score explanation data.
- Preserve a curated Stalker Venomancer profile as data, not code.

## Non-Goals

- No APL/rotation generation changes. That is M1.5.
- No raw DPS output. M1.4 emits projected index values only.
- No event-driven simulator. That is Phase 3.
- No empirical log calibration beyond reserving data structures for later corrections.
- No web UI.
- No complete removal of `coa_optimizer_extensible.py` in this milestone. It may become a compatibility wrapper later.

## Design Alternatives

### Option A: Keep Extending `coa_optimizer_extensible.py`

This is the fastest short-term path but increases coupling. Legality and scoring would remain difficult to test independently, and future simulator work would need to unwind the monolith.

### Option B: Extract a Small `coa_meta/` Package

Create focused package modules for domain loading, legal build rules, search, scoring profiles, and explanation DTOs. Keep `coa_optimizer_extensible.py` available while new tests and future CLIs target the package.

This is the recommended approach. It creates stable module boundaries without requiring full packaging/installer work before M1.7.

### Option C: Jump Directly to a Full Application Layout

Create a full `src/coa_meta`, pyproject packaging, CLI entry points, config directories, and report runners now. This would front-load M1.7 work and increase risk before legality/scoring behavior is proven.

## Architecture

Recommended module layout:

```text
coa_meta/
  __init__.py
  domain.py
  repository.py
  builds.py
  search.py
  scoring.py
  profiles.py
  explain.py
tests/
  fixtures/
  test_repository.py
  test_build_rules.py
  test_build_search.py
  test_scoring_profiles.py
  test_scoring_explanations.py
```

### Domain Module

`coa_meta/domain.py` owns serializable dataclasses and enums:

- `TalentNode`
- `ClassRecord`
- `TabRecord`
- `EssenceCaps`
- `BuildState`
- `SelectedRank`
- `BuildValidationResult`
- `ValidationIssue`
- `ScoreComponent`
- `ScoreBreakdown`
- `ScoredBuild`

Domain objects should not know how files are stored or how builds are searched.

### Repository Module

`coa_meta/repository.py` owns loading versioned artifacts:

- `TalentRepository.from_paths(entries_path, classes_path, essence_caps_path)`
- schema-version checks for `coa-normalized-v1`
- indexes by class name, class id, tab id, node id, spell id, and normalized lower-case node name
- class/tab ownership checks

The repository should fail loudly on invalid schema by default. An explicit `unsafe=True` option can be added later if needed, but M1.3 should default to safe loading.

### Legal Build Module

`coa_meta/builds.py` owns deterministic legality:

- budget checks
- required level checks
- required node checks
- tab AE/TE gate checks
- class ownership checks
- zero-cost closure checks
- rank spending checks
- serializable `BuildState` creation from node IDs or node-name inputs
- validation explanations

Legality should produce issue codes rather than only text. Example issue codes:

- `duplicate_node`
- `unknown_node`
- `wrong_class`
- `level_required`
- `ae_budget_exceeded`
- `te_budget_exceeded`
- `tab_ae_gate_unmet`
- `tab_te_gate_unmet`
- `required_node_missing`
- `rank_below_minimum`
- `rank_above_maximum`
- `zero_cost_closure_missing`

### Search Module

`coa_meta/search.py` owns legal candidate generation:

- deterministic beam search
- branch width and beam width settings
- budget usage floor
- ranked result serialization

Search must call `BuildRules.can_add()` and `BuildRules.add()` rather than duplicating legality.

### Scoring Module

`coa_meta/scoring.py` owns scoring mechanics:

- apply data-driven scoring profiles
- score node components
- score build-level synergies and anti-synergies
- normalize to projected DPS index
- produce confidence and uncertainty outputs

Scoring must not decide legality. It accepts only `BuildState` plus repository nodes.

### Profiles Module

`coa_meta/profiles.py` owns profile loading and defaults:

- built-in generic role templates
- built-in encounter templates
- JSON profile loader
- curated Stalker Venomancer data profile

Profile records should be plain dictionaries or dataclasses loaded from JSON. M1.4 should avoid YAML to keep dependencies minimal.

Suggested profile file layout:

```text
coa_meta/data/scoring_profiles/
  generic_dps.json
  generic_tank.json
  generic_healer_support.json
  venomancer_stalker.json
```

### Explain Module

`coa_meta/explain.py` converts validation and scoring objects into report-ready dictionaries. It should not contain core rules.

## Data Flow

M1.3 legality flow:

```text
normalized artifacts
  -> TalentRepository
  -> BuildRules
  -> BuildState
  -> BuildValidationResult
  -> BuildSearcher
  -> legal BuildState results
```

M1.4 scoring flow:

```text
legal BuildState results
  -> ScoringProfile
  -> TheoryScorer
  -> ScoreBreakdown
  -> ScoredBuild
  -> projected DPS index report data
```

## Rank Spending Model

The current prototype treats `max_rank` as a score hint rather than actual point spending. M1.3 should introduce explicit selected ranks.

Rules:

- A selected node has rank `1..max_rank`.
- If an input build selects an unranked node ID, default selected rank is `1`.
- Node cost is multiplied by selected rank unless builder data later proves a different per-rank cost model.
- Required IDs are satisfied when the required node is selected at rank at least 1.
- Tab AE/TE spend counts paid selected ranks in that tab.
- Zero-cost passive closure includes free nodes at rank 1.

This is an intentional model and should be documented in validation output assumptions.

## Free Starting/Passive Closure

The legal engine should derive a closure of zero-cost nodes whose prerequisites are satisfied and required level is met. This closure is included in the initial build state and appears in serialized state as `free_node_ids`.

Paid nodes should never be auto-selected.

## Builder UI Ground Truth

M1.3 includes a fixture format for official builder examples, but it does not require a large corpus.

Fixture file:

```text
tests/fixtures/builder_examples.json
```

Each example records:

- `name`
- `class_name`
- `level`
- `max_ae`
- `max_te`
- `selected`
- `expected_valid`
- `expected_issue_codes`

At least one valid and one invalid fixture should be checked in. More examples can be added after the user collects UI ground truth.

## Theory Scoring Profile Contract

A scoring profile should include:

- `schema_version`
- `profile_id`
- `class_name`
- `spec_key`
- `role`
- `encounter`
- `baseline_index`
- `weights`
- `synergies`
- `anti_synergies`
- `named_boosts`
- `regex_boosts`
- `confidence`
- `assumptions`

Scoring output should include:

- `projected_dps_index`
- `raw_score`
- `confidence`
- `uncertainty`
- `components`
- `assumptions`
- `warnings`
- `source: "theorycraft"`

## Confidence and Uncertainty

M1.4 should use transparent, deterministic confidence labels:

- `high`: source fields are explicit and profile is curated for class/spec/encounter.
- `medium`: source fields are explicit but profile is generic or partially inferred.
- `low`: heavy reliance on regex text, missing profile coverage, or many utility/tank/heal conflicts.

Uncertainty should be a numeric band such as:

```json
{
  "low": 92.5,
  "mid": 100.0,
  "high": 111.0
}
```

This is not a statistical confidence interval. It is a theorycraft uncertainty band.

## Error Handling

M1.3:

- invalid schema version: raise a repository load error
- unknown selected node: validation issue, not crash
- duplicate selected node: validation issue
- budget overflow: validation issue
- unresolved required ID outside class: warning if source data references a non-owned ID, validation issue if selected build depends on it

M1.4:

- missing profile: use generic profile and emit warning
- unknown encounter: reject with clear error
- invalid profile schema: reject with clear error
- regex compile failure: reject profile at load time

## Testing Strategy

M1.3 tests:

- repository loads current normalized artifacts
- invalid schema version fails
- zero-cost closure includes free starting/passive nodes
- required ID failure is explained
- tab AE/TE gates are explained
- AE/TE budget failures are explained
- rank above max fails
- rank cost affects budget and tab gates
- direct validation and search use the same legal rules

M1.4 tests:

- generic profiles load from JSON
- Stalker Venomancer curated profile loads from JSON
- node score components include tab, tag, school, resource, named, regex, and role components
- build synergies and anti-synergies are explained
- projected DPS index is emitted instead of raw DPS
- confidence and uncertainty are present
- missing class/spec profile falls back to generic profile with warning

## Documentation Updates

M1.3 should update:

- `docs/MODULES.md`
- `docs/data/normalized-schema.md` if build-state serialization references normalized fields
- a new `docs/data/build-state-schema.md`

M1.4 should update:

- `docs/data/scoring-profile-schema.md`
- `docs/DECISIONS.md` with the rank-spending and projected-index decisions

## Release Boundaries

M1.3 is complete when legal build validation and legal search pass tests and produce serializable explanations.

M1.4 is complete when legal build states can be scored using JSON profiles and produce projected DPS index reports with confidence and uncertainty.

Neither milestone should claim an observed meta or exact DPS.

