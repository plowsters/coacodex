# M1.3 Legal Build Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract and harden the legal build engine so selected CoA builds can be validated, explained, serialized, and searched independently from scoring.

**Architecture:** Add a small `coa_meta/` Python package with domain, repository, legal rules, search, and explanation modules. Keep the existing optimizer script available, but make tests target the package modules directly.

**Tech Stack:** Python 3.11+ standard library, `pytest`, normalized `coa-normalized-v1` JSON/JSONL artifacts.

---

## File Structure

Create:

- `coa_meta/__init__.py`: package marker and public version.
- `coa_meta/domain.py`: dataclasses for nodes, classes, build states, selected ranks, validation issues, and validation results.
- `coa_meta/repository.py`: loader and indexes for normalized artifacts.
- `coa_meta/builds.py`: `BuildRules` and build validation logic.
- `coa_meta/search.py`: legal beam search.
- `coa_meta/explain.py`: report-ready dictionary conversion.
- `tests/fixtures/legal_build_fixture.jsonl`: minimal self-contained fixture data.
- `tests/fixtures/builder_examples.json`: known valid and invalid selected-build fixtures.
- `tests/test_repository.py`: repository loading tests.
- `tests/test_build_rules.py`: legality tests.
- `tests/test_build_search.py`: search tests.
- `docs/data/build-state-schema.md`: build-state serialization docs.

Modify:

- `docs/MODULES.md`: mark M1.3 package files as the target legal build implementation.

---

### Task 1: Repository and Domain Red Test

**Files:**

- Create: `tests/fixtures/legal_build_fixture.jsonl`
- Create: `tests/test_repository.py`

- [ ] **Step 1: Write fixture data**

Create `tests/fixtures/legal_build_fixture.jsonl`:

```jsonl
{"schema_version":"coa-normalized-v1","build_id":39,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":10,"tab_name":"Class","tab_sort_order":0,"entry_type":"Ability","essence_kind":"ability","essence_type":"abilityEssence","entry_id":100,"spell_id":1000,"spell_ids":[1000],"name":"Free Form","icon":null,"ae_cost":0,"te_cost":0,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Free class mechanic.","required_level":0,"max_rank":1,"row":0,"col":0,"node_type":"SpendCircle","flags":0,"group":0,"is_passive":true,"is_starting_node":true,"required_ids":[],"connected_node_ids":[101],"tags":[],"damage_schools":[],"resources":[],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":39,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":10,"tab_name":"Class","tab_sort_order":0,"entry_type":"Ability","essence_kind":"ability","essence_type":"abilityEssence","entry_id":101,"spell_id":1001,"spell_ids":[1001],"name":"Builder Strike","icon":null,"ae_cost":1,"te_cost":0,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Generates Energy.","required_level":0,"max_rank":1,"row":1,"col":0,"node_type":"SpendSquare","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[100],"connected_node_ids":[102],"tags":["builder"],"damage_schools":["physical"],"resources":["Energy"],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":39,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":11,"tab_name":"Damage","tab_sort_order":1,"entry_type":"Talent","essence_kind":"talent","essence_type":"talentEssence","entry_id":102,"spell_id":1002,"spell_ids":[1002],"name":"Poison Talent","icon":null,"ae_cost":0,"te_cost":1,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Increases Nature damage over time.","required_level":0,"max_rank":3,"row":1,"col":1,"node_type":"SpendCircle","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[],"connected_node_ids":[103],"tags":["dot"],"damage_schools":["nature"],"resources":[],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":39,"build_slug":"test","build_name":"Test Builder","class_id":1,"class_name":"Testclass","tab_id":11,"tab_name":"Damage","tab_sort_order":1,"entry_type":"Talent","essence_kind":"talent","essence_type":"talentEssence","entry_id":103,"spell_id":1003,"spell_ids":[1003],"name":"Deep Poison","icon":null,"ae_cost":0,"te_cost":1,"required_tab_ae":0,"required_tab_te":2,"description_html":"","description_text":"Requires investment in Damage.","required_level":0,"max_rank":1,"row":2,"col":1,"node_type":"SpendCircle","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[102],"connected_node_ids":[],"tags":["dot"],"damage_schools":["nature"],"resources":[],"field_sources":{},"inferred":{},"raw":{}}
{"schema_version":"coa-normalized-v1","build_id":39,"build_slug":"test","build_name":"Test Builder","class_id":2,"class_name":"Otherclass","tab_id":20,"tab_name":"Class","tab_sort_order":0,"entry_type":"Ability","essence_kind":"ability","essence_type":"abilityEssence","entry_id":200,"spell_id":2000,"spell_ids":[2000],"name":"Other Ability","icon":null,"ae_cost":1,"te_cost":0,"required_tab_ae":0,"required_tab_te":0,"description_html":"","description_text":"Other class ability.","required_level":0,"max_rank":1,"row":0,"col":0,"node_type":"SpendSquare","flags":0,"group":0,"is_passive":false,"is_starting_node":false,"required_ids":[],"connected_node_ids":[],"tags":[],"damage_schools":[],"resources":[],"field_sources":{},"inferred":{},"raw":{}}
```

