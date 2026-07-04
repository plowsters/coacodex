# M1.6 Meta Report Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Phase 1 meta report runner that emits canonical JSON, Markdown, and static HTML reports for top builds per reportable class/spec.

**Architecture:** Add a focused reporting layer that expands `BuildScope` records, resolves eligible nodes through an `EligibilityPolicy`, runs the existing search/scoring/APL pipeline, and renders outputs from one canonical report model. Extend `BuildRules` so legality and search can operate over an injected eligible-node set without adding class-specific algorithm branches.

**Tech Stack:** Python 3.11+ standard library, dataclasses, JSON, existing `coa_meta` modules, current normalized artifacts, `python -m pytest`.

---

## File Structure

- Modify `coa_meta/builds.py`: add scope-limited legal pools via `BuildConfig.allowed_node_ids`.
- Create `coa_meta/reporting.py`: report dataclasses, class metadata loading, scope expansion, eligibility, orchestration, and writers.
- Create `coa_meta/report_assets.py`: optional local asset resolver for static HTML.
- Create `tests/fixtures/meta_classes.json`: small class/spec metadata fixture with shared and empty tabs.
- Create `tests/fixtures/meta_report_fixture.jsonl`: small normalized fixture for reportability, shared pools, and level filtering.
- Create `tests/test_report_eligibility.py`: reportable spec, shared pool, and level filter tests.
- Create `tests/test_meta_report_runner.py`: runner integration tests over the fixture.
- Create `tests/test_report_writers.py`: JSON, Markdown, HTML, and asset fallback tests.
- Create `docs/data/meta-report-schema.md`: document `coa-meta-report-v1`.
- Modify `docs/MODULES.md`: document report modules.
- Modify `docs/DECISIONS.md`: record per-spec report and shared class-pool decisions.

## Task 1: Scope-Limited Build Rules

**Files:**
- Modify: `coa_meta/builds.py`
- Test: `tests/test_report_eligibility.py`

- [ ] **Step 1: Write failing tests for eligible-node scopes**

Create `tests/test_report_eligibility.py` with the initial tests below:

```python
from __future__ import annotations

from pathlib import Path

from coa_meta.builds import BuildConfig, BuildRules
from coa_meta.domain import SelectedRank
from coa_meta.repository import TalentRepository

FIXTURE = Path(__file__).parent / "fixtures" / "legal_build_fixture.jsonl"


def test_build_rules_restrict_paid_nodes_to_allowed_scope():
    repo = TalentRepository.from_entries(FIXTURE)
    rules = BuildRules(
        repo,
        BuildConfig(
            class_name="Testclass",
            level=60,
            max_ae=2,
            max_te=3,
            allowed_node_ids=(100, 101, 102),
        ),
    )

    assert sorted(rules.nodes) == [100, 101, 102]
    result = rules.validate([SelectedRank(103, 1)])

    assert result.valid is False
    assert "node_not_in_scope" in result.issue_codes()


def test_build_rules_allow_valid_selection_inside_scope():
    repo = TalentRepository.from_entries(FIXTURE)
    rules = BuildRules(
        repo,
        BuildConfig(
            class_name="Testclass",
            level=60,
            max_ae=2,
            max_te=3,
            allowed_node_ids=(100, 101, 102),
        ),
    )

    result = rules.validate([SelectedRank(101, 1), SelectedRank(102, 1)])

    assert result.valid is True
    assert result.state is not None
    assert result.state.ae_spent == 1
    assert result.state.te_spent == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_report_eligibility.py -q
```

Expected: FAIL with `TypeError: BuildConfig.__init__() got an unexpected keyword argument 'allowed_node_ids'`.

- [ ] **Step 3: Add `allowed_node_ids` to build configuration and validation**

Modify `coa_meta/builds.py`:

```python
@dataclass(frozen=True)
class BuildConfig:
    class_name: str
    level: int = 60
    max_ae: int = 26
    max_te: int = 25
    allowed_node_ids: tuple[int, ...] | None = None
```

Replace `BuildRules.__init__` with:

```python
class BuildRules:
    def __init__(self, repository: TalentRepository, config: BuildConfig):
        self.repository = repository
        self.config = config
        allowed = set(config.allowed_node_ids) if config.allowed_node_ids is not None else None
        self.nodes = {
            node.entry_id: node
            for node in repository.nodes_for_class(config.class_name)
            if allowed is None or node.entry_id in allowed
        }
```

In `BuildRules.validate`, after the existing wrong-class check, add the scope check before spending is counted:

```python
            if node.entry_id not in self.nodes:
                issues.append(
                    ValidationIssue(
                        "node_not_in_scope",
                        f"{node.name} is not available in this build scope",
                        node_id,
                    )
                )
                continue
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
python -m pytest tests/test_report_eligibility.py tests/test_build_rules.py tests/test_build_search.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit scope-limited legality**

```bash
git add coa_meta/builds.py tests/test_report_eligibility.py
git commit -m "feat: support scoped build legality"
```

## Task 2: Report Fixtures and Eligibility Policy

**Files:**
- Create: `tests/fixtures/meta_classes.json`
- Create: `tests/fixtures/meta_report_fixture.jsonl`
- Modify: `tests/test_report_eligibility.py`
- Create: `coa_meta/reporting.py`

- [ ] **Step 1: Add report fixtures**

Create `tests/fixtures/meta_classes.json`:

```json
[
  {
    "schema_version": "coa-normalized-class-v1",
    "class_id": 1,
    "class_name": "Testclass",
    "tabs": [
      {"tab_id": 10, "tab_name": "Class", "sort_order": 0, "nominal_essence_kind": "ability"},
      {"tab_id": 11, "tab_name": "Damage", "sort_order": 1, "nominal_essence_kind": "talent"},
      {"tab_id": 12, "tab_name": "Support", "sort_order": 2, "nominal_essence_kind": "talent"},
      {"tab_id": 13, "tab_name": "Empty", "sort_order": 3, "nominal_essence_kind": "talent"},
      {"tab_id": 1, "tab_name": "None", "sort_order": 4, "nominal_essence_kind": "talent"}
    ],
    "essence_caps": {"max_level": 60, "ability": 26, "talent": 25}
  }
]
```

Create `tests/fixtures/meta_report_fixture.jsonl`:

```jsonl
{"schema_version":"coa-normalized-v1","build_id":1,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":10,"tab_name":"Class","tab_sort_order":0,"entry_type":"Ability","essence_kind":"ability","essence_type":"abilityEssence","entry_id":100,"spell_id":1000,"spell_ids":[1000],"name":"Shared Free","icon":"Interface\\Icons\\Shared_Free","ae_cost":0,"te_cost":0,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Free shared class passive.","required_level":0,"max_rank":1,"row":0,"col":0,"node_type":"SpendCircle","flags":0,"group":0,"is_passive":true,"is_starting_node":true,"required_ids":[],"connected_node_ids":[],"tags":[],"damage_schools":[],"resources":[],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":1,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":10,"tab_name":"Class","tab_sort_order":0,"entry_type":"Ability","essence_kind":"ability","essence_type":"abilityEssence","entry_id":101,"spell_id":1001,"spell_ids":[1001],"name":"Shared Strike","icon":"Interface\\Icons\\Shared_Strike","ae_cost":1,"te_cost":0,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Deals physical damage and generates Energy.","required_level":0,"max_rank":1,"row":1,"col":0,"node_type":"SpendSquare","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[100],"connected_node_ids":[],"tags":["builder"],"damage_schools":["physical"],"resources":["Energy"],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":1,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":10,"tab_name":"Class","tab_sort_order":0,"entry_type":"Ability","essence_kind":"ability","essence_type":"abilityEssence","entry_id":102,"spell_id":1002,"spell_ids":[1002],"name":"Shared Veteran Strike","icon":"Interface\\Icons\\Shared_Veteran","ae_cost":1,"te_cost":0,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Higher level shared attack.","required_level":50,"max_rank":1,"row":2,"col":0,"node_type":"SpendSquare","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[],"connected_node_ids":[],"tags":["spender"],"damage_schools":["physical"],"resources":["Energy"],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":1,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":11,"tab_name":"Damage","tab_sort_order":1,"entry_type":"Talent","essence_kind":"talent","essence_type":"talentEssence","entry_id":201,"spell_id":2001,"spell_ids":[2001],"name":"Damage Talent","icon":"Interface\\Icons\\Damage_Talent","ae_cost":0,"te_cost":1,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Increases damage over time.","required_level":0,"max_rank":1,"row":1,"col":1,"node_type":"SpendCircle","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[],"connected_node_ids":[],"tags":["dot"],"damage_schools":["nature"],"resources":[],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":1,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":11,"tab_name":"Damage","tab_sort_order":1,"entry_type":"Talent","essence_kind":"talent","essence_type":"talentEssence","entry_id":202,"spell_id":2002,"spell_ids":[2002],"name":"Deep Damage","icon":"Interface\\Icons\\Deep_Damage","ae_cost":0,"te_cost":1,"required_tab_ae":0,"required_tab_te":1,"description_html":"","description_text":"Requires investment in Damage.","required_level":0,"max_rank":1,"row":2,"col":1,"node_type":"SpendCircle","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[201],"connected_node_ids":[],"tags":["spender"],"damage_schools":["nature"],"resources":[],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":1,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":12,"tab_name":"Support","tab_sort_order":2,"entry_type":"Talent","essence_kind":"talent","essence_type":"talentEssence","entry_id":301,"spell_id":3001,"spell_ids":[3001],"name":"Support Talent","icon":"Interface\\Icons\\Support_Talent","ae_cost":0,"te_cost":1,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Adds utility.","required_level":0,"max_rank":1,"row":1,"col":1,"node_type":"SpendCircle","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[],"connected_node_ids":[],"tags":["utility"],"damage_schools":[],"resources":[],"field_sources":{},"inferred":{},"raw":{}}
```

- [ ] **Step 2: Write failing eligibility tests**

Append to `tests/test_report_eligibility.py`:

```python
from coa_meta.reporting import (
    BuildScope,
    EligibilityPolicy,
    load_class_metadata,
)

META_CLASSES = Path(__file__).parent / "fixtures" / "meta_classes.json"
META_NODES = Path(__file__).parent / "fixtures" / "meta_report_fixture.jsonl"


def test_reportable_specs_exclude_shared_empty_and_none_tabs():
    repo = TalentRepository.from_entries(META_NODES)
    classes = load_class_metadata(META_CLASSES)
    policy = EligibilityPolicy()

    specs = policy.reportable_specs(repo, classes)

    assert [(spec.class_name, spec.spec_id, spec.spec_name) for spec in specs] == [
        ("Testclass", 11, "Damage"),
        ("Testclass", 12, "Support"),
    ]
    warnings = policy.metadata_warnings(repo, classes)
    assert any("Testclass:Empty" in warning for warning in warnings)


def test_eligible_nodes_include_spec_tree_and_shared_class_pool():
    repo = TalentRepository.from_entries(META_NODES)
    policy = EligibilityPolicy()
    scope = BuildScope(
        class_name="Testclass",
        spec_id=11,
        spec_name="Damage",
        level=60,
        encounter_profile_id="baseline_single_target",
        search_profile_id="default",
        scoring_profile_id="auto",
        apl_profile_id="auto",
        top=3,
    )

    eligible = policy.eligible_node_ids(repo, scope)

    assert eligible == (100, 101, 102, 201, 202)


def test_level_filtering_excludes_known_high_level_shared_nodes():
    repo = TalentRepository.from_entries(META_NODES)
    policy = EligibilityPolicy()
    scope = BuildScope(
        class_name="Testclass",
        spec_id=11,
        spec_name="Damage",
        level=15,
        encounter_profile_id="baseline_single_target",
        search_profile_id="default",
        scoring_profile_id="auto",
        apl_profile_id="auto",
        top=3,
    )

    eligible = policy.eligible_node_ids(repo, scope)
    warnings = policy.scope_warnings(repo, scope)

    assert eligible == (100, 101, 201, 202)
    assert "shared_class_level_gating_incomplete" in warnings
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_report_eligibility.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'coa_meta.reporting'`.

- [ ] **Step 4: Implement report dataclasses, metadata loading, and eligibility**

Create `coa_meta/reporting.py` with this initial content:

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .domain import TalentNode
from .repository import TalentRepository

META_REPORT_SCHEMA_VERSION = "coa-meta-report-v1"
DEFAULT_PUBLIC_ENCOUNTER = "baseline_single_target"
ENCOUNTER_ALIASES = {DEFAULT_PUBLIC_ENCOUNTER: "single_target"}
SHARED_TAB_NAMES = {"Class", "None"}


@dataclass(frozen=True)
class ClassTabMetadata:
    class_name: str
    tab_id: int
    tab_name: str
    sort_order: int
    nominal_essence_kind: str


@dataclass(frozen=True)
class ReportableSpec:
    class_name: str
    spec_id: int
    spec_name: str
    sort_order: int = 0


@dataclass(frozen=True)
class BuildScope:
    class_name: str
    spec_id: int
    spec_name: str
    level: int
    encounter_profile_id: str
    search_profile_id: str
    scoring_profile_id: str
    apl_profile_id: str
    top: int

    @property
    def spec_key(self) -> str:
        return slugify_key(self.spec_name)

    @property
    def scoring_encounter(self) -> str:
        return ENCOUNTER_ALIASES.get(self.encounter_profile_id, self.encounter_profile_id)


def slugify_key(value: str) -> str:
    lowered = value.lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")


def load_class_metadata(path: Path | str) -> tuple[ClassTabMetadata, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tabs: list[ClassTabMetadata] = []
    for class_record in data:
        class_name = str(class_record.get("class_name", ""))
        for tab in class_record.get("tabs", []):
            tabs.append(
                ClassTabMetadata(
                    class_name=class_name,
                    tab_id=int(tab.get("tab_id", 0)),
                    tab_name=str(tab.get("tab_name", "")),
                    sort_order=int(tab.get("sort_order", 0)),
                    nominal_essence_kind=str(tab.get("nominal_essence_kind", "")),
                )
            )
    return tuple(tabs)


class EligibilityPolicy:
    def reportable_specs(
        self,
        repository: TalentRepository,
        class_metadata: tuple[ClassTabMetadata, ...] = tuple(),
    ) -> tuple[ReportableSpec, ...]:
        node_tabs: dict[tuple[str, int, str], list[TalentNode]] = {}
        for class_name in repository.class_names():
            for node in repository.nodes_for_class(class_name):
                if node.tab_name in SHARED_TAB_NAMES:
                    continue
                node_tabs.setdefault((node.class_name, node.tab_id, node.tab_name), []).append(node)

        metadata_order = {
            (item.class_name, item.tab_id, item.tab_name): item.sort_order for item in class_metadata
        }
        specs = [
            ReportableSpec(
                class_name=class_name,
                spec_id=tab_id,
                spec_name=tab_name,
                sort_order=metadata_order.get((class_name, tab_id, tab_name), 0),
            )
            for (class_name, tab_id, tab_name), nodes in node_tabs.items()
            if nodes
        ]
        return tuple(sorted(specs, key=lambda item: (item.class_name, item.sort_order, item.spec_name)))

    def eligible_node_ids(self, repository: TalentRepository, scope: BuildScope) -> tuple[int, ...]:
        eligible: list[int] = []
        for node in repository.nodes_for_class(scope.class_name):
            if node.required_level > scope.level:
                continue
            if node.tab_id == scope.spec_id or node.tab_name == "Class":
                eligible.append(node.entry_id)
        return tuple(sorted(set(eligible)))

    def metadata_warnings(
        self,
        repository: TalentRepository,
        class_metadata: tuple[ClassTabMetadata, ...],
    ) -> tuple[str, ...]:
        node_tabs = {
            (node.class_name, node.tab_id, node.tab_name)
            for class_name in repository.class_names()
            for node in repository.nodes_for_class(class_name)
        }
        warnings: list[str] = []
        for item in class_metadata:
            if item.tab_name in SHARED_TAB_NAMES:
                continue
            if (item.class_name, item.tab_id, item.tab_name) not in node_tabs:
                warnings.append(f"metadata_tab_has_no_nodes:{item.class_name}:{item.tab_name}")
        return tuple(warnings)

    def scope_warnings(self, repository: TalentRepository, scope: BuildScope) -> tuple[str, ...]:
        warnings: list[str] = []
        if scope.level < 60 and any(node.tab_name == "Class" for node in repository.nodes_for_class(scope.class_name)):
            warnings.append("shared_class_level_gating_incomplete")
        return tuple(warnings)
```

- [ ] **Step 5: Run eligibility tests**

Run:

```bash
python -m pytest tests/test_report_eligibility.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit eligibility policy**

```bash
git add coa_meta/reporting.py tests/fixtures/meta_classes.json tests/fixtures/meta_report_fixture.jsonl tests/test_report_eligibility.py
git commit -m "feat: add report eligibility policy"
```

## Task 3: Canonical Report Runner

**Files:**
- Modify: `coa_meta/reporting.py`
- Test: `tests/test_meta_report_runner.py`

- [ ] **Step 1: Write failing runner tests**

Create `tests/test_meta_report_runner.py`:

```python
from __future__ import annotations

from pathlib import Path

from coa_meta.reporting import MetaReportRunner, MetaRunConfig

FIXTURES = Path(__file__).parent / "fixtures"


def test_meta_report_runner_generates_spec_results_from_fixture():
    config = MetaRunConfig(
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        classes_path=FIXTURES / "meta_classes.json",
        class_names=("Testclass",),
        top=2,
        beam_width=4,
        branch_width=4,
        require_budget_fraction=0.0,
    )

    report = MetaReportRunner(config).run()
    data = report.to_dict()

    assert data["schema_version"] == "coa-meta-report-v1"
    assert data["run_config"]["top"] == 2
    assert [row["spec_name"] for row in data["spec_results"]] == ["Damage", "Support"]
    assert data["spec_results"][0]["top_builds"]
    assert data["spec_results"][0]["top_builds"][0]["projected_dps_index"] > 0
    assert data["spec_results"][0]["top_builds"][0]["generated_apl"]["schema_version"] == "coa-apl-v1"


def test_meta_report_runner_preserves_metadata_warnings():
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

    assert any("metadata_tab_has_no_nodes:Testclass:Empty" in warning for warning in report.warnings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_meta_report_runner.py -q
```

Expected: FAIL with `ImportError` for `MetaReportRunner` or `MetaRunConfig`.

- [ ] **Step 3: Add report dataclasses and runner integration**

Append these imports to the top of `coa_meta/reporting.py`:

```python
from datetime import datetime, timezone

from .apl import generate_apl
from .apl_profiles import load_apl_profile_by_role
from .builds import BuildConfig, BuildRules
from .profiles import load_profile_by_role
from .scoring import TheoryScorer
from .search import BuildSearchConfig, BuildSearcher
```

Append these dataclasses and the runner to `coa_meta/reporting.py`:

```python
CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}


@dataclass(frozen=True)
class MetaRunConfig:
    entries_path: Path
    classes_path: Path | None = None
    class_names: tuple[str, ...] = tuple()
    spec_names_or_ids: tuple[str, ...] = tuple()
    level: int = 60
    encounter_profile_ids: tuple[str, ...] = (DEFAULT_PUBLIC_ENCOUNTER,)
    search_profile_id: str = "default"
    scoring_profile_id: str = "auto"
    apl_profile_id: str = "auto"
    role: str = "dps"
    top: int = 3
    beam_width: int = 5
    branch_width: int = 10
    require_budget_fraction: float = 0.7
    max_ae: int = 26
    max_te: int = 25

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries_path": str(self.entries_path),
            "classes_path": str(self.classes_path) if self.classes_path else None,
            "class_names": list(self.class_names),
            "spec_names_or_ids": list(self.spec_names_or_ids),
            "level": self.level,
            "encounter_profile_ids": list(self.encounter_profile_ids),
            "search_profile_id": self.search_profile_id,
            "scoring_profile_id": self.scoring_profile_id,
            "apl_profile_id": self.apl_profile_id,
            "role": self.role,
            "top": self.top,
            "beam_width": self.beam_width,
            "branch_width": self.branch_width,
            "require_budget_fraction": self.require_budget_fraction,
            "max_ae": self.max_ae,
            "max_te": self.max_te,
        }


