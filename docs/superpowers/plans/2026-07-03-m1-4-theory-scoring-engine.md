# M1.4 Theory Scoring Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hard-coded Python theory scoring with data-driven scoring profiles that produce projected DPS index, confidence, uncertainty, and explainable score components for legal build states.

**Architecture:** Build on the M1.3 `coa_meta/` package. Add profile JSON files, profile loading, and a `TheoryScorer` that consumes only legal `BuildState` objects and repository nodes.

**Tech Stack:** Python 3.11+ standard library, `pytest`, JSON scoring profiles, M1.3 `coa_meta` package.

---

## File Structure

Create:

- `coa_meta/profiles.py`: scoring profile loader, defaults, and validation.
- `coa_meta/scoring.py`: scoring data classes and `TheoryScorer`.
- `coa_meta/data/scoring_profiles/generic_dps.json`: generic DPS profile.
- `coa_meta/data/scoring_profiles/generic_tank.json`: generic tank profile.
- `coa_meta/data/scoring_profiles/generic_healer_support.json`: generic healer/support profile.
- `coa_meta/data/scoring_profiles/venomancer_stalker.json`: curated Stalker Venomancer profile.
- `tests/test_scoring_profiles.py`: profile loading tests.
- `tests/test_scoring_engine.py`: theory scoring tests.
- `docs/data/scoring-profile-schema.md`: scoring profile documentation.

Modify:

- `coa_meta/explain.py`: include scoring explanations.
- `docs/DECISIONS.md`: add rank-spending and projected-index decisions.
- `docs/MODULES.md`: mark M1.4 implementation files.

---

### Task 1: Scoring Profile Red Tests

**Files:**

- Create: `tests/test_scoring_profiles.py`

- [ ] **Step 1: Write failing profile tests**

Create `tests/test_scoring_profiles.py`:

```python
import pytest

from coa_meta.profiles import ProfileLoadError, load_builtin_profile, load_profile_by_role


def test_loads_builtin_stalker_profile_from_json():
    profile = load_builtin_profile("venomancer_stalker", encounter="single_target")

    assert profile.profile_id == "venomancer_stalker"
    assert profile.class_name == "Venomancer"
    assert profile.spec_key == "stalker"
    assert profile.role == "dps"
    assert profile.encounter == "single_target"
    assert profile.baseline_index == 100
    assert profile.weights["tags"]["dot"] > 0


def test_loads_generic_role_profile_when_specific_profile_is_missing():
    profile, warnings = load_profile_by_role(class_name="Unknown", spec_key="unknown", role="dps", encounter="aoe_5")

    assert profile.profile_id == "generic_dps"
    assert warnings == ["specific_profile_missing"]
    assert profile.encounter == "aoe_5"


def test_rejects_unknown_encounter():
    with pytest.raises(ProfileLoadError, match="encounter"):
        load_builtin_profile("generic_dps", encounter="unknown")
```

- [ ] **Step 2: Run red profile tests**

Run:

```bash
pytest tests/test_scoring_profiles.py -q
```

Expected: fails because `coa_meta.profiles` does not exist.

---

### Task 2: Add JSON Scoring Profiles

**Files:**

- Create: `coa_meta/data/scoring_profiles/generic_dps.json`
- Create: `coa_meta/data/scoring_profiles/generic_tank.json`
- Create: `coa_meta/data/scoring_profiles/generic_healer_support.json`
- Create: `coa_meta/data/scoring_profiles/venomancer_stalker.json`

- [ ] **Step 1: Create generic DPS profile**

Create `coa_meta/data/scoring_profiles/generic_dps.json`:

```json
{
  "schema_version": "coa-scoring-profile-v1",
  "profile_id": "generic_dps",
  "class_name": "*",
  "spec_key": "generic",
  "role": "dps",
  "supported_encounters": ["single_target", "cleave_2", "aoe_5", "solo"],
  "baseline_index": 100,
  "weights": {
    "tabs": {"Class": 1.0},
    "tags": {"dot": 3.0, "proc": 3.0, "builder": 2.5, "spender": 2.5, "resource_management": 2.0, "cooldown": 2.0, "execute": 2.0, "summon": 1.5, "melee": 0.75, "ranged": 0.75, "aura": 1.0, "mobility": 0.4, "crowd_control": 0.25, "heal": -0.5, "hot": -0.5, "tank": -1.25},
    "schools": {"physical": 0.75, "fire": 0.75, "frost": 0.75, "shadow": 0.75, "holy": 0.75, "nature": 0.75, "arcane": 0.75, "fel": 0.75},
    "resources": {"Energy": 1.0, "Mana": 0.5, "Rage": 0.5, "Insanity": 0.5, "Felfury": 0.5, "Static": 0.5, "Heat": 0.5, "Advantage": 0.5}
  },
  "named_boosts": {},
  "regex_boosts": [
    {"pattern": "\\bcritical strike|critically|critical damage\\b", "weight": 1.25, "reason": "critical scaling"},
    {"pattern": "\\bhaste\\b", "weight": 1.25, "reason": "haste scaling"},
    {"pattern": "\\bcooldown\\b", "weight": 1.0, "reason": "cooldown interaction"},
    {"pattern": "\\bperiodic damage|damage over\\b", "weight": 1.5, "reason": "periodic damage"}
  ],
  "synergies": [],
  "anti_synergies": [],
  "confidence": {"base": "medium"},
  "assumptions": ["Generic DPS profile uses tooltip-derived features only.", "Output is a projected DPS index, not raw DPS."]
}
```

- [ ] **Step 2: Create generic tank profile**

Create `coa_meta/data/scoring_profiles/generic_tank.json`:

```json
{
  "schema_version": "coa-scoring-profile-v1",
  "profile_id": "generic_tank",
  "class_name": "*",
  "spec_key": "generic",
  "role": "tank",
  "supported_encounters": ["single_target", "cleave_2", "aoe_5", "solo"],
  "baseline_index": 100,
  "weights": {
    "tabs": {"Class": 1.0},
    "tags": {"tank": 5.0, "aura": 2.0, "cooldown": 2.5, "heal": 1.5, "hot": 1.0, "mobility": 1.0, "crowd_control": 1.0, "resource_management": 1.5, "dot": 0.5, "proc": 1.0},
    "schools": {},
    "resources": {"Energy": 0.5, "Mana": 0.5, "Rage": 1.0}
  },
  "named_boosts": {},
  "regex_boosts": [
    {"pattern": "\\barmor|block|parry|dodge|threat|damage taken|shield\\b", "weight": 3.0, "reason": "tank survival text"}
  ],
  "synergies": [],
  "anti_synergies": [],
  "confidence": {"base": "medium"},
  "assumptions": ["Generic tank profile values survival and control over damage."]
}
```

- [ ] **Step 3: Create generic healer/support profile**

Create `coa_meta/data/scoring_profiles/generic_healer_support.json`:

```json
{
  "schema_version": "coa-scoring-profile-v1",
  "profile_id": "generic_healer_support",
  "class_name": "*",
  "spec_key": "generic",
  "role": "healer_support",
  "supported_encounters": ["single_target", "cleave_2", "aoe_5", "solo"],
  "baseline_index": 100,
  "weights": {
    "tabs": {"Class": 1.0},
    "tags": {"heal": 5.0, "hot": 4.0, "aura": 3.0, "cooldown": 2.0, "resource_management": 2.0, "crowd_control": 0.75, "tank": 0.5, "dot": -0.25},
    "schools": {"holy": 1.0, "nature": 0.75, "shadow": -0.25},
    "resources": {"Mana": 1.5, "Energy": 0.25}
  },
  "named_boosts": {},
  "regex_boosts": [
    {"pattern": "\\bheal|healing|absorbs?|allies within|party and raid\\b", "weight": 2.5, "reason": "support text"}
  ],
  "synergies": [],
  "anti_synergies": [],
  "confidence": {"base": "medium"},
  "assumptions": ["Generic healer/support profile values healing, absorb, aura, and group utility text."]
}
```

- [ ] **Step 4: Create Stalker Venomancer profile**

Create `coa_meta/data/scoring_profiles/venomancer_stalker.json`:

```json
{
  "schema_version": "coa-scoring-profile-v1",
  "profile_id": "venomancer_stalker",
  "class_name": "Venomancer",
  "spec_key": "stalker",
  "role": "dps",
  "supported_encounters": ["single_target", "cleave_2", "aoe_5", "solo"],
  "baseline_index": 100,
  "weights": {
    "tabs": {"Stalking": 8.0, "Venom": 3.0, "Class": 1.0, "Vizier": 0.5, "Fortitude": -1.75},
    "tags": {"dot": 5.0, "proc": 4.0, "builder": 3.25, "spender": 3.75, "resource_management": 3.25, "cooldown": 2.75, "execute": 2.0, "summon": 1.25, "aura": 1.0, "melee": 0.5, "ranged": 0.25, "mobility": 0.75, "crowd_control": 0.5, "tank": -2.25, "heal": -0.75, "hot": -1.0},
    "schools": {"nature": 5.0, "shadow": 2.0, "arcane": 0.75, "physical": -0.25, "holy": -0.25, "fire": -0.25, "frost": -0.25, "fel": -0.25},
    "resources": {"Energy": 4.0, "Mana": -0.5, "Rage": -1.0}
  },
  "encounter_overrides": {
    "aoe_5": {
      "tags": {"summon": 2.5, "crowd_control": 1.0, "dot": 5.75},
      "named_boosts": {"Brood Lord": 13.0, "Contagion": 11.0, "Facemelter": 12.0}
    }
  },
  "named_boosts": {
    "Brood Marks": 20.0,
    "Venom Fang": 15.0,
    "Widow's Kiss": 14.0,
    "Nerubian Sting": 14.0,
    "Facemelter": 14.0,
    "Noxious Empowerment": 13.0,
    "Cunning of the Nerub'ar": 11.0,
    "Venomous Bite": 8.0,
    "Blistering Fangs": 7.0,
    "Contagion": 7.0,
    "Deadly Kiss": 7.0,
    "Nature Against Nature": 7.0,
    "Deadly Neurotoxins": 6.0,
    "Glory to Shadra": 6.0,
    "Virulent Resonance": 6.0,
    "Adrenal Venom": 5.0,
    "Blight Venom": 5.0,
    "Withering Venom": 5.0,
    "Rot": -2.0,
    "Fortitude": -4.0
  },
  "regex_boosts": [
    {"pattern": "\\bBrood Mark", "weight": 5.0, "reason": "Brood Mark interaction"},
    {"pattern": "\\bVenom Fang\\b", "weight": 5.0, "reason": "Venom Fang loop"},
    {"pattern": "\\bWidow", "weight": 4.0, "reason": "Widow interaction"},
    {"pattern": "\\bNerubian Sting\\b", "weight": 4.0, "reason": "Nerubian Sting interaction"},
    {"pattern": "\\bFacemelter\\b", "weight": 4.0, "reason": "mark spender interaction"},
    {"pattern": "\\bEnergy\\b", "weight": 3.0, "reason": "energy economy"},
    {"pattern": "\\bhaste\\b", "weight": 3.0, "reason": "haste scaling"},
    {"pattern": "\\bcritical strike|critically|critical damage\\b", "weight": 2.0, "reason": "critical scaling"},
    {"pattern": "\\bNature damage\\b", "weight": 2.0, "reason": "nature damage package"},
    {"pattern": "\\bShadow damage\\b", "weight": 1.0, "reason": "shadow damage package"},
    {"pattern": "\\bSpider Form\\b", "weight": 3.0, "reason": "Spider Form interaction"},
    {"pattern": "\\btank|threat|armor|block|parry|dodge\\b", "weight": -3.0, "reason": "non-DPS defensive text"}
  ],
  "synergies": [
    {"names": ["Brood Marks", "Venom Fang"], "weight": 12.0, "reason": "core mark builder"},
    {"names": ["Brood Marks", "Facemelter"], "weight": 12.0, "reason": "core mark spender"},
    {"names": ["Venom Fang", "Widow's Kiss"], "weight": 8.0, "reason": "every third fang conversion"},
    {"names": ["Nerubian Sting", "Nature Against Nature"], "weight": 8.0, "reason": "sting amplifies poison loop"},
    {"names": ["Facemelter", "Blistering Fangs"], "weight": 7.0, "reason": "high-mark spender refund"}
  ],
  "anti_synergies": [
    {"names": ["Cunning of the Nerub'ar", "Brood Lord"], "weight": -5.0, "reason": "likely competing Spider Form packages; test separately"}
  ],
  "confidence": {"base": "high"},
  "assumptions": ["Stalker Venomancer profile is a curated theorycraft profile.", "Output is a projected DPS index, not raw DPS."]
}
```

- [ ] **Step 5: Validate profile JSON syntax**

Run:

```bash
python -m json.tool coa_meta/data/scoring_profiles/generic_dps.json >/tmp/generic_dps.json
python -m json.tool coa_meta/data/scoring_profiles/generic_tank.json >/tmp/generic_tank.json
python -m json.tool coa_meta/data/scoring_profiles/generic_healer_support.json >/tmp/generic_healer_support.json
python -m json.tool coa_meta/data/scoring_profiles/venomancer_stalker.json >/tmp/venomancer_stalker.json
```

Expected: all commands exit 0.

---

### Task 3: Implement Profile Loader

**Files:**

- Create: `coa_meta/profiles.py`

- [ ] **Step 1: Add profile loader**

Create `coa_meta/profiles.py`:

```python
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROFILE_SCHEMA_VERSION = "coa-scoring-profile-v1"
SUPPORTED_ENCOUNTERS = {"single_target", "cleave_2", "aoe_5", "solo"}
PROFILE_DIR = Path(__file__).parent / "data" / "scoring_profiles"


class ProfileLoadError(ValueError):
    pass


@dataclass(frozen=True)
class ScoringProfile:
    profile_id: str
    class_name: str
    spec_key: str
    role: str
    encounter: str
    baseline_index: float
    weights: dict[str, dict[str, float]]
    named_boosts: dict[str, float]
    regex_boosts: tuple[dict[str, Any], ...]
    synergies: tuple[dict[str, Any], ...]
    anti_synergies: tuple[dict[str, Any], ...]
    confidence: dict[str, Any]
    assumptions: tuple[str, ...]


def _load_profile_json(profile_id: str) -> dict[str, Any]:
    path = PROFILE_DIR / f"{profile_id}.json"
    if not path.exists():
        raise ProfileLoadError(f"Unknown profile {profile_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ProfileLoadError(f"{profile_id} has invalid schema_version")
    return data


def load_builtin_profile(profile_id: str, encounter: str) -> ScoringProfile:
    if encounter not in SUPPORTED_ENCOUNTERS:
        raise ProfileLoadError(f"Unsupported encounter {encounter}")
    data = _load_profile_json(profile_id)
    if encounter not in data.get("supported_encounters", []):
        raise ProfileLoadError(f"{profile_id} does not support encounter {encounter}")
    merged = copy.deepcopy(data)
    overrides = merged.get("encounter_overrides", {}).get(encounter, {})
    if overrides:
        for group in ["tabs", "tags", "schools", "resources"]:
            merged.setdefault("weights", {}).setdefault(group, {}).update(overrides.get(group, {}))
        merged.setdefault("named_boosts", {}).update(overrides.get("named_boosts", {}))
    return ScoringProfile(
        profile_id=merged["profile_id"],
        class_name=merged["class_name"],
        spec_key=merged["spec_key"],
        role=merged["role"],
        encounter=encounter,
        baseline_index=float(merged.get("baseline_index", 100.0)),
        weights=merged.get("weights", {}),
        named_boosts={k: float(v) for k, v in merged.get("named_boosts", {}).items()},
        regex_boosts=tuple(merged.get("regex_boosts", [])),
        synergies=tuple(merged.get("synergies", [])),
        anti_synergies=tuple(merged.get("anti_synergies", [])),
        confidence=merged.get("confidence", {"base": "medium"}),
        assumptions=tuple(merged.get("assumptions", [])),
    )


def load_profile_by_role(class_name: str, spec_key: str, role: str, encounter: str) -> tuple[ScoringProfile, list[str]]:
    specific_id = f"{class_name.lower().replace(' ', '_')}_{spec_key}"
    warnings: list[str] = []
    try:
        return load_builtin_profile(specific_id, encounter), warnings
    except ProfileLoadError:
        warnings.append("specific_profile_missing")
    generic_id = {
        "dps": "generic_dps",
        "tank": "generic_tank",
        "healer_support": "generic_healer_support",
    }.get(role)
    if not generic_id:
        raise ProfileLoadError(f"Unsupported role {role}")
    return load_builtin_profile(generic_id, encounter), warnings
```

- [ ] **Step 2: Run profile tests**

Run:

```bash
pytest tests/test_scoring_profiles.py -q
```

Expected: 3 passed.

- [ ] **Step 3: Commit profile loader**

Run:

```bash
git add coa_meta/profiles.py coa_meta/data/scoring_profiles tests/test_scoring_profiles.py
git commit -m "feat: add data-driven scoring profiles"
```