- [ ] **Step 2: Write failing repository tests**

Create `tests/test_repository.py`:

```python
from pathlib import Path

import pytest

from coa_meta.repository import TalentRepository, RepositoryLoadError


FIXTURE = Path(__file__).parent / "fixtures" / "legal_build_fixture.jsonl"


def test_repository_loads_nodes_by_class_and_name():
    repo = TalentRepository.from_entries(FIXTURE)

    nodes = repo.nodes_for_class("Testclass")

    assert len(nodes) == 4
    assert repo.node_by_name("Testclass", "poison talent").entry_id == 102
    assert repo.node_by_id(101).class_name == "Testclass"


def test_repository_rejects_wrong_schema_version(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(FIXTURE.read_text().replace("coa-normalized-v1", "old-version", 1), encoding="utf-8")

    with pytest.raises(RepositoryLoadError, match="schema_version"):
        TalentRepository.from_entries(bad)
```

- [ ] **Step 3: Run red test**

Run:

```bash
pytest tests/test_repository.py -q
```

Expected: fails because `coa_meta.repository` does not exist.

---

### Task 2: Implement Domain and Repository

**Files:**

- Create: `coa_meta/__init__.py`
- Create: `coa_meta/domain.py`
- Create: `coa_meta/repository.py`

- [ ] **Step 1: Add package marker**

Create `coa_meta/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 2: Add domain dataclasses**

Create `coa_meta/domain.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EssenceKind = Literal["ability", "talent", "unknown"]


@dataclass(frozen=True)
class TalentNode:
    entry_id: int
    spell_id: int | None
    name: str
    class_id: int
    class_name: str
    tab_id: int
    tab_name: str
    entry_type: str
    essence_kind: EssenceKind
    ae_cost: int
    te_cost: int
    required_tab_ae: int
    required_tab_te: int
    required_level: int
    max_rank: int
    row: int
    col: int
    node_type: str
    is_passive: bool
    is_starting_node: bool
    required_ids: tuple[int, ...]
    connected_node_ids: tuple[int, ...]
    tags: tuple[str, ...]
    damage_schools: tuple[str, ...]
    resources: tuple[str, ...]
    description_text: str
    raw: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    @property
    def paid(self) -> bool:
        return self.ae_cost > 0 or self.te_cost > 0


@dataclass(frozen=True)
class SelectedRank:
    node_id: int
    rank: int = 1


