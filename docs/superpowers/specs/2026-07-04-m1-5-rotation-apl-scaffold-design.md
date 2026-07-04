# M1.5 Rotation and APL Scaffold Design

## Scope

This spec covers Phase 1 Milestone 1.5 from [ROADMAP.md](../../ROADMAP.md): Rotation and APL Scaffold Generator.

M1.5 adds a structured action-priority-list subsystem that generates editable rotation scaffolds from legal build states and normalized builder data. It does not execute rotations, simulate combat, ingest SavedVariables, or claim observed DPS.

## Current Context

M1.1 and M1.2 established reproducible normalized builder artifacts. M1.3 added legal build state objects and validation. M1.4 added data-driven theory scoring profiles.

Current durable package modules:

- `coa_meta/domain.py`: `TalentNode`, `BuildState`, validation DTOs.
- `coa_meta/repository.py`: versioned normalized node loading.
- `coa_meta/builds.py`: legal build validation and state creation.
- `coa_meta/search.py`: legal build search.
- `coa_meta/profiles.py`: scoring profile loading.
- `coa_meta/scoring.py`: projected theory score output.

The prototype monolith `coa_optimizer_extensible.py` already contains hand-written rotation scaffolding, including a generic strategy and a Stalker-specific branch. That code is useful as a migration reference, but M1.5 should not preserve production class-specific Python branches. The new APL path should treat every class through the same algorithm and use profile data to inject class/spec facts.

The current test baseline passes with:

```bash
python -m pytest -q
```

The bare `pytest` executable is not the preferred command in this workspace because it did not include the repository root on the import path during collection.

## Goals

- Create a canonical structured APL output schema.
- Add a JSON APL profile schema with a validation DSL.
- Generate priority lists from legal `BuildState` objects, selected `TalentNode` records, encounter type, and APL profile data.
- Generate independent single-target and AoE scaffolds.
- Export SimC-like text from canonical structured APL data.
- Keep APL generation separate from M1.4 scoring and future simulation.
- Wire `coa_optimizer_extensible.py` rotation output through the new module for compatibility.
- Use the old Stalker APL only as a semantic regression reference.

## Non-Goals

- No event-driven simulator or APL interpreter.
- No raw DPS, simulated DPS, or empirical DPS output.
- No SavedVariables, combat log, gear, stat snapshot, uptime, or proc-rate dependency.
- No production hard-coded Stalker/Venomancer branch.
- No web UI.
- No full M1.6 meta report runner.
- No complete removal of `coa_optimizer_extensible.py`.

## Design Alternatives

### Option A: Tag-Only Generator

Generate APLs only from normalized node tags and tooltip text. This is uniform and fast, but it gives weak control over resource aliases, thresholds, target-count policy, known condition templates, and future compatibility.

### Option B: JSON APL Profiles With Typed Loaders

Use JSON files for class/spec/role APL facts and Python loaders for validation. This matches the M1.4 scoring-profile approach and keeps tuning data out of production logic.

### Option C: Full APL Profile System With Validation DSL

Create a profile schema that includes resource metadata, thresholds, condition templates, branch definitions, and rule matchers. The DSL is validation-oriented and generation-oriented, not simulation-oriented. It reserves explicit future extension points but only requires Phase 1 data.

This is the selected approach. It gives the project a durable APL contract without requiring unavailable SavedVariables or empirical data.

## Architecture

Recommended module layout:

```text
coa_meta/
  apl.py
  apl_profiles.py
  data/
    apl_profiles/
      generic_dps.json
      generic_tank.json
      generic_healer_support.json
      venomancer_stalker.json
docs/
  data/
    apl-profile-schema.md
    apl-schema.md
tests/
  test_apl_profiles.py
  test_apl_generation.py
  test_apl_exports.py
  test_apl_stalker_regression.py
```

`coa_meta/apl_profiles.py` owns loading and validating `coa-apl-profile-v1` profile JSON. It should expose typed dataclasses and fail loudly for malformed profiles.

`coa_meta/apl.py` owns generated APL dataclasses, generation, canonical JSON serialization, SimC-like text serialization, slugification, confidence/warning propagation, and semantic deduplication.

`coa_optimizer_extensible.py` should delegate its existing rotation command and JSON rotation output to `coa_meta.apl`. Compatibility wiring should preserve the existing command surface while moving the source of behavior into the package.

## APL Profile Schema