---

### Task 4: Theory Scoring Red Tests

**Files:**

- Create: `tests/test_scoring_engine.py`

- [ ] **Step 1: Write failing scoring tests**

Create `tests/test_scoring_engine.py`:

```python
from pathlib import Path

from coa_meta.builds import BuildConfig, BuildRules
from coa_meta.domain import SelectedRank
from coa_meta.profiles import load_builtin_profile
from coa_meta.repository import TalentRepository
from coa_meta.scoring import TheoryScorer


FIXTURE = Path(__file__).parent / "fixtures" / "legal_build_fixture.jsonl"


def build_state():
    repo = TalentRepository.from_entries(FIXTURE)
    rules = BuildRules(repo, BuildConfig(class_name="Testclass", level=60, max_ae=2, max_te=3))
    result = rules.validate([SelectedRank(101, 1), SelectedRank(102, 2)])
    assert result.valid
    return repo, result.state


def test_theory_scorer_outputs_projected_index_and_components():
    repo, state = build_state()
    profile = load_builtin_profile("generic_dps", encounter="single_target")
    scorer = TheoryScorer(profile)

    scored = scorer.score_build(state, repo)

    assert scored.source == "theorycraft"
    assert scored.projected_dps_index > 100
    assert scored.raw_score > 0
    assert scored.confidence in {"low", "medium", "high"}
    assert scored.uncertainty["low"] < scored.uncertainty["mid"] < scored.uncertainty["high"]
    assert any(component.kind == "tag" for component in scored.components)
    assert any(component.kind == "school" for component in scored.components)


def test_synergies_and_anti_synergies_are_explained():
    from dataclasses import replace

    repo, state = build_state()
    profile = load_builtin_profile("generic_dps", encounter="single_target")
    custom_profile = replace(
        profile,
        synergies=({"names": ["Builder Strike", "Poison Talent"], "weight": 10.0, "reason": "test synergy"},),
        anti_synergies=({"names": ["Builder Strike", "Poison Talent"], "weight": -2.0, "reason": "test anti"},),
    )
    scorer = TheoryScorer(custom_profile)

    scored = scorer.score_build(state, repo)

    assert any(component.kind == "synergy" and component.reason == "test synergy" for component in scored.components)
    assert any(component.kind == "anti_synergy" and component.reason == "test anti" for component in scored.components)
```

- [ ] **Step 2: Run red scoring tests**

Run:

```bash
pytest tests/test_scoring_engine.py -q
```

Expected: fails because `coa_meta.scoring` does not exist.

---

### Task 5: Implement Theory Scorer

**Files:**

- Create: `coa_meta/scoring.py`

- [ ] **Step 1: Add scoring module**