@dataclass(frozen=True)
class BuildState:
    class_name: str
    selected_ranks: tuple[SelectedRank, ...]
    free_node_ids: tuple[int, ...]
    ae_spent: int
    te_spent: int
    tab_ae: tuple[tuple[int, int], ...]
    tab_te: tuple[tuple[int, int], ...]

    @property
    def selected_ids(self) -> frozenset[int]:
        return frozenset(rank.node_id for rank in self.selected_ranks) | frozenset(self.free_node_ids)

    def rank_for(self, node_id: int) -> int:
        for selected in self.selected_ranks:
            if selected.node_id == node_id:
                return selected.rank
        return 1 if node_id in self.free_node_ids else 0

    def tab_ae_map(self) -> dict[int, int]:
        return dict(self.tab_ae)

    def tab_te_map(self) -> dict[int, int]:
        return dict(self.tab_te)

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_name": self.class_name,
            "selected_ranks": [{"node_id": r.node_id, "rank": r.rank} for r in self.selected_ranks],
            "free_node_ids": list(self.free_node_ids),
            "ae_spent": self.ae_spent,
            "te_spent": self.te_spent,
            "tab_ae": dict(self.tab_ae),
            "tab_te": dict(self.tab_te),
        }


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    node_id: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildValidationResult:
    valid: bool
    state: BuildState | None
    issues: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...] = tuple()

    def issue_codes(self) -> list[str]:
        return [issue.code for issue in self.issues]
```

- [ ] **Step 3: Add repository loader**

Create `coa_meta/repository.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .domain import TalentNode

SCHEMA_VERSION = "coa-normalized-v1"


class RepositoryLoadError(ValueError):
    pass


def _as_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _int_tuple(values: list[Any] | None) -> tuple[int, ...]:
    out: list[int] = []
    for value in values or []:
        parsed = _as_int(value)
        if parsed:
            out.append(parsed)
    return tuple(out)


def node_from_raw(raw: dict[str, Any], source: str) -> TalentNode:
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise RepositoryLoadError(f"{source} has unsupported schema_version {raw.get('schema_version')!r}")
    entry_id = _as_int(raw.get("entry_id"))
    if not entry_id:
        raise RepositoryLoadError(f"{source} missing numeric entry_id")
    return TalentNode(
        entry_id=entry_id,
        spell_id=_as_int(raw.get("spell_id")) or None,
        name=raw.get("name") or "",
        class_id=_as_int(raw.get("class_id")),
        class_name=raw.get("class_name") or "",
        tab_id=_as_int(raw.get("tab_id")),
        tab_name=raw.get("tab_name") or "",
        entry_type=raw.get("entry_type") or "",
        essence_kind=raw.get("essence_kind") or "unknown",
        ae_cost=_as_int(raw.get("ae_cost")),
        te_cost=_as_int(raw.get("te_cost")),
        required_tab_ae=_as_int(raw.get("required_tab_ae")),
        required_tab_te=_as_int(raw.get("required_tab_te")),
        required_level=_as_int(raw.get("required_level")),
        max_rank=max(1, _as_int(raw.get("max_rank"), 1)),
        row=_as_int(raw.get("row")),
        col=_as_int(raw.get("col")),
        node_type=raw.get("node_type") or "",
        is_passive=bool(raw.get("is_passive")),
        is_starting_node=bool(raw.get("is_starting_node")),
        required_ids=_int_tuple(raw.get("required_ids")),
        connected_node_ids=_int_tuple(raw.get("connected_node_ids")),
        tags=tuple(raw.get("tags") or []),
        damage_schools=tuple(raw.get("damage_schools") or []),
        resources=tuple(raw.get("resources") or []),
        description_text=raw.get("description_text") or "",
        raw=raw,
    )


class TalentRepository:
    def __init__(self, nodes: list[TalentNode]):
        self._nodes = nodes
        self._by_id = {node.entry_id: node for node in nodes}
        self._by_class: dict[str, list[TalentNode]] = {}
        self._by_name: dict[tuple[str, str], TalentNode] = {}
        for node in nodes:
            self._by_class.setdefault(node.class_name, []).append(node)
            self._by_name[(node.class_name, node.name.lower())] = node

    @classmethod
    def from_entries(cls, entries_path: Path | str) -> "TalentRepository":
        path = Path(entries_path)
        nodes: list[TalentNode] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RepositoryLoadError(f"{path}:{line_no} invalid JSON: {exc}") from exc
                nodes.append(node_from_raw(raw, f"{path}:{line_no}"))
        return cls(nodes)

    def node_by_id(self, node_id: int) -> TalentNode:
        return self._by_id[node_id]

    def get_node(self, node_id: int) -> TalentNode | None:
        return self._by_id.get(node_id)

    def node_by_name(self, class_name: str, name: str) -> TalentNode:
        return self._by_name[(class_name, name.lower())]

    def nodes_for_class(self, class_name: str) -> list[TalentNode]:
        return list(self._by_class.get(class_name, []))

    def class_names(self) -> list[str]:
        return sorted(self._by_class)