APL profiles use schema version `coa-apl-profile-v1`.

Required top-level fields:

- `schema_version`
- `profile_id`
- `class_name`
- `spec_key`
- `role`
- `supported_encounters`
- `resources`
- `thresholds`
- `condition_templates`
- `rules`
- `branches`
- `assumptions`

Optional top-level fields:

- `future_inputs`
- `confidence`

Example profile shape:

```json
{
  "schema_version": "coa-apl-profile-v1",
  "profile_id": "generic_dps",
  "class_name": "*",
  "spec_key": "*",
  "role": "dps",
  "supported_encounters": ["single_target", "aoe_5"],
  "resources": [{"name": "Energy", "aliases": ["energy"], "default_pool": null}],
  "thresholds": {"spender": 80, "execute_health_pct": 35, "aoe_min_enemies": 3},
  "condition_templates": {
    "maintain_dot": "dot.{action_key}.remains<gcd",
    "cooldown_ready": "cooldown.{action_key}.ready",
    "spender_ready": "{primary_resource}>={spender_threshold}",
    "builder_ready": "{primary_resource}.deficit>0",
    "execute": "target.health.pct<{execute_health_pct}",
    "aoe": "active_enemies>={aoe_min_enemies}"
  },
  "rules": [
    {
      "id": "maintain_dots",
      "category": "maintenance",
      "match": {"tags_any": ["dot"], "active_only": true},
      "condition_template": "maintain_dot",
      "priority": 20,
      "confidence": "medium",
      "note": "maintain DoT/debuff uptime"
    }
  ],
  "branches": [
    {
      "encounter": "single_target",
      "include_categories": ["maintenance", "cooldown", "spender", "builder", "filler"]
    },
    {
      "encounter": "aoe_5",
      "include_categories": ["maintenance", "cooldown", "aoe", "spender", "builder", "filler"]
    }
  ],
  "assumptions": ["Generated from normalized builder data and static profile rules."],
  "future_inputs": ["combat_log_metrics", "saved_variables_snapshot", "sim_state"]
}
```

`future_inputs` is metadata only in M1.5. A profile must not require future inputs to generate a Phase 1 APL. If a profile marks combat logs, SavedVariables, gear snapshots, or simulator state as required, the loader should reject it.

## Validation DSL

The DSL should match selected nodes using normalized builder fields only.

Supported M1.5 match operators:

- `tags_any`
- `tags_all`
- `schools_any`
- `resources_any`
- `name_contains_any`
- `description_matches_any`
- `entry_type_in`
- `essence_kind_in`
- `active_only`
- `passive_only`
- `selected_rank_at_least`

Supported output categories:

- `precombat`
- `maintenance`
- `cooldown`
- `builder`
- `spender`
- `execute`
- `aoe`
- `filler`
- `utility`

Supported confidence labels:

- `high`
- `medium`
- `low`

Validation failures:

- invalid schema version
- missing required top-level field
- unsupported encounter
- unknown branch category
- unsupported match operator
- invalid confidence label
- rule references unknown condition template
- rule priority is not numeric
- rule marks a future input as required

Validation warnings:

- generic profile fallback used
- no action matched a branch category
- condition inferred from tags or tooltip text
- selected build has active nodes but no filler action

## Generated APL Schema

Generated APLs use schema version `coa-apl-v1`.

Required fields:

- `schema_version`
- `source`
- `profile_id`
- `class_name`
- `spec_key`
- `role`
- `encounter`
- `actions`
- `assumptions`
- `warnings`
- `provenance`

Example output:

```json
{
  "schema_version": "coa-apl-v1",
  "source": "theorycraft",
  "profile_id": "generic_dps",
  "class_name": "Venomancer",
  "spec_key": "stalker",
  "role": "dps",
  "encounter": "single_target",
  "actions": [
    {
      "action_key": "withering_venom",
      "action_name": "Withering Venom",
      "node_id": 123,
      "spell_id": 456,
      "category": "maintenance",
      "condition": "dot.withering_venom.remains<gcd",
      "priority": 20,
      "confidence": "medium",
      "notes": ["maintain DoT/debuff uptime"],
      "evidence": ["tag:dot", "profile_rule:maintain_dots"]
    }
  ],
  "assumptions": ["Generated from normalized builder data and static profile rules."],
  "warnings": ["condition inferred from normalized tooltip tags"],
  "provenance": {
    "build_state_schema": "M1.3 BuildState",
    "profile_schema": "coa-apl-profile-v1",
    "normalized_schema": "coa-normalized-v1"
  }
}
```

