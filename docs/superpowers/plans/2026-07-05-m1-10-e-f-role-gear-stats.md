# M1.10E/F Role Taxonomy and Gear/Stats Presentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Commit after each completed task.

**Goal:** Add five player-facing guide roles with provenance, then upgrade stat and gear output into honest, grouped guide sections.

**Architecture:** Introduce a dedicated role-resolution module that produces `melee_dps`, `caster_dps`, `tank`, `healer`, or `support` plus an explicit broad `engine_role` for existing scoring/APL profiles. Keep current `dps`, `tank`, and `healer_support` profiles working. Add v2 stat and gear report payloads that guide rendering can prefer while preserving old fields during migration.

**Tech Stack:** Python 3.14 stdlib, dataclasses, existing `coa_meta` package, JSON/JSONL artifacts, pytest, static HTML/CSS/JavaScript, no frontend build step.

---

## File Structure

Create:

- `coa_meta/roles.py`: player-facing role taxonomy, broad engine-role bridge, curated override loader, inference scores, `RoleResolution`.
- `coa_meta/data/role_overrides.json`: curated role mappings with provenance.
- `tests/test_roles.py`: role taxonomy, override, inference, and compatibility tests.

Modify:

- `coa_meta/reporting.py`: use `RoleResolution`, expose `role`, `engine_role`, and `role_provenance`, route scoring/APL/stat/gear through engine role where needed.
- `coa_meta/cli.py`: accept new role values plus backward aliases.
- `coa_meta/stats.py`: add five-role weights and v2 grouped stat priority report helpers.
- `coa_meta/gear.py`: add v2 best-vs-available gear recommendation helpers.
- `coa_meta/guide_models.py`: add guide role provenance, grouped stat priority, and gear recommendation report fields consumed by the renderer.
- `coa_meta/guide_builder.py`: map role provenance and v2 stat/gear payloads into guide specs/build cards.
- `coa_meta/guide_rendering.py`: render five-role filters, role provenance tooltip, grouped stats, and best-vs-available gear sections.
- `docs/data/meta-report-schema.md`: document `engine_role`, `role_provenance`, `coa-stat-priority-v2`, and `coa-gear-recommendation-v2`.
- `docs/README.md` and `docs/ROADMAP.md`: update M1.10E/F status after implementation.

Do not modify:

- Scraper normalization or DB enrichment.
- Existing broad scoring/APL profile schemas beyond adding optional future data.
- Generated `reports/` output in git.

---

## Task 1: Role Taxonomy Module

**Files:**

- Create: `coa_meta/roles.py`
- Create: `coa_meta/data/role_overrides.json`
- Create: `tests/test_roles.py`

- [ ] **Step 1: Add failing role tests**

Create `tests/test_roles.py`:

```python
from __future__ import annotations

from pathlib import Path

from coa_meta.repository import TalentRepository
from coa_meta.roles import (
    GUIDE_ROLES,
    RoleResolution,
    engine_role_for_guide_role,
    resolve_spec_role,
)
from coa_meta.reporting import BuildScope


FIXTURES = Path(__file__).parent / "fixtures"


def test_engine_role_bridge_preserves_existing_profile_roles():
    assert GUIDE_ROLES == ("melee_dps", "caster_dps", "tank", "healer", "support")
    assert engine_role_for_guide_role("melee_dps") == "dps"
    assert engine_role_for_guide_role("caster_dps") == "dps"
    assert engine_role_for_guide_role("tank") == "tank"
    assert engine_role_for_guide_role("healer") == "healer_support"
    assert engine_role_for_guide_role("support") == "healer_support"


def test_role_resolution_serializes_provenance():
    resolution = RoleResolution(
        role="caster_dps",
        engine_role="dps",
        source="inferred",
        confidence="medium",
        evidence=("spell_text:3",),
        scores={"caster_dps": 8.0, "melee_dps": 2.0},
    )

    payload = resolution.to_dict()

    assert payload["schema_version"] == "coa-role-resolution-v1"
    assert payload["role"] == "caster_dps"
    assert payload["engine_role"] == "dps"
    assert payload["evidence"] == ["spell_text:3"]


def test_curated_override_wins_for_fixture_support_spec():
    repo = TalentRepository.from_entries(FIXTURES / "meta_report_fixture.jsonl")
    scope = BuildScope(
        class_name="Testclass",
        spec_id=12,
        spec_name="Support",
        level=60,
        encounter_profile_id="baseline_single_target",
        search_profile_id="default",
        scoring_profile_id="auto",
        apl_profile_id="auto",
        top=1,
    )

    resolution = resolve_spec_role(repo, scope)

    assert resolution.role == "healer"
    assert resolution.engine_role == "healer_support"
    assert resolution.source == "curated"
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m pytest tests/test_roles.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'coa_meta.roles'`.

- [ ] **Step 3: Add curated override data**

Create `coa_meta/data/role_overrides.json`:

```json
{
  "schema_version": "coa-role-overrides-v1",
  "overrides": [
    {"class_name": "Testclass", "spec_name": "Support", "role": "healer", "confidence": "high", "evidence": ["fixture support spec"]},
    {"spec_key": "black_knight", "role": "tank", "confidence": "high", "evidence": ["curated tank spec key"]},
    {"spec_key": "defiance", "role": "tank", "confidence": "high", "evidence": ["curated tank spec key"]},
    {"spec_key": "dreadnought", "role": "tank", "confidence": "high", "evidence": ["curated tank spec key"]},
    {"spec_key": "fortitude", "role": "tank", "confidence": "medium", "evidence": ["curated tank-leaning spec key"]},
    {"spec_key": "moon_guard", "role": "tank", "confidence": "high", "evidence": ["curated tank spec key"]},
    {"spec_key": "mountain_king", "role": "tank", "confidence": "high", "evidence": ["curated tank spec key"]},
    {"spec_key": "oathkeeper", "role": "tank", "confidence": "high", "evidence": ["curated tank spec key"]},
    {"spec_key": "seraphim", "role": "tank", "confidence": "high", "evidence": ["curated tank spec key"]},
    {"spec_key": "vanguard", "role": "tank", "confidence": "high", "evidence": ["curated tank spec key"]},
    {"spec_key": "blessings", "role": "healer", "confidence": "high", "evidence": ["curated healer spec key"]},
    {"spec_key": "brewing", "role": "healer", "confidence": "high", "evidence": ["curated healer spec key"]},
    {"spec_key": "fleshweaver", "role": "healer", "confidence": "high", "evidence": ["curated healer spec key"]},
    {"spec_key": "flameweaving", "role": "healer", "confidence": "high", "evidence": ["curated healer spec key"]},
    {"spec_key": "invention", "role": "healer", "confidence": "high", "evidence": ["curated healer spec key"]},
    {"spec_key": "life", "role": "healer", "confidence": "high", "evidence": ["curated healer spec key"]},
    {"spec_key": "moon_priest", "role": "healer", "confidence": "high", "evidence": ["curated healer spec key"]},
    {"spec_key": "time", "role": "healer", "confidence": "medium", "evidence": ["curated healer spec key"]},
    {"spec_key": "vizier", "role": "healer", "confidence": "high", "evidence": ["curated healer spec key"]},
    {"spec_key": "voodoo", "role": "support", "confidence": "medium", "evidence": ["curated support-leaning spec key"]},
    {"spec_key": "inspiration", "role": "support", "confidence": "medium", "evidence": ["curated support-leaning spec key"]},
    {"spec_key": "artificer", "role": "support", "confidence": "medium", "evidence": ["curated support-leaning spec key"]},
    {"spec_key": "heretic", "role": "healer", "confidence": "medium", "evidence": ["curated healer/support hybrid key"]},
    {"spec_key": "piety", "role": "caster_dps", "confidence": "medium", "evidence": ["curated holy caster damage key"]},
    {"spec_key": "stalking", "role": "melee_dps", "confidence": "high", "evidence": ["curated Venomancer Stalking damage key"]}
  ]
}
```

- [ ] **Step 4: Implement `coa_meta/roles.py`**

Create `coa_meta/roles.py`:

```python
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .domain import TalentNode
from .repository import TalentRepository

GuideRole = Literal["melee_dps", "caster_dps", "tank", "healer", "support"]
EngineRole = Literal["dps", "tank", "healer_support"]

GUIDE_ROLES: tuple[GuideRole, ...] = ("melee_dps", "caster_dps", "tank", "healer", "support")
ENGINE_ROLES: tuple[EngineRole, ...] = ("dps", "tank", "healer_support")
ROLE_OVERRIDE_PATH = Path(__file__).parent / "data" / "role_overrides.json"


@dataclass(frozen=True)
class RoleResolution:
    role: GuideRole
    engine_role: EngineRole
    source: str
    confidence: str
    evidence: tuple[str, ...]
    scores: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "coa-role-resolution-v1",
            "role": self.role,
            "engine_role": self.engine_role,
            "source": self.source,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "scores": dict(sorted(self.scores.items())),
        }


def engine_role_for_guide_role(role: str) -> EngineRole:
    if role in {"melee_dps", "caster_dps"}:
        return "dps"
    if role == "tank":
        return "tank"
    if role in {"healer", "support"}:
        return "healer_support"
    if role == "dps":
        return "dps"
    if role == "healer_support":
        return "healer_support"
    raise ValueError(f"Unsupported guide role {role!r}")


def resolve_configured_role(configured_role: str, inferred: RoleResolution) -> RoleResolution:
    if configured_role == "auto":
        return inferred
    if configured_role == "dps":
        if inferred.role in {"melee_dps", "caster_dps"}:
            return inferred
        return _configured("melee_dps", "configured broad dps fallback")
    if configured_role == "healer_support":
        if inferred.role in {"healer", "support"}:
            return inferred
        return _configured("healer", "configured broad healer_support fallback")
    if configured_role in GUIDE_ROLES:
        return _configured(configured_role, "configured explicit guide role")
    if configured_role in ENGINE_ROLES:
        return _configured(configured_role, "configured broad engine role")
    raise ValueError(f"Unsupported role {configured_role!r}")


def resolve_spec_role(repository: TalentRepository, scope: Any) -> RoleResolution:
    override = _override_for(scope.class_name, scope.spec_name, scope.spec_key)
    if override:
        role = override["role"]
        return RoleResolution(
            role=role,
            engine_role=engine_role_for_guide_role(role),
            source="curated",
            confidence=str(override.get("confidence") or "medium"),
            evidence=tuple(str(item) for item in override.get("evidence") or []),
            scores={role: 100.0},
        )
    nodes = [
        node for node in repository.nodes_for_class(scope.class_name)
        if node.tab_id == scope.spec_id and node.tab_name == scope.spec_name
    ]
    return infer_role_from_nodes(nodes)


def infer_role_from_nodes(nodes: list[TalentNode]) -> RoleResolution:
    scores = _role_scores(nodes)
    role = max(GUIDE_ROLES, key=lambda item: (scores[item], -GUIDE_ROLES.index(item)))
    if scores["tank"] >= 20 and scores["tank"] >= scores["healer"] - 5:
        role = "tank"
    elif scores["healer"] >= 24 and scores["healer"] >= scores["support"] + 4:
        role = "healer"
    elif scores["support"] >= 22 and scores["support"] > scores["healer"]:
        role = "support"
    elif role in {"tank", "healer", "support"} and scores[role] < 10:
        role = "caster_dps" if scores["caster_dps"] >= scores["melee_dps"] else "melee_dps"
    confidence = "medium" if scores[role] >= 12 else "low"
    evidence = tuple(f"{key}:{value:.1f}" for key, value in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:3])
    return RoleResolution(
        role=role,
        engine_role=engine_role_for_guide_role(role),
        source="inferred",
        confidence=confidence,
        evidence=evidence,
        scores=scores,
    )


def _role_scores(nodes: list[TalentNode]) -> dict[str, float]:
    tags = Counter(tag for node in nodes for tag in node.tags)
    text = " ".join(f"{node.name} {node.description_text}" for node in nodes).lower()
    return {
        "tank": tags["tank"] * 3.0 + _count_text(text, (r"\\btank\\b", r"\\bthreat\\b", r"\\barmor\\b", r"\\bblock\\b", r"\\bparry\\b", r"\\bdodge\\b", r"damage taken")),
        "healer": tags["heal"] * 3.0 + tags["hot"] * 3.0 + _count_text(text, (r"\\bheal", r"\\bhealing\\b", r"\\bally\\b", r"\\ballies\\b", r"\\bparty\\b", r"\\braid\\b")),
        "support": tags["aura"] * 3.0 + tags["crowd_control"] * 1.5 + tags["resource_management"] + _count_text(text, (r"\\baura\\b", r"\\bbuff\\b", r"\\bdebuff\\b", r"\\bgroup\\b", r"\\ballies\\b")),
        "melee_dps": tags["melee"] * 2.0 + tags["builder"] + tags["spender"] + _count_text(text, (r"\\bmelee\\b", r"\\bstrike\\b", r"\\bfang\\b", r"\\bblade\\b")),
        "caster_dps": tags["ranged"] * 1.5 + tags["dot"] * 1.5 + tags["proc"] + _count_text(text, (r"\\bspell\\b", r"\\bcast\\b", r"\\bshadow\\b", r"\\bnature\\b", r"\\bfire\\b", r"\\bfrost\\b", r"\\barcane\\b")),
    }


def _count_text(text: str, patterns: tuple[str, ...]) -> float:
    return float(sum(len(re.findall(pattern, text)) for pattern in patterns))


def _configured(role: str, evidence: str) -> RoleResolution:
    guide_role = {
        "dps": "melee_dps",
        "healer_support": "healer",
        "tank": "tank",
    }.get(role, role)
    return RoleResolution(
        role=guide_role,
        engine_role=engine_role_for_guide_role(guide_role),
        source="configured",
        confidence="high",
        evidence=(evidence,),
        scores={guide_role: 100.0},
    )


def _override_for(class_name: str, spec_name: str, spec_key: str) -> dict[str, Any] | None:
    data = _load_overrides()
    for override in data:
        if override.get("class_name") == class_name and override.get("spec_name") == spec_name:
            return override
    for override in data:
        if override.get("spec_key") == spec_key:
            return override
    return None


def _load_overrides() -> tuple[dict[str, Any], ...]:
    if not ROLE_OVERRIDE_PATH.exists():
        return tuple()
    data = json.loads(ROLE_OVERRIDE_PATH.read_text(encoding="utf-8"))
    return tuple(dict(item) for item in data.get("overrides", []))
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
python -m pytest tests/test_roles.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add coa_meta/roles.py coa_meta/data/role_overrides.json tests/test_roles.py
git commit -m "feat: add guide role taxonomy"
```

---

## Task 2: Integrate Guide Roles Into Reporting and CLI