```

- [ ] **Step 4: Run repository tests**

Run:

```bash
pytest tests/test_repository.py -q
```

Expected: 2 passed.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add coa_meta tests/fixtures/legal_build_fixture.jsonl tests/test_repository.py
git commit -m "feat: add CoA domain repository"
```

---

### Task 3: Legal Rules Red Tests

**Files:**

- Create: `tests/test_build_rules.py`
- Create: `tests/fixtures/builder_examples.json`

- [ ] **Step 1: Write builder examples**

Create `tests/fixtures/builder_examples.json`:

```json
[
  {
    "name": "valid minimal class ability",
    "class_name": "Testclass",
    "level": 60,
    "max_ae": 2,
    "max_te": 3,
    "selected": [{"node_id": 101, "rank": 1}],
    "expected_valid": true,
    "expected_issue_codes": []
  },
  {
    "name": "invalid missing prerequisite",
    "class_name": "Testclass",
    "level": 60,
    "max_ae": 2,
    "max_te": 3,
    "selected": [{"node_id": 103, "rank": 1}],
    "expected_valid": false,
    "expected_issue_codes": ["tab_te_gate_unmet", "required_node_missing"]
  }
]
```

- [ ] **Step 2: Write failing legality tests**

Create `tests/test_build_rules.py`:

```python
import json
from pathlib import Path

from coa_meta.builds import BuildConfig, BuildRules
from coa_meta.domain import SelectedRank
from coa_meta.repository import TalentRepository


FIXTURE = Path(__file__).parent / "fixtures" / "legal_build_fixture.jsonl"
EXAMPLES = Path(__file__).parent / "fixtures" / "builder_examples.json"


def rules(level=60, max_ae=2, max_te=3):
    repo = TalentRepository.from_entries(FIXTURE)
    return BuildRules(repo, BuildConfig(class_name="Testclass", level=level, max_ae=max_ae, max_te=max_te))


def test_free_zero_cost_closure_is_in_initial_state():
    state = rules().initial_state()

    assert state.free_node_ids == (100,)
    assert state.ae_spent == 0
    assert state.te_spent == 0


def test_valid_build_serializes_spend_and_ranks():
    result = rules().validate([SelectedRank(101, 1), SelectedRank(102, 2)])

    assert result.valid is True
    assert result.state is not None
    assert result.state.ae_spent == 1
    assert result.state.te_spent == 2
    assert result.state.to_dict()["selected_ranks"] == [{"node_id": 101, "rank": 1}, {"node_id": 102, "rank": 2}]


def test_missing_prerequisite_and_tab_gate_are_explained():
    result = rules().validate([SelectedRank(103, 1)])

    assert result.valid is False
    assert "required_node_missing" in result.issue_codes()
    assert "tab_te_gate_unmet" in result.issue_codes()


def test_budget_and_rank_failures_are_explained():
    result = rules(max_te=2).validate([SelectedRank(102, 4)])

    assert result.valid is False
    assert "rank_above_maximum" in result.issue_codes()
    assert "te_budget_exceeded" in result.issue_codes()


def test_wrong_class_node_is_explained():
    result = rules().validate([SelectedRank(200, 1)])

    assert result.valid is False
    assert "wrong_class" in result.issue_codes()


def test_builder_example_fixture_expectations():
    engine = rules()
    examples = json.loads(EXAMPLES.read_text(encoding="utf-8"))

    for example in examples:
        selected = [SelectedRank(item["node_id"], item.get("rank", 1)) for item in example["selected"]]
        result = engine.validate(selected)
        assert result.valid is example["expected_valid"], example["name"]
        for code in example["expected_issue_codes"]:
            assert code in result.issue_codes(), example["name"]
```

