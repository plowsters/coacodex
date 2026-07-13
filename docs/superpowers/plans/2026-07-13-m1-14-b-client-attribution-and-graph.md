# M1.14B Client Attribution and CoA Advancement Graph — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the client's `CharacterAdvancement.dbc` CoA advancement graph, attribute every spell to CoA/Reborn/stock from client-native evidence, emit the `coa-client-advancement-v1` artifact plus class-type/essence metadata, and prove it node-by-node against the CoA Builder oracle — without rewiring the legality/tree pipeline (that stays M1.15).

**Architecture:** Additive to the M1.14A `coa_client_extract` module. Reuse its `ArchiveBackend`, header-driven `wdbc` reader, `manifest`, and provenance. New pure modules (`class_types`, `advancement`, `attribution`, `parity`) are unit-tested through synthetic fixtures and the existing `FakeArchiveBackend`; the exact `CharacterAdvancement` column layout is *decoded and semantically validated* against the real client (client tier), never assumed from a matching WDBC header.

**Tech Stack:** Python 3 (stdlib only for the package: `struct`, `dataclasses`, `hashlib`, `json`, `pathlib`), `pytest` with markers `stormlib`/`client`, StormLib (extraction-time only).

Design spec: [M1.14B Client Attribution and CoA Advancement Graph](../specs/2026-07-13-m1-14-b-client-attribution-and-graph-design.md).

## Global Constraints

- **Additive only.** Do not modify the Builder graph pipeline, `coa_meta` repository, reports, or guides. M1.14B produces artifacts + a parity report; nothing downstream consumes them yet.
- **StormLib is extraction-time only.** Never import it from `coa_meta`/report/guide paths. Default `pytest` run (`-m 'not stormlib and not client'`) must stay green with no StormLib and no client, via `FakeArchiveBackend` + synthetic fixtures.
- **Fail closed** (Decision 20). The regenerate CLI writes *nothing* without StormLib. Read the **effective patch-chain** copy of every table (never `patch-M` directly).
- **Committed fixtures are synthetic / self-authored** — never client asset bytes (redistribution boundary).
- **The Builder is never an input** to membership or mode attribution. It is the oracle used only to *measure* the model (the parity report). Curated display aliases are presentation metadata with provenance, not attribution inputs.
- **Semantic validation gates canonical emission.** A layout field that is not proven to `confidence: high` (FK resolves, adjacency resolves in its proven domain, scalars in range) blocks emission of that field — a matching WDBC header is not sufficient.
- **Verified structural anchors** (real client, 2026-07-13): `CharacterAdvancement.dbc` node id = column 0, spell id = column 5, class-type FK = column 32. Every other column is decoded, not assumed.
- **Class taxonomy:** `CharacterAdvancementClassTypes` ids 14–34 = 21 playable CoA classes; **35 = `ConquestOfAzeroth` sentinel (non-playable)**; 36–46 = Reborn. Alpha→display aliases (curated): `22 SonOfArugal→Bloodmage`, `16 DemonHunter→Felsworn`, `21 Monk→Templar`.
- **Observed headers** (expected values for drift checks; real client): `CharacterAdvancement` field_count 179 / record_size 692; `CharacterAdvancementClassTypes` 23 / 92; `CharacterAdvancementTabTypes` 19 / 76; `CharacterAdvancementCategories` 39 / 156; `CharacterAdvancementEssence` 9 / 36; `SkillLine` 56 / 224; `SkillLineAbility` 14 / 56.

---

## File Structure

**New files:**
- `coa_client_extract/class_types.py` — resolve `CharacterAdvancementClassTypes`/`TabTypes` into a versioned classification (`kind`), apply curated display aliases, assert the 21-class cardinality.
- `coa_client_extract/advancement.py` — read `CharacterAdvancement`, join companions, build `AdvancementNode`s with legality + `field_confidence` + raw slots; run semantic validators.
- `coa_client_extract/attribution.py` — participation model (`is_coa`/`modes`/`exclusive_mode`) + `memberships[]` from the node graph; deterministic truth table; skill-line fallback.
- `coa_client_extract/parity.py` — node-level (multiset) Builder-parity report.
- `coa_client_extract/decode_advancement.py` — the client-tier decode harness that determines the `CharacterAdvancement` column layout by JSON-correlation + semantic proof and writes a decode report.
- `tests/test_client_extract_class_types.py`, `tests/test_client_extract_advancement.py`, `tests/test_client_extract_advancement_semantic.py`, `tests/test_client_extract_attribution.py`, `tests/test_client_extract_parity.py`
- `docs/data/client-advancement-schema.md`, `docs/data/client-class-types-schema.md`

**Modified files:**
- `coa_client_extract/errors.py` — add `DbcSemanticError`.
- `coa_client_extract/wdbc.py` — add `parse_positional` + `PositionalDbc` (raw index-keyed reader for wide tables).
- `coa_client_extract/dbc_layouts.py` — add companion layouts, the `CharacterAdvancementLayout`/`EssenceCapLayout` dataclasses, and the decoded `CHARACTER_ADVANCEMENT` constant.
- `coa_client_extract/artifacts.py` — advancement/class-type/essence-cap record writers; fill `coa_attribution` on spell records.
- `coa_client_extract/cli.py` — wire the new readers and outputs into `regenerate`.
- `tests/test_client_extract_artifacts.py`, `tests/test_client_extract_cli.py`, `tests/test_client_extract_acceptance.py` — extend.
- `docs/data/client-spell-schema.md`, `docs/data/client-content-schema.md`, `docs/DECISIONS.md`, `docs/superpowers/specs/2026-07-06-m1-14-client-dbc-data-foundation-design.md`, `docs/ROADMAP.md`.

**Shared interfaces (defined by the tasks below; listed here so tasks can be read out of order):**
- `class_types.ClassType(class_type_id:int, internal:str, display:str, kind:str)` — `kind ∈ {"coa_class","coa_system","reborn","stock","meta"}`.
- `class_types.resolve_class_types(table: DbcTable) -> dict[int, ClassType]`
- `class_types.resolve_tab_types(table: DbcTable) -> dict[int, str]`
- `class_types.assert_playable_cardinality(resolved: dict[int, ClassType]) -> None`
- `dbc_layouts.CharacterAdvancementLayout` — named column fields (below).
- `advancement.AdvancementNode` — dataclass (below).
- `advancement.read_advancement(ca: wdbc.PositionalDbc, class_types, tab_types, layout) -> list[AdvancementNode]` (consumes positional `{index: value}` rows).
- `advancement.validate_semantics(nodes, class_types, tab_types) -> None` (raises `DbcSemanticError`).
- `attribution.AttributionResult(is_coa:bool, modes:tuple[str,...], exclusive_mode:str|None, confidence:str)`
- `attribution.attribute(nodes, class_types, skill_line_index=None) -> dict[int, SpellAttribution]` where `SpellAttribution` has `.result: AttributionResult` and `.memberships: list[dict]`.
- `parity.build_parity_report(nodes, builder_entries) -> dict`

---

## Task 1: Class-type / tab-type resolver with cardinality assertion

**Files:**
- Create: `coa_client_extract/class_types.py`
- Test: `tests/test_client_extract_class_types.py`

**Interfaces:**
- Consumes: `wdbc.DbcTable` (from M1.14A) — `.rows: list[dict]` with a resolved `id` and a `name` string column.
- Produces: `ClassType`, `resolve_class_types`, `resolve_tab_types`, `assert_playable_cardinality`, `PLAYABLE_COA_IDS`, `COA_SENTINEL_ID`, `DISPLAY_ALIASES`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_extract_class_types.py
import pytest

from coa_client_extract.class_types import (
    ClassType, resolve_class_types, resolve_tab_types,
    assert_playable_cardinality, DISPLAY_ALIASES, COA_SENTINEL_ID,
)


class _Table:
    """Minimal stand-in for wdbc.DbcTable: only .rows is used here."""
    def __init__(self, rows): self.rows = rows


def _class_rows():
    # (id, name) pairs mirroring CharacterAdvancementClassTypes bands.
    named = {
        2: "Hunter", 11: "DeathKnight", 12: "General", 13: "Hero",
        14: "Barbarian", 15: "WitchDoctor", 16: "DemonHunter", 21: "Monk",
        22: "SonOfArugal", 33: "Venomancer", 34: "Runemaster",
        35: "ConquestOfAzeroth", 36: "RebornHunter", 46: "RebornGeneral",
    }
    # fill the whole 2..46 range so the cardinality check has all playable ids
    for i in range(2, 47):
        named.setdefault(i, f"Class{i}")
    return _Table([{"id": i, "name": named[i]} for i in sorted(named)])


def test_resolves_kind_bands_and_sentinel():
    resolved = resolve_class_types(_class_rows())
    assert resolved[33].kind == "coa_class"
    assert resolved[33].display == "Venomancer"
    assert resolved[COA_SENTINEL_ID].kind == "coa_system"   # 35, non-playable
    assert resolved[36].kind == "reborn"
    assert resolved[2].kind == "stock"
    assert resolved[12].kind == "meta"                       # General/Hero


def test_applies_curated_display_aliases_without_touching_identity():
    resolved = resolve_class_types(_class_rows())
    assert resolved[22].internal == "SonOfArugal"
    assert resolved[22].display == "Bloodmage"
    assert resolved[16].display == "Felsworn"
    assert resolved[21].display == "Templar"
    assert set(DISPLAY_ALIASES) == {22, 16, 21}


def test_cardinality_exactly_21_playable():
    resolved = resolve_class_types(_class_rows())
    assert_playable_cardinality(resolved)   # must not raise