`source` should be `theorycraft` in M1.5.

## Generation Flow

1. Receive a valid `BuildState`, `TalentRepository`, encounter, and `APLProfile`.
2. Resolve selected nodes from `BuildState.selected_ids`.
3. Filter out passive nodes for action rules unless a rule explicitly matches `passive_only`.
4. Validate profile compatibility with encounter, role, and class/spec wildcard rules.
5. Apply profile rules to selected nodes.
6. Render condition templates with `action_key`, `primary_resource`, and threshold fields.
7. Filter rule matches by the encounter branch categories.
8. Sort by `priority`, then category order, then action name for deterministic output.
9. Deduplicate actions by `(action_key, condition, category)`.
10. Emit canonical `APLDocument`.
11. Export SimC-like text from `APLDocument.actions`.

Category order should default to:

```text
precombat -> maintenance -> cooldown -> execute -> aoe -> spender -> builder -> filler -> utility
```

Branch profile data may omit a category from an encounter. For example, the single-target branch should not include `aoe` unless a profile explicitly adds it.

## Profile Selection

APL profile selection should mirror scoring profile selection:

1. Try class/spec profile id, such as `venomancer_stalker`.
2. Fall back to generic role profile, such as `generic_dps`.
3. Return warnings when fallback occurs.

The selected profile must still use the same engine and rule matcher. Class/spec profiles are data specializations, not separate Python strategies.

## SimC-Like Text Export

SimC-like text is an export format, not the canonical data model.

Export format:

```text
actions+=/withering_venom,if=dot.withering_venom.remains<gcd  # maintain DoT/debuff uptime
```

Rules:

- `action_key` is lower-case snake_case.
- `,if=` is omitted when condition is empty.
- Notes are appended as comments.
- Export order follows canonical action order.

## Compatibility Wiring

`coa_optimizer_extensible.py` should keep existing CLI affordances:

- `rotation` command still prints SimC-like lines.
- `optimize --json` can still include `rotation_apl` text lines.
- `optimize --show-rotation` still prints rotation scaffolds.

The implementation should build the required `BuildState` or selected-node compatibility object, call the new APL generator, and serialize through the new exporter. The monolith should no longer own the production APL rules.

## Error Handling

Profile loading errors should raise `APLProfileLoadError`.

Generation errors should raise `APLGenerationError` only for programmer or contract failures, such as unsupported encounters or invalid profile references. Missing optional action categories should produce warnings inside the generated APL, not exceptions.

The generator should produce a valid but low-confidence APL when a legal build has sparse tags and only generic fallback can be used.

## Testing

Unit tests should cover:

- valid profile loading
- invalid schema version
- unsupported match operator
- unknown condition template
- generic fallback warnings
- selected build action generation
- branch-specific single-target and AoE output
- SimC-like text export
- canonical JSON serialization

The Stalker regression test should be semantic tolerance, not exact golden output. It should assert:

- selected Stalker nodes produce maintenance, builder, spender, execute, and AoE categories when the selected build contains matching nodes
- maintenance actions sort before spender actions
- execute actions include target-health conditions
- AoE actions appear in AoE output and are excluded from single-target output unless explicitly configured
- generated evidence references profile rules and normalized tags or tooltip text

Full verification command:

```bash
python -m pytest -q
```

## Documentation Updates

M1.5 should update:

- `docs/MODULES.md`: mark `coa_meta/apl.py`, `coa_meta/apl_profiles.py`, and `coa_meta/data/apl_profiles/*.json` as M1.5 implementation files.
- `docs/DECISIONS.md`: record that APL generation is profile-driven and structured JSON is canonical.
- `docs/data/apl-profile-schema.md`: document `coa-apl-profile-v1`.
- `docs/data/apl-schema.md`: document `coa-apl-v1`.

## Exit Criteria

M1.5 is complete when:

- legal build states can generate structured APL JSON
- single-target and AoE APLs are generated independently
- SimC-like text export is derived from structured APL data
- profile validation rejects malformed rules and unsupported DSL references
- every production class/spec path uses the same APL generation engine
- old Stalker behavior is covered by semantic regression tests only
- `coa_optimizer_extensible.py` delegates rotation output to the new package module
- `python -m pytest -q` passes