- [ ] **Step 3: Run red tests**

Run:

```bash
pytest tests/test_build_rules.py -q
```

Expected: fails because `coa_meta.builds` does not exist.

---

### Task 4: Implement Legal Rules

**Files:**

- Create: `coa_meta/builds.py`

- [ ] **Step 1: Add legal rule implementation**

Create `coa_meta/builds.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from .domain import BuildState, BuildValidationResult, SelectedRank, TalentNode, ValidationIssue
from .repository import TalentRepository


@dataclass(frozen=True)
class BuildConfig:
    class_name: str
    level: int = 60
    max_ae: int = 26
    max_te: int = 25


class BuildRules:
    def __init__(self, repository: TalentRepository, config: BuildConfig):
        self.repository = repository
        self.config = config
        self.nodes = {node.entry_id: node for node in repository.nodes_for_class(config.class_name)}

    def initial_state(self) -> BuildState:
        selected: set[int] = set()
        changed = True
        while changed:
            changed = False
            for node in self.nodes.values():
                if node.entry_id in selected or node.paid or node.required_level > self.config.level:
                    continue
                if all(req in selected or req not in self.nodes for req in node.required_ids):
                    selected.add(node.entry_id)
                    changed = True
        return BuildState(
            class_name=self.config.class_name,
            selected_ranks=tuple(),
            free_node_ids=tuple(sorted(selected)),
            ae_spent=0,
            te_spent=0,
            tab_ae=tuple(),
            tab_te=tuple(),
        )

    def validate(self, selected: list[SelectedRank]) -> BuildValidationResult:
        issues: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        by_id: dict[int, int] = {}

        for item in selected:
            if item.node_id in by_id:
                issues.append(ValidationIssue("duplicate_node", f"Node {item.node_id} selected more than once", item.node_id))
            by_id[item.node_id] = item.rank

        free_ids = set(self.initial_state().free_node_ids)
        selected_ids = set(by_id) | free_ids
        ae_spent = 0
        te_spent = 0
        tab_ae: dict[int, int] = {}
        tab_te: dict[int, int] = {}

        for node_id, rank in by_id.items():
            node = self.repository.get_node(node_id)
            if node is None:
                issues.append(ValidationIssue("unknown_node", f"Unknown node {node_id}", node_id))
                continue
            if node.class_name != self.config.class_name:
                issues.append(ValidationIssue("wrong_class", f"{node.name} belongs to {node.class_name}", node_id))
                continue
            if rank < 1:
                issues.append(ValidationIssue("rank_below_minimum", f"{node.name} rank must be at least 1", node_id, {"rank": rank}))
            if rank > node.max_rank:
                issues.append(ValidationIssue("rank_above_maximum", f"{node.name} rank {rank} exceeds max rank {node.max_rank}", node_id, {"rank": rank, "max_rank": node.max_rank}))
            paid_rank = max(rank, 1)
            ae_spent += node.ae_cost * paid_rank
            te_spent += node.te_cost * paid_rank
            tab_ae[node.tab_id] = tab_ae.get(node.tab_id, 0) + node.ae_cost * paid_rank
            tab_te[node.tab_id] = tab_te.get(node.tab_id, 0) + node.te_cost * paid_rank

        if ae_spent > self.config.max_ae:
            issues.append(ValidationIssue("ae_budget_exceeded", "Ability Essence budget exceeded", None, {"spent": ae_spent, "max": self.config.max_ae}))
        if te_spent > self.config.max_te:
            issues.append(ValidationIssue("te_budget_exceeded", "Talent Essence budget exceeded", None, {"spent": te_spent, "max": self.config.max_te}))

        for node_id, rank in by_id.items():
            node = self.nodes.get(node_id)
            if node is None:
                continue
            self._validate_node_requirements(node, rank, selected_ids, tab_ae, tab_te, issues)

        normalized = tuple(SelectedRank(node_id, by_id[node_id]) for node_id in sorted(by_id))
        state = BuildState(
            class_name=self.config.class_name,
            selected_ranks=normalized,
            free_node_ids=tuple(sorted(free_ids)),
            ae_spent=ae_spent,
            te_spent=te_spent,
            tab_ae=tuple(sorted(tab_ae.items())),
            tab_te=tuple(sorted(tab_te.items())),
        )
        return BuildValidationResult(valid=not issues, state=state, issues=tuple(issues), warnings=tuple(warnings))

    def can_add(self, state: BuildState, node: TalentNode, rank: int = 1) -> BuildValidationResult:
        selected = list(state.selected_ranks) + [SelectedRank(node.entry_id, rank)]
        return self.validate(selected)

    def add(self, state: BuildState, node: TalentNode, rank: int = 1) -> BuildState:
        result = self.can_add(state, node, rank)
        if not result.valid or result.state is None:
            codes = ", ".join(result.issue_codes())
            raise ValueError(f"Cannot add {node.name}: {codes}")
        return result.state

    def _validate_node_requirements(
        self,
        node: TalentNode,
        rank: int,
        selected_ids: set[int],
        tab_ae: dict[int, int],
        tab_te: dict[int, int],
        issues: list[ValidationIssue],
    ) -> None:
        if node.required_level > self.config.level:
            issues.append(ValidationIssue("level_required", f"{node.name} requires level {node.required_level}", node.entry_id, {"required_level": node.required_level}))
        available_tab_ae = tab_ae.get(node.tab_id, 0) - node.ae_cost * max(rank, 1)
        available_tab_te = tab_te.get(node.tab_id, 0) - node.te_cost * max(rank, 1)
        if available_tab_ae < node.required_tab_ae:
            issues.append(ValidationIssue("tab_ae_gate_unmet", f"{node.name} requires {node.required_tab_ae} AE in {node.tab_name}", node.entry_id, {"available": available_tab_ae, "required": node.required_tab_ae}))
        if available_tab_te < node.required_tab_te:
            issues.append(ValidationIssue("tab_te_gate_unmet", f"{node.name} requires {node.required_tab_te} TE in {node.tab_name}", node.entry_id, {"available": available_tab_te, "required": node.required_tab_te}))
        for required_id in node.required_ids:
            if required_id in self.nodes and required_id not in selected_ids:
                issues.append(ValidationIssue("required_node_missing", f"{node.name} requires node {required_id}", node.entry_id, {"required_id": required_id}))
```