def test_cardinality_raises_when_not_21():
    rows = [r for r in _class_rows().rows if r["id"] != 34]  # drop one playable class
    with pytest.raises(ValueError, match="expected 21 playable"):
        assert_playable_cardinality(resolve_class_types(_Table(rows)))


def test_tab_types_resolve_names():
    tabs = _Table([{"id": 1, "name": "Class"}, {"id": 49, "name": "Brewing"}])
    assert resolve_tab_types(tabs) == {1: "Class", 49: "Brewing"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_class_types.py -v`
Expected: FAIL with `ModuleNotFoundError: coa_client_extract.class_types`.

- [ ] **Step 3: Write the implementation**

```python
# coa_client_extract/class_types.py
from __future__ import annotations

from dataclasses import dataclass

# Verified against the real client (2026-07-13). Ids are CharacterAdvancementClassTypes row ids.
PLAYABLE_COA_IDS = range(14, 35)      # 14..34 inclusive = 21 playable CoA classes
COA_SENTINEL_ID = 35                  # ConquestOfAzeroth: umbrella sentinel, NOT playable
_REBORN_IDS = range(36, 47)
_META_IDS = {12, 13}                  # General, Hero
_STOCK_IDS = range(2, 12)             # Hunter..DeathKnight

# Curated alpha->display aliases (presentation metadata only; never change class_type_id or
# attribution). Alpha classes revamped into current classes; owner- and Builder-confirmed.
DISPLAY_ALIASES: dict[int, str] = {22: "Bloodmage", 16: "Felsworn", 21: "Templar"}
_ALIAS_EVIDENCE = ("builder_class_name", "project_owner_confirmation")


@dataclass(frozen=True)
class ClassType:
    class_type_id: int
    internal: str            # raw client name (independently recoverable identity)
    display: str             # internal, unless a curated alias overrides it
    kind: str                # coa_class | coa_system | reborn | stock | meta
    display_source: str = "client"
    display_evidence: tuple[str, ...] = ()


def _kind(cid: int) -> str:
    if cid == COA_SENTINEL_ID:
        return "coa_system"
    if cid in PLAYABLE_COA_IDS:
        return "coa_class"
    if cid in _REBORN_IDS:
        return "reborn"
    if cid in _META_IDS:
        return "meta"
    return "stock"


def resolve_class_types(table) -> dict[int, ClassType]:
    out: dict[int, ClassType] = {}
    for row in table.rows:
        cid = row["id"]
        internal = row.get("name") or ""
        if cid in DISPLAY_ALIASES:
            out[cid] = ClassType(cid, internal, DISPLAY_ALIASES[cid], _kind(cid),
                                  "curated_alias", _ALIAS_EVIDENCE)
        else:
            out[cid] = ClassType(cid, internal, internal, _kind(cid))
    return out


def resolve_tab_types(table) -> dict[int, str]:
    return {row["id"]: (row.get("name") or "") for row in table.rows}


def assert_playable_cardinality(resolved: dict[int, ClassType]) -> None:
    playable = [c for c in resolved.values() if c.kind == "coa_class"]
    if len(playable) != 21:
        raise ValueError(
            f"expected 21 playable CoA classes, resolved {len(playable)}: "
            f"{sorted(c.class_type_id for c in playable)}"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_class_types.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/class_types.py tests/test_client_extract_class_types.py
git commit -m "M1.14B: class-type/tab-type resolver with 21-class cardinality assertion"
```

---

## Task 2: `DbcSemanticError` + positional reader + companion layouts + `CharacterAdvancementLayout`

**Files:**
- Modify: `coa_client_extract/errors.py`
- Modify: `coa_client_extract/wdbc.py`
- Modify: `coa_client_extract/dbc_layouts.py`
- Test: `tests/test_client_extract_advancement_semantic.py` (created here; extended in Tasks 3–4)

**Interfaces:**
- Produces: `errors.DbcSemanticError`; `wdbc.parse_positional(data, expected_field_count, expected_record_size) -> PositionalDbc` (`.rows: list[dict[int,int]]`, `.drift: bool`); `dbc_layouts.CHARACTER_ADVANCEMENT_CLASS_TYPES`, `..._TAB_TYPES`, `..._ESSENCE`; `dbc_layouts.CharacterAdvancementLayout`; `dbc_layouts.CHARACTER_ADVANCEMENT` (anchors-only default, overwritten by the Task 3 decode).

Why a positional reader: M1.14A's `parse_dbc` returns rows keyed by the *named* columns a layout declares — right for the small spell family, wrong for a 173-cell advancement record whose columns are addressed by index. `parse_positional` returns each row as `{column_index: uint32}`, which the advancement reader/decoder index directly. The companion tables (ClassTypes/TabTypes) keep using named `parse_dbc` because they need their string `name` column (col 1).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_extract_advancement_semantic.py
import struct

from coa_client_extract.errors import DbcSemanticError, ExtractError
from coa_client_extract.wdbc import parse_positional
from coa_client_extract.dbc_layouts import (
    CHARACTER_ADVANCEMENT_CLASS_TYPES, CharacterAdvancementLayout, CHARACTER_ADVANCEMENT,
)


def test_semantic_error_is_extract_error():
    assert issubclass(DbcSemanticError, ExtractError)


def test_class_types_layout_headers_match_observed_client():
    lt = CHARACTER_ADVANCEMENT_CLASS_TYPES
    assert lt.expected_field_count == 23
    assert lt.expected_record_size == 92
    assert lt.columns["id"].index == 0
    assert lt.columns["name"].index == 1          # verified on real client


def test_advancement_layout_defaults_to_anchors_only():
    lt = CHARACTER_ADVANCEMENT
    assert (lt.node_id_col, lt.spell_id_col, lt.class_type_col) == (0, 5, 32)
    # unresolved fields default to None/() (decoded later, never assumed)
    assert lt.ae_cost_col is None
    assert lt.connected_node_cols == ()


def test_parse_positional_returns_index_keyed_rows():
    # two records, 3 cells each (record_size 12), no string block needed for positional read
    rec0 = struct.pack("<III", 6086, 0, 805775)
    rec1 = struct.pack("<III", 6096, 0, 12345)
    data = struct.pack("<4sIIII", b"WDBC", 2, 3, 12, 0) + rec0 + rec1
    raw = parse_positional(data, 3, 12)
    assert raw.drift is False
    assert raw.rows[0] == {0: 6086, 1: 0, 2: 805775}
    assert raw.rows[1][0] == 6096
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_advancement_semantic.py -v`
Expected: FAIL with `ImportError` for `DbcSemanticError` / `parse_positional` / `CharacterAdvancementLayout`.

- [ ] **Step 3a: Add `DbcSemanticError` to `errors.py`**

Append to `coa_client_extract/errors.py`:

```python
class DbcSemanticError(ExtractError):
    """A DBC column layout matched its WDBC header but failed semantic validation
    (foreign keys, adjacency domain, or value ranges). Distinct from DbcDriftError,
    which is a structural header mismatch."""
```

- [ ] **Step 3b: Add `parse_positional` to `wdbc.py`**

Append to `coa_client_extract/wdbc.py` (reuses the existing `_HEADER`, `_MAGIC`, `_CELL`):

```python
@dataclass(frozen=True)
class PositionalDbc:
    field_count: int
    record_size: int
    record_count: int
    rows: list[dict]      # each row: {column_index: uint32_value}
    drift: bool


def parse_positional(data: bytes, expected_field_count: int, expected_record_size: int) -> PositionalDbc:
    """Decode every record as raw {index: uint32} cells, without a named layout. Used for wide
    custom tables (CharacterAdvancement) whose columns are addressed by index during decode."""
    if len(data) < _HEADER.size:
        raise DbcDriftError("file smaller than DBC header")
    magic, record_count, field_count, record_size, string_size = _HEADER.unpack_from(data, 0)
    if magic != _MAGIC:
        raise DbcDriftError(f"bad magic {magic!r}, expected WDBC")
    drift = field_count != expected_field_count or record_size != expected_record_size
    records_start = _HEADER.size
    ncells = record_size // _CELL
    rows: list[dict] = []
    for i in range(record_count):
        base = records_start + i * record_size
        row = {c: struct.unpack_from("<I", data, base + c * _CELL)[0] for c in range(ncells)}
        rows.append(row)
    return PositionalDbc(field_count, record_size, record_count, rows, drift)
```

- [ ] **Step 3c: Add companion layouts + the advancement layout to `dbc_layouts.py`**

Append to `coa_client_extract/dbc_layouts.py`:

```python
from dataclasses import dataclass

# --- CoA advancement companion tables (headers + name column verified on the real client 2026-07-13) ---
# Col 0 = row id; col 1 = name string (verified) for the two *Types tables. Essence has no strings.
CHARACTER_ADVANCEMENT_CLASS_TYPES = DbcLayout(
    name="CharacterAdvancementClassTypes", expected_field_count=23, expected_record_size=92,
    columns={"id": FieldSpec(0, "uint32"), "name": FieldSpec(1, "str")},
)
CHARACTER_ADVANCEMENT_TAB_TYPES = DbcLayout(
    name="CharacterAdvancementTabTypes", expected_field_count=19, expected_record_size=76,
    columns={"id": FieldSpec(0, "uint32"), "name": FieldSpec(1, "str")},
)
CHARACTER_ADVANCEMENT_ESSENCE = DbcLayout(
    name="CharacterAdvancementEssence", expected_field_count=9, expected_record_size=36,
    columns={"id": FieldSpec(0, "uint32")},   # 9 opaque columns; decoded in Task 6 essence step
)


@dataclass(frozen=True)
class CharacterAdvancementLayout:
    """Resolved column map for CharacterAdvancement.dbc. Only the three anchors are known a
    priori (verified: node id col 0, spell id col 5, class-type FK col 32). Every other field is
    filled by the Task 3 decode harness and semantically validated before use; None / () means
    'not yet resolved to high confidence' and blocks that field from canonical emission."""
    node_id_col: int = 0
    spell_id_col: int = 5
    class_type_col: int = 32
    tab_type_col: int | None = None
    entry_type_col: int | None = None
    name_col: int | None = None
    icon_col: int | None = None
    ae_cost_col: int | None = None
    te_cost_col: int | None = None
    required_level_col: int | None = None
    required_tab_ae_col: int | None = None
    required_tab_te_col: int | None = None
    max_rank_col: int | None = None
    row_col: int | None = None
    column_col: int | None = None
    node_type_col: int | None = None
    connected_node_cols: tuple[int, ...] = ()
    required_id_cols: tuple[int, ...] = ()
    header_field_count: int = 179
    header_record_size: int = 692


# Anchors-only default; Task 3's client-tier decode overwrites this with the resolved columns.
CHARACTER_ADVANCEMENT = CharacterAdvancementLayout()


@dataclass(frozen=True)
class EssenceCapLayout:
    """Resolved columns for CharacterAdvancementEssence (9 opaque columns). All default None =
    undecoded; while None, essence caps are not emitted (a documented flip-blocker, not guessed)."""
    class_type_col: int | None = None
    ae_cap_col: int | None = None
    te_cap_col: int | None = None


# Undecoded default; Task 6's essence decode step overwrites this once columns are proven.
CHARACTER_ADVANCEMENT_ESSENCE_CAPS = EssenceCapLayout()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_advancement_semantic.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/errors.py coa_client_extract/wdbc.py coa_client_extract/dbc_layouts.py tests/test_client_extract_advancement_semantic.py
git commit -m "M1.14B: DbcSemanticError, parse_positional, CoA advancement companion layouts + layout"
```

---

## Task 3: Column-decode harness (client tier) — determine & prove the layout

**Files:**
- Create: `coa_client_extract/decode_advancement.py`
- Test: `tests/test_client_extract_advancement_semantic.py` (extend with a synthetic decode test)

This task produces the *method* that resolves the real column indices and proves them, plus a decode report. The correlation/proof functions are unit-tested on synthetic data (default tier); running against the real client to emit the report is client tier.

**Interfaces:**
- Consumes: `wdbc.DbcTable`, `class_types.resolve_class_types`, the loose `CharacterAdvancementData.json` (schema key), `dbc_layouts.CharacterAdvancementLayout`.
- Produces: `decode_advancement.correlate_scalar(ca, pairs, json_field) -> tuple[int|None, float]`, `decode_advancement.prove_adjacency_domain(ca, layout, candidate_cols) -> tuple[str,tuple[int,...]]`, `decode_advancement.decode_layout(ca, class_types, json_entries) -> tuple[CharacterAdvancementLayout, dict]` (dict = decode report), `decode_advancement.write_report(report, path)`.

- [ ] **Step 1: Write the failing test (synthetic scalar correlation + adjacency proof)**

```python
# append to tests/test_client_extract_advancement_semantic.py
from coa_client_extract.decode_advancement import correlate_scalar, prove_adjacency_domain
from coa_client_extract.dbc_layouts import CharacterAdvancementLayout


class _CA:
    def __init__(self, rows): self.rows = [dict(r) for r in rows]
    # rows here are dicts keyed by integer column index, mirroring a decoded raw record


def test_correlate_scalar_finds_matching_column():
    # col 7 holds AECost; col 9 is noise
    json_entries = [{"__spell": 100 + i, "AECost": i % 3} for i in range(200)]
    ca_rows = [{0: 500 + i, 5: 100 + i, 7: i % 3, 9: 999} for i in range(200)]
    pairs = [(je, next(r for r in ca_rows if r[5] == je["__spell"])) for je in json_entries]
    col, score = correlate_scalar(pairs, "AECost")
    assert col == 7
    assert score > 0.95


def test_prove_adjacency_domain_requires_resolution_into_node_ids():
    node_ids = {10, 11, 12, 13}
    # cols 20,21 hold node refs (padded with 0); col 30 holds an out-of-domain value
    ca_rows = [
        {0: 10, 20: 11, 21: 0, 30: 77777},
        {0: 11, 20: 12, 21: 13, 30: 88888},
        {0: 12, 20: 0, 21: 0, 30: 99999},
        {0: 13, 20: 10, 21: 0, 30: 12345},
    ]
    ok_domain, cols = prove_adjacency_domain(ca_rows, node_ids, candidate_cols=(20, 21))
    assert ok_domain == "node_id"
    assert cols == (20, 21)
    bad = prove_adjacency_domain(ca_rows, node_ids, candidate_cols=(30,))
    assert bad[0] == "unresolved"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_advancement_semantic.py -k "correlate or adjacency" -v`
Expected: FAIL with `ModuleNotFoundError: coa_client_extract.decode_advancement`.

- [ ] **Step 3: Write the decode harness**

```python
# coa_client_extract/decode_advancement.py
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .dbc_layouts import CharacterAdvancementLayout

# JSON field name (loose CharacterAdvancementData.json) -> layout attribute it resolves.
_SCALAR_FIELDS = {
    "AECost": "ae_cost_col", "TECost": "te_cost_col", "RequiredLevel": "required_level_col",
    "RequiredAEInvestment": "required_tab_ae_col", "RequiredTEInvestment": "required_tab_te_col",
    "Column": "column_col",
}


def _s32(u: int) -> int:
    return u - 0x100000000 if u >= 0x80000000 else u


def correlate_scalar(pairs, json_field) -> tuple[int | None, float]:
    """pairs: list of (json_entry, ca_raw_row_dict). ca_raw_row_dict maps column index -> uint32.
    Return the column whose value best equals json_entry[json_field] over the pairs, and the
    match fraction. The loose JSON is stale, so a strong-but-imperfect fraction is expected;
    the caller applies the confidence threshold."""
    cols = set().union(*[set(r) for _, r in pairs]) if pairs else set()
    best_col, best_score = None, 0.0
    for c in cols:
        matched = total = 0
        for je, row in pairs:
            if json_field in je and c in row:
                total += 1
                if row[c] == je[json_field] or _s32(row[c]) == je[json_field]:
                    matched += 1
        if total >= 50:
            score = matched / total
            if score > best_score:
                best_col, best_score = c, score
    return best_col, best_score


def prove_adjacency_domain(ca_rows, node_ids, candidate_cols) -> tuple[str, tuple[int, ...]]:
    """Every non-zero value in candidate_cols must resolve to an existing node id (col 0 domain).
    Zero is padding. Returns ('node_id', cols) when proven, else ('unresolved', ())."""
    for row in ca_rows:
        for c in candidate_cols:
            v = row.get(c, 0)
            if v and v not in node_ids:
                return "unresolved", ()
    return "node_id", tuple(candidate_cols)


def _unique_spell_pairs(ca_rows, json_entries):
    json_by_spell = defaultdict(list)
    for e in json_entries:
        sps = e.get("Spells") or []
        if len(sps) == 1:
            json_by_spell[int(sps[0])].append(e)
    ca_by_spell = defaultdict(list)
    for r in ca_rows:
        if r.get(5):
            ca_by_spell[r[5]].append(r)
    pairs = []
    for sp in set(json_by_spell) & set(ca_by_spell):
        if len(json_by_spell[sp]) == 1 and len(ca_by_spell[sp]) == 1:
            pairs.append((json_by_spell[sp][0], ca_by_spell[sp][0]))
    return pairs


def decode_layout(ca_rows, node_ids, json_entries, *, threshold=0.6) -> tuple[CharacterAdvancementLayout, dict]:
    """Resolve the non-anchor columns by correlating against the loose JSON schema key, then
    prove adjacency. Returns (layout, report). Every resolved field records its column, score,
    and confidence ('high' when score >= threshold and semantic checks pass, else the field is
    left None and reported as 'unresolved' so it blocks canonical emission)."""
    pairs = _unique_spell_pairs(ca_rows, json_entries)
    report = {"schema_version": "coa-ca-decode-report-v1", "unique_pairs": len(pairs), "fields": {}}
    kwargs = {}
    for json_field, attr in _SCALAR_FIELDS.items():
        col, score = correlate_scalar(pairs, json_field)
        conf = "high" if (col is not None and score >= threshold) else "unresolved"
        report["fields"][attr] = {"json_field": json_field, "column": col,
                                  "score": round(score, 3), "confidence": conf}
        if conf == "high":
            kwargs[attr] = col
    layout = CharacterAdvancementLayout(**kwargs)
    return layout, report


def write_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_advancement_semantic.py -k "correlate or adjacency" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/decode_advancement.py tests/test_client_extract_advancement_semantic.py
git commit -m "M1.14B: CharacterAdvancement column-decode harness (JSON-correlation + adjacency proof)"
```

- [ ] **Step 6: Client-tier decode run (produces the real layout + report)**

Run against the real client (requires `COA_CLIENT_ROOT` + StormLib). This is an operator step, not a unit test; it decodes the actual columns, proves adjacency (independently for `ConnectedNodes` and `RequiredIDs`), records the report to `reports/client_extract/coa_ca_decode_report.json`, and writes the resolved indices into a `CHARACTER_ADVANCEMENT` constant in `dbc_layouts.py` with a comment citing the report. Adjacency candidate columns are the contiguous node-id-domain blocks; the entry_type / tab_type / name / icon / node_type columns are resolved the same way (correlate against JSON `Type`, `Tab`, `Name`, `Icon`, `NodeType`). Any field that does not reach `high` stays `None` and is documented as Builder-fallback in the adapter. Commit the report + the `CHARACTER_ADVANCEMENT` constant.

```bash
git add coa_client_extract/dbc_layouts.py reports/client_extract/coa_ca_decode_report.json
git commit -m "M1.14B: decoded + validated CharacterAdvancement layout from real client"
```

---

## Task 4: Advancement graph reader + semantic validators

**Files:**
- Create: `coa_client_extract/advancement.py`
- Test: `tests/test_client_extract_advancement.py`; extend `tests/test_client_extract_advancement_semantic.py`

**Interfaces:**
- Consumes: `wdbc.PositionalDbc` (positional `{index: value}` rows for CharacterAdvancement), `class_types.ClassType`/`resolve_*`, `dbc_layouts.CharacterAdvancementLayout`, `errors.DbcSemanticError`.
- Produces: `AdvancementNode`, `read_advancement(ca, class_types, tab_types, layout)`, `validate_semantics(nodes, class_types, tab_types)`.
- Note: the synthetic tests pass a tiny `_Table` whose `.rows` are `{index: value}` dicts — the same shape `wdbc.parse_positional(...).rows` produces, so the reader is identical in tests and real use. `AdvancementNode` carries no spell name (the current name comes from the `coa-client-spell-v1` join at record-build time, not from the CharacterAdvancement string block).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_extract_advancement.py
import pytest

from coa_client_extract.class_types import resolve_class_types, resolve_tab_types
from coa_client_extract.dbc_layouts import CharacterAdvancementLayout
from coa_client_extract.advancement import AdvancementNode, read_advancement, validate_semantics
from coa_client_extract.errors import DbcSemanticError


class _Table:
    def __init__(self, rows): self.rows = rows


def _class_types():
    rows = [{"id": i, "name": n} for i, n in {
        2: "Hunter", 15: "WitchDoctor", 33: "Venomancer", 35: "ConquestOfAzeroth", 36: "RebornHunter",
    }.items()]
    return resolve_class_types(_Table(rows))


def _tab_types():
    return resolve_tab_types(_Table([{"id": 1, "name": "Class"}, {"id": 49, "name": "Brewing"}]))


def _layout():
    return CharacterAdvancementLayout(
        node_id_col=0, spell_id_col=5, class_type_col=32, tab_type_col=6, entry_type_col=7,
        ae_cost_col=8, required_level_col=9, connected_node_cols=(10, 11), required_id_cols=(12,),
    )


def _ca(rows):
    # rows are dicts keyed by column index (decoded raw). read_advancement consumes DbcTable.rows
    # where each row is that raw dict.
    return _Table(rows)


def test_reads_node_with_ownership_and_legality():
    ca = _ca([
        {0: 6086, 5: 805775, 32: 33, 6: 1, 7: 0, 8: 1, 9: 0, 10: 6096, 11: 7235, 12: 0},
    ])
    nodes = read_advancement(ca, _class_types(), _tab_types(), _layout())
    n = nodes[0]
    assert isinstance(n, AdvancementNode)
    assert n.node_id == 6086 and n.spell_id == 805775
    assert n.class_type_id == 33 and n.class_display == "Venomancer"
    assert n.legality["ae_cost"] == 1
    assert sorted(n.legality["connected_node_ids"]) == [6096, 7235]
    assert n.legality["required_ids"] == []            # 0 padding dropped


def test_shared_spell_yields_two_nodes():
    ca = _ca([
        {0: 7131, 5: 503748, 32: 15, 6: 49, 7: 1, 8: 1, 9: 10, 10: 0, 11: 0, 12: 0},
        {0: 12264, 5: 503748, 32: 15, 6: 1, 7: 0, 8: 1, 9: 0, 10: 0, 11: 0, 12: 0},
    ])
    nodes = read_advancement(ca, _class_types(), _tab_types(), _layout())
    assert {n.node_id for n in nodes} == {7131, 12264}
    assert {n.tab_name for n in nodes} == {"Brewing", "Class"}


def test_validate_semantics_rejects_dangling_adjacency():
    ca = _ca([{0: 1, 5: 100, 32: 33, 6: 1, 7: 0, 8: 0, 9: 0, 10: 999, 11: 0, 12: 0}])  # 999 not a node
    nodes = read_advancement(ca, _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="dangling"):
        validate_semantics(nodes, _class_types(), _tab_types())


def test_validate_semantics_rejects_out_of_range_level():
    ca = _ca([{0: 1, 5: 100, 32: 33, 6: 1, 7: 0, 8: 0, 9: 999, 10: 0, 11: 0, 12: 0}])  # level 999
    nodes = read_advancement(ca, _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="required_level"):
        validate_semantics(nodes, _class_types(), _tab_types())


def test_validate_semantics_rejects_unknown_class_band():
    ct = resolve_class_types(_Table([{"id": 99, "name": "Mystery"}]))
    ca = _ca([{0: 1, 5: 100, 32: 99, 6: 1, 7: 0, 8: 0, 9: 0, 10: 0, 11: 0, 12: 0}])
    nodes = read_advancement(ca, ct, _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="unknown class"):
        validate_semantics(nodes, ct, _tab_types())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_advancement.py -v`
Expected: FAIL with `ModuleNotFoundError: coa_client_extract.advancement`.

- [ ] **Step 3: Write the implementation**

```python
# coa_client_extract/advancement.py
from __future__ import annotations

from dataclasses import dataclass, field

from .errors import DbcSemanticError

_ENTRY_TYPES = {0: "Ability", 1: "Talent", 2: "Trait", 3: "TalentAbility"}
_MAX_LEVEL = 60


@dataclass(frozen=True)
class AdvancementNode:
    node_id: int
    spell_id: int
    class_type_id: int
    class_internal: str
    class_display: str
    class_kind: str
    tab_type_id: int
    tab_name: str
    entry_type: str
    essence_kind: str          # "ability" | "talent" | "" (derived from entry_type)
    legality: dict
    field_confidence: dict
    raw: tuple[int, ...]


def _slots(row: dict, cols) -> list[int]:
    # gather adjacency/required node ids from fixed slot columns, dropping 0 padding, de-duped, sorted
    seen: list[int] = []
    for c in cols:
        v = row.get(c, 0)
        if v and v not in seen:
            seen.append(v)
    return sorted(seen)


def _essence_kind(entry_type: str) -> str:
    if entry_type in ("Ability", "TalentAbility"):
        return "ability"
    if entry_type == "Talent":
        return "talent"
    return ""


def read_advancement(ca, class_types, tab_types, layout) -> list[AdvancementNode]:
    L = layout
    nodes: list[AdvancementNode] = []
    for row in ca.rows:
        cid = row.get(L.class_type_col, 0)
        ct = class_types.get(cid)
        etype = _ENTRY_TYPES.get(row.get(L.entry_type_col), "") if L.entry_type_col is not None else ""
        legality, conf = {}, {}
        for name, col in (
            ("ae_cost", L.ae_cost_col), ("te_cost", L.te_cost_col),
            ("required_level", L.required_level_col),
            ("required_tab_ae", L.required_tab_ae_col), ("required_tab_te", L.required_tab_te_col),
            ("max_rank", L.max_rank_col), ("row", L.row_col), ("col", L.column_col),
        ):
            if col is not None:
                legality[name] = row.get(col, 0)
                conf[name] = "high"
        if L.connected_node_cols:
            legality["connected_node_ids"] = _slots(row, L.connected_node_cols)
            conf["connected_node_ids"] = "high"
        if L.required_id_cols:
            legality["required_ids"] = _slots(row, L.required_id_cols)
            conf["required_ids"] = "high"
        nodes.append(AdvancementNode(
            node_id=row[L.node_id_col], spell_id=row.get(L.spell_id_col, 0),
            class_type_id=cid,
            class_internal=(ct.internal if ct else ""),
            class_display=(ct.display if ct else ""),
            class_kind=(ct.kind if ct else "unknown"),
            tab_type_id=row.get(L.tab_type_col, 0) if L.tab_type_col is not None else 0,
            tab_name=tab_types.get(row.get(L.tab_type_col, 0), "") if L.tab_type_col is not None else "",
            entry_type=etype, essence_kind=_essence_kind(etype),
            legality=legality, field_confidence=conf,
            raw=tuple(sorted(row.items())) if isinstance(row, dict) else (),
        ))
    return nodes


def validate_semantics(nodes, class_types, tab_types) -> None:
    node_ids = {n.node_id for n in nodes}
    for n in nodes:
        if n.class_kind == "unknown":
            raise DbcSemanticError(f"node {n.node_id}: unknown class type {n.class_type_id}")
        for adj_field in ("connected_node_ids", "required_ids"):
            for ref in n.legality.get(adj_field, []):
                if ref not in node_ids:
                    raise DbcSemanticError(
                        f"node {n.node_id}: dangling {adj_field} reference {ref}")
        lvl = n.legality.get("required_level")
        if lvl is not None and not (lvl == 0 or 1 <= lvl <= _MAX_LEVEL):
            raise DbcSemanticError(
                f"node {n.node_id}: required_level {lvl} outside {{0}} u [1,{_MAX_LEVEL}]")
        for cost in ("ae_cost", "te_cost", "required_tab_ae", "required_tab_te"):
            v = n.legality.get(cost)
            if v is not None and v < 0:
                raise DbcSemanticError(f"node {n.node_id}: {cost} negative ({v})")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_advancement.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/advancement.py tests/test_client_extract_advancement.py
git commit -m "M1.14B: CharacterAdvancement graph reader + semantic validators (FK/adjacency/range)"
```

---

## Task 5: Attribution — participation model + memberships

**Files:**
- Create: `coa_client_extract/attribution.py`
- Test: `tests/test_client_extract_attribution.py`

**Interfaces:**
- Consumes: `advancement.AdvancementNode`, `class_types.ClassType`.
- Produces: `AttributionResult`, `SpellAttribution`, `attribute(nodes, class_types, skill_line_index=None)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_extract_attribution.py
from coa_client_extract.attribution import attribute, AttributionResult
from coa_client_extract.advancement import AdvancementNode


def _node(node_id, spell_id, cid, kind, display, tab_id=1, tab="Class", etype="Ability"):
    return AdvancementNode(
        node_id=node_id, spell_id=spell_id, class_type_id=cid, class_internal=display,
        class_display=display, class_kind=kind, tab_type_id=tab_id, tab_name=tab,
        entry_type=etype, essence_kind="ability", legality={}, field_confidence={}, raw=(),
    )


def test_coa_membership_is_high_confidence_coa():
    nodes = [_node(1, 805775, 33, "coa_class", "Venomancer")]
    res = attribute(nodes, {})
    a = res[805775].result
    assert a.is_coa is True and a.modes == ("coa",) and a.exclusive_mode == "coa"
    assert a.confidence == "high"


def test_shared_spell_aggregates_memberships():
    nodes = [
        _node(7131, 503748, 15, "coa_class", "Witch Doctor", 49, "Brewing", "Talent"),
        _node(12264, 503748, 15, "coa_class", "Witch Doctor", 1, "Class", "Ability"),
    ]
    res = attribute(nodes, {})
    assert len(res[503748].memberships) == 2
    assert {m["tab_name"] for m in res[503748].memberships} == {"Brewing", "Class"}


def test_coa_plus_reborn_is_multimode_not_conflict():
    nodes = [
        _node(1, 900, 33, "coa_class", "Venomancer"),
        _node(2, 900, 36, "reborn", "RebornHunter"),
    ]
    a = attribute(nodes, {})[900].result
    assert a.is_coa is True
    assert a.modes == ("coa", "reborn") and a.exclusive_mode is None


def test_stock_membership_does_not_overwrite_coa():
    nodes = [
        _node(1, 950, 33, "coa_class", "Venomancer"),
        _node(2, 950, 2, "stock", "Hunter"),
    ]
    a = attribute(nodes, {})[950].result
    assert a.is_coa is True
    assert set(a.modes) == {"coa", "stock"}


def test_skill_line_fallback_for_graph_absent_spell():
    res = attribute([], {}, skill_line_index={7777: "coa"})
    a = res[7777].result
    assert a.is_coa is True and a.confidence == "medium"


def test_id_only_is_unknown_low():
    # a spell with no advancement node and no skill line is simply absent from the result;
    # callers treat absence as is_coa: false / low. Assert it is not present.
    res = attribute([], {}, skill_line_index={})
    assert 123456 not in res
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_attribution.py -v`
Expected: FAIL with `ModuleNotFoundError: coa_client_extract.attribution`.

- [ ] **Step 3: Write the implementation**

```python
# coa_client_extract/attribution.py
from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict

_KIND_TO_MODE = {"coa_class": "coa", "coa_system": "coa", "reborn": "reborn",
                 "stock": "stock", "meta": "stock"}


@dataclass(frozen=True)
class AttributionResult:
    is_coa: bool
    modes: tuple[str, ...]
    exclusive_mode: str | None
    confidence: str


@dataclass
class SpellAttribution:
    result: AttributionResult
    memberships: list[dict] = field(default_factory=list)


def attribute(nodes, class_types, skill_line_index=None) -> dict[int, SpellAttribution]:
    by_spell: dict[int, list] = defaultdict(list)
    for n in nodes:
        if n.spell_id:
            by_spell[n.spell_id].append(n)

    out: dict[int, SpellAttribution] = {}
    for spell_id, spell_nodes in by_spell.items():
        modes, memberships = [], []
        for n in spell_nodes:
            mode = _KIND_TO_MODE.get(n.class_kind, "stock")
            if mode not in modes:
                modes.append(mode)
            memberships.append({
                "mode": mode, "class_type_id": n.class_type_id,
                "class_internal": n.class_internal, "class_display": n.class_display,
                "tab_type_id": n.tab_type_id, "tab_name": n.tab_name,
                "node_id": n.node_id, "entry_type": n.entry_type,
            })
        modes = tuple(sorted(modes))
        is_coa = "coa" in modes
        out[spell_id] = SpellAttribution(
            AttributionResult(is_coa, modes,
                              modes[0] if len(modes) == 1 else None, "high"),
            memberships,
        )

    # Skill-line fallback for spells absent from the graph (medium confidence, coa only).
    for spell_id, mode in (skill_line_index or {}).items():
        if spell_id not in out and mode == "coa":
            out[spell_id] = SpellAttribution(
                AttributionResult(True, ("coa",), "coa", "medium"), [])
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_attribution.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/attribution.py tests/test_client_extract_attribution.py
git commit -m "M1.14B: participation-model attribution (is_coa/modes/exclusive_mode + memberships)"
```

---

## Task 6: Artifact writers + fill spell attribution

**Files:**
- Modify: `coa_client_extract/artifacts.py`
- Test: extend `tests/test_client_extract_artifacts.py`

**Interfaces:**
- Consumes: `advancement.AdvancementNode`, `class_types.ClassType`, `attribution.SpellAttribution`.
- Produces: `build_advancement_records(nodes, *, provenance, spell_names=None) -> list[dict]`, `build_class_type_records(class_types) -> list[dict]`, `build_essence_cap_records(essence, layout) -> list[dict]`, `fill_spell_attribution(spell_records, attribution) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_client_extract_artifacts.py
from coa_client_extract.artifacts import (
    build_advancement_records, build_class_type_records, fill_spell_attribution,
)
from coa_client_extract.advancement import AdvancementNode
from coa_client_extract.attribution import AttributionResult, SpellAttribution
from coa_client_extract.class_types import ClassType


def _node():
    return AdvancementNode(
        node_id=6086, spell_id=805775, class_type_id=33, class_internal="Venomancer",
        class_display="Venomancer", class_kind="coa_class", tab_type_id=1, tab_name="Class",
        entry_type="Ability", essence_kind="ability",
        legality={"ae_cost": 1, "connected_node_ids": [6096, 7235], "required_ids": []},
        field_confidence={"ae_cost": "high", "connected_node_ids": "high"}, raw=(),
    )


def test_advancement_record_shape():
    recs = build_advancement_records([_node()], provenance={"client_build": "3.3.5a+patch-CZZ"},
                                     spell_names={805775: "Adrenal Venom"})
    r = recs[0]
    assert r["schema_version"] == "coa-client-advancement-v1"
    assert r["node_id"] == 6086 and r["spell_id"] == 805775
    assert r["name"] == "Adrenal Venom"                 # joined from the client spell artifact
    assert r["class"]["display"] == "Venomancer" and r["class"]["kind"] == "coa_class"
    assert r["legality"]["connected_node_ids"] == [6096, 7235]
    assert r["field_confidence"]["ae_cost"] == "high"
    assert r["provenance"]["client_build"] == "3.3.5a+patch-CZZ"


def test_class_type_record_records_alias_provenance():
    cts = {22: ClassType(22, "SonOfArugal", "Bloodmage", "coa_class", "curated_alias",
                         ("builder_class_name", "project_owner_confirmation"))}
    r = build_class_type_records(cts)[0]
    assert r["schema_version"] == "coa-client-class-types-v1"
    assert r["internal"] == "SonOfArugal" and r["display"] == "Bloodmage"
    assert r["display_source"] == "curated_alias"


def test_fill_spell_attribution_replaces_unknown_and_keeps_raw_signals():
    spells = [{"schema_version": "coa-client-spell-v1", "spell_id": 805775,
               "coa_attribution": {"status": "unknown", "archive_family": "other", "id_range": "high"}}]
    attr = {805775: SpellAttribution(AttributionResult(True, ("coa",), "coa", "high"), [])}
    a = fill_spell_attribution(spells, attr)[0]["coa_attribution"]
    assert a["is_coa"] is True and a["modes"] == ["coa"] and a["exclusive_mode"] == "coa"
    assert a["archive_family"] == "other" and a["id_range"] == "high"   # raw signals retained
    assert "status" not in a


def test_fill_spell_attribution_absent_spell_is_low():
    spells = [{"spell_id": 999, "coa_attribution": {"status": "unknown"}}]
    a = fill_spell_attribution(spells, {})[0]["coa_attribution"]
    assert a == {"is_coa": False, "modes": [], "exclusive_mode": None, "confidence": "low"}


def test_essence_caps_empty_when_undecoded_and_records_when_decoded():
    from coa_client_extract.artifacts import build_essence_cap_records
    from coa_client_extract.dbc_layouts import EssenceCapLayout

    class _Ess:
        rows = [{0: 1, 5: 33, 7: 12, 8: 9}]
    assert build_essence_cap_records(_Ess(), EssenceCapLayout()) == []          # undecoded -> []
    decoded = EssenceCapLayout(class_type_col=5, ae_cap_col=7, te_cap_col=8)
    rec = build_essence_cap_records(_Ess(), decoded)[0]
    assert rec == {"schema_version": "coa-client-essence-caps-v1",
                   "class_type_id": 33, "ae_cap": 12, "te_cap": 9}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_artifacts.py -k "advancement or class_type or attribution" -v`
Expected: FAIL with `ImportError` for the new functions.

- [ ] **Step 3: Add the writers to `artifacts.py`**

Append to `coa_client_extract/artifacts.py`:

```python
def build_advancement_records(nodes, *, provenance: dict, spell_names: dict | None = None) -> list[dict]:
    spell_names = spell_names or {}
    records = []
    for n in nodes:
        records.append({
            "schema_version": "coa-client-advancement-v1",
            "node_id": n.node_id,
            "spell_id": n.spell_id,
            "name": spell_names.get(n.spell_id, ""),   # current name from coa-client-spell-v1 join
            "class": {"class_type_id": n.class_type_id, "internal": n.class_internal,
                      "display": n.class_display, "kind": n.class_kind},
            "tab": {"tab_type_id": n.tab_type_id, "name": n.tab_name},
            "entry_type": n.entry_type,
            "essence_kind": n.essence_kind,
            "legality": n.legality,
            "field_confidence": n.field_confidence,
            "raw": {"cols": [v for _, v in n.raw]},
            "provenance": dict(provenance),
        })
    return records


def build_essence_cap_records(essence, layout) -> list[dict]:
    """Emit coa-client-essence-caps-v1 from CharacterAdvancementEssence, using the columns the
    Task 6 essence decode resolved (class_type_col, ae_cap_col, te_cap_col). `layout` is an
    EssenceCapLayout with those indices; if any is None (undecoded / unproven), emit nothing —
    essence caps are gated by the same decode-and-proof rule as node legality and, when unresolved,
    stay a documented flip-blocker rather than shipping guessed values."""
    if layout is None or None in (layout.class_type_col, layout.ae_cap_col, layout.te_cap_col):
        return []
    out = []
    for row in essence.rows:
        out.append({
            "schema_version": "coa-client-essence-caps-v1",
            "class_type_id": row.get(layout.class_type_col),
            "ae_cap": row.get(layout.ae_cap_col),
            "te_cap": row.get(layout.te_cap_col),
        })
    return out


def build_class_type_records(class_types) -> list[dict]:
    out = []
    for ct in class_types.values():
        out.append({
            "schema_version": "coa-client-class-types-v1",
            "class_type_id": ct.class_type_id,
            "internal": ct.internal, "display": ct.display, "kind": ct.kind,
            "display_source": ct.display_source,
            "display_evidence": list(ct.display_evidence),
        })
    return out


def fill_spell_attribution(spell_records, attribution) -> list[dict]:
    for rec in spell_records:
        # Retain the M1.14A raw signals (archive_family/id_range) as provenance (spec: archive
        # family is kept as raw provenance only), and replace the M1.14A `status: unknown`.
        raw = rec.get("coa_attribution", {})
        keep = {k: raw[k] for k in ("archive_family", "id_range") if k in raw}
        attr = attribution.get(rec.get("spell_id"))
        if attr is None:
            block = {"is_coa": False, "modes": [], "exclusive_mode": None, "confidence": "low"}
        else:
            r = attr.result
            block = {"is_coa": r.is_coa, "modes": list(r.modes),
                     "exclusive_mode": r.exclusive_mode, "confidence": r.confidence}
        block.update(keep)
        rec["coa_attribution"] = block
    return spell_records
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_artifacts.py -v`
Expected: PASS (existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/artifacts.py tests/test_client_extract_artifacts.py
git commit -m "M1.14B: advancement/class-type/essence-cap writers + fill spell attribution"
```

---

## Task 7: Node-level (multiset) Builder-parity report

**Files:**
- Create: `coa_client_extract/parity.py`
- Test: `tests/test_client_extract_parity.py`

**Interfaces:**
- Consumes: `advancement.AdvancementNode`; Builder entries as dicts with `spell_id`, `class_name`, `tab_name`, `entry_type` (the shape of `coa_scraper/dist/coa_entries.jsonl`).
- Produces: `build_parity_report(nodes, builder_entries, *, provenance=None) -> dict` (the optional `provenance` dict of reproducibility pins is merged into the report).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_extract_parity.py
from coa_client_extract.parity import build_parity_report
from coa_client_extract.advancement import AdvancementNode


def _node(node_id, spell_id, display, tab, etype="Ability"):
    return AdvancementNode(
        node_id=node_id, spell_id=spell_id, class_type_id=33, class_internal=display,
        class_display=display, class_kind="coa_class", tab_type_id=1, tab_name=tab,
        entry_type=etype, essence_kind="ability", legality={}, field_confidence={}, raw=(),
    )


def test_multiset_ownership_counts_duplicate_spell():
    # shared spell 503748 -> two Witch Doctor nodes; both present in Builder
    nodes = [
        _node(1, 503748, "Witch Doctor", "Brewing", "Talent"),
        _node(2, 503748, "Witch Doctor", "Class", "Ability"),
    ]
    builder = [
        {"spell_id": 503748, "class_name": "Witch Doctor", "tab_name": "Brewing", "entry_type": "Talent"},
        {"spell_id": 503748, "class_name": "Witch Doctor", "tab_name": "Class", "entry_type": "Ability"},
    ]
    rep = build_parity_report(nodes, builder)
    assert rep["builder_records"] == 2
    assert rep["unique_spell_recall"] == 1.0
    assert rep["multiset_ownership_agreement"] == 1.0
    assert rep["builder_only_records"] == 0


def test_reports_builder_only_when_multiplicity_missing():
    nodes = [_node(1, 503748, "Witch Doctor", "Brewing", "Talent")]   # only one of two
    builder = [
        {"spell_id": 503748, "class_name": "Witch Doctor", "tab_name": "Brewing", "entry_type": "Talent"},
        {"spell_id": 503748, "class_name": "Witch Doctor", "tab_name": "Class", "entry_type": "Ability"},
    ]
    rep = build_parity_report(nodes, builder)
    assert rep["unique_spell_recall"] == 1.0            # spell present
    assert rep["multiset_ownership_agreement"] < 1.0    # but a node instance is missing
    assert rep["builder_only_records"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_parity.py -v`
Expected: FAIL with `ModuleNotFoundError: coa_client_extract.parity`.

- [ ] **Step 3: Write the implementation**

```python
# coa_client_extract/parity.py
from __future__ import annotations

from collections import Counter


def _key(spell_id, class_name, tab_name, entry_type):
    return (int(spell_id), class_name, tab_name, entry_type)


def build_parity_report(nodes, builder_entries, *, provenance=None) -> dict:
    # Scope the client side to CoA-class nodes; the Builder oracle is CoA-only, so Reborn/stock
    # nodes would otherwise flood client_only_records with meaningless entries.
    coa_nodes = [n for n in nodes if n.spell_id and n.class_kind == "coa_class"]
    client_keys = Counter(
        _key(n.spell_id, n.class_display, n.tab_name, n.entry_type) for n in coa_nodes
    )
    builder_keys = Counter(
        _key(e["spell_id"], e["class_name"], e.get("tab_name", ""), e.get("entry_type", ""))
        for e in builder_entries
    )
    client_spells = {n.spell_id for n in coa_nodes}
    builder_spells = {int(e["spell_id"]) for e in builder_entries}

    # multiset agreement = intersection size over builder total (counts multiplicity)
    inter = client_keys & builder_keys        # Counter intersection = min per key
    inter_total = sum(inter.values())
    builder_total = sum(builder_keys.values())
    builder_only = builder_keys - client_keys
    client_only = client_keys - builder_keys

    report = {
        "schema_version": "coa-builder-parity-v1",
        "builder_records": builder_total,
        "client_nodes": sum(client_keys.values()),
        "unique_spell_recall": round(len(client_spells & builder_spells) / len(builder_spells), 4)
                               if builder_spells else 1.0,
        "multiset_ownership_agreement": round(inter_total / builder_total, 4) if builder_total else 1.0,
        "builder_only_records": sum(builder_only.values()),
        "client_only_records": sum(client_only.values()),
        "builder_only_sample": [list(k) for k in list(builder_only)[:20]],
    }
    if provenance:
        report["provenance"] = dict(provenance)   # reproducibility pins (Decision 10)
    return report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_parity.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/parity.py tests/test_client_extract_parity.py
git commit -m "M1.14B: node-level (multiset) Builder-parity report"
```

---

## Task 8: CLI wiring — regenerate emits new artifacts + parity report

**Files:**
- Modify: `coa_client_extract/cli.py`
- Test: extend `tests/test_client_extract_cli.py`

**Interfaces:**
- Consumes: everything above, plus `class_types`, `advancement`, `attribution`, `parity`, and the loose JSON for the parity oracle path (optional `--builder-entries`).
- Produces: adds `coa_client_advancement.jsonl`, `coa_client_class_types.jsonl`, and (when `--builder-entries` given) `coa_builder_parity_report.json` to `regenerate` outputs; fills attribution on the spell artifact.

This task **modifies** `tests/test_client_extract_cli.py`: M1.14B makes `regenerate` read the CoA advancement tables, so the existing `_fake_backend()`/`_synthetic_layouts()` must gain them and the existing attribution assertions change (`status: "unknown"` → `is_coa`, with the raw `archive_family`/`id_range` retained).

- [ ] **Step 1: Extend the fake backend + layouts and update assertions**

Add these helpers to `tests/test_client_extract_cli.py` and extend `_fake_backend()`/`_synthetic_layouts()`:

```python
def _pos_dbc(rows, fc, rs):
    # positional DBC (no string block); rows: list of {col: int}
    import struct
    body = b"".join(struct.pack("<" + "I" * (rs // 4), *[r.get(c, 0) for c in range(rs // 4)]) for r in rows)
    return struct.pack("<4sIIII", b"WDBC", len(rows), fc, rs, 0) + body


def _named_dbc(rows, fc, rs, strings):
    import struct
    body = b"".join(struct.pack("<" + "I" * (rs // 4), *[r.get(c, 0) for c in range(rs // 4)]) for r in rows)
    return struct.pack("<4sIIII", b"WDBC", len(rows), fc, rs, len(strings)) + body + strings


def _ca_tables():
    # CharacterAdvancement: one Venomancer node for 805775 (small synthetic layout, 10 cells/40 bytes)
    ca = _pos_dbc([{0: 6086, 1: 805775, 2: 33, 3: 1, 4: 0, 5: 1, 6: 0, 7: 0, 8: 0, 9: 0}], 10, 40)
    # ClassTypes: 21 playable (14..34) + sentinel (35) + one stock (2); only 33 is named "Venomancer"
    ct_strings = b"\x00Venomancer\x00"
    ct_rows = [{0: i, 1: (1 if i == 33 else 0)} for i in list(range(14, 35)) + [35, 2]]
    ct = _named_dbc(ct_rows, 23, 92, ct_strings)
    tt = _named_dbc([{0: 1, 1: 1}], 19, 76, b"\x00Class\x00")   # tab id 1 -> "Class"
    ess = _pos_dbc([], 9, 36)                                   # empty essence table (caps undecoded)
    return ca, ct, tt, ess
```

In `_fake_backend()`, add the four tables to `entries` (all supplied by `common.MPQ` like the spell family):

```python
    ca, ct, tt, ess = _ca_tables()
    entries["DBFilesClient\\CharacterAdvancement.dbc"] = [(Path("common.MPQ"), ca)]
    entries["DBFilesClient\\CharacterAdvancementClassTypes.dbc"] = [(Path("common.MPQ"), ct)]
    entries["DBFilesClient\\CharacterAdvancementTabTypes.dbc"] = [(Path("common.MPQ"), tt)]
    entries["DBFilesClient\\CharacterAdvancementEssence.dbc"] = [(Path("common.MPQ"), ess)]
```

In `_synthetic_layouts()`, add the small advancement layout keyed as the CLI expects:

```python
    from coa_client_extract.dbc_layouts import CharacterAdvancementLayout
    layouts["CharacterAdvancementLayout"] = CharacterAdvancementLayout(
        node_id_col=0, spell_id_col=1, class_type_col=2, tab_type_col=3, entry_type_col=4,
        ae_cost_col=5, required_level_col=6, connected_node_cols=(7, 8), required_id_cols=(9,),
        header_field_count=10, header_record_size=40,
    )
    return layouts
```

Update the existing assertions in `test_regenerate_writes_artifacts_with_injected_backend`: replace the `status`/attribution block with the participation model and add the new-artifact checks:

```python
    # attribution is now filled from the client advancement graph (805775 -> Venomancer node)
    assert spell["coa_attribution"]["is_coa"] is True
    assert spell["coa_attribution"]["modes"] == ["coa"]
    assert spell["coa_attribution"]["archive_family"] == "base"   # raw M1.14A signal retained
    assert spell["coa_attribution"]["id_range"] == "high"
    adv = [json.loads(l) for l in (out / "coa_client_advancement.jsonl").read_text().splitlines()]
    assert adv[0]["schema_version"] == "coa-client-advancement-v1"
    assert adv[0]["class"]["display"] == "Venomancer" and adv[0]["name"] == "Adrenal Venom"
    assert (out / "coa_client_class_types.jsonl").is_file()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_cli.py -v`
Expected: FAIL — `regenerate` does not yet read CharacterAdvancement / emit `coa_client_advancement.jsonl`, and the updated `is_coa` assertion is unmet.

- [ ] **Step 3: Extend `regenerate` in `cli.py`**

In `coa_client_extract/cli.py`, after the existing spell/content extraction and before writing outputs, add the advancement pipeline. Read the companion tables through the backend (effective chain), resolve class/tab types, read + validate the advancement graph, attribute spells, and write the new artifacts:

```python
# --- inside regenerate(), after content_records is built, before out_dir writes ---
from .class_types import resolve_class_types, resolve_tab_types, assert_playable_cardinality
from .advancement import read_advancement, validate_semantics
from .attribution import attribute
from .artifacts import (
    build_advancement_records, build_class_type_records, build_essence_cap_records,
    fill_spell_attribution,
)
from .wdbc import parse_dbc, parse_positional
from .dbc_layouts import (
    CHARACTER_ADVANCEMENT_CLASS_TYPES, CHARACTER_ADVANCEMENT_TAB_TYPES,
    CHARACTER_ADVANCEMENT, CHARACTER_ADVANCEMENT_ESSENCE, CHARACTER_ADVANCEMENT_ESSENCE_CAPS,
)

def read_named(name, layout):
    m = backend.read_effective_file(root, attach, f"DBFilesClient\\{name}.dbc")
    return m, parse_dbc(m.data, layout)          # named columns incl. "name" (col 1)

def read_positional(name, fc, rs):
    m = backend.read_effective_file(root, attach, f"DBFilesClient\\{name}.dbc")
    return m, parse_positional(m.data, fc, rs)   # {index: value} rows

ct_member, ct_tbl = read_named("CharacterAdvancementClassTypes", CHARACTER_ADVANCEMENT_CLASS_TYPES)
tt_member, tt_tbl = read_named("CharacterAdvancementTabTypes", CHARACTER_ADVANCEMENT_TAB_TYPES)
ca_layout = (layouts.get("CharacterAdvancementLayout") if layouts else None) or CHARACTER_ADVANCEMENT
ca_member, ca_raw = read_positional("CharacterAdvancement",
                                    ca_layout.header_field_count, ca_layout.header_record_size)
ess_member, ess_raw = read_positional("CharacterAdvancementEssence",
                                      CHARACTER_ADVANCEMENT_ESSENCE.expected_field_count,
                                      CHARACTER_ADVANCEMENT_ESSENCE.expected_record_size)

class_types = resolve_class_types(ct_tbl)
tab_types = resolve_tab_types(tt_tbl)
assert_playable_cardinality(class_types)

nodes = read_advancement(ca_raw, class_types, tab_types, ca_layout)
validate_semantics(nodes, class_types, tab_types)
spell_attr = attribute(nodes, class_types)

# current names come from the already-extracted spell records (Spell.dbc), not the CA string block
spell_names = {r["spell_id"]: r.get("name", "") for r in spell_records}
adv_records = build_advancement_records(nodes, provenance={
    "client_build": _client_build(plan),
    "source_dbcs": {"CharacterAdvancement": ca_member.effective_archive.name},
    "extraction_date": date.today().isoformat(),
}, spell_names=spell_names)
class_type_records = build_class_type_records(class_types)
essence_records = build_essence_cap_records(ess_raw, CHARACTER_ADVANCEMENT_ESSENCE_CAPS)  # [] until decoded
spell_records = fill_spell_attribution(spell_records, spell_attr)
```

Then add the outputs (`essence_records` may be empty until the essence columns are decoded — that is intended and non-blocking for M1.14B):

```python
outputs["coa_client_advancement.jsonl"] = write_jsonl(adv_records, out_dir / "coa_client_advancement.jsonl")
outputs["coa_client_class_types.jsonl"] = write_jsonl(class_type_records, out_dir / "coa_client_class_types.jsonl")
if essence_records:
    outputs["coa_client_essence_caps.jsonl"] = write_jsonl(essence_records, out_dir / "coa_client_essence_caps.jsonl")
```

If a `--builder-entries` path is provided, also build and write the parity report:

```python
if builder_entries_path:
    import hashlib
    from .parity import build_parity_report
    builder_path = Path(builder_entries_path)
    builder_entries = [json.loads(l) for l in builder_path.read_text().splitlines()]
    pins = {
        "client_build": _client_build(plan),
        "source_dbc_sha256": {
            "CharacterAdvancement": hashlib.sha256(ca_member.data).hexdigest(),
            "CharacterAdvancementClassTypes": hashlib.sha256(ct_member.data).hexdigest(),
        },
        "builder_entries_file": builder_path.name,
        "builder_entries_sha256": hashlib.sha256(builder_path.read_bytes()).hexdigest(),
        "extraction_date": date.today().isoformat(),
    }
    report = build_parity_report(nodes, builder_entries, provenance=pins)
    write_json(report, out_dir / "coa_builder_parity_report.json")
```

Add the `--builder-entries` argument to the `regenerate` subparser (and the `builder_entries_path` parameter to `regenerate(...)`, default `None`) and thread it through. `ExtractedMember.data` carries the raw bytes for the sha256 pins.

- [ ] **Step 4: Run the full client-extract test module**

Run: `python -m pytest tests/ -k client_extract -v`
Expected: PASS (all client-extract tests, including the new CLI test).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/cli.py tests/test_client_extract_cli.py
git commit -m "M1.14B: wire advancement/attribution/parity into regenerate CLI"
```

---

## Task 9: Schema docs + Decisions + roadmap/umbrella updates

**Files:**
- Create: `docs/data/client-advancement-schema.md`, `docs/data/client-class-types-schema.md`
- Modify: `docs/data/client-spell-schema.md`, `docs/data/client-content-schema.md`, `docs/DECISIONS.md`, `docs/superpowers/specs/2026-07-06-m1-14-client-dbc-data-foundation-design.md`, `docs/ROADMAP.md`

- [ ] **Step 1: Write `docs/data/client-advancement-schema.md`**

Document `coa-client-advancement-v1`: every field from the Task 6 record shape (`node_id` = canonical identity, `spell_id` many-to-one, `class`/`tab`/`entry_type`/`essence_kind`, `legality` with the `{0} ∪ [1,60]` required-level rule, `field_confidence` — only `high` fields feed the M1.15 adapter, `raw.cols` for audit, per-table `provenance`, and the `coa_attribution` participation block). State that node identity is the advancement-row id, not the spell id, and cite the shared-spell `503748` example.

- [ ] **Step 2: Write `docs/data/client-class-types-schema.md`**

Document `coa-client-class-types-v1`: `class_type_id`, `internal`, `display`, `kind` (`coa_class`/`coa_system`/`reborn`/`stock`/`meta`), `display_source` (`client`|`curated_alias`), `display_evidence`. State the bands (14–34 playable, 35 sentinel, 36–46 Reborn) and the three curated aliases with provenance.

- [ ] **Step 3: Update `client-spell-schema.md` and `client-content-schema.md`**

In `client-spell-schema.md`, replace the M1.14A `coa_attribution.status: "unknown"` description with the filled participation block (`is_coa`/`modes`/`exclusive_mode`/`confidence`), and note the alpha→display rename does not affect the client `class_type_id`. In `client-content-schema.md`, note the loose `CharacterAdvancementData.json` is superseded by `CharacterAdvancement.dbc` and retained only as a QA drift signal.

- [ ] **Step 4: Update `docs/DECISIONS.md`**

Amend Decision 18 (archive-family mechanism replaced by the `CharacterAdvancement.dbc` registry; principle unchanged). Add Decision 21 (staged, per-field Decision 1 supersession, gated on node-level parity + semantic validation) and Decision 22 (client DBC = canonical offline legality source; live corrections via user-reported verified overrides; Builder removed from the authority chain; four-way discrepancy classification with only extraction/unresolved blocking). Copy the precedence and classification wording verbatim from the spec's Decision impacts section.

- [ ] **Step 5: Update the umbrella spec + roadmap status**

In the M1.14 umbrella spec, update the M1.14B row/section: attribution source is `CharacterAdvancement.dbc` (not archive family), and it also carries the graph/legality (staged to M1.15). In `docs/ROADMAP.md`, mark M1.14B status and link this spec + plan.

- [ ] **Step 6: Commit**

```bash
git add docs/
git commit -m "M1.14B: schema docs, Decisions 18/21/22, roadmap + umbrella updates"
```

---

## Task 10: Native integration (stormlib tier) + client-tier acceptance test

**Files:**
- Modify: `tests/test_client_extract_integration_stormlib.py`, `tests/test_client_extract_acceptance.py`

**Interfaces:**
- Consumes: the real client via `COA_CLIENT_ROOT` + StormLib; the Builder oracle `coa_scraper/dist/coa_entries.jsonl`.

- [ ] **Step 0: Update the existing acceptance assertion**

M1.14B fills attribution, so in `tests/test_client_extract_acceptance.py` the existing
`test_spell_805775_is_current_adrenal_venom` assertion `assert venom["coa_attribution"]["status"] == "unknown"`
(≈ line 34) must become:

```python
    assert venom["coa_attribution"]["is_coa"] is True          # M1.14B fills attribution
    assert "coa" in venom["coa_attribution"]["modes"]
    assert venom["coa_attribution"]["archive_family"] == family_of(effective)   # raw signal retained
```

- [ ] **Step 1: Add a stormlib-tier CharacterAdvancement override test**

In `tests/test_client_extract_integration_stormlib.py` (M1.14A's native tier, `@pytest.mark.stormlib`, miniature self-authored MPQs), add a case: a base archive contains a `CharacterAdvancement.dbc`; a patch archive overrides it; assert `read_effective_file` returns the patch bytes and the `ExtractedMember` provenance names the patch as `effective_archive` (per-table provenance for the advancement family). Mirror the existing miniature-MPQ construction already in that file; only the logical path (`DBFilesClient\\CharacterAdvancement.dbc`) and asserted bytes change.

- [ ] **Step 2: Write the acceptance test (marked `client`)**

```python
# append to tests/test_client_extract_acceptance.py
import json
from pathlib import Path
import pytest

from coa_client_extract.class_types import resolve_class_types, resolve_tab_types, assert_playable_cardinality
from coa_client_extract.advancement import read_advancement, validate_semantics
from coa_client_extract.attribution import attribute
from coa_client_extract.parity import build_parity_report


@pytest.mark.client
def test_real_client_advancement_parity(client_backend, client_plan):
    # client_backend/client_plan: existing acceptance fixtures opening the real archives.
    from coa_client_extract.wdbc import parse_dbc, parse_positional
    from coa_client_extract.dbc_layouts import (
        CHARACTER_ADVANCEMENT_CLASS_TYPES, CHARACTER_ADVANCEMENT_TAB_TYPES, CHARACTER_ADVANCEMENT,
    )
    root, attach = client_plan.open_chain

    def named(name, layout):
        m = client_backend.read_effective_file(root, attach, f"DBFilesClient\\{name}.dbc")
        return parse_dbc(m.data, layout)

    class_types = resolve_class_types(named("CharacterAdvancementClassTypes", CHARACTER_ADVANCEMENT_CLASS_TYPES))
    tab_types = resolve_tab_types(named("CharacterAdvancementTabTypes", CHARACTER_ADVANCEMENT_TAB_TYPES))
    assert_playable_cardinality(class_types)                        # exactly 21 playable

    m = client_backend.read_effective_file(root, attach, "DBFilesClient\\CharacterAdvancement.dbc")
    ca = parse_positional(m.data, CHARACTER_ADVANCEMENT.header_field_count,
                          CHARACTER_ADVANCEMENT.header_record_size)
    nodes = read_advancement(ca, class_types, tab_types, CHARACTER_ADVANCEMENT)
    validate_semantics(nodes, class_types, tab_types)               # FK/adjacency/range all pass

    builder = [json.loads(l) for l in
               Path("coa_scraper/dist/coa_entries.jsonl").read_text().splitlines()]
    rep = build_parity_report(nodes, builder)
    assert rep["unique_spell_recall"] == 1.0
    assert rep["multiset_ownership_agreement"] == 1.0              # 100% after alpha->display rename

    attr = attribute(nodes, class_types)
    a = attr[805775]
    assert a.result.is_coa is True
    assert any(m["class_display"] == "Venomancer" for m in a.memberships)
    assert len(attr[503748].memberships) == 2                      # shared node
```

- [ ] **Step 3: Run the acceptance test against the real client**

Run: `COA_CLIENT_ROOT="$HOME/Games/ascension-wow/drive_c/Program Files/Ascension Launcher/resources/ascension-live/Data" python -m pytest tests/test_client_extract_acceptance.py -m client -v`
Expected: PASS. If `multiset_ownership_agreement` < 1.0, inspect `builder_only_sample` — a remaining gap is either an undecoded column (fix the layout) or a genuine client-vs-Builder difference (client wins per Decision 22; it must not be an extraction defect).

- [ ] **Step 4: Regenerate the real artifacts + parity report**

```bash
python -m coa_client_extract regenerate \
  --client-root "$HOME/Games/ascension-wow/drive_c/Program Files/Ascension Launcher/resources/ascension-live/Data" \
  --out reports/client_extract \
  --builder-entries coa_scraper/dist/coa_entries.jsonl
```
Confirm `reports/client_extract/` contains `coa_client_advancement.jsonl`, `coa_client_class_types.jsonl`, `coa_client_spell.jsonl` (attribution filled), and `coa_builder_parity_report.json` with `multiset_ownership_agreement: 1.0`.

- [ ] **Step 5: Full suite + commit**

Run: `python -m pytest` (default tier — must be green without StormLib/client) then the marked tiers if available (`-m stormlib`, `-m client`).

```bash
git add tests/test_client_extract_acceptance.py tests/test_client_extract_integration_stormlib.py
git commit -m "M1.14B: stormlib-tier CA override + client-tier acceptance (100% multiset parity)"
```

---

## Self-Review Notes (for the executor)

- **Decode dependency:** Tasks 4–10 reference the `CHARACTER_ADVANCEMENT` layout constant produced by Task 3 Step 6 (client tier). Synthetic unit tests supply their own `CharacterAdvancementLayout`, so Tasks 4–8 are fully testable *without* the client; only Task 3 Step 6 and Task 10 require the real install. Do Task 3's client decode before Task 10.
- **Reader split in `regenerate`:** M1.14A's `regenerate` has a local `read_table(name)` for the spell family. Task 8 adds `read_named(name, layout)` (named columns — companion `*Types` tables, whose `name` is the verified col 1, no decode needed) and `read_positional(name, fc, rs)` (index-keyed cells — the wide `CharacterAdvancement`/`Essence` tables). Keep `read_table` for the spell family untouched.
- **Only `high`-confidence fields are emitted into `legality`/adapter.** A field left `None` in the layout is simply absent from `legality`; that is intended (it becomes Builder-fallback in M1.15), not a bug.
- **Essence caps are non-blocking for M1.14B.** `build_essence_cap_records` returns `[]` while `CHARACTER_ADVANCEMENT_ESSENCE_CAPS` is undecoded, and `regenerate` simply omits the file — the existing per-class `coa_scraper/dist/coa_essence_caps.json` remains the essence source under Decision 21's per-field rule. Decoding the client `CharacterAdvancementEssence` (9 opaque columns) to `high` is a flip-gate item for M1.15, not an M1.14B blocker. Do not fabricate its column indices.
- **Do not rewire `coa_meta`.** If any task tempts you to touch `repository.py` or reports, stop — that is M1.15.