**Files:**

- Modify: `coa_meta/reporting.py`
- Modify: `coa_meta/cli.py`
- Modify: `tests/test_meta_report_runner.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add failing report tests**

Add to `tests/test_meta_report_runner.py`:

```python
def test_meta_report_exposes_guide_role_engine_role_and_provenance():
    config = MetaRunConfig(
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        classes_path=FIXTURES / "meta_classes.json",
        class_names=("Testclass",),
        top=1,
        beam_width=2,
        branch_width=2,
        require_budget_fraction=0.0,
    )

    report = MetaReportRunner(config).run()
    by_spec = {result.spec_name: result.to_dict() for result in report.spec_results}

    assert by_spec["Damage"]["role"] in {"melee_dps", "caster_dps"}
    assert by_spec["Damage"]["engine_role"] == "dps"
    assert by_spec["Support"]["role"] == "healer"
    assert by_spec["Support"]["engine_role"] == "healer_support"
    assert by_spec["Support"]["role_provenance"]["source"] == "curated"
    assert by_spec["Support"]["top_builds"][0]["provenance"]["engine_role"] == "healer_support"
```

- [ ] **Step 2: Add failing CLI role option test**

Add to `tests/test_cli.py`:

```python
def test_meta_cli_accepts_new_guide_role_values(monkeypatch, tmp_path):
    calls = {}

    class DummyRunner:
        def __init__(self, config):
            calls["config"] = config

        def run(self):
            return None

    monkeypatch.setattr("coa_meta.cli.MetaReportRunner", DummyRunner)
    monkeypatch.setattr("coa_meta.cli.write_report_outputs", lambda *args, **kwargs: tuple())

    from coa_meta.cli import main

    main([
        "meta",
        "--entries", str(tmp_path / "entries.jsonl"),
        "--role", "caster_dps",
        "--format", "json",
        "--out", str(tmp_path / "out"),
    ])

    assert calls["config"].role == "caster_dps"
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
python -m pytest tests/test_meta_report_runner.py tests/test_cli.py -q
```

Expected: fail because `SpecResult` has no `engine_role` or `role_provenance`, and CLI choices do not include `caster_dps`.

- [ ] **Step 4: Modify `reporting.py` imports and supported roles**

Add imports:

```python
from .roles import GUIDE_ROLES, ENGINE_ROLES, RoleResolution, resolve_configured_role, resolve_spec_role
```

Replace `SUPPORTED_META_ROLES` with:

```python
SUPPORTED_META_ROLES = {"auto", *GUIDE_ROLES, *ENGINE_ROLES}
```

Keep `infer_spec_role()` and `resolve_scope_role()` as compatibility wrappers for tests or external callers:

```python
def infer_spec_role(repository: TalentRepository, scope: BuildScope) -> str:
    return resolve_spec_role(repository, scope).engine_role


def resolve_scope_role(repository: TalentRepository, scope: BuildScope, configured_role: str) -> str:
    return resolve_scope_role_detail(repository, scope, configured_role).engine_role


def resolve_scope_role_detail(repository: TalentRepository, scope: BuildScope, configured_role: str) -> RoleResolution:
    if configured_role not in SUPPORTED_META_ROLES:
        raise ValueError(f"Unsupported role {configured_role!r}; expected one of {sorted(SUPPORTED_META_ROLES)}")
    inferred = resolve_spec_role(repository, scope)
    return resolve_configured_role(configured_role, inferred)
```

- [ ] **Step 5: Extend `SpecResult`**

Add fields:

```python
engine_role: str
role_provenance: dict[str, Any]
```

Update `to_dict()`:

```python
"engine_role": self.engine_role,
"role_provenance": self.role_provenance,
```

- [ ] **Step 6: Use role details in `_run_scope`**

Replace:

```python
role = resolve_scope_role(repository, scope, self.config.role)
```

with:

```python
role_resolution = resolve_scope_role_detail(repository, scope, self.config.role)
role = role_resolution.role
engine_role = role_resolution.engine_role
```

Use `engine_role` for:

- `load_profile_by_role(...)`
- `load_apl_profile_by_role(...)`
- `stat_priority_for_role(...)` until Task 3 adds guide-role stat reports
- `recommend_weapon_and_armor(...)` until Task 4 adds guide-role gear reports
- simulation/APL broad role profile compatibility

Use `role` for:

- `SpecResult.role`
- player-facing summaries
- build provenance field `role`
- `build_playstyle_fingerprint(...)`
- `build_rotation_loop(...)`

Add build provenance:

```python
"role": role,
"engine_role": engine_role,
"role_provenance": role_resolution.to_dict(),
```

Return `SpecResult(..., engine_role=engine_role, role_provenance=role_resolution.to_dict(), ...)`.

- [ ] **Step 7: Update assumptions and summary helper**

Change report assumption text to:

```python
"Auto role inference resolves player-facing roles and maps them to broad scoring/APL profiles.",
```

Update `_summary_strengths()` so:

```python
if role == "tank": ...
if role == "healer": ...
if role == "support": ...
if role == "caster_dps": ...
return ["Prioritizes melee damage, resource, cooldown, and proc features from normalized tags."]
```

- [ ] **Step 8: Run focused tests**

Run:

```bash
python -m pytest tests/test_roles.py tests/test_meta_report_runner.py tests/test_cli.py -q
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add coa_meta/reporting.py coa_meta/cli.py tests/test_meta_report_runner.py tests/test_cli.py
git commit -m "feat: expose guide role provenance"
```

---

## Task 3: Grouped Stat Priority Payloads

**Files:**

- Modify: `coa_meta/stats.py`
- Modify: `coa_meta/reporting.py`
- Modify: `tests/test_stats.py`
- Modify: `tests/test_meta_report_runner.py`

- [ ] **Step 1: Add failing stat report tests**

Add to `tests/test_stats.py`:

```python
from coa_meta.stats import stat_priority_report_for_role