@dataclass(frozen=True)
class BuildReport:
    rank: int
    projected_dps_index: float
    confidence_label: str
    selected_nodes: tuple[dict[str, Any], ...]
    score_breakdown: dict[str, Any]
    generated_apl: dict[str, Any]
    explanation: dict[str, Any]
    provenance: dict[str, Any]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "projected_dps_index": self.projected_dps_index,
            "confidence_label": self.confidence_label,
            "selected_nodes": list(self.selected_nodes),
            "score_breakdown": self.score_breakdown,
            "generated_apl": self.generated_apl,
            "explanation": self.explanation,
            "provenance": self.provenance,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class SpecResult:
    class_name: str
    spec_id: int
    spec_name: str
    level: int
    encounter_profile_id: str
    search_profile_id: str
    scoring_profile_id: str
    apl_profile_id: str
    top_builds: tuple[BuildReport, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_name": self.class_name,
            "spec_id": self.spec_id,
            "spec_name": self.spec_name,
            "level": self.level,
            "encounter_profile_id": self.encounter_profile_id,
            "search_profile_id": self.search_profile_id,
            "scoring_profile_id": self.scoring_profile_id,
            "apl_profile_id": self.apl_profile_id,
            "top_builds": [build.to_dict() for build in self.top_builds],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class MetaReport:
    schema_version: str
    generated_at: str
    input_artifacts: dict[str, str]
    run_config: dict[str, Any]
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    class_summaries: tuple[dict[str, Any], ...]
    spec_results: tuple[SpecResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "input_artifacts": self.input_artifacts,
            "run_config": self.run_config,
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "class_summaries": list(self.class_summaries),
            "spec_results": [result.to_dict() for result in self.spec_results],
        }


class MetaReportRunner:
    def __init__(self, config: MetaRunConfig, eligibility: EligibilityPolicy | None = None):
        self.config = config
        self.eligibility = eligibility or EligibilityPolicy()

    def run(self) -> MetaReport:
        repository = TalentRepository.from_entries(self.config.entries_path)
        metadata = load_class_metadata(self.config.classes_path) if self.config.classes_path else tuple()
        warnings = list(self.eligibility.metadata_warnings(repository, metadata))
        scopes = self._expand_scopes(repository, metadata)
        spec_results = tuple(self._run_scope(repository, scope) for scope in scopes)
        return MetaReport(
            schema_version=META_REPORT_SCHEMA_VERSION,
            generated_at=datetime.now(timezone.utc).isoformat(),
            input_artifacts={
                "entries": str(self.config.entries_path),
                "classes": str(self.config.classes_path) if self.config.classes_path else "",
            },
            run_config=self.config.to_dict(),
            assumptions=(
                "Projected DPS index is a theorycraft score, not observed DPS.",
                "Shared Class nodes are included for each reportable spec.",
            ),
            warnings=tuple(warnings),
            class_summaries=_class_summaries(spec_results),
            spec_results=spec_results,
        )

    def _expand_scopes(
        self,
        repository: TalentRepository,
        metadata: tuple[ClassTabMetadata, ...],
    ) -> tuple[BuildScope, ...]:
        specs = self.eligibility.reportable_specs(repository, metadata)
        class_filter = set(self.config.class_names)
        spec_filter = {item.casefold() for item in self.config.spec_names_or_ids}
        scopes: list[BuildScope] = []
        for spec in specs:
            if class_filter and spec.class_name not in class_filter:
                continue
            if spec_filter and str(spec.spec_id).casefold() not in spec_filter and spec.spec_name.casefold() not in spec_filter:
                continue
            for encounter_id in self.config.encounter_profile_ids:
                scopes.append(
                    BuildScope(
                        class_name=spec.class_name,
                        spec_id=spec.spec_id,
                        spec_name=spec.spec_name,
                        level=self.config.level,
                        encounter_profile_id=encounter_id,
                        search_profile_id=self.config.search_profile_id,
                        scoring_profile_id=self.config.scoring_profile_id,
                        apl_profile_id=self.config.apl_profile_id,
                        top=self.config.top,
                    )
                )
        return tuple(scopes)

    def _run_scope(self, repository: TalentRepository, scope: BuildScope) -> SpecResult:
        warnings = list(self.eligibility.scope_warnings(repository, scope))
        eligible_ids = self.eligibility.eligible_node_ids(repository, scope)
        rules = BuildRules(
            repository,
            BuildConfig(
                class_name=scope.class_name,
                level=scope.level,
                max_ae=self.config.max_ae,
                max_te=self.config.max_te,
                allowed_node_ids=eligible_ids,
            ),
        )
        search_results = BuildSearcher(repository, rules).search(
            BuildSearchConfig(
                top=max(scope.top * 3, scope.top),
                beam_width=self.config.beam_width,
                branch_width=self.config.branch_width,
                require_budget_fraction=self.config.require_budget_fraction,
            )
        )
        scoring_profile, scoring_warnings = load_profile_by_role(
            scope.class_name,
            scope.spec_key,
            self.config.role,
            scope.scoring_encounter,
        )
        apl_profile, apl_warnings = load_apl_profile_by_role(scope.class_name, scope.spec_key, self.config.role)
        scored_rows: list[tuple[Any, Any]] = []
        for result in search_results:
            if result.state is None:
                continue
            scored_rows.append((result, TheoryScorer(scoring_profile).score_build(result.state, repository)))
        scored_rows.sort(
            key=lambda item: (
                item[1].projected_dps_index,
                CONFIDENCE_RANK.get(item[1].confidence, 0),
                _build_key(item[0].state),
            ),
            reverse=True,
        )
        top_builds: list[BuildReport] = []
        for index, (result, scored) in enumerate(scored_rows[: scope.top], start=1):
            assert result.state is not None
            apl_doc = generate_apl(
                result.state,
                repository,
                apl_profile,
                encounter=scope.scoring_encounter,
                profile_warnings=apl_warnings,
            )
            selected_nodes = tuple(_node_to_report(repository.node_by_id(node_id)) for node_id in sorted(result.state.selected_ids))
            top_builds.append(
                BuildReport(
                    rank=index,
                    projected_dps_index=scored.projected_dps_index,
                    confidence_label=scored.confidence,
                    selected_nodes=selected_nodes,
                    score_breakdown=scored.to_dict(),
                    generated_apl=apl_doc.to_dict(),
                    explanation={"score_components": [component.__dict__ for component in scored.components]},
                    provenance={
                        "normalized_schema": "coa-normalized-v1",
                        "scoring_profile_id": scoring_profile.profile_id,
                        "apl_profile_id": apl_profile.profile_id,
                    },
                    warnings=tuple(scoring_warnings + list(scored.warnings) + list(apl_doc.warnings)),
                )
            )
        if not top_builds:
            warnings.append("no_valid_builds_found")
        return SpecResult(
            class_name=scope.class_name,
            spec_id=scope.spec_id,
            spec_name=scope.spec_name,
            level=scope.level,
            encounter_profile_id=scope.encounter_profile_id,
            search_profile_id=scope.search_profile_id,
            scoring_profile_id=scoring_profile.profile_id,
            apl_profile_id=apl_profile.profile_id,
            top_builds=tuple(top_builds),
            warnings=tuple(warnings),
        )


def _build_key(state: Any) -> str:
    if state is None:
        return ""
    return ",".join(str(rank.node_id) for rank in state.selected_ranks)


def _node_to_report(node: TalentNode) -> dict[str, Any]:
    return {
        "node_id": node.entry_id,
        "spell_id": node.spell_id,
        "name": node.name,
        "tab_id": node.tab_id,
        "tab_name": node.tab_name,
        "essence_kind": node.essence_kind,
        "ae_cost": node.ae_cost,
        "te_cost": node.te_cost,
        "required_level": node.required_level,
        "icon": node.raw.get("icon") or node.raw.get("iconPath"),
        "tags": list(node.tags),
        "damage_schools": list(node.damage_schools),
        "resources": list(node.resources),
    }


def _class_summaries(spec_results: tuple[SpecResult, ...]) -> tuple[dict[str, Any], ...]:
    by_class: dict[str, list[SpecResult]] = {}
    for result in spec_results:
        by_class.setdefault(result.class_name, []).append(result)
    summaries: list[dict[str, Any]] = []
    for class_name, rows in sorted(by_class.items()):
        best = None
        for row in rows:
            if row.top_builds and (best is None or row.top_builds[0].projected_dps_index > best.top_builds[0].projected_dps_index):
                best = row
        summaries.append(
            {
                "class_name": class_name,
                "spec_count": len(rows),
                "best_spec_name": best.spec_name if best else None,
                "best_projected_dps_index": best.top_builds[0].projected_dps_index if best else None,
                "summary_note": "Derived from per-spec projected build rankings.",
            }
        )
    return tuple(summaries)
```

- [ ] **Step 4: Run runner tests**

Run:

```bash
python -m pytest tests/test_meta_report_runner.py tests/test_report_eligibility.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit report runner**

```bash
git add coa_meta/reporting.py tests/test_meta_report_runner.py
git commit -m "feat: add meta report runner"
```

## Task 4: JSON, Markdown, HTML Writers and Asset Resolver

**Files:**
- Create: `coa_meta/report_assets.py`
- Modify: `coa_meta/reporting.py`
- Test: `tests/test_report_writers.py`

- [ ] **Step 1: Write failing writer tests**

Create `tests/test_report_writers.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from coa_meta.report_assets import AssetResolver
from coa_meta.reporting import MetaReportRunner, MetaRunConfig, render_html_report, render_markdown_report, write_report_outputs

FIXTURES = Path(__file__).parent / "fixtures"


def _report():
    return MetaReportRunner(
        MetaRunConfig(
            entries_path=FIXTURES / "meta_report_fixture.jsonl",
            classes_path=FIXTURES / "meta_classes.json",
            class_names=("Testclass",),
            top=1,
            beam_width=2,
            branch_width=2,
            require_budget_fraction=0.0,
        )
    ).run()


def test_writes_json_markdown_and_html_outputs(tmp_path):
    report = _report()

    written = write_report_outputs(report, tmp_path, formats=("json", "md", "html"))

    assert {path.name for path in written} == {"meta-report.json", "meta-report.md", "meta-report.html"}
    data = json.loads((tmp_path / "meta-report.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == "coa-meta-report-v1"
    assert "Projected DPS Index" in (tmp_path / "meta-report.md").read_text(encoding="utf-8")
    assert "<html" in (tmp_path / "meta-report.html").read_text(encoding="utf-8")


def test_markdown_and_html_include_warnings_and_theorycraft_label():
    report = _report()

    markdown = render_markdown_report(report)
    html = render_html_report(report)

    assert "theorycraft" in markdown.lower()
    assert "metadata_tab_has_no_nodes:Testclass:Empty" in markdown
    assert "Observed DPS" not in markdown
    assert "Projected DPS Index" in html


def test_asset_resolver_returns_none_for_missing_assets(tmp_path):
    resolver = AssetResolver(tmp_path)

    assert resolver.class_tree_image("Testclass") is None
    assert resolver.node_icon("Interface\\Icons\\Missing") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_report_writers.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'coa_meta.report_assets'`.

- [ ] **Step 3: Implement asset resolver**

Create `coa_meta/report_assets.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AssetResolver:
    asset_root: Path | None = None

    def class_tree_image(self, class_name: str) -> str | None:
        if self.asset_root is None:
            return None
        root = Path(self.asset_root)
        if not root.exists():
            return None
        slug = _asset_slug(class_name)
        for path in root.rglob("*"):
            lowered = path.name.lower()
            if path.is_file() and slug in lowered and lowered.endswith((".webp", ".png", ".jpg", ".jpeg")):
                return str(path)
        return None

    def node_icon(self, icon: str | None) -> str | None:
        if not icon or self.asset_root is None:
            return None
        root = Path(self.asset_root)
        if not root.exists():
            return None
        icon_slug = _asset_slug(icon.split("\\")[-1])
        for path in root.rglob("*"):
            lowered = path.stem.lower()
            if path.is_file() and icon_slug and icon_slug in lowered:
                return str(path)
        return None


def _asset_slug(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())
```

- [ ] **Step 4: Implement report renderers and output writer**

Append to `coa_meta/reporting.py`:

```python
def render_markdown_report(report: MetaReport) -> str:
    data = report.to_dict()
    lines = [
        "# CoA Phase 1 Meta Report",
        "",
        "This report is a theorycraft projection. Projected DPS Index is not observed DPS.",
        "",
        "## Run",
        "",
        f"- Generated: `{data['generated_at']}`",
        f"- Schema: `{data['schema_version']}`",
        f"- Level: `{data['run_config']['level']}`",
        "",
    ]
    if data["warnings"]:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- `{warning}`" for warning in data["warnings"])
        lines.append("")
    lines.extend(["## Spec Results", ""])
    for result in data["spec_results"]:
        lines.append(f"### {result['class_name']} - {result['spec_name']}")
        if result["warnings"]:
            lines.extend(f"- Warning: `{warning}`" for warning in result["warnings"])
        lines.append("")
        lines.append("| Rank | Projected DPS Index | Confidence | Selected Nodes |")
        lines.append("| --- | ---: | --- | --- |")
        for build in result["top_builds"]:
            nodes = ", ".join(node["name"] for node in build["selected_nodes"])
            lines.append(
                f"| {build['rank']} | {build['projected_dps_index']} | {build['confidence_label']} | {nodes} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html_report(report: MetaReport, asset_resolver: Any | None = None) -> str:
    data = report.to_dict()
    warning_items = "".join(f"<li><code>{_html_escape(warning)}</code></li>" for warning in data["warnings"])
    sections: list[str] = []
    for result in data["spec_results"]:
        rows: list[str] = []
        for build in result["top_builds"]:
            nodes = ", ".join(_html_escape(node["name"]) for node in build["selected_nodes"])
            rows.append(
                "<tr>"
                f"<td>{build['rank']}</td>"
                f"<td>{build['projected_dps_index']}</td>"
                f"<td>{_html_escape(build['confidence_label'])}</td>"
                f"<td>{nodes}</td>"
                "</tr>"
            )
        sections.append(
            "<section>"
            f"<h2>{_html_escape(result['class_name'])} - {_html_escape(result['spec_name'])}</h2>"
            "<table><thead><tr><th>Rank</th><th>Projected DPS Index</th><th>Confidence</th><th>Selected Nodes</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
            "</section>"
        )
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>CoA Phase 1 Meta Report</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:24px;}table{border-collapse:collapse;width:100%;margin-bottom:24px;}th,td{border:1px solid #ccc;padding:6px 8px;text-align:left;}th{background:#f4f4f4;}code{background:#eee;padding:1px 4px;}</style>"
        "</head><body>"
        "<h1>CoA Phase 1 Meta Report</h1>"
        "<p>This report is a theorycraft projection. Projected DPS Index is not observed DPS.</p>"
        f"<h2>Warnings</h2><ul>{warning_items}</ul>"
        f"{''.join(sections)}"
        "</body></html>"
    )


def write_report_outputs(
    report: MetaReport,
    out_dir: Path | str,
    formats: tuple[str, ...] = ("json", "md", "html"),
    asset_resolver: Any | None = None,
) -> tuple[Path, ...]:
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for fmt in formats:
        if fmt == "json":
            path = output_dir / "meta-report.json"
            path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        elif fmt == "md":
            path = output_dir / "meta-report.md"
            path.write_text(render_markdown_report(report), encoding="utf-8")
        elif fmt == "html":
            path = output_dir / "meta-report.html"
            path.write_text(render_html_report(report, asset_resolver=asset_resolver), encoding="utf-8")
        else:
            raise ValueError(f"Unsupported report format {fmt}")
        written.append(path)
    return tuple(written)


def _html_escape(value: Any) -> str:
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
```

- [ ] **Step 5: Run writer tests**

Run:

```bash
python -m pytest tests/test_report_writers.py tests/test_meta_report_runner.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit report writers**

```bash
git add coa_meta/reporting.py coa_meta/report_assets.py tests/test_report_writers.py
git commit -m "feat: render meta report outputs"
```

## Task 5: Schema Documentation and Full Verification

**Files:**
- Create: `docs/data/meta-report-schema.md`
- Modify: `docs/MODULES.md`
- Modify: `docs/DECISIONS.md`

- [ ] **Step 1: Document meta report schema**

Create `docs/data/meta-report-schema.md`:

```markdown
# Meta Report Schema

Schema version: `coa-meta-report-v1`

The meta report is the canonical Phase 1 theorycraft output. JSON is the source of truth. Markdown and HTML are renderings of the same model.

## Top-Level Object

- `schema_version`: always `coa-meta-report-v1`
- `generated_at`: UTC ISO timestamp
- `input_artifacts`: paths used for normalized entries and class metadata
- `run_config`: class/spec/level/encounter/search settings
- `assumptions`: report-level assumptions
- `warnings`: report-level warnings
- `class_summaries`: summaries derived from spec results
- `spec_results`: one row per class/spec/encounter profile

## Spec Result

- `class_name`
- `spec_id`
- `spec_name`
- `level`
- `encounter_profile_id`
- `search_profile_id`
- `scoring_profile_id`
- `apl_profile_id`
- `top_builds`
- `warnings`

## Build Result

- `rank`
- `projected_dps_index`
- `confidence_label`
- `selected_nodes`
- `score_breakdown`
- `generated_apl`
- `explanation`
- `provenance`
- `warnings`

`projected_dps_index` is a theorycraft index. It is not raw DPS, simulated DPS, observed DPS, or empirical DPS.
```

- [ ] **Step 2: Update module documentation**

Append to `docs/MODULES.md`:

```markdown

## Meta Report Runner

- `coa_meta.reporting`: expands class/spec scopes, applies eligibility rules, runs legal search, scoring, APL generation, and writes canonical report data.
- `coa_meta.report_assets`: resolves optional local scraper assets for static HTML output.

M1.6 reports use `coa-meta-report-v1`. JSON is canonical; Markdown and HTML are derived views.
```

- [ ] **Step 3: Record design decisions**

Append to `docs/DECISIONS.md`:

```markdown

## M1.6 Meta Report Scope

- Default reports rank top 3 builds per reportable class/spec for one `baseline_single_target` encounter profile.
- Reportable specs are normalized non-shared talent trees with nodes.
- `Class` is a shared class pool included in each spec's legal node set.
- `None` and metadata-only tabs are not standalone report rows.
- Lower-level runs filter known `required_level` data and warn when class/trainer source data is incomplete.
```

- [ ] **Step 4: Run full verification**

Run:

```bash
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit docs and verification checkpoint**

```bash
git add docs/data/meta-report-schema.md docs/MODULES.md docs/DECISIONS.md
git commit -m "docs: document meta report schema"
```

## M1.6 Completion Gate

Run:

```bash
python -m pytest -q
```

Expected: all tests pass.

M1.6 is complete when package APIs can generate JSON, Markdown, and static HTML report outputs from normalized artifacts without invoking a CLI entry point.