Create `coa_meta/scoring.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .domain import BuildState, TalentNode
from .profiles import ScoringProfile
from .repository import TalentRepository


@dataclass(frozen=True)
class ScoreComponent:
    kind: str
    key: str
    value: float
    node_id: int | None = None
    reason: str = ""


@dataclass(frozen=True)
class ScoredBuild:
    source: str
    projected_dps_index: float
    raw_score: float
    confidence: str
    uncertainty: dict[str, float]
    components: tuple[ScoreComponent, ...]
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "projected_dps_index": self.projected_dps_index,
            "raw_score": self.raw_score,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "components": [component.__dict__ for component in self.components],
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
        }


class TheoryScorer:
    def __init__(self, profile: ScoringProfile):
        self.profile = profile
        self._compiled_regex = [
            (re.compile(item["pattern"], flags=re.IGNORECASE), float(item["weight"]), item.get("reason", item["pattern"]))
            for item in profile.regex_boosts
        ]

    def score_build(self, state: BuildState, repository: TalentRepository) -> ScoredBuild:
        components: list[ScoreComponent] = []
        selected_nodes = [repository.get_node(node_id) for node_id in state.selected_ids]
        nodes = [node for node in selected_nodes if node is not None]
        for node in nodes:
            components.extend(self.score_node(node))
        components.extend(self._score_named_sets(nodes, self.profile.synergies, "synergy"))
        components.extend(self._score_named_sets(nodes, self.profile.anti_synergies, "anti_synergy"))
        raw_score = sum(component.value for component in components)
        projected = round(self.profile.baseline_index + raw_score, 2)
        confidence = self._confidence(nodes)
        spread = {"high": 8.0, "medium": 14.0, "low": 22.0}[confidence]
        uncertainty = {
            "low": round(projected * (1.0 - spread / 100.0), 2),
            "mid": projected,
            "high": round(projected * (1.0 + spread / 100.0), 2),
        }
        return ScoredBuild(
            source="theorycraft",
            projected_dps_index=projected,
            raw_score=round(raw_score, 2),
            confidence=confidence,
            uncertainty=uncertainty,
            components=tuple(components),
            assumptions=self.profile.assumptions,
            warnings=tuple(),
        )

    def score_node(self, node: TalentNode) -> list[ScoreComponent]:
        components: list[ScoreComponent] = []
        self._add_weight(components, "tab", node.tab_name, self.profile.weights.get("tabs", {}).get(node.tab_name, 0.0), node.entry_id, f"tab:{node.tab_name}")
        for tag in node.tags:
            self._add_weight(components, "tag", tag, self.profile.weights.get("tags", {}).get(tag, 0.0), node.entry_id, f"tag:{tag}")
        for school in node.damage_schools:
            self._add_weight(components, "school", school, self.profile.weights.get("schools", {}).get(school, 0.0), node.entry_id, f"school:{school}")
        for resource in node.resources:
            self._add_weight(components, "resource", resource, self.profile.weights.get("resources", {}).get(resource, 0.0), node.entry_id, f"resource:{resource}")
        text = f"{node.name}\n{node.description_text}"
        for name, weight in self.profile.named_boosts.items():
            if name.lower() in text.lower():
                self._add_weight(components, "named", name, weight, node.entry_id, f"name/text:{name}")
        for pattern, weight, reason in self._compiled_regex:
            if pattern.search(text):
                self._add_weight(components, "regex", pattern.pattern, weight, node.entry_id, reason)
        return components

    def _score_named_sets(self, nodes: list[TalentNode], sets: tuple[dict[str, Any], ...], kind: str) -> list[ScoreComponent]:
        names = {node.name for node in nodes}
        components: list[ScoreComponent] = []
        for item in sets:
            required = set(item.get("names", []))
            if required and required.issubset(names):
                components.append(ScoreComponent(kind=kind, key="+".join(sorted(required)), value=float(item.get("weight", 0.0)), reason=item.get("reason", "")))
        return components

    def _confidence(self, nodes: list[TalentNode]) -> str:
        base = self.profile.confidence.get("base", "medium")
        if base == "high" and self.profile.class_name != "*":
            return "high"
        inferred_heavy = sum(1 for node in nodes if not node.tags and not node.damage_schools and not node.resources)
        if inferred_heavy > max(3, len(nodes) // 2):
            return "low"
        return base if base in {"low", "medium", "high"} else "medium"

    @staticmethod
    def _add_weight(components: list[ScoreComponent], kind: str, key: str, value: float, node_id: int, reason: str) -> None:
        if value:
            components.append(ScoreComponent(kind=kind, key=key, value=float(value), node_id=node_id, reason=reason))
```

- [ ] **Step 2: Run scoring tests**

Run:

```bash
pytest tests/test_scoring_engine.py -q
```

Expected: 2 passed.

- [ ] **Step 3: Run profile and scoring tests together**

Run:

```bash
pytest tests/test_scoring_profiles.py tests/test_scoring_engine.py -q
```

Expected: 5 passed.

- [ ] **Step 4: Commit scorer**

Run:

```bash
git add coa_meta/scoring.py tests/test_scoring_engine.py
git commit -m "feat: add theory scoring engine"
```

---

### Task 6: Explanation and Smoke Integration

**Files:**

- Modify: `coa_meta/explain.py`
- Create: `tests/test_scoring_integration.py`

- [ ] **Step 1: Extend explanation module**

Append to `coa_meta/explain.py`:

```python
def scored_build_to_dict(scored) -> dict:
    return scored.to_dict()
```

- [ ] **Step 2: Add integration test against current artifacts**

Create `tests/test_scoring_integration.py`:

```python
from pathlib import Path

from coa_meta.builds import BuildConfig, BuildRules
from coa_meta.profiles import load_builtin_profile
from coa_meta.repository import TalentRepository
from coa_meta.scoring import TheoryScorer
from coa_meta.search import BuildSearchConfig, BuildSearcher


def test_scores_venomancer_search_result_from_current_artifacts():
    repo = TalentRepository.from_entries(Path("coa_scraper/dist/coa_entries.jsonl"))
    rules = BuildRules(repo, BuildConfig(class_name="Venomancer", level=60, max_ae=26, max_te=25))
    result = BuildSearcher(repo, rules).search(BuildSearchConfig(top=1, beam_width=5, branch_width=10))[0]
    profile = load_builtin_profile("venomancer_stalker", encounter="single_target")

    scored = TheoryScorer(profile).score_build(result.state, repo)

    assert scored.source == "theorycraft"
    assert scored.projected_dps_index > 100
    assert scored.confidence == "high"
```

- [ ] **Step 3: Run integration test**

Run:

```bash
pytest tests/test_scoring_integration.py -q
```

Expected: 1 passed.

- [ ] **Step 4: Commit integration**

Run:

```bash
git add coa_meta/explain.py tests/test_scoring_integration.py
git commit -m "test: add scoring integration smoke test"
```

---

### Task 7: Scoring Documentation

**Files:**

- Create: `docs/data/scoring-profile-schema.md`
- Modify: `docs/DECISIONS.md`
- Modify: `docs/MODULES.md`

- [ ] **Step 1: Add scoring profile schema docs**

Create `docs/data/scoring-profile-schema.md`:

```markdown
# Scoring Profile Schema

Scoring profiles use schema version `coa-scoring-profile-v1`.

## Purpose

Profiles convert legal build states into theorycraft projected DPS indexes. They do not produce observed DPS and do not prove live meta rankings.

## Required Fields

- `schema_version`
- `profile_id`
- `class_name`
- `spec_key`
- `role`
- `supported_encounters`
- `baseline_index`
- `weights`
- `named_boosts`
- `regex_boosts`
- `synergies`
- `anti_synergies`
- `confidence`
- `assumptions`

## Output

The theory scorer emits:

- `source: theorycraft`
- `projected_dps_index`
- `raw_score`
- `confidence`
- `uncertainty`
- `components`
- `assumptions`
- `warnings`

Projected indexes are relative theorycraft values. They are not raw DPS.
```

- [ ] **Step 2: Update decisions**

Append to `docs/DECISIONS.md`:

```markdown

## Decision 11: Rank Spending Uses Linear Cost Until Builder UI Proves Otherwise

Status: accepted.

Selected rank cost is modeled as node cost multiplied by selected rank. If official builder examples show a different per-rank model, the legal build engine should change and this decision should be superseded.

## Decision 12: Theory Scoring Profiles Are JSON Data

Status: accepted.

M1.4 scoring profiles live as JSON files so class/spec tuning can change without editing scoring code. The scorer owns mechanics for applying profile data, not individual class hard-coding.
```

- [ ] **Step 3: Update module docs**

In `docs/MODULES.md`, under `## Theory Scoring Module`, add:

```markdown
M1.4 implementation files:

- `coa_meta/profiles.py`
- `coa_meta/scoring.py`
- `coa_meta/data/scoring_profiles/*.json`
```

- [ ] **Step 4: Commit docs**

Run:

```bash
git add docs/data/scoring-profile-schema.md docs/DECISIONS.md docs/MODULES.md
git commit -m "docs: document theory scoring profiles"
```

---

### Task 8: M1.4 Completion Gate

**Files:**

- Verify only.

- [ ] **Step 1: Run full Python milestone tests**

Run:

```bash
pytest tests/test_repository.py tests/test_build_rules.py tests/test_build_search.py tests/test_scoring_profiles.py tests/test_scoring_engine.py tests/test_scoring_integration.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run scraper validation**

Run:

```bash
npm test --prefix coa_scraper
```

Expected: unit test and validation pass.

- [ ] **Step 3: Check documentation markers**

Run:

```bash
python - <<'PY'
from pathlib import Path
terms = ["TB" + "D", "TO" + "DO", "FIX" + "ME", "implement " + "later"]
matches = []
for root in [Path("docs"), Path("coa_meta"), Path("tests")]:
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".py", ".json"}:
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if any(term in line for term in terms):
                matches.append(f"{path}:{line_no}:{line}")
if matches:
    print("\n".join(matches))
    raise SystemExit(1)
print("no red-flag markers")
PY
```

Expected output:

```text
no red-flag markers
```

- [ ] **Step 4: Check git status**

Run:

```bash
git status --short
```

Expected: no uncommitted M1.4 changes.