def test_stat_priority_report_groups_stats_and_has_one_disclaimer():
    report = stat_priority_report_for_role("caster_dps", engine_role="dps")
    payload = report.to_dict()

    assert payload["schema_version"] == "coa-stat-priority-v2"
    assert payload["role"] == "caster_dps"
    assert payload["engine_role"] == "dps"
    assert "simulations or combat logs" in payload["disclaimer"]
    assert [group["group_id"] for group in payload["groups"]] == ["primary", "secondary", "situational"]
    assert payload["groups"][0]["entries"]
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m pytest tests/test_stats.py -q
```

Expected: fail because `stat_priority_report_for_role` does not exist.

- [ ] **Step 3: Add dataclasses to `stats.py`**

Add:

```python
@dataclass(frozen=True)
class StatPriorityGroup:
    group_id: str
    label: str
    entries: tuple[StatPriority, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"group_id": self.group_id, "label": self.label, "entries": [entry.to_dict() for entry in self.entries]}


@dataclass(frozen=True)
class StatPriorityReport:
    role: str
    engine_role: str
    disclaimer: str
    source: str
    confidence: str
    groups: tuple[StatPriorityGroup, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "coa-stat-priority-v2",
            "role": self.role,
            "engine_role": self.engine_role,
            "disclaimer": self.disclaimer,
            "source": self.source,
            "confidence": self.confidence,
            "groups": [group.to_dict() for group in self.groups],
            "warnings": list(self.warnings),
        }
```

- [ ] **Step 4: Add five-role stat weights**

Add:

```python
GUIDE_ROLE_STAT_WEIGHTS = {
    "melee_dps": {"attack_power": 3.0, "strength": 2.2, "agility": 2.0, "hit_rating": 1.5, "expertise_rating": 1.3, "crit_rating": 1.2, "haste_rating": 1.0, "stamina": 0.2},
    "caster_dps": {"spell_power": 3.0, "intellect": 2.0, "hit_rating": 1.6, "haste_rating": 1.3, "crit_rating": 1.1, "spirit": 0.4, "stamina": 0.2},
    "tank": ROLE_STAT_WEIGHTS["tank"],
    "healer": {"spell_power": 3.0, "intellect": 2.4, "spirit": 1.8, "haste_rating": 1.3, "crit_rating": 1.0, "stamina": 0.4},
    "support": {"spell_power": 2.4, "intellect": 2.0, "spirit": 1.2, "haste_rating": 1.2, "crit_rating": 0.9, "attack_power": 0.8, "stamina": 0.4},
}
```

- [ ] **Step 5: Add report helper**

Add:

```python
STAT_DISCLAIMER = "Stat priorities are early theorycraft until simulations or combat logs are available."


def stat_priority_report_for_role(role: str, *, engine_role: str) -> StatPriorityReport:
    weights = GUIDE_ROLE_STAT_WEIGHTS.get(role) or ROLE_STAT_WEIGHTS.get(engine_role)
    if not weights:
        raise ValueError(f"Unsupported role {role!r}")
    entries = tuple(
        StatPriority(
            stat=stat,
            weight=weight,
            confidence="medium" if role in GUIDE_ROLE_STAT_WEIGHTS else "low",
            reason=f"Generic {role} priority from role heuristics; pending simulator/log calibration.",
        )
        for stat, weight in sorted(weights.items(), key=lambda item: (-item[1], item[0]))
    )
    primary = entries[:3]
    secondary = entries[3:7]
    situational = entries[7:]
    return StatPriorityReport(
        role=role,
        engine_role=engine_role,
        disclaimer=STAT_DISCLAIMER,
        source="heuristic",
        confidence="medium",
        groups=(
            StatPriorityGroup("primary", "Best stats to target", primary),
            StatPriorityGroup("secondary", "Good supporting stats", secondary),
            StatPriorityGroup("situational", "Situational stats", situational),
        ),
        warnings=("stat_priority_not_simulated",),
    )
