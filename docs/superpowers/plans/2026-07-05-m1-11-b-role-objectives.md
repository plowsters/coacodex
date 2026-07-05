# M1.11B Role Map and Role-Specific Objective Indexes Implementation Plan

> **For agentic workers:** Use TDD. Commit after each checkpoint. Do not change tree rendering or scraper behavior in this milestone.

**Goal:** Replace heuristic role display and DPS-only guide scoring with a source-backed role map, primary/secondary role support, and role-specific objective indexes.

**Architecture:** Add a role map loader and objective layer while preserving the existing broad `engine_role` bridge. Keep `projected_dps_index` for compatibility and add guide-facing `primary_index` fields.

---

## Checkpoint 1: Role Map Schema and Loader

Files:

- Create `docs/data/role-map-schema.md`
- Create `coa_meta/data/spec_roles.json`
- Modify `coa_meta/roles.py`
- Modify `pyproject.toml`
- Create or extend `tests/test_roles.py`

### Step 1: Add failing tests

Add tests that assert:

- Role map loads 70 reportable specs.
- Every row has `class_name`, `source_spec_name`, `display_spec_name`, `primary_role`, `secondary_roles`, `engine_role`, `source`, `confidence`, and `evidence`.
- Valid roles are exactly `melee_dps`, `caster_dps`, `ranged_dps`, `tank`, `healer`, `support`.
- Hybrids serialize primary plus secondary roles:
  - `Inspiration Guardian`: primary `melee_dps`, secondary `support`
  - `Farstrider Ranger`: primary `ranged_dps`, secondary `support`
  - `Wind Stormbringer`: primary `caster_dps`, secondary `support`
  - `Accursed Bloodmage`: primary `melee_dps`, secondary `caster_dps`
- Legacy source/display pairs serialize correctly:
  - Runemaster `Arcane` -> `Glyphic`
  - Runemaster `Runic` -> `Engravement`
  - Venomancer `Venom` -> `Rot`
  - Primalist `Life` -> `Grovekeeper`
  - Primalist `Primal` -> `Wildwalker`
  - Witch Hunter `Houndmaster` -> `Darkness`

Run:

```bash
PYTHONPATH=. pytest tests/test_roles.py tests/test_display_names.py
```

Expected: RED.

### Step 2: Add schema docs and data file

Write `docs/data/role-map-schema.md` with `coa-spec-role-map-v1`.

Create `coa_meta/data/spec_roles.json` from the M1.11B design role table.

Use:

- `source: "authoritative_video"` for launch-video rows.
- `source_urls: []` until the exact video URL is recorded.
- `confidence: "high"` for unambiguous rows.
- `confidence: "medium"` for Templar `Crusader` until the source URL/video line is verified.

### Step 3: Implement loader

In `coa_meta/roles.py`, add:

```text
SpecRoleRecord
load_spec_role_records(path=SPEC_ROLE_MAP_PATH)
resolve_spec_role_record(class_name, spec_name, spec_key)
roles_for_filter(record)
```

Update package data in `pyproject.toml`.

Resolution order:

1. `spec_roles.json`
2. `role_overrides.json`
3. inference

### Step 4: Verify and commit

Run:

```bash
PYTHONPATH=. pytest tests/test_roles.py tests/test_display_names.py
```

Commit:

```bash
git add coa_meta pyproject.toml tests docs/data/role-map-schema.md
git commit -m "Add official CoA spec role map"
```

---

## Checkpoint 2: Primary and Secondary Role Reporting

Files:

- Modify `coa_meta/roles.py`
- Modify `coa_meta/reporting.py`
- Modify `coa_meta/guide_models.py`
- Modify `coa_meta/guide_builder.py`
- Extend `tests/test_meta_report_runner.py`
- Extend `tests/test_guide_builder.py`

### Step 1: Add failing report tests

Assert:

- `SpecResult.to_dict()` includes `primary_role`, `secondary_roles`, and `roles`.
- `role` remains the primary role for compatibility.
- `role_provenance` includes the role map source and secondary roles.
- Hybrid specs preserve primary sorting role but include secondary filter role.

### Step 2: Extend dataclasses and serialization

Role model:

```text
RoleResolution
  role: primary role
  secondary_roles: tuple[GuideRole, ...]
  roles: tuple[GuideRole, ...]
  engine_role
  source
  confidence
  evidence
  scores
```

Spec result:

```text
role
primary_role
secondary_roles
roles
engine_role
role_provenance
```

### Step 3: Guide model bridge

Guide specs should expose:

```text
role
primary_role
secondary_roles
roles
```

Existing templates can keep `spec.role` as primary role.

### Step 4: Verify and commit

Run:

```bash
PYTHONPATH=. pytest tests/test_roles.py tests/test_meta_report_runner.py tests/test_guide_builder.py
```

Commit:

```bash
git add coa_meta tests
git commit -m "Expose primary and secondary guide roles"
```

---

## Checkpoint 3: Role-Specific Objective Index Payload

Files:

- Create `coa_meta/objectives.py`
- Modify `coa_meta/reporting.py`
- Modify `coa_meta/build_diversity.py` only if needed for payload labels
- Extend `tests/test_scoring_engine.py`
- Extend `tests/test_meta_report_runner.py`

### Step 1: Add failing objective tests

Assert:

- Damage roles produce `Projected Damage Index`.
- Healer produces `Projected Healing Index`.
- Tank produces `Projected Survival/Threat Index`.
- Support produces `Projected Support Index`.
- `projected_dps_index` remains present.
- `primary_index` is present on every build.
- `alternate_objective_scores` exists for hybrids.

### Step 2: Implement objective scoring wrapper

`TheoryScorer` can still produce the base numeric score. `coa_meta/objectives.py` should translate score components into role-specific objective payloads:

```text
RoleObjectiveResult
  objective_id
  role
  primary_index
  primary_index_label
  objective_breakdown
  alternate_objective_scores
  warnings
```

Initial implementation can reuse the current score value while changing labels and component grouping. It must not claim empirical role performance.

### Step 3: Wire into build reports

Add to `BuildReport`:

```text
primary_index
primary_index_label
objective_id
objective_breakdown
alternate_objective_scores
```

Keep old ordering by current numeric score until a later role-specific search rewrite. The guide must display the new label.

### Step 4: Verify and commit

Run:

```bash
PYTHONPATH=. pytest tests/test_scoring_engine.py tests/test_meta_report_runner.py
```

Commit:

```bash
git add coa_meta tests
git commit -m "Add role-specific objective index payloads"
```

---

## Checkpoint 4: Guide Rendering for Hybrid Roles and Objective Labels

Files:

- Modify `coa_meta/guide_builder.py`
- Modify `coa_meta/guide_rendering.py`
- Modify `coa_meta/guide_models.py`
- Extend `tests/test_guide_rendering.py`
- Extend `tests/test_guide_builder.py`

### Step 1: Add failing rendering tests

Assert:

- Hybrid specs appear when filtering by secondary role.
- Cards show primary and secondary role chips.
- Build cards display `Projected Healing Index`, `Projected Survival/Threat Index`, or `Projected Support Index` where appropriate.
- Tooltip text for role-specific indexes does not say "DPS" for tanks/healers/support.

### Step 2: Update index grouping

Change role section membership from `spec.role == role` to `role in spec.roles`.

Cards may appear in more than one section. Keep canonical guide URLs stable.

### Step 3: Update build cards and tooltips

Use:

```text
build.primary_index_label
build.primary_index
```

Fallback to `Projected Damage Index` and `projected_dps_index` for older reports.

### Step 4: Verify and commit

Run:

```bash
PYTHONPATH=. pytest tests/test_guide_builder.py tests/test_guide_rendering.py
```

Commit:

```bash
git add coa_meta tests
git commit -m "Render hybrid roles and objective labels"
```

---

## Checkpoint 5: Schema Docs and Smoke

Files:

- Modify `docs/data/meta-report-schema.md`
- Modify `docs/ROADMAP.md` if status changes
- Modify `docs/README.md` if command output notes change

### Step 1: Document schema changes

Update meta report schema:

- `primary_role`
- `secondary_roles`
- `roles`
- `primary_index`
- `primary_index_label`
- `objective_id`
- `objective_breakdown`
- `alternate_objective_scores`

### Step 2: Full verification

Run:

```bash
PYTHONPATH=. pytest
PYTHONPATH=. python -m coa_meta meta \
  --entries tests/fixtures/meta_report_fixture.jsonl \
  --classes tests/fixtures/meta_classes.json \
  --out /tmp/coa-m1-11-b-smoke \
  --format json --format md --format html
```

If current real artifacts exist:

```bash
PYTHONPATH=. python -m coa_meta meta \
  --entries coa_scraper/dist/coa_entries.jsonl \
  --classes coa_scraper/dist/coa_classes.json \
  --db-tooltips coa_scraper/dist/coa_db_spell_tooltips.jsonl \
  --out reports/meta \
  --format json --format md --format html
```

### Step 3: Final commit

Commit:

```bash
git add docs
git commit -m "Document M1.11B role objective schema"
```

## Completion Criteria

- Official role map is the preferred source for role resolution.
- Hybrid specs serialize primary and secondary roles.
- Guide filters include secondary roles.
- Non-DPS roles display role-specific theorycraft indexes.
- Existing consumers that read `projected_dps_index` still work.
