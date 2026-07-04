# M1.5 Rotation APL Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Phase 1 APL scaffold system that generates canonical JSON and SimC-like text from legal build states, normalized builder data, and validated JSON APL profiles.

**Architecture:** Add `coa_meta.apl_profiles` for `coa-apl-profile-v1` loading and validation, and `coa_meta.apl` for APL document generation and export. Keep all production class/spec behavior data-driven through JSON profiles, then wire the existing `coa_optimizer_extensible.py` rotation output to the new package module.

**Tech Stack:** Python 3.11+ standard library, dataclasses, JSON profile files, existing `coa_meta` package, `python -m pytest`.

---

## File Structure

- Create `coa_meta/apl_profiles.py`: loads and validates APL profile JSON into typed dataclasses.
- Create `coa_meta/apl.py`: generated APL dataclasses, matching, generation, canonical JSON serialization, and SimC-like text export.
- Create `coa_meta/data/apl_profiles/generic_dps.json`: default DPS APL generation rules.
- Create `coa_meta/data/apl_profiles/generic_tank.json`: conservative tank APL generation rules.
- Create `coa_meta/data/apl_profiles/generic_healer_support.json`: conservative healer/support APL generation rules.
- Create `coa_meta/data/apl_profiles/venomancer_stalker.json`: Stalker-specific data profile used by the generic engine.
- Create `tests/fixtures/apl_build_fixture.jsonl`: small normalized fixture with builder, spender, execute, AoE, cooldown, and passive examples.
- Create `tests/test_apl_profiles.py`: profile loading and validation tests.
- Create `tests/test_apl_generation.py`: generation and branch tests.
- Create `tests/test_apl_exports.py`: canonical JSON and SimC-like export tests.
- Create `tests/test_apl_stalker_regression.py`: semantic tolerance tests against old Stalker behavior.
- Modify `coa_optimizer_extensible.py`: delegate rotation generation to `coa_meta.apl`.
- Modify `docs/MODULES.md`: record M1.5 implementation files.
- Modify `docs/DECISIONS.md`: record profile-driven structured APL decision.
- Create `docs/data/apl-profile-schema.md`: document `coa-apl-profile-v1`.
- Create `docs/data/apl-schema.md`: document `coa-apl-v1`.

## Task 1: APL Profile Loader and Validation

**Files:**
- Create: `coa_meta/apl_profiles.py`
- Test: `tests/test_apl_profiles.py`

- [ ] **Step 1: Write failing profile loader tests**

Create `tests/test_apl_profiles.py`:

```python
from __future__ import annotations

import pytest

from coa_meta.apl_profiles import (
    APLProfileLoadError,
    load_apl_profile_by_role,
    load_builtin_apl_profile,
    validate_apl_profile_data,
)


def test_loads_builtin_generic_dps_profile():
    profile = load_builtin_apl_profile("generic_dps")

    assert profile.schema_version == "coa-apl-profile-v1"
    assert profile.profile_id == "generic_dps"
    assert profile.class_name == "*"
    assert profile.role == "dps"
    assert "single_target" in profile.supported_encounters
    assert profile.rules
    assert profile.branches


def test_rejects_invalid_schema_version():
    data = {
        "schema_version": "bad",
        "profile_id": "bad_profile",
        "class_name": "*",
        "spec_key": "*",
        "role": "dps",
        "supported_encounters": ["single_target"],
        "resources": [],
        "thresholds": {},
        "condition_templates": {},
        "rules": [],
        "branches": [],
        "assumptions": [],
    }

    with pytest.raises(APLProfileLoadError, match="invalid schema_version"):
        validate_apl_profile_data(data, source="test")


def test_rejects_unsupported_match_operator():
    data = {
        "schema_version": "coa-apl-profile-v1",
        "profile_id": "bad_profile",
        "class_name": "*",
        "spec_key": "*",
        "role": "dps",
        "supported_encounters": ["single_target"],
        "resources": [],
        "thresholds": {},
        "condition_templates": {"ready": ""},
        "rules": [
            {
                "id": "bad_rule",
                "category": "builder",
                "match": {"unsupported_operator": ["builder"]},
                "condition_template": "ready",
                "priority": 10,
                "confidence": "medium",
                "note": "bad matcher",
            }
        ],
        "branches": [{"encounter": "single_target", "include_categories": ["builder"]}],
        "assumptions": [],
    }

    with pytest.raises(APLProfileLoadError, match="unsupported match operator"):
        validate_apl_profile_data(data, source="test")


def test_rejects_unknown_condition_template():
    data = {
        "schema_version": "coa-apl-profile-v1",
        "profile_id": "bad_profile",
        "class_name": "*",
        "spec_key": "*",
        "role": "dps",
        "supported_encounters": ["single_target"],
        "resources": [],
        "thresholds": {},
        "condition_templates": {"ready": ""},
        "rules": [
            {
                "id": "bad_rule",
                "category": "builder",
                "match": {"tags_any": ["builder"]},
                "condition_template": "missing_template",
                "priority": 10,
                "confidence": "medium",
                "note": "bad template",
            }
        ],
        "branches": [{"encounter": "single_target", "include_categories": ["builder"]}],
        "assumptions": [],
    }

    with pytest.raises(APLProfileLoadError, match="unknown condition template"):
        validate_apl_profile_data(data, source="test")


def test_rejects_required_future_input():
    data = {
        "schema_version": "coa-apl-profile-v1",
        "profile_id": "bad_profile",
        "class_name": "*",
        "spec_key": "*",
        "role": "dps",
        "supported_encounters": ["single_target"],
        "resources": [],
        "thresholds": {},
        "condition_templates": {"ready": ""},
        "rules": [],
        "branches": [{"encounter": "single_target", "include_categories": ["builder"]}],
        "assumptions": [],
        "required_inputs": ["saved_variables_snapshot"],
    }

    with pytest.raises(APLProfileLoadError, match="future input"):
        validate_apl_profile_data(data, source="test")


def test_profile_by_role_falls_back_to_generic_profile():
    profile, warnings = load_apl_profile_by_role(
        class_name="Imaginary Class",
        spec_key="missing",
        role="dps",
    )

    assert profile.profile_id == "generic_dps"
    assert warnings == ["specific_apl_profile_missing"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_apl_profiles.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'coa_meta.apl_profiles'`.

- [ ] **Step 3: Implement profile loader module**

Create `coa_meta/apl_profiles.py`:

```python
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APL_PROFILE_SCHEMA_VERSION = "coa-apl-profile-v1"
PROFILE_DIR = Path(__file__).parent / "data" / "apl_profiles"

SUPPORTED_MATCH_OPERATORS = {
    "tags_any",
    "tags_all",
    "schools_any",
    "resources_any",
    "name_contains_any",
    "description_matches_any",
    "entry_type_in",
    "essence_kind_in",
    "active_only",
    "passive_only",
    "selected_rank_at_least",
}
SUPPORTED_CATEGORIES = {
    "precombat",
    "maintenance",
    "cooldown",
    "builder",
    "spender",
    "execute",
    "aoe",
    "filler",
    "utility",
}
SUPPORTED_CONFIDENCE = {"high", "medium", "low"}
FUTURE_INPUTS = {"combat_log_metrics", "saved_variables_snapshot", "sim_state"}


class APLProfileLoadError(ValueError):
    pass


@dataclass(frozen=True)
class APLResource:
    name: str
    aliases: tuple[str, ...]
    default_pool: int | None = None


@dataclass(frozen=True)
class APLRuleProfile:
    id: str
    category: str
    match: dict[str, Any]
    condition_template: str
    priority: float
    confidence: str
    note: str


@dataclass(frozen=True)
class APLBranchProfile:
    encounter: str
    include_categories: tuple[str, ...]


@dataclass(frozen=True)
class APLProfile:
    schema_version: str
    profile_id: str
    class_name: str
    spec_key: str
    role: str
    supported_encounters: tuple[str, ...]
    resources: tuple[APLResource, ...]
    thresholds: dict[str, Any]
    condition_templates: dict[str, str]
    rules: tuple[APLRuleProfile, ...]
    branches: tuple[APLBranchProfile, ...]
    assumptions: tuple[str, ...]
    future_inputs: tuple[str, ...]
    confidence: dict[str, Any]


def load_builtin_apl_profile(profile_id: str) -> APLProfile:
    path = PROFILE_DIR / f"{profile_id}.json"
    if not path.exists():
        raise APLProfileLoadError(f"Unknown APL profile {profile_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return validate_apl_profile_data(data, source=str(path))


def load_apl_profile_by_role(class_name: str, spec_key: str, role: str) -> tuple[APLProfile, list[str]]:
    specific_id = f"{class_name.lower().replace(' ', '_')}_{spec_key}"
    warnings: list[str] = []
    try:
        return load_builtin_apl_profile(specific_id), warnings
    except APLProfileLoadError:
        warnings.append("specific_apl_profile_missing")

    generic_id = {
        "dps": "generic_dps",
        "tank": "generic_tank",
        "healer_support": "generic_healer_support",
    }.get(role)
    if not generic_id:
        raise APLProfileLoadError(f"Unsupported role {role}")
    return load_builtin_apl_profile(generic_id), warnings


def validate_apl_profile_data(data: dict[str, Any], source: str = "<memory>") -> APLProfile:
    profile = copy.deepcopy(data)
    required = {
        "schema_version",
        "profile_id",
        "class_name",
        "spec_key",
        "role",
        "supported_encounters",
        "resources",
        "thresholds",
        "condition_templates",
        "rules",
        "branches",
        "assumptions",
    }
    missing = sorted(required - set(profile))
    if missing:
        raise APLProfileLoadError(f"{source} missing required fields: {', '.join(missing)}")
    if profile.get("schema_version") != APL_PROFILE_SCHEMA_VERSION:
        raise APLProfileLoadError(f"{source} invalid schema_version {profile.get('schema_version')!r}")

    required_inputs = set(profile.get("required_inputs", []))
    future_required = sorted(required_inputs & FUTURE_INPUTS)
    if future_required:
        raise APLProfileLoadError(f"{source} marks future input as required: {', '.join(future_required)}")

    condition_templates = {
        str(key): str(value) for key, value in dict(profile.get("condition_templates", {})).items()
    }
    rules = tuple(_validate_rule(item, condition_templates, source) for item in profile.get("rules", []))
    branches = tuple(_validate_branch(item, source) for item in profile.get("branches", []))
    supported = tuple(str(item) for item in profile.get("supported_encounters", []))
    branch_encounters = {branch.encounter for branch in branches}
    for encounter in branch_encounters:
        if encounter not in supported:
            raise APLProfileLoadError(f"{source} unsupported encounter in branch {encounter!r}")

    resources = tuple(
        APLResource(
            name=str(item.get("name", "")),
            aliases=tuple(str(alias) for alias in item.get("aliases", [])),
            default_pool=item.get("default_pool"),
        )
        for item in profile.get("resources", [])
    )
    return APLProfile(
        schema_version=APL_PROFILE_SCHEMA_VERSION,
        profile_id=str(profile["profile_id"]),
        class_name=str(profile["class_name"]),
        spec_key=str(profile["spec_key"]),
        role=str(profile["role"]),
        supported_encounters=supported,
        resources=resources,
        thresholds=dict(profile.get("thresholds", {})),
        condition_templates=condition_templates,
        rules=rules,
        branches=branches,
        assumptions=tuple(str(item) for item in profile.get("assumptions", [])),
        future_inputs=tuple(str(item) for item in profile.get("future_inputs", [])),
        confidence=dict(profile.get("confidence", {})),
    )


def _validate_rule(item: dict[str, Any], templates: dict[str, str], source: str) -> APLRuleProfile:
    rule_id = str(item.get("id", ""))
    category = str(item.get("category", ""))
    if category not in SUPPORTED_CATEGORIES:
        raise APLProfileLoadError(f"{source} rule {rule_id} has invalid category {category!r}")
    match = dict(item.get("match", {}))
    for operator in match:
        if operator not in SUPPORTED_MATCH_OPERATORS:
            raise APLProfileLoadError(f"{source} rule {rule_id} has unsupported match operator {operator!r}")
    template = str(item.get("condition_template", ""))
    if template and template not in templates:
        raise APLProfileLoadError(f"{source} rule {rule_id} references unknown condition template {template!r}")
    confidence = str(item.get("confidence", "medium"))
    if confidence not in SUPPORTED_CONFIDENCE:
        raise APLProfileLoadError(f"{source} rule {rule_id} has invalid confidence {confidence!r}")
    try:
        priority = float(item.get("priority", 100))
    except (TypeError, ValueError) as exc:
        raise APLProfileLoadError(f"{source} rule {rule_id} priority is not numeric") from exc
    return APLRuleProfile(
        id=rule_id,
        category=category,
        match=match,
        condition_template=template,
        priority=priority,
        confidence=confidence,
        note=str(item.get("note", "")),
    )


def _validate_branch(item: dict[str, Any], source: str) -> APLBranchProfile:
    encounter = str(item.get("encounter", ""))
    categories = tuple(str(category) for category in item.get("include_categories", []))
    for category in categories:
        if category not in SUPPORTED_CATEGORIES:
            raise APLProfileLoadError(f"{source} branch {encounter} has unknown branch category {category!r}")
    return APLBranchProfile(encounter=encounter, include_categories=categories)
```

- [ ] **Step 4: Create profile directory and minimal generic profile files**

Create `coa_meta/data/apl_profiles/generic_dps.json`, `coa_meta/data/apl_profiles/generic_tank.json`, and `coa_meta/data/apl_profiles/generic_healer_support.json` using the full JSON content from Task 2.

- [ ] **Step 5: Run profile tests**

Run:

```bash
python -m pytest tests/test_apl_profiles.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit profile loader**

Run:

```bash
git add coa_meta/apl_profiles.py tests/test_apl_profiles.py coa_meta/data/apl_profiles
git commit -m "feat: add APL profile loader"
```

## Task 2: Built-In APL Profiles and Test Fixture

**Files:**
- Create: `coa_meta/data/apl_profiles/generic_dps.json`
- Create: `coa_meta/data/apl_profiles/generic_tank.json`
- Create: `coa_meta/data/apl_profiles/generic_healer_support.json`
- Create: `coa_meta/data/apl_profiles/venomancer_stalker.json`
- Create: `tests/fixtures/apl_build_fixture.jsonl`
- Test: `tests/test_apl_profiles.py`

- [ ] **Step 1: Add fixture normalized records**

Create `tests/fixtures/apl_build_fixture.jsonl`:

```jsonl
{"schema_version":"coa-normalized-v1","build_id":39,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":10,"tab_name":"Class","tab_sort_order":0,"entry_type":"Ability","essence_kind":"ability","essence_type":"abilityEssence","entry_id":100,"spell_id":1000,"spell_ids":[1000],"name":"Free Form","icon":null,"ae_cost":0,"te_cost":0,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Free class mechanic.","required_level":0,"max_rank":1,"row":0,"col":0,"node_type":"SpendCircle","flags":0,"group":0,"is_passive":true,"is_starting_node":true,"required_ids":[],"connected_node_ids":[101],"tags":[],"damage_schools":[],"resources":[],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":39,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":10,"tab_name":"Class","tab_sort_order":0,"entry_type":"Ability","essence_kind":"ability","essence_type":"abilityEssence","entry_id":101,"spell_id":1001,"spell_ids":[1001],"name":"Builder Strike","icon":null,"ae_cost":1,"te_cost":0,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Generates Energy.","required_level":0,"max_rank":1,"row":1,"col":0,"node_type":"SpendSquare","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[100],"connected_node_ids":[102],"tags":["builder"],"damage_schools":["physical"],"resources":["Energy"],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":39,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":10,"tab_name":"Class","tab_sort_order":0,"entry_type":"Ability","essence_kind":"ability","essence_type":"abilityEssence","entry_id":102,"spell_id":1002,"spell_ids":[1002],"name":"Power Spender","icon":null,"ae_cost":1,"te_cost":0,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Consumes Energy to deal damage.","required_level":0,"max_rank":1,"row":2,"col":0,"node_type":"SpendSquare","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[101],"connected_node_ids":[],"tags":["spender"],"damage_schools":["physical"],"resources":["Energy"],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":39,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":11,"tab_name":"Damage","tab_sort_order":1,"entry_type":"Talent","essence_kind":"talent","essence_type":"talentEssence","entry_id":103,"spell_id":1003,"spell_ids":[1003],"name":"Poison Talent","icon":null,"ae_cost":0,"te_cost":1,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Deals Nature damage over time.","required_level":0,"max_rank":1,"row":1,"col":1,"node_type":"SpendCircle","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[],"connected_node_ids":[],"tags":["dot"],"damage_schools":["nature"],"resources":[],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":39,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":11,"tab_name":"Damage","tab_sort_order":1,"entry_type":"Ability","essence_kind":"ability","essence_type":"abilityEssence","entry_id":104,"spell_id":1004,"spell_ids":[1004],"name":"Burst Cooldown","icon":null,"ae_cost":1,"te_cost":0,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"A cooldown that increases damage for 12 seconds.","required_level":0,"max_rank":1,"row":2,"col":1,"node_type":"SpendSquare","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[],"connected_node_ids":[],"tags":["cooldown"],"damage_schools":[],"resources":[],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":39,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":11,"tab_name":"Damage","tab_sort_order":1,"entry_type":"Ability","essence_kind":"ability","essence_type":"abilityEssence","entry_id":105,"spell_id":1005,"spell_ids":[1005],"name":"Execute Strike","icon":null,"ae_cost":1,"te_cost":0,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Deals extra damage to low health targets.","required_level":0,"max_rank":1,"row":3,"col":1,"node_type":"SpendSquare","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[],"connected_node_ids":[],"tags":["execute"],"damage_schools":["physical"],"resources":["Energy"],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":39,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":11,"tab_name":"Damage","tab_sort_order":1,"entry_type":"Ability","essence_kind":"ability","essence_type":"abilityEssence","entry_id":106,"spell_id":1006,"spell_ids":[1006],"name":"Cleave Burst","icon":null,"ae_cost":1,"te_cost":0,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Deals damage to all enemies nearby.","required_level":0,"max_rank":1,"row":4,"col":1,"node_type":"SpendSquare","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[],"connected_node_ids":[],"tags":[],"damage_schools":["fire"],"resources":[],"field_sources":{},"inferred":{},"raw":{}}
```

- [ ] **Step 2: Add built-in DPS profile**

Create `coa_meta/data/apl_profiles/generic_dps.json`:

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
    "always": "",
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
    },
    {
      "id": "use_cooldowns",
      "category": "cooldown",
      "match": {"tags_any": ["cooldown", "resource_management"], "active_only": true},
      "condition_template": "cooldown_ready",
      "priority": 40,
      "confidence": "medium",
      "note": "use selected cooldowns when ready"
    },
    {
      "id": "execute_actions",
      "category": "execute",
      "match": {"tags_any": ["execute"], "active_only": true},
      "condition_template": "execute",
      "priority": 50,
      "confidence": "medium",
      "note": "execute window action"
    },
    {
      "id": "aoe_text_actions",
      "category": "aoe",
      "match": {"description_matches_any": ["nearby enemies", "all enemies", "up to [0-9]+ enemies"], "active_only": true},
      "condition_template": "aoe",
      "priority": 60,
      "confidence": "low",
      "note": "AoE condition inferred from tooltip text"
    },
    {
      "id": "spenders",
      "category": "spender",
      "match": {"tags_any": ["spender"], "active_only": true},
      "condition_template": "spender_ready",
      "priority": 70,
      "confidence": "medium",
      "note": "spend at profile threshold"
    },
    {
      "id": "builders",
      "category": "builder",
      "match": {"tags_any": ["builder"], "active_only": true},
      "condition_template": "builder_ready",
      "priority": 80,
      "confidence": "medium",
      "note": "build primary resource"
    },
    {
      "id": "active_filler",
      "category": "filler",
      "match": {"entry_type_in": ["Ability"], "active_only": true},
      "condition_template": "always",
      "priority": 200,
      "confidence": "low",
      "note": "fallback active ability"
    }
  ],
  "branches": [
    {"encounter": "single_target", "include_categories": ["maintenance", "cooldown", "execute", "spender", "builder", "filler"]},
    {"encounter": "aoe_5", "include_categories": ["maintenance", "cooldown", "execute", "aoe", "spender", "builder", "filler"]}
  ],
  "assumptions": ["Generated from normalized builder data and static DPS APL profile rules."],
  "future_inputs": ["combat_log_metrics", "saved_variables_snapshot", "sim_state"],
  "confidence": {"base": "medium"}
}
```

- [ ] **Step 3: Add tank profile**

Create `coa_meta/data/apl_profiles/generic_tank.json`:

```json
{
  "schema_version": "coa-apl-profile-v1",
  "profile_id": "generic_tank",
  "class_name": "*",
  "spec_key": "*",
  "role": "tank",
  "supported_encounters": ["single_target", "aoe_5"],
  "resources": [{"name": "Resource", "aliases": ["resource"], "default_pool": null}],
  "thresholds": {"spender": 70, "execute_health_pct": 35, "aoe_min_enemies": 3},
  "condition_templates": {
    "always": "",
    "cooldown_ready": "cooldown.{action_key}.ready",
    "spender_ready": "{primary_resource}>={spender_threshold}",
    "builder_ready": "{primary_resource}.deficit>0",
    "aoe": "active_enemies>={aoe_min_enemies}"
  },
  "rules": [
    {
      "id": "defensive_cooldowns",
      "category": "cooldown",
      "match": {"tags_any": ["tank", "cooldown"], "active_only": true},
      "condition_template": "cooldown_ready",
      "priority": 30,
      "confidence": "medium",
      "note": "use defensive or tank cooldowns when ready"
    },
    {
      "id": "aoe_text_actions",
      "category": "aoe",
      "match": {"description_matches_any": ["nearby enemies", "all enemies", "up to [0-9]+ enemies"], "active_only": true},
      "condition_template": "aoe",
      "priority": 60,
      "confidence": "low",
      "note": "AoE condition inferred from tooltip text"
    },
    {
      "id": "spenders",
      "category": "spender",
      "match": {"tags_any": ["spender"], "active_only": true},
      "condition_template": "spender_ready",
      "priority": 70,
      "confidence": "medium",
      "note": "spend at profile threshold"
    },
    {
      "id": "builders",
      "category": "builder",
      "match": {"tags_any": ["builder"], "active_only": true},
      "condition_template": "builder_ready",
      "priority": 80,
      "confidence": "medium",
      "note": "build primary resource"
    }
  ],
  "branches": [
    {"encounter": "single_target", "include_categories": ["cooldown", "spender", "builder"]},
    {"encounter": "aoe_5", "include_categories": ["cooldown", "aoe", "spender", "builder"]}
  ],
  "assumptions": ["Generated from normalized builder data and static tank APL profile rules."],
  "future_inputs": ["combat_log_metrics", "saved_variables_snapshot", "sim_state"],
  "confidence": {"base": "medium"}
}
```

- [ ] **Step 4: Add healer/support profile**

Create `coa_meta/data/apl_profiles/generic_healer_support.json`:

```json
{
  "schema_version": "coa-apl-profile-v1",
  "profile_id": "generic_healer_support",
  "class_name": "*",
  "spec_key": "*",
  "role": "healer_support",
  "supported_encounters": ["single_target", "aoe_5"],
  "resources": [{"name": "Mana", "aliases": ["mana"], "default_pool": null}],
  "thresholds": {"spender": 70, "execute_health_pct": 35, "aoe_min_enemies": 3},
  "condition_templates": {
    "always": "",
    "maintain_hot": "hot.{action_key}.remains<gcd",
    "cooldown_ready": "cooldown.{action_key}.ready",
    "builder_ready": "{primary_resource}.deficit>0"
  },
  "rules": [
    {
      "id": "maintain_hots",
      "category": "maintenance",
      "match": {"tags_any": ["hot"], "active_only": true},
      "condition_template": "maintain_hot",
      "priority": 20,
      "confidence": "medium",
      "note": "maintain healing over time effect"
    },
    {
      "id": "support_cooldowns",
      "category": "cooldown",
      "match": {"tags_any": ["heal", "cooldown", "aura"], "active_only": true},
      "condition_template": "cooldown_ready",
      "priority": 40,
      "confidence": "medium",
      "note": "use support cooldowns when ready"
    },
    {
      "id": "resource_builders",
      "category": "builder",
      "match": {"tags_any": ["builder", "resource_management"], "active_only": true},
      "condition_template": "builder_ready",
      "priority": 80,
      "confidence": "medium",
      "note": "recover or build resource"
    }
  ],
  "branches": [
    {"encounter": "single_target", "include_categories": ["maintenance", "cooldown", "builder"]},
    {"encounter": "aoe_5", "include_categories": ["maintenance", "cooldown", "builder"]}
  ],
  "assumptions": ["Generated from normalized builder data and static healer/support APL profile rules."],
  "future_inputs": ["combat_log_metrics", "saved_variables_snapshot", "sim_state"],
  "confidence": {"base": "medium"}
}
```

- [ ] **Step 5: Add Venomancer Stalker profile data**

Create `coa_meta/data/apl_profiles/venomancer_stalker.json`:

```json
{
  "schema_version": "coa-apl-profile-v1",
  "profile_id": "venomancer_stalker",
  "class_name": "Venomancer",
  "spec_key": "stalker",
  "role": "dps",
  "supported_encounters": ["single_target", "aoe_5"],
  "resources": [{"name": "Energy", "aliases": ["energy"], "default_pool": null}],
  "thresholds": {"spender": 80, "execute_health_pct": 35, "aoe_min_enemies": 3},
  "condition_templates": {
    "always": "",
    "maintain_dot": "dot.{action_key}.remains<gcd",
    "cooldown_ready": "cooldown.{action_key}.ready",
    "brood_spender": "brood_marks>=5",
    "brood_builder": "brood_marks<5",
    "execute": "target.health.pct<{execute_health_pct}",
    "aoe": "active_enemies>={aoe_min_enemies}"
  },
  "rules": [
    {
      "id": "stalker_dot_maintenance",
      "category": "maintenance",
      "match": {"name_contains_any": ["Withering Venom", "Nerubian Sting"], "active_only": true},
      "condition_template": "maintain_dot",
      "priority": 20,
      "confidence": "medium",
      "note": "maintain Stalker poison or sting effect"
    },
    {
      "id": "stalker_cooldowns",
      "category": "cooldown",
      "match": {"name_contains_any": ["Noxious Empowerment"], "active_only": true},
      "condition_template": "cooldown_ready",
      "priority": 40,
      "confidence": "medium",
      "note": "use Stalker burst window when ready"
    },
    {
      "id": "stalker_execute",
      "category": "execute",
      "match": {"name_contains_any": ["Widowmaker"], "active_only": true},
      "condition_template": "execute",
      "priority": 50,
      "confidence": "medium",
      "note": "execute if selected"
    },
    {
      "id": "stalker_aoe",
      "category": "aoe",
      "match": {"name_contains_any": ["Contagion", "Brood Lord"], "active_only": true},
      "condition_template": "aoe",
      "priority": 60,
      "confidence": "medium",
      "note": "Stalker AoE package"
    },
    {
      "id": "stalker_spenders",
      "category": "spender",
      "match": {"name_contains_any": ["Facemelter"], "active_only": true},
      "condition_template": "brood_spender",
      "priority": 70,
      "confidence": "medium",
      "note": "spend Brood Marks"
    },
    {
      "id": "stalker_generic_builders",
      "category": "builder",
      "match": {"tags_any": ["builder"], "active_only": true},
      "condition_template": "brood_builder",
      "priority": 80,
      "confidence": "low",
      "note": "build Stalker resource package when detected"
    },
    {
      "id": "stalker_filler",
      "category": "filler",
      "match": {"entry_type_in": ["Ability", "Talent"], "active_only": true},
      "condition_template": "always",
      "priority": 200,
      "confidence": "low",
      "note": "fallback selected active node"
    }
  ],
  "branches": [
    {"encounter": "single_target", "include_categories": ["maintenance", "cooldown", "execute", "spender", "builder", "filler"]},
    {"encounter": "aoe_5", "include_categories": ["maintenance", "cooldown", "execute", "aoe", "spender", "builder", "filler"]}
  ],
  "assumptions": ["Generated from normalized builder data and Stalker APL profile rules."],
  "future_inputs": ["combat_log_metrics", "saved_variables_snapshot", "sim_state"],
  "confidence": {"base": "medium"}
}
```

- [ ] **Step 6: Run profile tests after adding data**

Run:

```bash
python -m pytest tests/test_apl_profiles.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit built-in profile data**

Run:

```bash
git add coa_meta/data/apl_profiles tests/fixtures/apl_build_fixture.jsonl tests/test_apl_profiles.py
git commit -m "feat: add built-in APL profiles"
```

## Task 3: APL Document Model and Exporters

**Files:**
- Create: `coa_meta/apl.py`
- Test: `tests/test_apl_exports.py`

- [ ] **Step 1: Write failing export tests**

Create `tests/test_apl_exports.py`:

```python
from __future__ import annotations

from coa_meta.apl import APLAction, APLDocument, apl_to_simc_lines


def test_apl_document_serializes_to_canonical_dict():
    document = APLDocument(
        schema_version="coa-apl-v1",
        source="theorycraft",
        profile_id="generic_dps",
        class_name="Testclass",
        spec_key="generic",
        role="dps",
        encounter="single_target",
        actions=(
            APLAction(
                action_key="poison_talent",
                action_name="Poison Talent",
                node_id=103,
                spell_id=1003,
                category="maintenance",
                condition="dot.poison_talent.remains<gcd",
                priority=20,
                confidence="medium",
                notes=("maintain DoT/debuff uptime",),
                evidence=("tag:dot", "profile_rule:maintain_dots"),
            ),
        ),
        assumptions=("Generated from normalized builder data.",),
        warnings=("condition inferred from normalized tooltip tags",),
        provenance={"profile_schema": "coa-apl-profile-v1"},
    )

    payload = document.to_dict()

    assert payload["schema_version"] == "coa-apl-v1"
    assert payload["source"] == "theorycraft"
    assert payload["actions"][0]["action_key"] == "poison_talent"
    assert payload["actions"][0]["evidence"] == ["tag:dot", "profile_rule:maintain_dots"]


def test_simc_export_uses_action_key_condition_and_note():
    document = APLDocument(
        schema_version="coa-apl-v1",
        source="theorycraft",
        profile_id="generic_dps",
        class_name="Testclass",
        spec_key="generic",
        role="dps",
        encounter="single_target",
        actions=(
            APLAction(
                action_key="poison_talent",
                action_name="Poison Talent",
                node_id=103,
                spell_id=1003,
                category="maintenance",
                condition="dot.poison_talent.remains<gcd",
                priority=20,
                confidence="medium",
                notes=("maintain DoT/debuff uptime",),
                evidence=("tag:dot", "profile_rule:maintain_dots"),
            ),
        ),
        assumptions=(),
        warnings=(),
        provenance={},
    )

    assert apl_to_simc_lines(document) == [
        "actions+=/poison_talent,if=dot.poison_talent.remains<gcd  # maintain DoT/debuff uptime"
    ]


def test_simc_export_omits_if_when_condition_is_empty():
    document = APLDocument(
        schema_version="coa-apl-v1",
        source="theorycraft",
        profile_id="generic_dps",
        class_name="Testclass",
        spec_key="generic",
        role="dps",
        encounter="single_target",
        actions=(
            APLAction(
                action_key="auto_attack",
                action_name="Auto Attack",
                node_id=None,
                spell_id=None,
                category="filler",
                condition="",
                priority=200,
                confidence="low",
                notes=("fallback active ability",),
                evidence=("profile_rule:active_filler",),
            ),
        ),
        assumptions=(),
        warnings=(),
        provenance={},
    )

    assert apl_to_simc_lines(document) == ["actions+=/auto_attack  # fallback active ability"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_apl_exports.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'coa_meta.apl'`.

- [ ] **Step 3: Implement APL dataclasses and exporter**

Create the initial `coa_meta/apl.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

APL_SCHEMA_VERSION = "coa-apl-v1"


class APLGenerationError(ValueError):
    pass


@dataclass(frozen=True)
class APLAction:
    action_key: str
    action_name: str
    node_id: int | None
    spell_id: int | None
    category: str
    condition: str
    priority: float
    confidence: str
    notes: tuple[str, ...]
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_key": self.action_key,
            "action_name": self.action_name,
            "node_id": self.node_id,
            "spell_id": self.spell_id,
            "category": self.category,
            "condition": self.condition,
            "priority": self.priority,
            "confidence": self.confidence,
            "notes": list(self.notes),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class APLDocument:
    schema_version: str
    source: str
    profile_id: str
    class_name: str
    spec_key: str
    role: str
    encounter: str
    actions: tuple[APLAction, ...]
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    provenance: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "profile_id": self.profile_id,
            "class_name": self.class_name,
            "spec_key": self.spec_key,
            "role": self.role,
            "encounter": self.encounter,
            "actions": [action.to_dict() for action in self.actions],
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "provenance": dict(self.provenance),
        }


def slugify_action(name: str) -> str:
    normalized = name.lower().replace("'", "")
    return re.sub(r"[^a-z0-9_]+", "_", normalized).strip("_")


def apl_to_simc_lines(document: APLDocument) -> list[str]:
    lines: list[str] = []
    for action in document.actions:
        condition = f",if={action.condition}" if action.condition else ""
        note = f"  # {action.notes[0]}" if action.notes else ""
        lines.append(f"actions+=/{action.action_key}{condition}{note}")
    return lines
```

- [ ] **Step 4: Run export tests**

Run:

```bash
python -m pytest tests/test_apl_exports.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit APL document model**

Run:

```bash
git add coa_meta/apl.py tests/test_apl_exports.py
git commit -m "feat: add APL document exports"
```

## Task 4: APL Generator and Branch Logic

**Files:**
- Modify: `coa_meta/apl.py`
- Test: `tests/test_apl_generation.py`

- [ ] **Step 1: Write failing generation tests**

Create `tests/test_apl_generation.py`:

```python
from __future__ import annotations

from pathlib import Path

from coa_meta.apl import generate_apl
from coa_meta.apl_profiles import load_builtin_apl_profile
from coa_meta.builds import BuildConfig, BuildRules
from coa_meta.domain import SelectedRank
from coa_meta.repository import TalentRepository

FIXTURE = Path(__file__).parent / "fixtures" / "apl_build_fixture.jsonl"


def build_state():
    repo = TalentRepository.from_entries(FIXTURE)
    rules = BuildRules(repo, BuildConfig(class_name="Testclass", level=60, max_ae=10, max_te=5))
    result = rules.validate(
        [
            SelectedRank(101, 1),
            SelectedRank(102, 1),
            SelectedRank(103, 1),
            SelectedRank(104, 1),
            SelectedRank(105, 1),
            SelectedRank(106, 1),
        ]
    )
    assert result.valid
    assert result.state is not None
    return repo, result.state


def test_generates_single_target_apl_from_selected_build():
    repo, state = build_state()
    profile = load_builtin_apl_profile("generic_dps")

    document = generate_apl(state, repo, profile, encounter="single_target")
    categories = [action.category for action in document.actions]

    assert document.schema_version == "coa-apl-v1"
    assert document.source == "theorycraft"
    assert "maintenance" in categories
    assert "cooldown" in categories
    assert "execute" in categories
    assert "spender" in categories
    assert "builder" in categories
    assert "aoe" not in categories
    assert any(action.action_name == "Poison Talent" for action in document.actions)
    assert any("profile_rule:maintain_dots" in action.evidence for action in document.actions)


def test_generates_aoe_branch_independently():
    repo, state = build_state()
    profile = load_builtin_apl_profile("generic_dps")

    document = generate_apl(state, repo, profile, encounter="aoe_5")
    aoe_actions = [action for action in document.actions if action.category == "aoe"]

    assert aoe_actions
    assert aoe_actions[0].condition == "active_enemies>=3"
    assert aoe_actions[0].action_name == "Cleave Burst"


def test_orders_maintenance_before_spender_and_builder():
    repo, state = build_state()
    profile = load_builtin_apl_profile("generic_dps")

    document = generate_apl(state, repo, profile, encounter="single_target")
    by_category = {action.category: index for index, action in enumerate(document.actions)}

    assert by_category["maintenance"] < by_category["spender"]
    assert by_category["spender"] < by_category["builder"]


def test_generation_warns_when_generic_profile_used():
    repo, state = build_state()
    profile, warnings = load_builtin_apl_profile("generic_dps"), ["specific_apl_profile_missing"]

    document = generate_apl(state, repo, profile, encounter="single_target", profile_warnings=warnings)

    assert "specific_apl_profile_missing" in document.warnings
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_apl_generation.py -q
```

Expected: FAIL with `ImportError: cannot import name 'generate_apl'`.

- [ ] **Step 3: Add generator implementation**

Extend `coa_meta/apl.py` with these functions and constants:

```python
from .apl_profiles import APLProfile, APLRuleProfile
from .domain import BuildState, TalentNode
from .repository import TalentRepository

CATEGORY_ORDER = {
    "precombat": 0,
    "maintenance": 10,
    "cooldown": 20,
    "execute": 30,
    "aoe": 40,
    "spender": 50,
    "builder": 60,
    "filler": 70,
    "utility": 80,
}


def generate_apl(
    state: BuildState,
    repository: TalentRepository,
    profile: APLProfile,
    encounter: str,
    profile_warnings: list[str] | None = None,
) -> APLDocument:
    if encounter not in profile.supported_encounters:
        raise APLGenerationError(f"{profile.profile_id} does not support encounter {encounter}")
    branch = next((item for item in profile.branches if item.encounter == encounter), None)
    if branch is None:
        raise APLGenerationError(f"{profile.profile_id} has no branch for encounter {encounter}")

    nodes = [repository.get_node(node_id) for node_id in state.selected_ids]
    selected_nodes = [node for node in nodes if node is not None]
    selected_ranks = {selected.node_id: selected.rank for selected in state.selected_ranks}
    actions: list[APLAction] = []
    warnings: list[str] = list(profile_warnings or [])

    for rule in profile.rules:
        if rule.category not in branch.include_categories:
            continue
        for node in selected_nodes:
            if _node_matches_rule(node, selected_ranks.get(node.entry_id, state.rank_for(node.entry_id)), rule):
                actions.append(_action_from_match(node, rule, profile))
                if _uses_inferred_condition(node, rule):
                    warning = "condition inferred from normalized tooltip tags"
                    if warning not in warnings:
                        warnings.append(warning)

    deduped = _dedupe_actions(actions)
    categories = {action.category for action in deduped}
    for category in branch.include_categories:
        if category not in categories:
            warnings.append(f"no action matched category:{category}")
    if selected_nodes and "filler" not in categories:
        warnings.append("selected build has active nodes but no filler action")

    return APLDocument(
        schema_version=APL_SCHEMA_VERSION,
        source="theorycraft",
        profile_id=profile.profile_id,
        class_name=state.class_name,
        spec_key=profile.spec_key,
        role=profile.role,
        encounter=encounter,
        actions=tuple(sorted(deduped, key=_action_sort_key)),
        assumptions=profile.assumptions,
        warnings=tuple(warnings),
        provenance={
            "build_state_schema": "M1.3 BuildState",
            "profile_schema": "coa-apl-profile-v1",
            "normalized_schema": "coa-normalized-v1",
        },
    )


def _node_matches_rule(node: TalentNode, selected_rank: int, rule: APLRuleProfile) -> bool:
    match = rule.match
    if match.get("active_only") and node.is_passive:
        return False
    if match.get("passive_only") and not node.is_passive:
        return False
    if "selected_rank_at_least" in match and selected_rank < int(match["selected_rank_at_least"]):
        return False
    if "tags_any" in match and not set(match["tags_any"]) & set(node.tags):
        return False
    if "tags_all" in match and not set(match["tags_all"]).issubset(set(node.tags)):
        return False
    if "schools_any" in match and not set(match["schools_any"]) & set(node.damage_schools):
        return False
    if "resources_any" in match and not set(match["resources_any"]) & set(node.resources):
        return False
    if "name_contains_any" in match:
        lowered = node.name.lower()
        if not any(str(item).lower() in lowered for item in match["name_contains_any"]):
            return False
    if "description_matches_any" in match:
        if not any(re.search(str(pattern), node.description_text, re.IGNORECASE) for pattern in match["description_matches_any"]):
            return False
    if "entry_type_in" in match and node.entry_type not in set(match["entry_type_in"]):
        return False
    if "essence_kind_in" in match and node.essence_kind not in set(match["essence_kind_in"]):
        return False
    return True


def _action_from_match(node: TalentNode, rule: APLRuleProfile, profile: APLProfile) -> APLAction:
    action_key = slugify_action(node.name)
    condition = _render_condition(rule.condition_template, action_key, profile)
    evidence = [f"profile_rule:{rule.id}"]
    for tag in node.tags:
        if tag in rule.match.get("tags_any", []) or tag in rule.match.get("tags_all", []):
            evidence.insert(0, f"tag:{tag}")
    return APLAction(
        action_key=action_key,
        action_name=node.name,
        node_id=node.entry_id,
        spell_id=node.spell_id,
        category=rule.category,
        condition=condition,
        priority=rule.priority,
        confidence=rule.confidence,
        notes=(rule.note,) if rule.note else tuple(),
        evidence=tuple(evidence),
    )


def _render_condition(template_name: str, action_key: str, profile: APLProfile) -> str:
    if not template_name:
        return ""
    template = profile.condition_templates.get(template_name, "")
    primary_resource = profile.resources[0].aliases[0] if profile.resources and profile.resources[0].aliases else "resource"
    values = {
        "action_key": action_key,
        "primary_resource": primary_resource,
        "spender_threshold": profile.thresholds.get("spender", 80),
        "execute_health_pct": profile.thresholds.get("execute_health_pct", 35),
        "aoe_min_enemies": profile.thresholds.get("aoe_min_enemies", 3),
    }
    return template.format(**values)


def _uses_inferred_condition(node: TalentNode, rule: APLRuleProfile) -> bool:
    return bool(node.tags or rule.match.get("description_matches_any"))


def _dedupe_actions(actions: list[APLAction]) -> list[APLAction]:
    seen: set[tuple[str, str, str]] = set()
    output: list[APLAction] = []
    for action in sorted(actions, key=_action_sort_key):
        key = (action.action_key, action.condition, action.category)
        if key in seen:
            continue
        seen.add(key)
        output.append(action)
    return output


def _action_sort_key(action: APLAction) -> tuple[float, int, str]:
    return (action.priority, CATEGORY_ORDER.get(action.category, 999), action.action_name)
```

- [ ] **Step 4: Run generation tests**

Run:

```bash
python -m pytest tests/test_apl_generation.py -q
```

Expected: PASS.

- [ ] **Step 5: Run related APL tests together**

Run:

```bash
python -m pytest tests/test_apl_profiles.py tests/test_apl_exports.py tests/test_apl_generation.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit generator**

Run:

```bash
git add coa_meta/apl.py tests/test_apl_generation.py tests/fixtures/apl_build_fixture.jsonl
git commit -m "feat: generate APL documents from profiles"
```

## Task 5: Stalker Semantic Regression

**Files:**
- Test: `tests/test_apl_stalker_regression.py`
- Modify: `coa_meta/data/apl_profiles/venomancer_stalker.json`

- [ ] **Step 1: Write failing Stalker semantic tests**

Create `tests/test_apl_stalker_regression.py`:

```python
from __future__ import annotations

from pathlib import Path

from coa_meta.apl import generate_apl
from coa_meta.apl_profiles import load_builtin_apl_profile
from coa_meta.domain import BuildState, SelectedRank
from coa_meta.repository import TalentRepository

ENTRIES = Path("coa_scraper/dist/coa_entries.jsonl")
STALKER_NODE_IDS = {
    "Withering Venom": 7152,
    "Contagion": 7190,
    "Widowmaker": 12201,
    "Noxious Empowerment": 29577,
    "Nerubian Sting": 29580,
    "Facemelter": 30464,
}


def stalker_state() -> tuple[TalentRepository, BuildState]:
    repo = TalentRepository.from_entries(ENTRIES)
    selected = tuple(SelectedRank(node_id, 1) for node_id in sorted(STALKER_NODE_IDS.values()))
    state = BuildState(
        class_name="Venomancer",
        selected_ranks=selected,
        free_node_ids=tuple(),
        ae_spent=0,
        te_spent=len(selected),
        tab_ae=tuple(),
        tab_te=((77, len(selected)),),
    )
    return repo, state


def test_stalker_single_target_matches_old_apl_semantics():
    repo, state = stalker_state()
    profile = load_builtin_apl_profile("venomancer_stalker")

    document = generate_apl(state, repo, profile, encounter="single_target")
    by_name = {action.action_name: action for action in document.actions}
    categories = [action.category for action in document.actions]

    assert by_name["Withering Venom"].category == "maintenance"
    assert by_name["Nerubian Sting"].category == "maintenance"
    assert by_name["Facemelter"].category == "spender"
    assert by_name["Widowmaker"].category == "execute"
    assert by_name["Widowmaker"].condition == "target.health.pct<35"
    assert "aoe" not in categories
    assert categories.index("maintenance") < categories.index("spender")
    assert any("profile_rule:stalker_dot_maintenance" in action.evidence for action in document.actions)


def test_stalker_aoe_branch_contains_aoe_actions():
    repo, state = stalker_state()
    profile = load_builtin_apl_profile("venomancer_stalker")

    document = generate_apl(state, repo, profile, encounter="aoe_5")
    by_name = {action.action_name: action for action in document.actions}

    assert by_name["Contagion"].category == "aoe"
    assert by_name["Contagion"].condition == "active_enemies>=3"
    assert by_name["Facemelter"].category == "spender"
```

- [ ] **Step 2: Run tests to verify failure if profile data is incomplete**

Run:

```bash
python -m pytest tests/test_apl_stalker_regression.py -q
```

Expected if Task 2 profile is present and generator is complete: PASS. Expected if profile data was not committed correctly: FAIL with a missing action assertion naming the absent Stalker action.

- [ ] **Step 3: Adjust only profile data if semantic assertions fail**

If the test fails because a selected Stalker node is classified as `filler`, adjust `coa_meta/data/apl_profiles/venomancer_stalker.json` by adding a data rule that matches the node by `name_contains_any`. Do not add Python branches for Stalker.

Example rule for a missing maintenance action:

```json
{
  "id": "stalker_missing_maintenance_name",
  "category": "maintenance",
  "match": {"name_contains_any": ["Nerubian Sting"], "active_only": true},
  "condition_template": "maintain_dot",
  "priority": 20,
  "confidence": "medium",
  "note": "maintain Stalker poison or sting effect"
}
```

- [ ] **Step 4: Run Stalker and generator tests**

Run:

```bash
python -m pytest tests/test_apl_generation.py tests/test_apl_stalker_regression.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit semantic regression coverage**

Run:

```bash
git add tests/test_apl_stalker_regression.py coa_meta/data/apl_profiles/venomancer_stalker.json
git commit -m "test: add Stalker APL semantic regression"
```

## Task 6: Compatibility Wiring in Prototype CLI

**Files:**
- Modify: `coa_optimizer_extensible.py`
- Test: `tests/test_apl_compatibility.py`

- [ ] **Step 1: Write compatibility tests**

Create `tests/test_apl_compatibility.py`:

```python
from __future__ import annotations

from pathlib import Path

from coa_optimizer_extensible import generate_compat_rotation_lines

FIXTURE = Path(__file__).parent / "fixtures" / "apl_build_fixture.jsonl"


def test_compat_rotation_lines_delegate_to_package_generator():
    lines = generate_compat_rotation_lines(
        entries_path=FIXTURE,
        class_name="Testclass",
        profile_name="generic",
        encounter="single_target",
        selected_names=["Poison Talent", "Builder Strike", "Power Spender"],
        role="dps",
    )

    assert any(line.startswith("actions+=/poison_talent,if=dot.poison_talent.remains<gcd") for line in lines)
    assert any(line.startswith("actions+=/power_spender,if=energy>=80") for line in lines)
    assert any(line.startswith("actions+=/builder_strike,if=energy.deficit>0") for line in lines)
```

- [ ] **Step 2: Run compatibility test to verify it fails**

Run:

```bash
python -m pytest tests/test_apl_compatibility.py -q
```

Expected: FAIL with `ImportError: cannot import name 'generate_compat_rotation_lines'`.

- [ ] **Step 3: Add compatibility helper imports**

Modify the import section of `coa_optimizer_extensible.py` by adding:

```python
from coa_meta.apl import apl_to_simc_lines, generate_apl
from coa_meta.apl_profiles import load_apl_profile_by_role
from coa_meta.builds import BuildConfig as PackageBuildConfig
from coa_meta.builds import BuildRules as PackageBuildRules
from coa_meta.domain import SelectedRank as PackageSelectedRank
from coa_meta.repository import TalentRepository as PackageTalentRepository
```

- [ ] **Step 4: Add compatibility helper function**

Add this function near the existing rotation strategy functions in `coa_optimizer_extensible.py`:

```python
def generate_compat_rotation_lines(
    entries_path: Path,
    class_name: str,
    profile_name: str,
    encounter: str,
    selected_names: list[str],
    role: str = "dps",
) -> list[str]:
    package_repo = PackageTalentRepository.from_entries(entries_path)
    selected_ids: list[int] = []
    for name in selected_names:
        selected_ids.append(package_repo.node_by_name(class_name, name).entry_id)
    package_rules = PackageBuildRules(
        package_repo,
        PackageBuildConfig(class_name=class_name, level=60, max_ae=99, max_te=99),
    )
    validation = package_rules.validate([PackageSelectedRank(node_id, 1) for node_id in selected_ids])
    if not validation.valid or validation.state is None:
        raise SystemExit(f"selected rotation nodes are not legal: {validation.issue_codes()}")

    spec_key = "stalker" if profile_name == "stalker" else profile_name
    apl_profile, warnings = load_apl_profile_by_role(class_name=class_name, spec_key=spec_key, role=role)
    apl_encounter = "aoe_5" if encounter in {"aoe", "aoe_5"} else "single_target"
    document = generate_apl(validation.state, package_repo, apl_profile, encounter=apl_encounter, profile_warnings=warnings)
    return apl_to_simc_lines(document)
```

- [ ] **Step 5: Replace rotation command implementation**

In `command_rotation`, replace direct `make_rotation_strategy(...).generate(selected)` usage with:

```python
    selected_names = args.selected_names
    if not selected_names and args.from_build_json:
        payload = json.loads(args.from_build_json.read_text(encoding="utf-8"))
        if isinstance(payload, list) and payload:
            payload = payload[0]
        selected_names = [
            item["name"]
            for tab_nodes in (payload.get("paid_by_tab") or {}).values()
            for item in tab_nodes
            if item.get("name")
        ]
    if not selected_names:
        selected_names = [node.name for node in nodes.values() if not node.is_passive]
    for line in generate_compat_rotation_lines(
        entries_path=args.entries,
        class_name=args.class_name,
        profile_name=args.profile,
        encounter=args.encounter,
        selected_names=selected_names,
        role="dps",
    ):
        print(line)
```

- [ ] **Step 6: Replace JSON rotation output path**

In `command_optimize`, replace:

```python
            selected = [nodes[i] for i in st.selected if i in nodes]
            rot = make_rotation_strategy(args.class_name, args.profile, args.encounter).generate(selected)
            item["rotation_apl"] = [r.simc_like() for r in rot]
```

with:

```python
            selected_names = [nodes[i].name for i in st.selected if i in nodes]
            item["rotation_apl"] = generate_compat_rotation_lines(
                entries_path=args.entries,
                class_name=args.class_name,
                profile_name=args.profile,
                encounter=args.encounter,
                selected_names=selected_names,
                role="dps",
            )
```

Also replace the `--show-rotation` direct strategy call with the same helper and print returned lines.

- [ ] **Step 7: Run compatibility tests**

Run:

```bash
python -m pytest tests/test_apl_compatibility.py -q
```

Expected: PASS.

- [ ] **Step 8: Run old and new Python tests together**

Run:

```bash
python -m pytest tests/test_build_rules.py tests/test_build_search.py tests/test_scoring_engine.py tests/test_apl_compatibility.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit compatibility wiring**

Run:

```bash
git add coa_optimizer_extensible.py tests/test_apl_compatibility.py
git commit -m "feat: wire prototype rotations to APL generator"
```

## Task 7: M1.5 Documentation and Completion Gate

**Files:**
- Modify: `docs/MODULES.md`
- Modify: `docs/DECISIONS.md`
- Create: `docs/data/apl-profile-schema.md`
- Create: `docs/data/apl-schema.md`

- [ ] **Step 1: Update module docs**

In `docs/MODULES.md`, under "Rotation and APL Module", add:

```markdown
M1.5 implementation files:

- `coa_meta/apl.py`
- `coa_meta/apl_profiles.py`
- `coa_meta/data/apl_profiles/*.json`
```

- [ ] **Step 2: Add architecture decision**

Append to `docs/DECISIONS.md`:

```markdown
## Decision 13: APL Generation Uses Structured Profiles

Status: accepted.

M1.5 APL generation uses `coa-apl-profile-v1` JSON profile data and emits `coa-apl-v1` structured JSON as the canonical artifact. SimC-like text is an export derived from structured APL data.

Reasoning:

- Every class/spec should use the same production APL generation engine.
- Class/spec behavior belongs in data profiles, not hard-coded Python branches.
- Phase 1 can generate theorycraft rotation scaffolds without SavedVariables, combat logs, gear snapshots, or simulator state.
- Structured APLs can later be edited, rendered, and executed by a simulator.
```

- [ ] **Step 3: Add APL profile schema doc**

Create `docs/data/apl-profile-schema.md`:

```markdown
# APL Profile Schema

APL profiles use schema version `coa-apl-profile-v1`.

## Purpose

Profiles drive Phase 1 action-priority-list generation from normalized builder data and legal build states. They do not execute rotations, ingest logs, or produce DPS.

## Required Fields

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

## Supported Match Operators

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

## Future Inputs

Profiles may list `combat_log_metrics`, `saved_variables_snapshot`, or `sim_state` in `future_inputs` for compatibility planning. M1.5 profiles must not require those inputs.
```

- [ ] **Step 4: Add generated APL schema doc**

Create `docs/data/apl-schema.md`:

```markdown
# Generated APL Schema

Generated APL documents use schema version `coa-apl-v1`.

## Purpose

Generated APL documents are editable Phase 1 rotation scaffolds. They are canonical structured data. SimC-like text is an export format.

## Required Fields

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

## Action Fields

- `action_key`
- `action_name`
- `node_id`
- `spell_id`
- `category`
- `condition`
- `priority`
- `confidence`
- `notes`
- `evidence`

## Source Label

M1.5 uses `source: theorycraft`. Generated APLs must not be labeled as simulated or empirical.
```

- [ ] **Step 5: Run full Python verification**

Run:

```bash
python -m pytest -q
```

Expected: PASS with all tests passing.

- [ ] **Step 6: Run documentation placeholder scan**

Run:

```bash
python -c 'from pathlib import Path; pats=["T"+"BD","TO"+"DO","implement "+"later","fill in "+"details"]; paths=[Path("docs/superpowers/plans/2026-07-04-m1-5-rotation-apl-scaffold.md"),Path("docs/superpowers/specs/2026-07-04-m1-5-rotation-apl-scaffold-design.md"),Path("docs/data/apl-profile-schema.md"),Path("docs/data/apl-schema.md")]; hits=[(str(p),pat) for p in paths if p.exists() for pat in pats if pat in p.read_text(encoding="utf-8")]; print(hits); raise SystemExit(1 if hits else 0)'
```

Expected: no matches.

- [ ] **Step 7: Check git status**

Run:

```bash
git status --short
```

Expected: only intentional M1.5 files are modified or untracked before the final commit. Pre-existing staged M1.4 docs may still be staged if they were not committed before M1.5 implementation began.

- [ ] **Step 8: Commit docs**

Run:

```bash
git add docs/MODULES.md docs/DECISIONS.md docs/data/apl-profile-schema.md docs/data/apl-schema.md
git commit -m "docs: document APL profile schemas"
```

- [ ] **Step 9: Commit completion checkpoint if needed**

If Task 7 Step 7 shows only already-committed changes plus pre-existing staged M1.4 docs, no completion commit is needed. If any M1.5 source or test file remains modified, commit those exact paths with:

```bash
git add coa_meta/apl.py coa_meta/apl_profiles.py coa_meta/data/apl_profiles tests/test_apl_profiles.py tests/test_apl_exports.py tests/test_apl_generation.py tests/test_apl_stalker_regression.py tests/test_apl_compatibility.py tests/fixtures/apl_build_fixture.jsonl coa_optimizer_extensible.py
git commit -m "chore: complete M1.5 APL scaffold"
```

## Plan Self-Review

Spec coverage:

- Structured `coa-apl-v1` output is implemented in Tasks 3 and 4.
- `coa-apl-profile-v1` loading and validation DSL are implemented in Tasks 1 and 2.
- Single-target and AoE independent branches are implemented in Task 4.
- SimC-like export is implemented in Task 3.
- Compatibility wiring is implemented in Task 6.
- Stalker semantic tolerance is implemented in Task 5.
- Documentation requirements are implemented in Task 7.

Placeholder scan:

- This plan intentionally contains no unresolved placeholder markers and no missing code-content steps.

Type consistency:

- Profile loader exposes `APLProfile`, `APLRuleProfile`, `APLBranchProfile`, `APLResource`, `load_builtin_apl_profile`, `load_apl_profile_by_role`, and `validate_apl_profile_data`.
- APL generator exposes `APLAction`, `APLDocument`, `generate_apl`, `apl_to_simc_lines`, and `slugify_action`.
- Compatibility helper uses the package `TalentRepository`, `BuildRules`, and `SelectedRank` under aliased names to avoid collisions with prototype classes.