```

- [ ] **Step 6: Attach v2 payload in report runner**

In `reporting.py`, import `stat_priority_report_for_role`.

In `_run_scope`, keep old list:

```python
stat_priority = tuple(priority.to_dict() for priority in stat_priority_for_role(engine_role))
stat_priority_report = stat_priority_report_for_role(role, engine_role=engine_role).to_dict()
```

Add `stat_priority_report: dict[str, Any]` to `BuildReport` and `to_dict()`.

- [ ] **Step 7: Add report-runner assertion**

In `tests/test_meta_report_runner.py`, extend the role test:

```python
build = by_spec["Support"]["top_builds"][0]
assert build["stat_priority_report"]["schema_version"] == "coa-stat-priority-v2"
assert build["stat_priority_report"]["role"] == "healer"
```

- [ ] **Step 8: Run tests**

Run:

```bash
python -m pytest tests/test_stats.py tests/test_meta_report_runner.py -q
```

Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add coa_meta/stats.py coa_meta/reporting.py tests/test_stats.py tests/test_meta_report_runner.py
git commit -m "feat: add grouped stat priorities"
```

---

## Task 4: Best-vs-Available Gear Payloads

**Files:**

- Modify: `coa_meta/gear.py`
- Modify: `coa_meta/reporting.py`
- Modify: `tests/test_gear.py`
- Modify: `tests/test_meta_report_runner.py`

- [ ] **Step 1: Add failing gear report tests**

Add to `tests/test_gear.py`:

```python
from coa_meta.gear import recommend_gear_for_guide_role


def test_guide_gear_recommendation_splits_best_and_available():
    payload = recommend_gear_for_guide_role("tank", engine_role="tank", items=tuple()).to_dict()

    assert payload["schema_version"] == "coa-gear-recommendation-v2"
    assert payload["role"] == "tank"
    assert payload["best_weapon_types"]
    assert payload["available_weapon_types"]
    assert "item_data_missing" in payload["warnings"]
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m pytest tests/test_gear.py -q
```

Expected: fail because `recommend_gear_for_guide_role` does not exist.

- [ ] **Step 3: Add `GearRecommendationReport`**

In `gear.py`, add:

```python
@dataclass(frozen=True)
class GearRecommendationReport:
    role: str
    engine_role: str
    best_weapon_types: tuple[str, ...]
    best_armor_types: tuple[str, ...]
    available_weapon_types: tuple[str, ...]
    available_armor_types: tuple[str, ...]
    item_scores: tuple[ItemScore, ...]
    source: str
    confidence: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "coa-gear-recommendation-v2",
            "role": self.role,
            "engine_role": self.engine_role,
            "best_weapon_types": list(self.best_weapon_types),
            "best_armor_types": list(self.best_armor_types),
            "available_weapon_types": list(self.available_weapon_types),
            "available_armor_types": list(self.available_armor_types),
            "item_scores": [score.to_dict() for score in self.item_scores],
            "source": self.source,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
        }
```

- [ ] **Step 4: Add defaults and helper**

Add:

```python
GUIDE_ROLE_GEAR_DEFAULTS = {
    "melee_dps": {"best_weapon_types": ("sword", "axe", "dagger", "mace"), "best_armor_types": ("leather", "mail"), "available_weapon_types": ("sword", "axe", "dagger", "mace", "staff"), "available_armor_types": ("cloth", "leather", "mail", "plate")},
    "caster_dps": {"best_weapon_types": ("staff", "dagger", "mace"), "best_armor_types": ("cloth", "leather"), "available_weapon_types": ("staff", "dagger", "mace", "sword"), "available_armor_types": ("cloth", "leather", "mail")},
    "tank": {"best_weapon_types": ("shield", "sword", "mace", "axe"), "best_armor_types": ("plate", "mail"), "available_weapon_types": ("shield", "sword", "mace", "axe"), "available_armor_types": ("plate", "mail", "leather")},
    "healer": {"best_weapon_types": ("staff", "mace", "dagger"), "best_armor_types": ("cloth", "leather", "mail"), "available_weapon_types": ("staff", "mace", "dagger", "sword"), "available_armor_types": ("cloth", "leather", "mail")},
    "support": {"best_weapon_types": ("staff", "mace", "dagger", "sword"), "best_armor_types": ("cloth", "leather", "mail"), "available_weapon_types": ("staff", "mace", "dagger", "sword", "axe"), "available_armor_types": ("cloth", "leather", "mail", "plate")},
}
```

Add:

```python
def recommend_gear_for_guide_role(role: str, *, engine_role: str, items: tuple[ItemRecord, ...]) -> GearRecommendationReport:
    defaults = GUIDE_ROLE_GEAR_DEFAULTS.get(role)
    if defaults is None:
        raise GearLoadError(f"Unsupported guide role {role!r}")
    warnings: list[str] = []
    scores: tuple[ItemScore, ...] = tuple()
    source = "defaults"
    confidence = "low"
    if items:
        scores = rank_items_for_role(engine_role, items)
        source = "mixed"
        confidence = "medium"
        if any(item.confidence == "low" for item in items):
            warnings.append("item_data_low_confidence")
    else:
        warnings.extend(("item_data_missing", "gear_targets_from_role_defaults"))
    available_weapon_types = tuple(sorted({item.weapon_type for item in items if item.weapon_type})) or tuple(defaults["available_weapon_types"])
    available_armor_types = tuple(sorted({item.armor_type for item in items if item.armor_type})) or tuple(defaults["available_armor_types"])
    return GearRecommendationReport(
        role=role,
        engine_role=engine_role,
        best_weapon_types=tuple(defaults["best_weapon_types"]),
        best_armor_types=tuple(defaults["best_armor_types"]),
        available_weapon_types=available_weapon_types,
        available_armor_types=available_armor_types,
        item_scores=scores[:10],
        source=source,
        confidence=confidence,
        warnings=tuple(warnings),
    )
```

- [ ] **Step 5: Attach v2 payload in report runner**

In `reporting.py`, import `recommend_gear_for_guide_role`.

In `_run_scope`, keep old v1 recommendation and add:

```python
gear_recommendation = recommend_weapon_and_armor(engine_role, tuple())
gear_recommendation_report = recommend_gear_for_guide_role(role, engine_role=engine_role, items=tuple()).to_dict()
```

Add `gear_recommendation_report: dict[str, Any]` to `BuildReport` and `to_dict()`.

- [ ] **Step 6: Add report-runner assertion**

In `tests/test_meta_report_runner.py`:

```python
assert build["gear_recommendation_report"]["schema_version"] == "coa-gear-recommendation-v2"
assert build["gear_recommendation_report"]["role"] == "healer"
assert "best_weapon_types" in build["gear_recommendation_report"]
```

- [ ] **Step 7: Run tests**

Run:

```bash
python -m pytest tests/test_gear.py tests/test_meta_report_runner.py -q
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add coa_meta/gear.py coa_meta/reporting.py tests/test_gear.py tests/test_meta_report_runner.py
git commit -m "feat: add guide gear recommendations"
```

---

## Task 5: Render Role Provenance, Grouped Stats, and Gear Sections

**Files:**

- Modify: `coa_meta/guide_models.py`
- Modify: `coa_meta/guide_builder.py`
- Modify: `coa_meta/guide_rendering.py`
- Modify: `tests/test_guide_builder.py`
- Modify: `tests/test_guide_rendering.py`
- Modify: `tests/test_report_writers.py`

- [ ] **Step 1: Add failing guide tests**

Add to `tests/test_guide_builder.py`:

```python
def test_guide_specs_include_role_provenance():
    site = build_guide_site(_report(), entries_path=FIXTURES / "meta_report_fixture.jsonl")
    support = next(spec for spec in site.specs if spec.spec_name == "Support")

    assert support.role == "healer"
    assert support.role_provenance["source"] == "curated"
```

Add to `tests/test_guide_rendering.py`:

```python
def test_spec_html_renders_grouped_stats_and_best_gear_targets():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")

    html = render_spec_html(site, spec)

    assert "Best stats to target" in html
    assert "Stat priorities are early theorycraft" in html
    assert "Best targets for this spec" in html
    assert "Available to this class" in html
```

- [ ] **Step 2: Run guide tests to verify RED**

Run:

```bash
python -m pytest tests/test_guide_builder.py tests/test_guide_rendering.py -q
```

Expected: fail because `GuideSpec` lacks role provenance and rendering still uses old stat/gear sections.

- [ ] **Step 3: Extend guide models**

Add to `GuideSpec`:

```python
role_provenance: dict[str, Any] | None = None
```

Update `to_dict()`:

```python
"role_provenance": dict(self.role_provenance or {}),
```

Add to `GuideBuildCard`:

```python
stat_priority_report: dict[str, Any] | None = None
gear_recommendation_report: dict[str, Any] | None = None
```

Update `to_dict()`.

- [ ] **Step 4: Map report payloads in guide builder**

In `build_guide_site()`:

```python
role_provenance=result.get("role_provenance") or {},
```

In `_build_cards()`:

```python
stat_priority_report=dict(build.get("stat_priority_report") or {}),
gear_recommendation_report=dict(build.get("gear_recommendation_report") or {}),
```

- [ ] **Step 5: Render role provenance tooltip**

In `render_spec_html()`, add a role chip with `data-tooltip-id="role:<slug>"`.

In `_tooltip_script()`, add role provenance tooltip payloads:

```python
payload[f"role:{spec.slug}"] = {
    "html": "<strong>Role Source</strong><div>...</div>",
    "text": "...",
}
```

- [ ] **Step 6: Render grouped stats**

Replace the static stats section with `_render_stats_section(spec)`.

Implementation behavior:

- Use first build's `stat_priority_report`.
- Render disclaimer once in a warning panel.
- Render each group with heading and stat chips.
- Fall back to current list if v2 payload is absent.

- [ ] **Step 7: Render best-vs-available gear**

Replace the static weapons/armor section with `_render_gear_section(spec)`.

Implementation behavior:

- Use first build's `gear_recommendation_report`.
- Render "Best targets for this spec" first.
- Render "Available to this class" second.
- Render warnings only when present.
- Use typed chips for weapon/armor types.

- [ ] **Step 8: Update legacy report writer tests**

Change `render_spec_guide_html()` in `reporting.py` so HTML spec-page generation uses the guide renderer where possible. If the compatibility path must remain separate, update it to prefer v2 stat/gear payloads.

Implementation order:

- First try to make `write_report_outputs()` use the guide renderer for HTML spec pages.
- If that creates a large report-writer refactor, update `render_spec_guide_html()` directly and keep the delegation as a later cleanup.

Add an assertion in `tests/test_report_writers.py`:

```python
assert "Best targets for this spec" in html
assert "Best stats to target" in html
```

- [ ] **Step 9: Run guide/report tests**

Run:

```bash
python -m pytest tests/test_guide_builder.py tests/test_guide_rendering.py tests/test_report_writers.py -q
```

Expected: pass.

- [ ] **Step 10: Commit**

```bash
git add coa_meta/guide_models.py coa_meta/guide_builder.py coa_meta/guide_rendering.py tests/test_guide_builder.py tests/test_guide_rendering.py tests/test_report_writers.py
git commit -m "feat: render role-aware stats and gear"
```

---

## Task 6: Schema Docs, Smoke Test, and Status Update

**Files:**

- Modify: `docs/data/meta-report-schema.md`
- Modify: `docs/README.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-07-05-m1-10-guide-site-report-ux-design.md`

- [ ] **Step 1: Update schema docs**

In `docs/data/meta-report-schema.md`, document:

- `engine_role`
- `role_provenance`
- `stat_priority_report`
- `gear_recommendation_report`
- compatibility status of old `stat_priority` and `gear_recommendation`

- [ ] **Step 2: Run focused suite**

Run:

```bash
python -m pytest tests/test_roles.py tests/test_stats.py tests/test_gear.py tests/test_meta_report_runner.py tests/test_guide_builder.py tests/test_guide_rendering.py tests/test_report_writers.py tests/test_cli.py -q
```

Expected: pass.

- [ ] **Step 3: Run full suite**

Run:

```bash
python -m pytest -q
```

Expected: pass.

- [ ] **Step 4: Generate smoke report**

Run:

```bash
python -m coa_meta meta \
  --entries coa_scraper/dist/coa_entries.jsonl \
  --classes coa_scraper/dist/coa_classes.json \
  --db-tooltips coa_scraper/dist/coa_db_spell_tooltips.jsonl \
  --out reports/meta-m1-10-ef-smoke \
  --format json --format html \
  --class Venomancer \
  --top 3
```

Expected:

- command exits 0
- `reports/meta-m1-10-ef-smoke/meta-report.json` exists
- spec HTML exists under `reports/meta-m1-10-ef-smoke/specs/`

- [ ] **Step 5: Inspect smoke markers**

Run:

```bash
rg -l "coa-role-resolution-v1|coa-stat-priority-v2|coa-gear-recommendation-v2|Best targets for this spec|Best stats to target" reports/meta-m1-10-ef-smoke
```

Expected: JSON and spec HTML files are listed.

Do not stage generated `reports/` output unless the user explicitly requests sample output committed.

- [ ] **Step 6: Update roadmap status**

Update:

- `docs/ROADMAP.md`: M1.10E/F implemented.
- `docs/README.md`: M1.10 A-F implemented; next planning focus is any remaining M1.10 cleanup or P2.
- `docs/superpowers/specs/2026-07-05-m1-10-guide-site-report-ux-design.md`: implementation status.

- [ ] **Step 7: Commit docs**

```bash
git add docs/data/meta-report-schema.md docs/README.md docs/ROADMAP.md docs/superpowers/specs/2026-07-05-m1-10-guide-site-report-ux-design.md
git commit -m "docs: mark m1.10 role gear progress"
```

---

## Manual QA Checklist

- [ ] Guide index role filters show `Melee DPS`, `Caster DPS`, `Tank`, `Healer`, and `Support`.
- [ ] Spec page role chip has provenance tooltip with source, confidence, and evidence.
- [ ] Broad engine roles remain visible in JSON provenance but not as primary player labels.
- [ ] Existing `--role dps` and `--role healer_support` CLI values still work.
- [ ] New `--role melee_dps`, `--role caster_dps`, `--role healer`, and `--role support` values work.
- [ ] Stats section has exactly one disclaimer panel per spec.
- [ ] Gear section shows best targets before available options.
- [ ] Gear/stat warnings are section-level and not repeated on every stat/item chip.
- [ ] No generated report artifacts are staged by default.

## Rollback Plan

If five-role JSON breaks downstream consumers, keep `SpecResult.role` as the broad role for one release and add `guide_role` plus `engine_role`. Preserve the `RoleResolution` module and guide rendering changes.

If gear/stat v2 payloads cause renderer regressions, keep report payload generation and temporarily render the old stat/gear sections with a visible warning. Do not remove the role taxonomy work.