- [ ] **Step 2: Run legality tests**

Run:

```bash
pytest tests/test_build_rules.py -q
```

Expected: 6 passed.

- [ ] **Step 3: Run repository and legality tests together**

Run:

```bash
pytest tests/test_repository.py tests/test_build_rules.py -q
```

Expected: 8 passed.

- [ ] **Step 4: Commit Task 4**

Run:

```bash
git add coa_meta/builds.py tests/test_build_rules.py tests/fixtures/builder_examples.json
git commit -m "feat: add legal build validation"
```

---

### Task 5: Search Red Tests

**Files:**

- Create: `tests/test_build_search.py`

- [ ] **Step 1: Write failing search tests**

Create `tests/test_build_search.py`:

```python
from pathlib import Path

from coa_meta.builds import BuildConfig, BuildRules
from coa_meta.repository import TalentRepository
from coa_meta.search import BuildSearchConfig, BuildSearcher


FIXTURE = Path(__file__).parent / "fixtures" / "legal_build_fixture.jsonl"


def test_search_uses_legal_rules_and_returns_serializable_states():
    repo = TalentRepository.from_entries(FIXTURE)
    rules = BuildRules(repo, BuildConfig(class_name="Testclass", level=60, max_ae=2, max_te=3))
    searcher = BuildSearcher(repo, rules)

    results = searcher.search(BuildSearchConfig(top=3, beam_width=5, branch_width=5))

    assert results
    assert all(result.valid for result in results)
    assert all(result.state is not None for result in results)
    assert results[0].state.to_dict()["class_name"] == "Testclass"
    assert 100 in results[0].state.free_node_ids


def test_search_does_not_return_builds_that_fail_tab_gates():
    repo = TalentRepository.from_entries(FIXTURE)
    rules = BuildRules(repo, BuildConfig(class_name="Testclass", level=60, max_ae=2, max_te=1))
    searcher = BuildSearcher(repo, rules)

    results = searcher.search(BuildSearchConfig(top=10, beam_width=5, branch_width=5))

    for result in results:
        selected_ids = result.state.selected_ids
        assert 103 not in selected_ids
```

- [ ] **Step 2: Run red search tests**

Run:

```bash
pytest tests/test_build_search.py -q
```

Expected: fails because `coa_meta.search` does not exist.

---

### Task 6: Implement Legal Search

**Files:**

- Create: `coa_meta/search.py`
- Create: `coa_meta/explain.py`

- [ ] **Step 1: Add search module**

Create `coa_meta/search.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from .builds import BuildRules
from .domain import BuildValidationResult, SelectedRank
from .repository import TalentRepository


@dataclass(frozen=True)
class BuildSearchConfig:
    top: int = 10
    beam_width: int = 10
    branch_width: int = 40
    require_budget_fraction: float = 0.0


class BuildSearcher:
    def __init__(self, repository: TalentRepository, rules: BuildRules):
        self.repository = repository
        self.rules = rules

    def search(self, config: BuildSearchConfig) -> list[BuildValidationResult]:
        start = self.rules.initial_state()
        paid_nodes = [node for node in self.rules.nodes.values() if node.paid]
        beam = [start]
        seen = {tuple()}
        results: list[BuildValidationResult] = [BuildValidationResult(True, start, tuple())]
        max_steps = max(1, self.rules.config.max_ae + self.rules.config.max_te)

        for _ in range(max_steps):
            candidates = []
            for state in beam:
                legal_added = []
                for node in paid_nodes:
                    if node.entry_id in state.selected_ids:
                        continue
                    result = self.rules.can_add(state, node, 1)
                    if result.valid and result.state is not None:
                        key = tuple(sorted((rank.node_id, rank.rank) for rank in result.state.selected_ranks))
                        if key in seen:
                            continue
                        seen.add(key)
                        legal_added.append(result)
                legal_added.sort(key=lambda item: self._search_score(item), reverse=True)
                candidates.extend(legal_added[: config.branch_width])
            if not candidates:
                break
            candidates.sort(key=self._search_score, reverse=True)
            beam = [item.state for item in candidates[: config.beam_width] if item.state is not None]
            results.extend(candidates)

        min_spend = (self.rules.config.max_ae + self.rules.config.max_te) * config.require_budget_fraction
        filtered = [item for item in results if item.state and item.state.ae_spent + item.state.te_spent >= min_spend]
        filtered.sort(key=self._search_score, reverse=True)
        return filtered[: config.top]

    def _search_score(self, result: BuildValidationResult) -> float:
        if result.state is None:
            return -1.0
        return result.state.ae_spent + result.state.te_spent + len(result.state.selected_ranks) * 0.01
```

- [ ] **Step 2: Add explanation module**

Create `coa_meta/explain.py`:

```python
from __future__ import annotations

from .domain import BuildValidationResult, ValidationIssue


def issue_to_dict(issue: ValidationIssue) -> dict:
    return {
        "code": issue.code,
        "message": issue.message,
        "node_id": issue.node_id,
        "details": issue.details,
    }


def validation_to_dict(result: BuildValidationResult) -> dict:
    return {
        "valid": result.valid,
        "state": result.state.to_dict() if result.state else None,
        "issues": [issue_to_dict(issue) for issue in result.issues],
        "warnings": [issue_to_dict(issue) for issue in result.warnings],
    }
```

- [ ] **Step 3: Run search tests**

Run:

```bash
pytest tests/test_build_search.py -q
```

Expected: 2 passed.

- [ ] **Step 4: Run all M1.3 tests**

Run:

```bash
pytest tests/test_repository.py tests/test_build_rules.py tests/test_build_search.py -q
```

Expected: 10 passed.

- [ ] **Step 5: Commit Task 6**

Run:

```bash
git add coa_meta/search.py coa_meta/explain.py tests/test_build_search.py
git commit -m "feat: add legal build search"
```

---

### Task 7: Documentation and Current Artifact Smoke Test

**Files:**

- Create: `docs/data/build-state-schema.md`
- Modify: `docs/MODULES.md`

- [ ] **Step 1: Add build-state schema docs**

Create `docs/data/build-state-schema.md`:

```markdown
# Build State Schema

Build states are serializable records produced by the M1.3 legal build engine.

## Fields

- `class_name`: CoA class name.
- `selected_ranks`: paid selected nodes as `{node_id, rank}` records.
- `free_node_ids`: zero-cost starting/passive nodes auto-included by legal closure.
- `ae_spent`: total Ability Essence spent by paid selections.
- `te_spent`: total Talent Essence spent by paid selections.
- `tab_ae`: per-tab Ability Essence spend.
- `tab_te`: per-tab Talent Essence spend.

## Rank Model

If a selected node omits rank, rank defaults to `1`. Cost is currently multiplied by selected rank. This is an intentional M1.3 model until official per-rank cost behavior is validated against builder UI examples.

## Validation Output

Validation returns `valid`, `state`, `issues`, and `warnings`. Issue objects include stable `code` values for tests and downstream reporting.
```

- [ ] **Step 2: Update module docs**

In `docs/MODULES.md`, under `## Build Legality and Search Module`, add:

```markdown
M1.3 implementation files:

- `coa_meta/domain.py`
- `coa_meta/repository.py`
- `coa_meta/builds.py`
- `coa_meta/search.py`
- `coa_meta/explain.py`
```

- [ ] **Step 3: Add smoke test against current generated artifacts**

Run:

```bash
python - <<'PY'
from pathlib import Path
from coa_meta.builds import BuildConfig, BuildRules
from coa_meta.repository import TalentRepository
from coa_meta.search import BuildSearchConfig, BuildSearcher

repo = TalentRepository.from_entries(Path("coa_scraper/dist/coa_entries.jsonl"))
rules = BuildRules(repo, BuildConfig(class_name="Venomancer", level=60, max_ae=26, max_te=25))
results = BuildSearcher(repo, rules).search(BuildSearchConfig(top=3, beam_width=5, branch_width=10))
print(len(results), results[0].state.class_name if results else "none")
PY
```

Expected output:

```text
3 Venomancer
```

- [ ] **Step 4: Run full verification**

Run:

```bash
pytest tests/test_repository.py tests/test_build_rules.py tests/test_build_search.py -q
npm test --prefix coa_scraper
```

Expected:

- `pytest`: 10 passed.
- `npm test`: unit test and validation pass.

- [ ] **Step 5: Commit M1.3 docs**

Run:

```bash
git add docs/data/build-state-schema.md docs/MODULES.md
git commit -m "docs: document legal build state schema"
```

---

### Task 8: M1.3 Completion Gate

**Files:**

- Verify only.

- [ ] **Step 1: Check milestone requirements**

Run:

```bash
python - <<'PY'
from pathlib import Path
required = [
    Path("coa_meta/domain.py"),
    Path("coa_meta/repository.py"),
    Path("coa_meta/builds.py"),
    Path("coa_meta/search.py"),
    Path("coa_meta/explain.py"),
    Path("docs/data/build-state-schema.md"),
]
missing = [str(path) for path in required if not path.exists()]
if missing:
    print("missing:", missing)
    raise SystemExit(1)
print("m1.3 files present")
PY
```

Expected output:

```text
m1.3 files present
```

- [ ] **Step 2: Check git status**

Run:

```bash
git status --short
```

Expected: no uncommitted M1.3 changes.
