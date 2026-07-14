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
- `coa_client_extract/parity.py` — node-id crosswalk Builder-parity report (ownership/identity/adjacency/legality) + a scoped `readiness` object (attribution/ownership/adjacency + per-field legality + cosmetic layout + leveling + full_builder_retirement roll-up) with a `blockers` diagnostic list.
- `coa_client_extract/decode_advancement.py` — the client-tier decode harness that determines the `CharacterAdvancement` column layout by JSON-correlation + semantic proof and writes a decode report.
- `tests/test_client_extract_class_types.py`, `tests/test_client_extract_advancement.py`, `tests/test_client_extract_advancement_semantic.py`, `tests/test_client_extract_attribution.py`, `tests/test_client_extract_parity.py`
- `docs/data/client-advancement-schema.md`, `docs/data/client-class-types-schema.md`

**Modified files:**
- `coa_client_extract/errors.py` — add `DbcSemanticError`.
- `coa_client_extract/wdbc.py` — add `parse_positional` + `PositionalDbc` (raw index-keyed reader for wide tables).
- `coa_client_extract/dbc_layouts.py` — add companion layouts, the `CharacterAdvancementLayout` dataclass, and the decoded `CHARACTER_ADVANCEMENT` constant (no essence-cap layout — caps are constants, essence is extracted raw).
- `coa_client_extract/artifacts.py` — advancement/class-type/tab-type/raw-essence record writers; fill `coa_attribution` + `memberships[]` on spell records.
- `coa_client_extract/cli.py` — wire the new readers and outputs into `regenerate`.
- `tests/test_client_extract_artifacts.py`, `tests/test_client_extract_cli.py`, `tests/test_client_extract_acceptance.py` — extend.
- `docs/data/client-spell-schema.md`, `docs/data/client-content-schema.md`, `docs/DECISIONS.md`, `docs/superpowers/specs/2026-07-06-m1-14-client-dbc-data-foundation-design.md`, `docs/ROADMAP.md`.

**Shared interfaces (defined by the tasks below; listed here so tasks can be read out of order):**
- `class_types.ClassType(class_type_id:int, internal:str, display:str, kind:str, display_source:str="client", display_evidence:tuple[str,...]=())` — `kind ∈ {"coa_class","coa_system","reborn","stock","meta","unknown"}`.
- `class_types.resolve_class_types(table: DbcTable) -> dict[int, ClassType]`
- `class_types.resolve_tab_types(table: DbcTable) -> dict[int, str]`
- `class_types.assert_playable_cardinality(resolved: dict[int, ClassType]) -> None`
- `dbc_layouts.CharacterAdvancementLayout` — named column fields (below).
- `advancement.AdvancementNode` — dataclass (below).
- `advancement.read_advancement(ca: wdbc.PositionalDbc, class_types, tab_types, layout) -> list[AdvancementNode]` (consumes positional `{index: value}` rows).
- `advancement.validate_semantics(nodes, class_types, tab_types) -> None` (raises `DbcSemanticError`).
- `attribution.AttributionResult(is_coa:bool, modes:tuple[str,...], exclusive_mode:str|None, confidence:str)`
- `attribution.attribute(nodes, class_types, skill_line_index=None) -> dict[int, SpellAttribution]` where `SpellAttribution` has `.result: AttributionResult` and `.memberships: list[dict]`.
- `attribution.derive_coa_skill_lines(skill_line_ability_rows, coa_spell_ids) -> set[int]` (proven CoA skill-line set) and `attribution.build_skill_line_index(skill_line_ability_rows, coa_line_ids) -> dict[int,str]`
- `parity.build_parity_report(nodes, builder_entries, *, class_types=None, low_confidence_fields=(), unresolved_layout_columns=(), expected_builder_records=None, provenance=None) -> dict` — computes ownership (entry_id↔node_id crosswalk), `identity_mismatches`, `per_class`/`per_tab` counts, `adjacency_mismatches`, and Decision-22 `legality_diffs` internally; carries `ownership_recall`/`ownership_precision`, the scoped `readiness` object, and a `blockers` diagnostic list (schema `coa-builder-parity-v2`).
- `parity.flip_gate_inputs(layout) -> tuple[list[str], list[str]]` — `(low_confidence_fields, unresolved_layout_columns)` derived from a resolved `CharacterAdvancementLayout`; adjacency confidence is folded into these two lists.
- `parity.EXPECTED_BUILDER_RECORDS = 3612` — pinned Builder artifact size; the CLI passes it as `expected_builder_records` to guard against a truncated oracle.

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


def test_unknown_class_id_is_unknown_not_stock():
    # an id outside every known band must be "unknown" (flagged), never silently bucketed "stock"
    resolved = resolve_class_types(_Table([{"id": 99, "name": "Mystery"}]))
    assert resolved[99].kind == "unknown"


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
    if cid in _STOCK_IDS:
        return "stock"
    return "unknown"     # outside every known band: possible new class / drift, never silently stock


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
- Produces: `errors.DbcSemanticError`; `wdbc.parse_positional(data, expected_field_count, expected_record_size, *, strict=False) -> PositionalDbc` (`.rows: list[{cell_index: uint32}]`, `.cell_count`, `.strings`, `.drift`, `.read_string(offset)`); `dbc_layouts.CHARACTER_ADVANCEMENT_CLASS_TYPES`, `..._TAB_TYPES`, `..._ESSENCE`, `..._SKILL_LINE_ABILITY`; `dbc_layouts.CharacterAdvancementLayout` (indices **and** a per-field `confidence` map); `dbc_layouts.CHARACTER_ADVANCEMENT` (anchors-only default, overwritten by the Task 3 decode).

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
    # unresolved fields default to None/() and no field is proven until the decode fills confidence
    assert lt.ae_cost_col is None
    assert lt.connected_node_cols == ()
    assert lt.confidence == {}


def test_parse_positional_returns_index_keyed_rows_and_strings():
    import pytest
    from coa_client_extract.errors import DbcDriftError
    strings = b"\x00Adrenal Venom\x00"
    rec0 = struct.pack("<III", 6086, 1, 805775)   # col1 = string offset 1 -> "Adrenal Venom"
    rec1 = struct.pack("<III", 6096, 0, 12345)
    data = struct.pack("<4sIIII", b"WDBC", 2, 3, 12, len(strings)) + rec0 + rec1 + strings
    raw = parse_positional(data, 3, 12)
    assert raw.drift is False
    assert raw.cell_count == 3 and raw.record_size == 12
    assert raw.rows[0] == {0: 6086, 1: 1, 2: 805775}
    assert raw.rows[1][0] == 6096
    assert raw.strings == strings                 # string block retained for name/icon correlation
    assert raw.read_string(1) == "Adrenal Venom"


def test_parse_positional_rejects_truncation():
    import pytest
    from coa_client_extract.errors import DbcDriftError
    # header claims 2 records * 12 bytes + 4-byte string block, but body is short
    data = struct.pack("<4sIIII", b"WDBC", 2, 3, 12, 4) + struct.pack("<III", 1, 0, 0)
    with pytest.raises(DbcDriftError, match="truncated"):
        parse_positional(data, 3, 12)


def test_parse_positional_rejects_non_divisible_record_size():
    import pytest
    from coa_client_extract.errors import DbcDriftError
    data = struct.pack("<4sIIII", b"WDBC", 0, 3, 13, 0)   # 13 not divisible by 4
    with pytest.raises(DbcDriftError, match="record_size"):
        parse_positional(data, 3, 13)


def test_parse_positional_strict_raises_on_drift():
    import pytest
    from coa_client_extract.errors import DbcDriftError
    data = struct.pack("<4sIIII", b"WDBC", 0, 99, 12, 0)  # field_count 99 != expected 3
    assert parse_positional(data, 3, 12).drift is True    # non-strict: flagged
    with pytest.raises(DbcDriftError):
        parse_positional(data, 3, 12, strict=True)
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
    field_count: int          # logical field count from the header (may exceed cell_count)
    cell_count: int           # record_size // 4 — the number of addressable 4-byte cells
    record_size: int
    record_count: int
    rows: list[dict]          # each row: {cell_index: uint32_value}
    strings: bytes            # retained string block, for name/icon correlation
    drift: bool

    def read_string(self, offset: int) -> str:
        if offset <= 0 or offset >= len(self.strings):
            return ""
        end = self.strings.find(b"\x00", offset)
        if end < 0:
            end = len(self.strings)
        return self.strings[offset:end].decode("utf-8", "replace")


def parse_positional(data: bytes, expected_field_count: int, expected_record_size: int,
                     *, strict: bool = False) -> PositionalDbc:
    """Decode every record as raw {cell_index: uint32} cells plus the string block, without a named
    layout. Used for wide custom tables (CharacterAdvancement) addressed by index during decode.

    Note the logical/raw distinction: the real CharacterAdvancement header reports field_count 179
    while record_size 692 holds only 173 four-byte cells. Cells are addressed 0..cell_count-1;
    field_count is preserved for provenance and drift, not for indexing."""
    if len(data) < _HEADER.size:
        raise DbcDriftError("file smaller than DBC header")
    magic, record_count, field_count, record_size, string_size = _HEADER.unpack_from(data, 0)
    if magic != _MAGIC:
        raise DbcDriftError(f"bad magic {magic!r}, expected WDBC")
    if record_size % _CELL != 0:
        raise DbcDriftError(f"record_size {record_size} not a multiple of {_CELL}")
    records_start = _HEADER.size
    string_start = records_start + record_count * record_size
    expected_len = string_start + string_size
    if len(data) < expected_len:
        raise DbcDriftError(f"truncated ({len(data)} bytes, expected >= {expected_len})")
    drift = field_count != expected_field_count or record_size != expected_record_size
    if drift and strict:
        raise DbcDriftError(
            f"field_count {field_count} / record_size {record_size} != expected "
            f"{expected_field_count} / {expected_record_size}")
    strings = data[string_start:string_start + string_size]
    cell_count = record_size // _CELL
    rows: list[dict] = []
    for i in range(record_count):
        base = records_start + i * record_size
        rows.append({c: struct.unpack_from("<I", data, base + c * _CELL)[0] for c in range(cell_count)})
    return PositionalDbc(field_count, cell_count, record_size, record_count, rows, strings, drift)
```

- [ ] **Step 3c: Add companion layouts + the advancement layout to `dbc_layouts.py`**

Append to `coa_client_extract/dbc_layouts.py`:

```python
from dataclasses import dataclass, field

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
    columns={"id": FieldSpec(0, "uint32")},   # per-level progression, extracted raw (Task 6)
)
# SkillLineAbility: id(0), skill_line(1), spell(2). The CoA skill-line SET is proven empirically at
# extraction time (attribution.derive_coa_skill_lines) from the lines that carry graph CoA spells —
# NOT a hard-coded range, since CoA spells attach to per-spec lines, not only the 475-495 class band.
CHARACTER_ADVANCEMENT_SKILL_LINE_ABILITY = DbcLayout(
    name="SkillLineAbility", expected_field_count=14, expected_record_size=56,
    columns={"id": FieldSpec(0, "uint32"), "skill_line": FieldSpec(1, "uint32"),
             "spell": FieldSpec(2, "uint32")},
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
    # Proven numeric->string entry-type map from the Task 3 decode (JSON keys are strings, e.g.
    # {"0": "Ability", "1": "Talent"}). read_advancement consumes THIS, never a hard-coded table,
    # so the mapping is load-bearing proof rather than an assumption. Empty until decode fills it.
    entry_type_map: dict = field(default_factory=dict)
    # Per-legality-field proof from the Task 3 decode: field name -> "high" | "medium" | "unproven".
    # read_advancement emits a field into `legality` ONLY when its confidence is "high"; a configured
    # column with no "high" confidence is treated as unproven and withheld (never assumed).
    confidence: dict = field(default_factory=dict)


# Anchors-only default; Task 3's client-tier decode overwrites this with the resolved columns and
# their proven confidence. The anchors themselves (node_id/spell_id/class_type) are structurally
# verified, but legality fields stay unproven until decode fills `confidence`.
CHARACTER_ADVANCEMENT = CharacterAdvancementLayout()
```

There is deliberately **no** essence-cap layout: per-class essence caps are the documented uniform
constants (AE 26 / TE 25), not a DBC-decoded quantity, so `CharacterAdvancementEssence` is extracted
raw (Task 6, `build_essence_raw_records`) rather than decoded into caps. Do not add a cap-column
layout — that would re-introduce the contradiction the design review resolved.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_advancement_semantic.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/errors.py coa_client_extract/wdbc.py coa_client_extract/dbc_layouts.py tests/test_client_extract_advancement_semantic.py
git commit -m "M1.14B: DbcSemanticError, hardened parse_positional, CoA advancement layouts + confidence"
```

---

## Task 3: Column-decode harness (client tier) — determine & prove the layout

**Files:**
- Create: `coa_client_extract/decode_advancement.py`
- Test: `tests/test_client_extract_advancement_semantic.py` (extend with a synthetic decode test)

This task produces the *method* that resolves every column and **proves** it (with recorded evidence, uniqueness margins, and a minimum-nonzero floor), plus an executable decode command. The correlation/proof functions are unit-tested on synthetic data (default tier); running against the real client to emit the report + resolved layout is client tier. A field is `high` only when it clears the score threshold, beats the runner-up by a margin, has enough non-zero evidence, and (for FKs/adjacency) resolves into the correct domain.

**Interfaces:**
- Consumes: `wdbc.PositionalDbc` (rows + string block), `class_types.resolve_class_types`/`resolve_tab_types`, the loose `CharacterAdvancementData.json` (schema key), `dbc_layouts.CharacterAdvancementLayout`.
- Produces: `decode_advancement.correlate_scalar(pairs, json_field) -> ScalarProof(column, score, runner_up, margin, nonzero) | None`, `decode_advancement.prove_adjacency_domain(ca_rows, node_ids, candidate_cols, *, min_nonzero) -> tuple[str, tuple[int,...]]`, `decode_advancement.decode_layout(ca, class_types, tab_types, json_entries, *, score_threshold=0.85, margin_threshold=0.15, min_nonzero=50) -> tuple[CharacterAdvancementLayout, dict]`, `decode_advancement.write_report(report, path)`, and the CLI subcommand `python -m coa_client_extract decode-advancement`.

- [ ] **Step 1: Write the failing tests (evidence-based correlation + strict adjacency proof)**

```python
# append to tests/test_client_extract_advancement_semantic.py
from coa_client_extract.decode_advancement import (
    correlate_scalar, prove_adjacency_domain, decode_layout,
)


def _pairs(json_field, values, ca_cols):
    # values: list of ints; ca_cols: dict col->list aligned with values. Builds (json,row) pairs.
    pairs = []
    for i, v in enumerate(values):
        je = {"Spells": [1000 + i], json_field: v}
        row = {5: 1000 + i, **{c: col[i] for c, col in ca_cols.items()}}
        pairs.append((je, row))
    return pairs


def test_correlate_scalar_records_margin_and_nonzero():
    vals = [i % 4 for i in range(200)]
    # col 7 == field; col 9 is pure noise (constant); col 8 partially agrees
    ca = {7: vals, 8: [v if i % 2 else 0 for i, v in enumerate(vals)], 9: [3] * 200}
    proof = correlate_scalar(_pairs("AECost", vals, ca), "AECost")
    assert proof.column == 7 and proof.score == 1.0
    assert proof.runner_up < proof.score and proof.margin > 0.15
    assert proof.nonzero >= 50


def test_correlate_scalar_none_when_no_min_evidence():
    # only 10 pairs -> below the 50-nonzero floor -> no proof
    vals = [1] * 10
    assert correlate_scalar(_pairs("AECost", vals, {7: vals}), "AECost") is None


def test_prove_adjacency_rejects_all_zero_and_out_of_domain():
    node_ids = {10, 11, 12, 13}
    rows = [{0: 10, 20: 11, 21: 0}, {0: 11, 20: 12, 21: 13}, {0: 12, 20: 13, 21: 0},
            {0: 13, 20: 10, 21: 12}]
    assert prove_adjacency_domain(rows, node_ids, (20, 21), min_nonzero=3)[0] == "node_id"
    # all-zero block: no evidence -> unresolved (not a silent pass)
    zeros = [{0: n, 40: 0} for n in node_ids]
    assert prove_adjacency_domain(zeros, node_ids, (40,), min_nonzero=1)[0] == "unresolved"
    # out-of-domain value -> unresolved
    bad = [{0: 10, 50: 99999}]
    assert prove_adjacency_domain(bad, node_ids, (50,), min_nonzero=1)[0] == "unresolved"


def test_decode_layout_marks_unproven_fields_unproven():
    # a table where AECost is cleanly in col 7 but RequiredLevel has no matching column
    vals = [i % 4 for i in range(200)]
    ca_rows = [{0: 500 + i, 5: 1000 + i, 7: vals[i]} for i in range(200)]
    json_entries = [{"Spells": [1000 + i], "AECost": vals[i], "RequiredLevel": 99} for i in range(200)]
    from coa_client_extract.wdbc import PositionalDbc
    ca = PositionalDbc(179, 173, 692, 200, ca_rows, b"\x00", drift=False)
    layout, report = decode_layout(ca, {}, {}, json_entries)
    # confidence is keyed by the FIELD name read_advancement gates on, NOT the "_col" attribute
    assert layout.confidence.get("ae_cost") == "high"
    assert layout.ae_cost_col == 7
    assert report["fields"]["ae_cost_col"]["column"] == 7
    assert report["fields"]["required_level_col"]["confidence"] != "high"  # no clean column


def test_decode_layout_resolves_tab_entry_and_both_adjacency_blocks():
    from coa_client_extract.wdbc import PositionalDbc
    from coa_client_extract.decode_advancement import load_resolved_layout
    from coa_client_extract.class_types import resolve_tab_types

    class _T:
        def __init__(self, rows): self.rows = rows
    tab_types = resolve_tab_types(_T([{"id": 1, "name": "Class"}, {"id": 49, "name": "Brewing"}]))

    n = 200
    ca_rows, json_entries = [], []
    for i in range(n):
        nid, nxt, prev = 500 + i, 500 + (i + 1) % n, 500 + (i - 1) % n
        tab = 1 if i % 3 == 0 else 49                             # tab pattern independent of entry type
        etype_num, etype_str = (0, "Ability") if i % 2 == 0 else (1, "Talent")
        ca_rows.append({0: nid, 5: 1000 + i, 32: 33,
                        6: tab, 4: etype_num, 7: i % 4,          # tab col 6, entry col 4, ae col 7
                        20: nxt, 21: 0, 40: prev})               # connected col 20, required col 40
        # loose JSON "Tab" is the display NAME (as in the real client), not the numeric id -> the
        # decode must translate it back through tab_types to resolve tab_type_col.
        json_entries.append({"ID": nid, "Spells": [1000 + i], "Tab": tab_types[tab], "Type": etype_str,
                             "AECost": i % 4, "ConnectedNodes": [nxt], "RequiredIDs": [prev]})
    ca = PositionalDbc(179, 173, 692, n, ca_rows, b"\x00", drift=False)
    layout, report = decode_layout(ca, {}, tab_types, json_entries, min_nonzero=50)

    assert layout.tab_type_col == 6 and layout.confidence["tab_type"] == "high"   # resolved via name->id
    assert layout.entry_type_col == 4 and layout.confidence["entry_type"] == "high"
    assert report["entry_type_map"] == {"0": "Ability", "1": "Talent"}   # proven, not hard-coded
    assert layout.connected_node_cols == (20,) and layout.confidence["connected_node_ids"] == "high"
    assert layout.required_id_cols == (40,) and layout.confidence["required_ids"] == "high"

    # the finished layout round-trips through the report so regenerate loads it with no hand-editing
    import tempfile, os
    from coa_client_extract.decode_advancement import write_report
    path = os.path.join(tempfile.mkdtemp(), "report.json")
    write_report(report, __import__("pathlib").Path(path))
    reloaded = load_resolved_layout(path)
    assert reloaded.tab_type_col == 6 and reloaded.entry_type_col == 4
    assert reloaded.connected_node_cols == (20,) and reloaded.confidence["required_ids"] == "high"
    assert reloaded.entry_type_map == {"0": "Ability", "1": "Talent"}   # proven map survives round-trip
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_advancement_semantic.py -k "correlate or adjacency or decode_layout" -v`
Expected: FAIL with `ImportError`/`ModuleNotFoundError` for `decode_advancement`.

- [ ] **Step 3: Write the decode harness**

```python
# coa_client_extract/decode_advancement.py
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .dbc_layouts import CharacterAdvancementLayout

# JSON field (loose CharacterAdvancementData.json) -> layout attribute it resolves. Every entry
# here is proven by correlation, never assumed. Names follow the loose JSON's own field names.
_SCALAR_FIELDS = {
    "AECost": "ae_cost_col", "TECost": "te_cost_col", "RequiredLevel": "required_level_col",
    "RequiredAEInvestment": "required_tab_ae_col", "RequiredTEInvestment": "required_tab_te_col",
    "MaxRank": "max_rank_col", "Row": "row_col", "Column": "column_col",
}


@dataclass(frozen=True)
class ScalarProof:
    column: int
    score: float
    runner_up: float
    margin: float
    nonzero: int


def _s32(u: int) -> int:
    return u - 0x100000000 if u >= 0x80000000 else u


def correlate_scalar(pairs, json_field, *, min_nonzero: int = 50) -> ScalarProof | None:
    """Rank every column by exact-match fraction against json_field over (json, row) pairs, and
    return the winner WITH its uniqueness margin over the runner-up and its non-zero evidence
    count. Returns None when the best column lacks >= min_nonzero non-zero matched values (guards
    against zero-dominated columns matching a mostly-zero field by accident)."""
    cols = set().union(*[set(r) for _, r in pairs]) if pairs else set()
    scored = []
    for c in cols:
        matched = total = nonzero = 0
        for je, row in pairs:
            if json_field in je and c in row:
                total += 1
                jv = je[json_field]
                if row[c] == jv or _s32(row[c]) == jv:
                    matched += 1
                    if row[c] != 0:
                        nonzero += 1
        if total >= min_nonzero:
            scored.append((matched / total, nonzero, c))
    if not scored:
        return None
    scored.sort(reverse=True)
    top = scored[0]
    runner = scored[1][0] if len(scored) > 1 else 0.0
    if top[1] < min_nonzero:
        return None
    return ScalarProof(top[2], round(top[0], 4), round(runner, 4), round(top[0] - runner, 4), top[1])


def prove_adjacency_domain(ca_rows, node_ids, candidate_cols, *, min_nonzero: int = 50) -> tuple[str, tuple[int, ...]]:
    """Prove the candidate columns are node-id references: every non-zero value resolves to an
    existing node id (col-0 domain), and there is at least min_nonzero non-zero evidence across
    the block (an all-zero block is 'unresolved', never a silent pass). Zero is padding."""
    nonzero = 0
    for row in ca_rows:
        for c in candidate_cols:
            v = row.get(c, 0)
            if v:
                nonzero += 1
                if v not in node_ids:
                    return "unresolved", ()
    if nonzero < min_nonzero:
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


# decode attr -> the legality/ownership field name read_advancement emits (so confidence keys line up
# with what read_advancement's emit()/gates check — keyed by FIELD name, not the "_col" attribute).
_LEGALITY_NAME = {
    "ae_cost_col": "ae_cost", "te_cost_col": "te_cost", "required_level_col": "required_level",
    "required_tab_ae_col": "required_tab_ae", "required_tab_te_col": "required_tab_te",
    "max_rank_col": "max_rank", "row_col": "row", "column_col": "col",
    "tab_type_col": "tab_type", "entry_type_col": "entry_type",
    "connected_node_cols": "connected_node_ids", "required_id_cols": "required_ids",
}


def _json_by_id(json_entries):
    return {int(e["ID"]): e for e in json_entries if e.get("ID") is not None}


def _node_id_hit_rate(ca_rows, node_ids) -> dict:
    """Per-column fraction of non-zero values that resolve to a node id (recorded evidence)."""
    cols = set().union(*[set(r) for r in ca_rows]) if ca_rows else set()
    out = {}
    for c in sorted(cols):
        nz = [r[c] for r in ca_rows if r.get(c)]
        if nz:
            out[str(c)] = round(sum(1 for v in nz if v in node_ids) / len(nz), 3)
    return out


_ANCHOR_COLS = {0, 5, 32}   # node_id, spell_id, class_type FK — never adjacency, excluded from discovery


def _discover_adjacency_blocks(ca_rows, node_ids, *, min_hit=0.9, min_nonzero=50):
    """Deterministically find contiguous column runs whose non-zero values overwhelmingly resolve to
    node ids — candidate adjacency blocks. No operator interpretation: the runs are computed here.
    The three anchor columns (node_id/spell/class) are excluded so col 0 is not mistaken for a block."""
    cols = [c for c in sorted(set().union(*[set(r) for r in ca_rows])) if c not in _ANCHOR_COLS] \
        if ca_rows else []
    good = set()
    for c in cols:
        nz = [r[c] for r in ca_rows if r.get(c)]
        if len(nz) >= min_nonzero and sum(1 for v in nz if v in node_ids) / len(nz) >= min_hit:
            good.add(c)
    blocks, run = [], []
    for c in cols:
        if c in good:
            run.append(c)
        elif run:
            blocks.append(tuple(run)); run = []
    if run:
        blocks.append(tuple(run))
    return blocks


def _classify_adjacency(ca_rows, json_by_id, block):
    """Match a proven node-ref block to the JSON ConnectedNodes or RequiredIDs field by per-node set
    agreement. Returns (json_field | None, agreement_fraction)."""
    best = (None, 0.0)
    for jf in ("ConnectedNodes", "RequiredIDs"):
        agree = total = 0
        for r in ca_rows:
            je = json_by_id.get(r.get(0))
            if not je or jf not in je:
                continue
            total += 1
            if {r.get(c) for c in block if r.get(c)} == set(je.get(jf) or []):
                agree += 1
        if total and agree / total > best[1]:
            best = (jf, round(agree / total, 4))
    return best


def _decode_entry_type(pairs, *, min_nonzero=50, score_threshold=0.85):
    """Prove the entry-type column by a ROBUST majority numeric->string mapping. A strict 1:1 that any
    single stale/noisy pair would reject fails against the real (stale) loose JSON; instead, for each
    candidate column map each numeric value to its MOST-COMMON JSON 'Type' string, and accept the column
    only when that mapping explains >= score_threshold of pairs, is injective, and has >= 2 classes.
    Returns (column, {str(int): str} mapping, evidence_count) or (None, {}, 0)."""
    from collections import Counter, defaultdict
    cols = set().union(*[set(r) for _, r in pairs]) if pairs else set()
    best = (None, {}, 0.0, 0)
    for c in sorted(cols):
        by_val, total = defaultdict(Counter), 0
        for je, row in pairs:
            if "Type" in je and c in row:
                by_val[row[c]][je["Type"]] += 1
                total += 1
        if total < min_nonzero or len(by_val) < 2:
            continue
        mapping = {v: cnt.most_common(1)[0][0] for v, cnt in by_val.items()}
        if len(set(mapping.values())) != len(mapping):        # mapping must be injective
            continue
        agree = sum(cnt[mapping[v]] for v, cnt in by_val.items())
        score = agree / total
        if score >= score_threshold and score > best[2]:
            best = (c, {str(k): v for k, v in mapping.items()}, score, total)
    return best[0], best[1], best[3]


def decode_layout(ca, class_types, tab_types, json_entries, *,
                  score_threshold: float = 0.85, margin_threshold: float = 0.15,
                  min_nonzero: int = 50) -> tuple[CharacterAdvancementLayout, dict]:
    """Resolve EVERY non-anchor adapter column from the loose-JSON schema key with recorded evidence,
    and emit the finished layout (no operator interpretation): scalars by exact-match correlation;
    the tab FK by correlation AND tag-domain membership; entry_type by a proven numeric->string
    mapping; and BOTH adjacency blocks by deterministic block discovery + `prove_adjacency_domain` +
    per-node set-match against the JSON's ConnectedNodes/RequiredIDs. A field is `high` only when its
    evidence clears the thresholds; otherwise it is left None/unproven (blocks canonical emission).
    Returns (layout, report); report['resolved_layout'] is the finished layout, loaded back by
    `load_resolved_layout` so `regenerate` consumes it with zero hand-editing."""
    ca_rows = ca.rows
    node_ids = {r.get(0) for r in ca_rows if r.get(0)}
    pairs = _unique_spell_pairs(ca_rows, json_entries)
    json_by_id = _json_by_id(json_entries)
    report = {"schema_version": "coa-ca-decode-report-v3", "unique_pairs": len(pairs),
              "thresholds": {"score": score_threshold, "margin": margin_threshold,
                             "min_nonzero": min_nonzero},
              "fields": {}}
    kwargs: dict = {}
    confidence: dict = {}

    def _record_scalar(attr, proof: ScalarProof | None, *, in_domain=True):
        if proof is None:
            report["fields"][attr] = {"confidence": "unproven", "column": None}
            return
        high = (proof.score >= score_threshold and proof.margin >= margin_threshold
                and proof.nonzero >= min_nonzero and in_domain)
        report["fields"][attr] = {
            "column": proof.column, "score": proof.score, "runner_up": proof.runner_up,
            "margin": proof.margin, "nonzero": proof.nonzero, "in_fk_domain": bool(in_domain),
            "confidence": "high" if high else "low"}
        if high:
            kwargs[attr] = proof.column
            confidence[_LEGALITY_NAME[attr]] = "high"

    # 1. scalar legality/position fields
    for json_field, attr in _SCALAR_FIELDS.items():
        _record_scalar(attr, correlate_scalar(pairs, json_field, min_nonzero=min_nonzero))

    # 2. tab-type FK: the loose JSON "Tab" is a display NAME string (e.g. "Frost"), NOT the numeric FK
    #    id, so a direct scalar correlation cannot match. Translate each name to its tab-type id via the
    #    resolved tab-types table, correlate the TRANSLATED id against columns, then require the winning
    #    column's non-zero domain to be tab-type ids. (Names already present as ids pass through.)
    name_to_tab_id = {name: tid for tid, name in tab_types.items()} if tab_types else {}
    def _tab_id(v):
        return v if v in tab_types else name_to_tab_id.get(v)
    tab_pairs = [({**je, "_TabId": _tab_id(je.get("Tab"))}, row)
                 for je, row in pairs if _tab_id(je.get("Tab")) is not None]
    tab_proof = correlate_scalar(tab_pairs, "_TabId", min_nonzero=min_nonzero)
    tab_domain_ok = bool(tab_types) and tab_proof is not None and all(
        r[tab_proof.column] in tab_types for r in ca_rows if r.get(tab_proof.column))
    _record_scalar("tab_type_col", tab_proof, in_domain=tab_domain_ok)

    # 3. entry-type: proven numeric -> JSON 'Type' string mapping
    et_col, et_map, et_ev = _decode_entry_type(pairs, min_nonzero=min_nonzero)
    report["fields"]["entry_type_col"] = {
        "column": et_col, "mapping": et_map, "evidence": et_ev,
        "confidence": "high" if et_col is not None else "unproven"}
    report["entry_type_map"] = et_map
    if et_col is not None:
        kwargs["entry_type_col"] = et_col
        kwargs["entry_type_map"] = et_map        # proven map rides into resolved_layout -> the reader
        confidence["entry_type"] = "high"

    # 4. adjacency: discover node-ref blocks, prove each, classify vs ConnectedNodes / RequiredIDs
    report["node_id_hit_rate"] = _node_id_hit_rate(ca_rows, node_ids)
    report["adjacency"] = []
    for block in _discover_adjacency_blocks(ca_rows, node_ids, min_nonzero=min_nonzero):
        domain, cols = prove_adjacency_domain(ca_rows, node_ids, block, min_nonzero=min_nonzero)
        jf, agree = (_classify_adjacency(ca_rows, json_by_id, block)
                     if domain == "node_id" else (None, 0.0))
        report["adjacency"].append({"block": list(block), "domain": domain,
                                    "json_field": jf, "agreement": agree})
        if domain == "node_id" and agree >= score_threshold:
            if jf == "ConnectedNodes":
                kwargs["connected_node_cols"] = cols
                confidence["connected_node_ids"] = "high"
            elif jf == "RequiredIDs":
                kwargs["required_id_cols"] = cols
                confidence["required_ids"] = "high"

    layout = CharacterAdvancementLayout(**kwargs, confidence=confidence)
    report["resolved_layout"] = {
        **{k: (list(v) if isinstance(v, tuple) else v) for k, v in kwargs.items()},
        "confidence": confidence}
    return layout, report


def load_resolved_layout(path) -> CharacterAdvancementLayout | None:
    """Reconstruct the resolved CharacterAdvancementLayout from a committed decode report's
    `resolved_layout` block, so `regenerate` consumes the proven layout with NO hand-editing."""
    p = Path(path)
    if not p.is_file():
        return None
    rl = json.loads(p.read_text()).get("resolved_layout")
    if not rl:
        return None
    conf = rl.pop("confidence", {})
    kwargs = {k: (tuple(v) if isinstance(v, list) else v) for k, v in rl.items()}
    return CharacterAdvancementLayout(**kwargs, confidence=conf)


def write_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_advancement_semantic.py -k "correlate or adjacency or decode_layout" -v`
Expected: PASS.

- [ ] **Step 5: Add the executable `decode-advancement` CLI subcommand**

In `cli.py`, add a `decode-advancement` subcommand so the decode is reproducible and **self-applying** — it opens the client (StormLib), reads `CharacterAdvancement` positionally + the companion `*Types` tables + the loose JSON, runs `decode_layout`, and writes the full report **including its `resolved_layout` block** to `--out`. There is **no** paste-block and no hand-edit of `dbc_layouts.py`: `regenerate` (Task 8) calls `decode_advancement.load_resolved_layout(report_path)` to rebuild the proven `CharacterAdvancementLayout` directly from the committed report, falling back to the anchors-only `CHARACTER_ADVANCEMENT` constant only when no report is present. Add a default-tier test that the subcommand's arg wiring parses (monkeypatched backend), and a `@pytest.mark.client` test that it runs end-to-end and every adapter-fed field it emits is `confidence: high` (i.e. `set(report["resolved_layout"]["confidence"]) ⊇` the adapter field set).

- [ ] **Step 6: Commit + client-tier decode run**

```bash
git add coa_client_extract/decode_advancement.py coa_client_extract/cli.py tests/test_client_extract_advancement_semantic.py
git commit -m "M1.14B: evidence-based CharacterAdvancement decode + self-applying decode-advancement command"
```

Then run the real decode (requires `COA_CLIENT_ROOT` + StormLib). It proves adjacency independently for `ConnectedNodes` and `RequiredIDs`, resolves tab (FK-domain-checked) + entry_type (proven numeric→string map) + the scalar legality/position fields the same evidence-based way, and writes `reports/client_extract/coa_ca_decode_report.json` with the finished `resolved_layout`. Any field not reaching `high` stays out of `confidence` and is Builder-fallback (adapter). Commit the report — that committed file *is* the layout `regenerate` consumes (no `dbc_layouts.py` edit):

```bash
python -m coa_client_extract decode-advancement \
  --client-root "$COA_CLIENT_ROOT" \
  --content-json "$COA_CLIENT_ROOT/Content/CharacterAdvancementData.json" \
  --out reports/client_extract/coa_ca_decode_report.json
git add reports/client_extract/coa_ca_decode_report.json
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


def _layout(confidence=None):
    return CharacterAdvancementLayout(
        node_id_col=0, spell_id_col=5, class_type_col=32, tab_type_col=6, entry_type_col=7,
        ae_cost_col=8, required_level_col=9, connected_node_cols=(10, 11), required_id_cols=(12,),
        max_rank_col=13, entry_type_map={"0": "Ability", "1": "Talent"},
        confidence=confidence if confidence is not None else {
            "tab_type": "high", "entry_type": "high",
            "ae_cost": "high", "required_level": "high",
            "connected_node_ids": "high", "required_ids": "high", "max_rank": "high",
        },
    )


def _ca(rows):
    # rows are dicts keyed by column index (decoded raw), the shape parse_positional produces.
    return _Table(rows)


def _row(node_id, spell, cls, tab=1, entry=0, ae=1, lvl=0, c1=0, c2=0, req=0, rank=1):
    return {0: node_id, 5: spell, 32: cls, 6: tab, 7: entry, 8: ae, 9: lvl,
            10: c1, 11: c2, 12: req, 13: rank}


def test_reads_node_with_ownership_and_confidence_gated_legality():
    ca = _ca([_row(6086, 805775, 33, tab=1, entry=0, ae=1, c1=0, c2=0)])
    n = read_advancement(ca, _class_types(), _tab_types(), _layout())[0]
    assert isinstance(n, AdvancementNode)
    assert n.node_id == 6086 and n.spell_id == 805775
    assert n.class_type_id == 33 and n.class_display == "Venomancer"
    assert n.tab_name == "Class" and n.entry_type == "Ability"
    assert n.legality["ae_cost"] == 1 and n.field_confidence["ae_cost"] == "high"
    assert n.legality["required_ids"] == []            # 0 padding dropped


def test_unproven_legality_field_is_withheld():
    # confidence lacks ae_cost -> it must NOT appear in legality even though the column is set
    layout = _layout(confidence={"required_level": "high"})
    n = read_advancement(_ca([_row(1, 100, 33)]), _class_types(), _tab_types(), layout)[0]
    assert "ae_cost" not in n.legality
    assert "required_level" in n.legality


def test_shared_spell_yields_two_nodes():
    ca = _ca([_row(7131, 503748, 15, tab=49, entry=1), _row(12264, 503748, 15, tab=1, entry=0)])
    nodes = read_advancement(ca, _class_types(), _tab_types(), _layout())
    assert {n.node_id for n in nodes} == {7131, 12264}
    assert {n.tab_name for n in nodes} == {"Brewing", "Class"}


def test_validate_semantics_rejects_dangling_adjacency():
    nodes = read_advancement(_ca([_row(1, 100, 33, c1=999)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="dangling"):
        validate_semantics(nodes, _class_types(), _tab_types())


def test_validate_semantics_rejects_out_of_range_level():
    nodes = read_advancement(_ca([_row(1, 100, 33, lvl=999)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="required_level"):
        validate_semantics(nodes, _class_types(), _tab_types())


def test_validate_semantics_rejects_unknown_class_band():
    ct = resolve_class_types(_Table([{"id": 99, "name": "Mystery"}]))
    nodes = read_advancement(_ca([_row(1, 100, 99)]), ct, _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="unknown class"):
        validate_semantics(nodes, ct, _tab_types())


def test_validate_semantics_rejects_duplicate_and_zero_node_ids():
    dup = read_advancement(_ca([_row(1, 100, 33), _row(1, 101, 33)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="duplicate node"):
        validate_semantics(dup, _class_types(), _tab_types())
    zero = read_advancement(_ca([_row(0, 100, 33)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="node id 0"):
        validate_semantics(zero, _class_types(), _tab_types())


def test_validate_semantics_rejects_unknown_tab_and_entry():
    bad_tab = read_advancement(_ca([_row(1, 100, 33, tab=777)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="unknown tab"):
        validate_semantics(bad_tab, _class_types(), _tab_types())
    bad_entry = read_advancement(_ca([_row(1, 100, 33, entry=99)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="unknown entry_type"):
        validate_semantics(bad_entry, _class_types(), _tab_types())


def test_validate_semantics_rejects_self_reference_and_excessive_cost():
    self_ref = read_advancement(_ca([_row(5, 100, 33, c1=5)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="self-reference"):
        validate_semantics(self_ref, _class_types(), _tab_types())
    huge = read_advancement(_ca([_row(1, 100, 33, ae=100000)]), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="ae_cost"):
        validate_semantics(huge, _class_types(), _tab_types())


def test_tab_type_and_entry_type_are_confidence_gated():
    # a layout that did NOT prove tab_type/entry_type high must withhold them (ownership is gated
    # exactly like legality) -> tab withheld, entry_type "" -> validate_semantics then blocks.
    layout = _layout(confidence={"ae_cost": "high"})   # tab_type/entry_type absent -> not high
    n = read_advancement(_ca([_row(1, 100, 33, tab=1, entry=0)]),
                         _class_types(), _tab_types(), layout)[0]
    assert n.tab_type_id == 0 and n.tab_name == ""     # withheld, not shipped as ownership
    assert n.entry_type == ""
    with pytest.raises(DbcSemanticError, match="unknown entry_type"):
        validate_semantics([n], _class_types(), _tab_types())


def test_graph_invariants_reject_missing_root():
    # two connected nodes in one tab, each requiring the other -> no root
    rows = [_row(1, 100, 33, tab=1, c1=2, req=2), _row(2, 101, 33, tab=1, c1=1, req=1)]
    nodes = read_advancement(_ca(rows), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="no root"):
        validate_semantics(nodes, _class_types(), _tab_types())


def test_graph_invariants_reject_orphan_node():
    # node 1 is an isolated root; node 2 has a prerequisite (not a root) but NO connected edge,
    # so it is unreachable from the roots over the visual tree -> orphan.
    rows = [_row(1, 100, 33, tab=1, c1=0, req=0), _row(2, 101, 33, tab=1, c1=0, req=1)]
    nodes = read_advancement(_ca(rows), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="orphan"):
        validate_semantics(nodes, _class_types(), _tab_types())


def test_graph_invariants_reject_prerequisite_cycle():
    # node 1 is a root connected to 2 and 3; nodes 2 and 3 require each other -> prerequisite cycle
    # (all three are reachable and a root exists, so only the acyclicity check fires)
    rows = [_row(1, 100, 33, tab=1, c1=2, c2=3, req=0), _row(2, 101, 33, tab=1, c1=1, req=3),
            _row(3, 102, 33, tab=1, c1=1, req=2)]
    nodes = read_advancement(_ca(rows), _class_types(), _tab_types(), _layout())
    with pytest.raises(DbcSemanticError, match="cycle"):
        validate_semantics(nodes, _class_types(), _tab_types())


def test_graph_invariants_accept_valid_tree():
    # 1 (root) -> 2 -> 3, a clean chain: root exists, all reachable via connected edges, acyclic
    rows = [_row(1, 100, 33, tab=1, c1=2, req=0), _row(2, 101, 33, tab=1, c1=3, req=1),
            _row(3, 102, 33, tab=1, c1=0, req=2)]
    nodes = read_advancement(_ca(rows), _class_types(), _tab_types(), _layout())
    validate_semantics(nodes, _class_types(), _tab_types())   # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_advancement.py -v`
Expected: FAIL with `ModuleNotFoundError: coa_client_extract.advancement`.

- [ ] **Step 3: Write the implementation**

```python
# coa_client_extract/advancement.py
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .errors import DbcSemanticError

_MAX_LEVEL = 60
# Plausibility ceilings (cells are unsigned, so a mis-mapped column reads as a huge int — an
# upper bound catches that where a negative check cannot). Generous but far below a stray uint32.
_MAX_COST = 500
_MAX_RANK = 20
_MAX_ROWCOL = 200

# Which legality fields are node-id references (validated against the node-id domain).
_ADJ_FIELDS = ("connected_node_ids", "required_ids")
# Scalar legality fields with an inclusive upper bound.
_BOUNDS = {"ae_cost": _MAX_COST, "te_cost": _MAX_COST, "required_tab_ae": _MAX_COST,
           "required_tab_te": _MAX_COST, "max_rank": _MAX_RANK, "row": _MAX_ROWCOL, "col": _MAX_ROWCOL}


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
    raw: dict                  # {cell_index: value} preserved for audit (explicit indices)


def _slots(row: dict, cols) -> list[int]:
    # gather node ids from fixed slot columns, dropping 0 padding, de-duped, sorted
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
    """Build nodes from positional rows. A legality field is emitted ONLY when the layout proved
    it to `high` confidence (layout.confidence); a configured-but-unproven column is withheld, so
    a mis-decoded column never becomes canonical output."""
    L = layout
    conf_map = L.confidence or {}
    nodes: list[AdvancementNode] = []
    # Ownership FK columns are confidence-gated exactly like legality scalars: a node's tab and entry
    # type are emitted only when their columns proved `high`. A wrong column that coincidentally
    # resolves to a valid FK is withheld (tab_type_id=0 / entry_type="") and then blocks in
    # validate_semantics, rather than being shipped as canonical ownership.
    tab_ok = L.tab_type_col is not None and conf_map.get("tab_type") == "high"
    entry_ok = L.entry_type_col is not None and conf_map.get("entry_type") == "high"
    for row in ca.rows:
        cid = row.get(L.class_type_col, 0)
        ct = class_types.get(cid)
        tab_id = row.get(L.tab_type_col, 0) if tab_ok else 0
        # proven numeric->string map from the decode (JSON keys are strings); never hard-coded
        etype = L.entry_type_map.get(str(row.get(L.entry_type_col, "")), "") if entry_ok else ""
        legality, conf = {}, {}

        def emit(name, value):
            if conf_map.get(name) == "high":     # gate every legality field on proven confidence
                legality[name] = value
                conf[name] = "high"

        for name, col in (
            ("ae_cost", L.ae_cost_col), ("te_cost", L.te_cost_col),
            ("required_level", L.required_level_col),
            ("required_tab_ae", L.required_tab_ae_col), ("required_tab_te", L.required_tab_te_col),
            ("max_rank", L.max_rank_col), ("row", L.row_col), ("col", L.column_col),
        ):
            if col is not None:
                emit(name, row.get(col, 0))
        if L.connected_node_cols:
            emit("connected_node_ids", _slots(row, L.connected_node_cols))
        if L.required_id_cols:
            emit("required_ids", _slots(row, L.required_id_cols))

        nodes.append(AdvancementNode(
            node_id=row.get(L.node_id_col, 0), spell_id=row.get(L.spell_id_col, 0),
            class_type_id=cid,
            class_internal=(ct.internal if ct else ""),
            class_display=(ct.display if ct else ""),
            class_kind=(ct.kind if ct else "unknown"),
            tab_type_id=tab_id,
            tab_name=(tab_types.get(tab_id, "") if tab_ok else ""),
            entry_type=etype, essence_kind=_essence_kind(etype),
            legality=legality, field_confidence=conf,
            raw=dict(row),
        ))
    return nodes


def validate_semantics(nodes, class_types, tab_types) -> None:
    """Reject a mis-decoded or structurally invalid graph. A matching WDBC header is not enough:
    ownership FKs must resolve, adjacency must resolve in the node-id domain, and scalars must be
    plausible. Any failure raises DbcSemanticError (blocks canonical emission)."""
    node_ids = {n.node_id for n in nodes}
    dup = [nid for nid, c in Counter(n.node_id for n in nodes).items() if c > 1]
    if dup:
        raise DbcSemanticError(f"duplicate node ids: {sorted(dup)[:10]}")
    for n in nodes:
        if n.node_id == 0:
            raise DbcSemanticError("node id 0 is invalid")
        if n.class_kind == "unknown":
            raise DbcSemanticError(f"node {n.node_id}: unknown class type {n.class_type_id}")
        if n.tab_type_id and n.tab_type_id not in tab_types:
            raise DbcSemanticError(f"node {n.node_id}: unknown tab type {n.tab_type_id}")
        if n.entry_type == "":
            raise DbcSemanticError(f"node {n.node_id}: unknown entry_type")
        for adj_field in _ADJ_FIELDS:
            for ref in n.legality.get(adj_field, []):
                if ref == n.node_id:
                    raise DbcSemanticError(f"node {n.node_id}: self-reference in {adj_field}")
                if ref not in node_ids:
                    raise DbcSemanticError(f"node {n.node_id}: dangling {adj_field} reference {ref}")
        lvl = n.legality.get("required_level")
        if lvl is not None and not (lvl == 0 or 1 <= lvl <= _MAX_LEVEL):
            raise DbcSemanticError(
                f"node {n.node_id}: required_level {lvl} outside {{0}} u [1,{_MAX_LEVEL}]")
        for field_name, ceiling in _BOUNDS.items():
            v = n.legality.get(field_name)
            if v is not None and v > ceiling:
                raise DbcSemanticError(f"node {n.node_id}: {field_name} {v} exceeds ceiling {ceiling}")
    _validate_graph_invariants(nodes)


def _validate_graph_invariants(nodes) -> None:
    """Per (class, tab) subgraph, reject a mis-decoded adjacency layout with graph-level invariants
    that node-level ownership equality does NOT imply (identical (spell, class, tab, type) membership
    says nothing about whether the adjacency EDGES form a valid graph):

      - every tab with >1 node has a root (a node with no in-subgraph prerequisite);
      - every node is reachable from the roots over the union of connected/required edges (no orphans);
      - the prerequisite (required_ids) graph is acyclic.

    Runs only when adjacency was decoded to `high` (present in `legality`); when adjacency is
    undecoded it leaves `adjacency_ready` false via the parity readiness gate, not a semantic error here."""
    from collections import defaultdict, deque
    if not any("connected_node_ids" in n.legality or "required_ids" in n.legality for n in nodes):
        return
    subgraphs = defaultdict(list)
    for n in nodes:
        subgraphs[(n.class_type_id, n.tab_type_id)].append(n)
    for (cid, tid), sub in subgraphs.items():
        ids = {n.node_id for n in sub}
        by_id = {n.node_id: n for n in sub}
        roots = [n.node_id for n in sub
                 if not [r for r in n.legality.get("required_ids", []) if r in ids]]
        if len(sub) > 1 and not roots:
            raise DbcSemanticError(
                f"class {cid} tab {tid}: no root node (every node has a prerequisite)")
        # reachability over the undirected connected-node (visual tree) edges, from the roots
        adj = defaultdict(set)
        for n in sub:
            for e in n.legality.get("connected_node_ids", []):
                if e in ids:
                    adj[n.node_id].add(e)
                    adj[e].add(n.node_id)
        seen, q = set(roots), deque(roots)
        while q:
            for nb in adj[q.popleft()]:
                if nb not in seen:
                    seen.add(nb)
                    q.append(nb)
        orphans = ids - seen
        if orphans:
            raise DbcSemanticError(
                f"class {cid} tab {tid}: {len(orphans)} unreachable/orphan node(s) "
                f"{sorted(orphans)[:5]}")
        # prerequisite graph must be acyclic (iterative DFS, three-color)
        color = dict.fromkeys(ids, 0)   # 0 white, 1 gray, 2 black
        for start in ids:
            if color[start] != 0:
                continue
            stack = [(start, iter([r for r in by_id[start].legality.get("required_ids", []) if r in ids]))]
            color[start] = 1
            while stack:
                u, it = stack[-1]
                nxt = next(it, None)
                if nxt is None:
                    color[u] = 2
                    stack.pop()
                elif color[nxt] == 1:
                    raise DbcSemanticError(f"class {cid} tab {tid}: prerequisite cycle at node {nxt}")
                elif color[nxt] == 0:
                    color[nxt] = 1
                    stack.append((nxt, iter([r for r in by_id[nxt].legality.get("required_ids", []) if r in ids])))
```

Note: `validate_semantics` requires `entry_type` and (when present) `tab_type` to resolve, so those
ownership columns must be decoded before extraction passes — enforcing the decode rather than shipping
a graph with unknown ownership. It also runs the per-(class, tab) **graph invariants** above: exact
node-level Builder ownership does **not** by itself imply a well-formed graph (identical membership
says nothing about the adjacency edges), so roots/reachability/acyclicity are checked explicitly.
These invariants run against real adjacency at the Task 10 acceptance; if the real client legitimately
violates a specific one (e.g. an intentional disconnected component), that invariant is relaxed with a
recorded justification rather than silently dropped.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_advancement.py -v`
Expected: PASS (all).

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
- Produces: `AttributionResult`, `SpellAttribution`, `attribute(nodes, class_types, skill_line_index=None)`, `derive_coa_skill_lines(skill_line_ability_rows, coa_spell_ids)`, `build_skill_line_index(skill_line_ability_rows, coa_line_ids)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_extract_attribution.py
from coa_client_extract.attribution import attribute, AttributionResult
from coa_client_extract.advancement import AdvancementNode


def _node(node_id, spell_id, cid, kind, display, tab_id=1, tab="Class", etype="Ability"):
    return AdvancementNode(
        node_id=node_id, spell_id=spell_id, class_type_id=cid, class_internal=display,
        class_display=display, class_kind=kind, tab_type_id=tab_id, tab_name=tab,
        entry_type=etype, essence_kind="ability", legality={}, field_confidence={}, raw={},
    )


def test_coa_membership_is_high_confidence_coa():
    nodes = [_node(1, 805775, 33, "coa_class", "Venomancer")]
    res = attribute(nodes, {})
    a = res[805775].result
    assert a.is_coa is True and a.modes == ("coa",) and a.exclusive_mode == "coa"
    assert a.confidence == "high"


def test_unknown_kind_contributes_no_mode_not_stock():
    # a node on an out-of-band (unknown) class must NOT be silently attributed as stock.
    nodes = [_node(1, 960, 999, "unknown", "???")]
    a = attribute(nodes, {})[960].result
    assert a.is_coa is False and a.modes == () and a.exclusive_mode is None
    assert a.confidence == "low"


def test_derive_and_build_skill_line_index_from_proven_lines():
    from coa_client_extract.attribution import derive_coa_skill_lines, build_skill_line_index
    # spell 900 is a known CoA graph spell attached to spec SkillLine 512 (NOT the 475-495 band);
    # 7777 is a graph-ABSENT spell on that same proven line -> medium-confidence coa fallback.
    rows = [
        {0: 1, 1: 512, 2: 900},    # proven CoA spell 900 on line 512 -> line 512 is a CoA line
        {0: 2, 1: 512, 2: 7777},   # graph-absent spell on the proven CoA line 512 -> coa (medium)
        {0: 3, 1: 44, 2: 1234},    # stock line -> ignored
        {0: 4, 1: 512, 2: 0},      # no spell -> ignored
    ]
    coa_lines = derive_coa_skill_lines(rows, coa_spell_ids={900})
    assert coa_lines == {512}                       # derived, not the hard-coded 475-495 range
    assert build_skill_line_index(rows, coa_lines) == {900: "coa", 7777: "coa"}


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

# class-kind -> participation mode. An unrecognized kind is deliberately absent:
# `.get(kind)` returns None so an out-of-band class contributes NO mode (never a
# silent "stock" default, which would mislabel unknowns as legal stock content).
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


def derive_coa_skill_lines(skill_line_ability_rows, coa_spell_ids):
    """PROVE the CoA SkillLine set empirically: the set of SkillLines that already carry at least one
    spell the registry attributed `coa`. Discovery showed CoA advancement spells attach to per-SPEC
    skill lines (Venomancer -> Stalking/Rot), not just the class-band lines 475-495, so a hard-coded
    range would miss most of them. Rows are positional dicts from `parse_positional(SkillLineAbility)`:
    col 1 = SkillLine FK, col 2 = Spell FK."""
    coa_spells = set(coa_spell_ids)
    return {row.get(1) for row in skill_line_ability_rows
            if row.get(2) in coa_spells and row.get(1)}


def build_skill_line_index(skill_line_ability_rows, coa_line_ids):
    """Map spell_id -> "coa" for abilities whose SkillLine is in the PROVEN CoA skill-line set
    (`derive_coa_skill_lines`). This is the medium-confidence fallback for spells absent from
    CharacterAdvancement.dbc — a graph-absent spell sharing a proven CoA line is likely CoA. The
    caller passes the derived set; there is no hard-coded skill-line range."""
    coa_lines = set(coa_line_ids)
    index: dict[int, str] = {}
    for row in skill_line_ability_rows:
        skill_line, spell_id = row.get(1), row.get(2)
        if skill_line in coa_lines and spell_id:
            index[spell_id] = "coa"
    return index


def attribute(nodes, class_types, skill_line_index=None) -> dict[int, SpellAttribution]:
    by_spell: dict[int, list] = defaultdict(list)
    for n in nodes:
        if n.spell_id:
            by_spell[n.spell_id].append(n)

    out: dict[int, SpellAttribution] = {}
    for spell_id, spell_nodes in by_spell.items():
        modes, memberships = [], []
        for n in spell_nodes:
            mode = _KIND_TO_MODE.get(n.class_kind)   # None for an unknown kind
            if mode and mode not in modes:
                modes.append(mode)
            memberships.append({
                "mode": mode or "unknown", "class_type_id": n.class_type_id,
                "class_internal": n.class_internal, "class_display": n.class_display,
                "tab_type_id": n.tab_type_id, "tab_name": n.tab_name,
                "node_id": n.node_id, "entry_type": n.entry_type,
            })
        modes = tuple(sorted(modes))
        is_coa = "coa" in modes
        # A graph-present spell with at least one recognized mode is high confidence;
        # if every node was an unknown kind, no mode is claimed -> low confidence.
        confidence = "high" if modes else "low"
        out[spell_id] = SpellAttribution(
            AttributionResult(is_coa, modes,
                              modes[0] if len(modes) == 1 else None, confidence),
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
Expected: PASS (8 tests).

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
- Produces: `build_advancement_records(nodes, *, provenance, spell_names=None, attribution=None) -> list[dict]`, `build_class_type_records(class_types) -> list[dict]`, `build_tab_type_records(tab_types) -> list[dict]`, `build_essence_raw_records(essence, *, provenance) -> list[dict]`, `fill_spell_attribution(spell_records, attribution) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_client_extract_artifacts.py
from coa_client_extract.artifacts import (
    build_advancement_records, build_class_type_records, build_tab_type_records,
    build_essence_raw_records, fill_spell_attribution,
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
        field_confidence={"ae_cost": "high", "connected_node_ids": "high"},
        raw={0: 6086, 5: 805775, 32: 33},
    )


def test_advancement_record_shape():
    attr = {805775: SpellAttribution(AttributionResult(True, ("coa",), "coa", "high"), [])}
    recs = build_advancement_records([_node()], provenance={"client_build": "3.3.5a+patch-CZZ"},
                                     spell_names={805775: "Adrenal Venom"}, attribution=attr)
    r = recs[0]
    assert r["schema_version"] == "coa-client-advancement-v1"
    assert r["node_id"] == 6086 and r["spell_id"] == 805775
    assert r["name"] == "Adrenal Venom"                 # joined from the client spell artifact
    assert r["class"]["display"] == "Venomancer" and r["class"]["kind"] == "coa_class"
    assert r["tab"] == {"tab_type_id": 1, "name": "Class"}
    assert r["legality"]["connected_node_ids"] == [6096, 7235]
    assert r["field_confidence"]["ae_cost"] == "high"
    assert r["raw"]["cols"] == {0: 6086, 5: 805775, 32: 33}    # index-keyed audit map
    assert r["provenance"]["client_build"] == "3.3.5a+patch-CZZ"
    assert r["coa_attribution"] == {"is_coa": True, "modes": ["coa"],
                                    "exclusive_mode": "coa", "confidence": "high"}


def test_advancement_record_attribution_absent_is_low():
    r = build_advancement_records([_node()], provenance={})[0]
    assert r["coa_attribution"] == {"is_coa": False, "modes": [],
                                    "exclusive_mode": None, "confidence": "low"}


def test_class_type_record_records_alias_provenance():
    cts = {22: ClassType(22, "SonOfArugal", "Bloodmage", "coa_class", "curated_alias",
                         ("builder_class_name", "project_owner_confirmation"))}
    r = build_class_type_records(cts)[0]
    assert r["schema_version"] == "coa-client-class-types-v1"
    assert r["internal"] == "SonOfArugal" and r["display"] == "Bloodmage"
    assert r["kind"] == "coa_class"
    assert r["display_source"] == "curated_alias"
    assert r["display_evidence"] == ["builder_class_name", "project_owner_confirmation"]


def test_tab_type_record_shape():
    recs = build_tab_type_records({1: "Class", 49: "Brewing"})
    assert {x["tab_type_id"]: x["name"] for x in recs} == {1: "Class", 49: "Brewing"}
    assert all(x["schema_version"] == "coa-client-tab-types-v1" for x in recs)


def test_fill_spell_attribution_replaces_unknown_and_keeps_raw_signals():
    spells = [{"schema_version": "coa-client-spell-v1", "spell_id": 805775,
               "coa_attribution": {"status": "unknown", "archive_family": "other", "id_range": "high"}}]
    membership = {"mode": "coa", "class_type_id": 33, "tab_name": "Class", "node_id": 6086}
    attr = {805775: SpellAttribution(
        AttributionResult(True, ("coa",), "coa", "high"), [membership])}
    rec = fill_spell_attribution(spells, attr)[0]
    a = rec["coa_attribution"]
    assert a["is_coa"] is True and a["modes"] == ["coa"] and a["exclusive_mode"] == "coa"
    assert a["archive_family"] == "other" and a["id_range"] == "high"   # raw signals retained
    assert "status" not in a
    assert rec["memberships"] == [membership]           # memberships attached, never discarded


def test_fill_spell_attribution_absent_spell_is_low():
    spells = [{"spell_id": 999, "coa_attribution": {"status": "unknown"}}]
    rec = fill_spell_attribution(spells, {})[0]
    assert rec["coa_attribution"] == {"is_coa": False, "modes": [],
                                      "exclusive_mode": None, "confidence": "low"}
    assert rec["memberships"] == []


def test_essence_raw_records_preserve_cells_and_provenance():
    # CharacterAdvancementEssence is per-level progression, extracted RAW (undecoded semantics);
    # caps are the documented constants AE 26 / TE 25, NOT decoded here.
    class _Ess:
        rows = [{0: 1, 1: 60, 2: 26}, {0: 2, 1: 61, 2: 25}]
    recs = build_essence_raw_records(_Ess(), provenance={"client_build": "3.3.5a+patch-CZZ"})
    assert len(recs) == 2
    assert recs[0]["schema_version"] == "coa-client-essence-v1"
    assert recs[0]["cols"] == {0: 1, 1: 60, 2: 26}      # raw cells, no column meaning asserted
    assert recs[0]["provenance"]["client_build"] == "3.3.5a+patch-CZZ"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_artifacts.py -v`
Expected: FAIL with `ImportError` for the new functions (`build_tab_type_records`, `build_essence_raw_records`).

- [ ] **Step 3: Add the writers to `artifacts.py`**

Append to `coa_client_extract/artifacts.py`:

```python
def _attribution_block(attr) -> dict:
    """One participation block from a SpellAttribution, or the low/absent default."""
    if attr is None:
        return {"is_coa": False, "modes": [], "exclusive_mode": None, "confidence": "low"}
    r = attr.result
    return {"is_coa": r.is_coa, "modes": list(r.modes),
            "exclusive_mode": r.exclusive_mode, "confidence": r.confidence}


def build_advancement_records(nodes, *, provenance: dict, spell_names: dict | None = None,
                              attribution: dict | None = None) -> list[dict]:
    spell_names = spell_names or {}
    attribution = attribution or {}
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
            "raw": {"cols": dict(n.raw)},              # index-keyed {cell_index: value} audit map
            "provenance": dict(provenance),
            "coa_attribution": _attribution_block(attribution.get(n.spell_id)),
        })
    return records


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


def build_tab_type_records(tab_types) -> list[dict]:
    """Emit coa-client-tab-types-v1 from the resolved {tab_type_id: name} map."""
    return [{"schema_version": "coa-client-tab-types-v1", "tab_type_id": tid, "name": name}
            for tid, name in sorted(tab_types.items())]


def build_essence_raw_records(essence, *, provenance: dict) -> list[dict]:
    """Emit CharacterAdvancementEssence RAW as coa-client-essence-v1.

    This table is per-level/per-tier essence *progression* data, NOT per-class caps (caps are the
    documented uniform constants AE 26 / TE 25). Its per-level semantics are undecoded, so M1.14B
    ships the raw index-keyed cells + provenance for auditability; the parity report reflects this as
    `readiness.leveling_progression_ready: false` (an M1.15 leveling gate) and it NEVER blocks any
    max-level readiness dimension or `full_builder_retirement_ready`. No column meaning is asserted here."""
    return [{"schema_version": "coa-client-essence-v1", "cols": dict(row),
             "provenance": dict(provenance)} for row in essence.rows]


def fill_spell_attribution(spell_records, attribution) -> list[dict]:
    for rec in spell_records:
        # Retain the M1.14A raw signals (archive_family/id_range) as provenance (spec: archive
        # family is kept as raw provenance only), and replace the M1.14A `status: unknown`.
        raw = rec.get("coa_attribution", {})
        keep = {k: raw[k] for k in ("archive_family", "id_range") if k in raw}
        attr = attribution.get(rec.get("spell_id"))
        block = _attribution_block(attr)
        block.update(keep)
        rec["coa_attribution"] = block
        # Stable multi-membership: attach the aggregated memberships[] (never a scalar that flips
        # to an array, never discarded). Absent attribution -> empty list.
        rec["memberships"] = list(attr.memberships) if attr is not None else []
    return spell_records
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_artifacts.py -v`
Expected: PASS (existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/artifacts.py tests/test_client_extract_artifacts.py
git commit -m "M1.14B: advancement/class-type/tab-type/raw-essence writers + fill spell attribution (memberships)"
```

---

## Task 7: Node-level (node-id crosswalk) Builder-parity report

**Files:**
- Create: `coa_client_extract/parity.py`
- Test: `tests/test_client_extract_parity.py`

**Interfaces:**
- Consumes: `advancement.AdvancementNode` (its `node_id` is the node identity, and its `legality` dict carries `high`-confidence `connected_node_ids`/`required_ids` + legality scalars); Builder entries as dicts with `entry_id` (the node identity), `spell_id`, `class_name`, `tab_name`, `entry_type`, `connected_node_ids`, `required_ids`, and legality fields — the real shape of `coa_scraper/dist/coa_entries.jsonl` (verified: 3,612 records, unique `entry_id`s, adjacency references `entry_id`s).
- Produces: `build_parity_report(nodes, builder_entries, *, class_types=None, low_confidence_fields=(), unresolved_layout_columns=(), expected_builder_records=None, provenance=None) -> dict` and `flip_gate_inputs(layout) -> tuple[list[str], list[str]]`. The report **computes** ownership (node-id `entry_id`↔`node_id` crosswalk), `identity_mismatches`, per-class AND per-tab counts, `adjacency_mismatches`, and Decision-22-classified `legality_diffs` internally — nothing is passed in pre-computed. It emits a scoped `readiness` object (`attribution_ready`, `ownership_ready`, `adjacency_ready`, per-field `legality`, cosmetic `layout`, `leveling_progression_ready`, `full_builder_retirement_ready`) plus a flat `blockers` diagnostic list. A proven field supersedes the Builder for itself alone; an unresolved legality field blocks flipping THAT field (and `full_builder_retirement_ready`) but never attribution/ownership. The undecoded raw essence sets `leveling_progression_ready` false separately and never blocks.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_extract_parity.py
from coa_client_extract.parity import build_parity_report, flip_gate_inputs
from coa_client_extract.advancement import AdvancementNode
from coa_client_extract.class_types import ClassType


def _node(node_id, spell_id, display, tab, etype="Ability", *, legality=None):
    return AdvancementNode(
        node_id=node_id, spell_id=spell_id, class_type_id=33, class_internal=display,
        class_display=display, class_kind="coa_class", tab_type_id=1, tab_name=tab,
        entry_type=etype, essence_kind="ability", legality=legality or {},
        field_confidence={}, raw={},
    )


def _builder(entry_id, spell_id, display, tab, etype="Ability", *,
             connected=None, required=None, **legality):
    b = {"entry_id": entry_id, "spell_id": spell_id, "class_name": display,
         "tab_name": tab, "entry_type": etype,
         "connected_node_ids": connected or [], "required_ids": required or []}
    b.update(legality)      # ae_cost, te_cost, required_level, ...
    return b


def _clean_pair():
    # one Witch Doctor node, identical on both sides; adjacency + legality decoded high and matching
    nodes = [_node(7131, 503748, "Witch Doctor", "Brewing", "Talent",
                   legality={"ae_cost": 1, "connected_node_ids": [7132], "required_ids": []})]
    builder = [_builder(7131, 503748, "Witch Doctor", "Brewing", "Talent",
                        connected=[7132], required=[], ae_cost=1)]
    return nodes, builder


def test_exact_node_id_ownership_and_per_tab_counts():
    nodes = [
        _node(7131, 503748, "Witch Doctor", "Brewing", "Talent"),
        _node(12264, 503748, "Witch Doctor", "Class", "Ability"),
    ]
    builder = [
        _builder(7131, 503748, "Witch Doctor", "Brewing", "Talent"),
        _builder(12264, 503748, "Witch Doctor", "Class", "Ability"),
    ]
    rep = build_parity_report(nodes, builder)
    assert rep["builder_records"] == 2 and rep["client_nodes"] == 2
    assert rep["builder_only_records"] == 0 and rep["client_only_records"] == 0
    assert rep["identity_mismatches"] == 0
    assert rep["ownership_recall"] == 1.0 and rep["ownership_precision"] == 1.0
    assert rep["per_class"]["Witch Doctor"]["client_nodes"] == 2
    brewing = next(x for x in rep["per_tab"]
                   if x["class"] == "Witch Doctor" and x["tab"] == "Brewing")
    assert brewing["client_nodes"] == 1 and brewing["builder_records"] == 1
    # clean synthetic case with nothing withheld -> every readiness dimension earns true
    assert rep["blockers"] == []
    assert rep["readiness"]["ownership_ready"] is True
    assert rep["readiness"]["attribution_ready"] is True
    assert rep["readiness"]["full_builder_retirement_ready"] is True
    assert rep["readiness"]["leveling_progression_ready"] is False   # essence undecoded, separate, never blocks


def test_builder_only_node_breaks_ownership_not_attribution():
    nodes = [_node(7131, 503748, "Witch Doctor", "Brewing", "Talent")]   # missing 12264
    builder = [
        _builder(7131, 503748, "Witch Doctor", "Brewing", "Talent"),
        _builder(12264, 503748, "Witch Doctor", "Class", "Ability"),
    ]
    rep = build_parity_report(nodes, builder)
    assert rep["builder_only_records"] == 1 and 12264 in rep["builder_only_sample"]
    assert rep["ownership_recall"] < 1.0
    assert "builder_only_node_instances" in rep["blockers"]
    assert rep["readiness"]["ownership_ready"] is False
    assert rep["readiness"]["attribution_ready"] is True   # attribution is anchor-based, independent
    assert rep["readiness"]["full_builder_retirement_ready"] is False


def test_client_only_node_breaks_ownership_precision():
    # client covers every Builder node (recall 1.0) but adds an extra wrongly-attributed CoA node
    nodes = [
        _node(7131, 503748, "Witch Doctor", "Brewing", "Talent"),
        _node(99999, 999999, "Witch Doctor", "Class", "Ability"),   # not in Builder
    ]
    builder = [_builder(7131, 503748, "Witch Doctor", "Brewing", "Talent")]
    rep = build_parity_report(nodes, builder)
    assert rep["ownership_recall"] == 1.0 and rep["ownership_precision"] < 1.0
    assert rep["client_only_records"] == 1 and 99999 in rep["client_only_sample"]
    assert "client_only_node_instances" in rep["blockers"]
    assert rep["readiness"]["ownership_ready"] is False


def test_identity_mismatch_same_id_different_anchor_breaks_ownership():
    # node_id matches an entry_id but the anchored (spell_id, class) disagrees -> decode/attribution
    # defect. tab/entry_type are deliberately NOT part of the identity tuple (they are decode-gated).
    nodes = [_node(7131, 503748, "Witch Doctor", "Brewing", "Talent")]
    builder = [_builder(7131, 888888, "Witch Doctor", "Brewing", "Talent")]   # spell_id differs
    rep = build_parity_report(nodes, builder)
    assert rep["builder_only_records"] == 0 and rep["client_only_records"] == 0
    assert rep["identity_mismatches"] == 1
    assert "identity_mismatch" in rep["blockers"]
    assert rep["readiness"]["ownership_ready"] is False


def test_adjacency_mismatch_breaks_adjacency_not_ownership():
    nodes = [_node(7131, 503748, "Witch Doctor", "Brewing", "Talent",
                   legality={"connected_node_ids": [7132, 7133], "required_ids": []})]
    builder = [_builder(7131, 503748, "Witch Doctor", "Brewing", "Talent",
                        connected=[7132], required=[])]        # client has an extra edge
    rep = build_parity_report(nodes, builder)
    assert rep["adjacency_mismatches"] == 1 and 7131 in rep["adjacency_mismatch_sample"]
    assert "adjacency_mismatch" in rep["blockers"]
    assert rep["readiness"]["adjacency_ready"] is False
    assert rep["readiness"]["ownership_ready"] is True     # ownership is independent of adjacency
    assert rep["readiness"]["full_builder_retirement_ready"] is False


def test_legality_class_b_difference_recorded_but_field_stays_ready():
    # client decoded ae_cost high; value differs from Builder -> client wins offline (class b)
    nodes = [_node(7131, 503748, "Witch Doctor", "Brewing", "Talent",
                   legality={"ae_cost": 2, "connected_node_ids": [], "required_ids": []})]
    builder = [_builder(7131, 503748, "Witch Doctor", "Brewing", "Talent",
                        connected=[], required=[], ae_cost=1)]
    rep = build_parity_report(nodes, builder)
    diffs = [d for d in rep["legality_diffs"] if d["field"] == "ae_cost"]
    assert diffs and diffs[0]["class"] == "b" and diffs[0]["client"] == 2 and diffs[0]["builder"] == 1
    # ae_cost decoded high (nothing withheld) -> stays ready despite the client-wins value diff
    assert rep["readiness"]["legality"]["ae_cost"] == "ready"


def test_undecoded_legality_blocks_retirement_not_ownership():
    # THE scoped-readiness invariant: an unresolved legality field blocks flipping THAT field and
    # full_builder_retirement, but never ownership or attribution.
    nodes, builder = _clean_pair()
    rep = build_parity_report(nodes, builder,
                              low_confidence_fields=["te_cost"],
                              unresolved_layout_columns=["max_rank"])
    assert "low_confidence:te_cost" in rep["blockers"]
    assert "unresolved_layout_column:max_rank" in rep["blockers"]
    assert rep["readiness"]["legality"]["te_cost"] == "unresolved"
    assert rep["readiness"]["legality"]["max_rank"] == "unresolved"
    assert rep["readiness"]["legality"]["required_level"] == "ready"   # not withheld -> ready
    assert rep["readiness"]["full_builder_retirement_ready"] is False
    assert rep["readiness"]["ownership_ready"] is True                 # unaffected by legality
    assert rep["readiness"]["attribution_ready"] is True


def test_cosmetic_layout_fields_never_block():
    nodes, builder = _clean_pair()
    rep = build_parity_report(nodes, builder, unresolved_layout_columns=["row"])
    assert rep["readiness"]["layout"]["row"] == "unresolved"
    # row is cosmetic: it must not drag down retirement (all required legality here is ready)
    assert rep["readiness"]["full_builder_retirement_ready"] is True


def test_cardinality_and_expected_count_gates():
    nodes, builder = _clean_pair()
    cts = {i: ClassType(i, f"C{i}", f"C{i}", "coa_class") for i in range(14, 34)}  # only 20 playable
    cts[35] = ClassType(35, "ConquestOfAzeroth", "ConquestOfAzeroth", "coa_system")
    rep = build_parity_report(nodes, builder, class_types=cts, expected_builder_records=3612)
    assert "playable_class_count" in rep["blockers"]      # 20 != 21
    assert "builder_record_count" in rep["blockers"]      # 1 != 3612
    assert rep["readiness"]["attribution_ready"] is False  # taxonomy broken
    assert rep["readiness"]["ownership_ready"] is False


def test_empty_inputs_block():
    rep = build_parity_report([], [], provenance={"client_build": "3.3.5a+patch-CZZ"})
    assert "empty_client_input" in rep["blockers"]
    assert "empty_builder_input" in rep["blockers"]
    assert rep["provenance"]["client_build"] == "3.3.5a+patch-CZZ"
    assert rep["readiness"]["ownership_ready"] is False
    assert rep["readiness"]["attribution_ready"] is False   # no coa_nodes


def test_flip_gate_inputs_splits_unresolved_from_low_confidence():
    from coa_client_extract.dbc_layouts import CharacterAdvancementLayout
    layout = CharacterAdvancementLayout(
        tab_type_col=3, entry_type_col=4,
        ae_cost_col=5,                       # resolved but not proven high -> low_confidence
        required_level_col=None,             # never resolved -> unresolved
        connected_node_cols=(7, 8),          # resolved but not proven high -> low_confidence
        required_id_cols=(),                 # never resolved -> unresolved
        confidence={"ae_cost": "medium", "connected_node_ids": "low",
                    "tab_type": "high", "entry_type": "high"},
    )
    low, unresolved = flip_gate_inputs(layout)
    assert "ae_cost" in low and "connected_node_ids" in low
    assert "required_level" in unresolved and "required_ids" in unresolved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_parity.py -v`
Expected: FAIL with `ModuleNotFoundError: coa_client_extract.parity`.

- [ ] **Step 3: Write the implementation**

```python
# coa_client_extract/parity.py
from __future__ import annotations

# adapter columns -> the CharacterAdvancementLayout attribute holding their column index.
_SCALAR_FIELD_COLS = {
    "ae_cost": "ae_cost_col", "te_cost": "te_cost_col", "required_level": "required_level_col",
    "required_tab_ae": "required_tab_ae_col", "required_tab_te": "required_tab_te_col",
    "max_rank": "max_rank_col", "row": "row_col", "col": "column_col",
    "tab_type": "tab_type_col", "entry_type": "entry_type_col",
}
_ADJACENCY_FIELD_COLS = {"connected_node_ids": "connected_node_cols", "required_ids": "required_id_cols"}

# legality scalars compared per node when the client decoded them to `high` (incl. cosmetic row/col).
_LEGALITY_FIELDS = ("ae_cost", "te_cost", "required_level", "required_tab_ae",
                    "required_tab_te", "max_rank", "row", "col")
# the REQUIRED legality responsibilities that gate per-field readiness + full_builder_retirement_ready.
# row/col are cosmetic layout fields (readiness.layout) and are deliberately excluded here.
_REQUIRED_LEGALITY = ("required_level", "ae_cost", "te_cost", "required_tab_ae",
                      "required_tab_te", "max_rank")

EXPECTED_BUILDER_RECORDS = 3612   # pinned Builder artifact size (the CLI passes this to guard truncation)


def flip_gate_inputs(layout):
    """Derive (low_confidence_fields, unresolved_layout_columns) from a resolved
    CharacterAdvancementLayout. A column never resolved (None / empty tuple) is 'unresolved'; a
    resolved column that did not prove to `high` confidence is 'low_confidence'. Both mark the field
    not-high, which build_parity_report turns into per-field readiness. Adjacency columns are handled
    the same way — their *value* agreement with the Builder is measured separately (adjacency_mismatches),
    but if adjacency never decoded high it is unresolved (so `adjacency_ready` cannot be true)."""
    conf = layout.confidence or {}
    low, unresolved = [], []
    for field, attr in {**_SCALAR_FIELD_COLS, **_ADJACENCY_FIELD_COLS}.items():
        col = getattr(layout, attr)
        resolved = col is not None and col != ()
        if not resolved:
            unresolved.append(field)
        elif conf.get(field) != "high":
            low.append(field)
    return low, unresolved


def _identity(spell_id, class_name):
    # The ownership-alignment identity uses ONLY the structurally-anchored fields: spell_id (col 5)
    # and class (col 32 FK). tab_name/entry_type are decode-gated (often unresolved) and must NOT
    # enter this tuple — otherwise a node whose tab/entry_type simply hasn't decoded would read as an
    # identity mismatch, coupling ownership to metadata decode (which Decision 21 keeps independent).
    return (int(spell_id), class_name)


def _norm(v):
    # normalize representation differences (Decision 22 class c): missing/None == 0
    return 0 if v is None else v


def build_parity_report(nodes, builder_entries, *, class_types=None,
                        low_confidence_fields=(), unresolved_layout_columns=(),
                        expected_builder_records=None, provenance=None) -> dict:
    """Node-level Builder-parity report + a SCOPED, per-responsibility/per-field `readiness` object
    (Decision 21), computing every comparison from a real node-id crosswalk.

    The Builder's `entry_id` and the client's `node_id` are the same advancement-row identity; the
    report crosswalks them directly and proves the id spaces align by checking each matched id's
    anchored tuple (spell_id, class) — `identity_mismatches`. Ownership is an exact
    SET over node ids: `builder_only` AND `client_only` must both be empty (a client graph that covers
    every Builder node but adds extras is not ownership-ready). Adjacency and legality are compared per
    matched node; legality differences are classified per Decision 22.

    There is NO single flip boolean. Instead `readiness` earns each dimension independently:
    `attribution_ready` (anchored class_type FK + 21-class cardinality, no legality dependency),
    `ownership_ready` (exact ownership + zero identity_mismatches + count/cardinality guards),
    `adjacency_ready` (both edge domains decoded high AND zero adjacency_mismatches), per-field
    `legality[field]` (`ready` only when decoded high and not a Decision-22 (a)/(d) defect; else
    `unresolved`, which keeps the Builder fallback and blocks flipping THAT field only — never
    attribution/ownership), cosmetic `layout.row`/`layout.col` (block nothing), a separate
    `leveling_progression_ready: False` (raw essence, M1.15), and the roll-up
    `full_builder_retirement_ready`. `blockers` is a flat diagnostic list of the specific unmet
    conditions, mirrored by the readiness object (not itself a gate). `low_confidence_fields` /
    `unresolved_layout_columns` come from `flip_gate_inputs(layout)`; a field is decoded-high iff it is
    in neither."""
    coa_nodes = [n for n in nodes if n.class_kind == "coa_class"]
    client_by_id = {n.node_id: n for n in coa_nodes}
    builder_by_id = {int(e["entry_id"]): e for e in builder_entries}
    client_ids, builder_ids = set(client_by_id), set(builder_by_id)
    matched = client_ids & builder_ids
    builder_only_ids = sorted(builder_ids - client_ids)
    client_only_ids = sorted(client_ids - builder_ids)

    # identity: matched ids whose anchored (spell_id, class) tuple disagrees — proves the id spaces
    # align (not accidental id collisions), using only structurally-verified anchors so an undecoded
    # tab/entry_type never fabricates a mismatch.
    identity_mismatch_ids = [
        nid for nid in matched
        if _identity(client_by_id[nid].spell_id, client_by_id[nid].class_display)
        != _identity(builder_by_id[nid]["spell_id"], builder_by_id[nid]["class_name"])]

    # adjacency parity (computed) over matched nodes that decoded adjacency to `high`
    adjacency_mismatch_ids = set()
    for nid in matched:
        n, e = client_by_id[nid], builder_by_id[nid]
        for field in ("connected_node_ids", "required_ids"):
            if field in n.legality and set(n.legality[field]) != set(e.get(field) or []):
                adjacency_mismatch_ids.add(nid)

    # legality parity (computed, Decision-22 classified) over matched nodes. Only fields the client
    # decoded to `high` (present in n.legality) are value-compared -> class (b) or (c); a field the
    # client could not decode is captured globally by low_confidence/unresolved (class a/d).
    legality_diffs = []
    for nid in matched:
        n, e = client_by_id[nid], builder_by_id[nid]
        for f in _LEGALITY_FIELDS:
            if f in e and f in n.legality:
                cv, bv = _norm(n.legality[f]), _norm(e[f])
                if cv != bv:                     # proven-high client value differs -> client wins
                    legality_diffs.append({"node_id": nid, "field": f,
                                           "client": cv, "builder": bv, "class": "b"})

    # per-class and per-tab node counts (+ the asymmetric-only tallies)
    def _counts(key):
        cc = {}
        blank = lambda: {"client_nodes": 0, "builder_records": 0, "client_only": 0, "builder_only": 0}
        for n in coa_nodes:
            cc.setdefault(key(n.class_display, n.tab_name), blank())["client_nodes"] += 1
        for e in builder_entries:
            cc.setdefault(key(e["class_name"], e.get("tab_name", "")), blank())["builder_records"] += 1
        for nid in client_only_ids:
            n = client_by_id[nid]
            cc[key(n.class_display, n.tab_name)]["client_only"] += 1
        for nid in builder_only_ids:
            e = builder_by_id[nid]
            cc[key(e["class_name"], e.get("tab_name", ""))]["builder_only"] += 1
        return cc

    per_class = _counts(lambda cls, tab: cls)
    per_tab = [{"class": cls, "tab": tab, **v}
               for (cls, tab), v in sorted(_counts(lambda cls, tab: (cls, tab)).items())]

    ownership_recall = round(len(matched) / len(builder_ids), 4) if builder_ids else 1.0
    ownership_precision = round(len(matched) / len(client_ids), 4) if client_ids else 1.0
    client_spells = {n.spell_id for n in coa_nodes}
    builder_spells = {int(e["spell_id"]) for e in builder_entries}

    # ---- scoped readiness (Decision 21). A field is decoded-high iff it is in neither
    # low_confidence_fields nor unresolved_layout_columns (both come from flip_gate_inputs(layout)).
    not_high = set(low_confidence_fields) | set(unresolved_layout_columns)
    field_ready = lambda f: f not in not_high

    taxonomy_ok = class_types is None or (
        sum(1 for c in class_types.values() if c.kind == "coa_class") == 21
        and not (class_types.get(35) is not None and class_types.get(35).kind == "coa_class"))
    count_ok = expected_builder_records is None or len(builder_entries) == expected_builder_records

    # attribution rests on the anchored class_type FK — NO legality dependency
    attribution_ready = bool(coa_nodes) and taxonomy_ok
    # ownership: exact node-id ownership + identity-tuple parity + count/cardinality/non-empty guards
    ownership_ready = (bool(coa_nodes) and bool(builder_entries) and taxonomy_ok and count_ok
                       and not builder_only_ids and not client_only_ids and not identity_mismatch_ids)
    # adjacency: BOTH edge domains decoded high AND zero per-node mismatches
    adjacency_ready = (field_ready("connected_node_ids") and field_ready("required_ids")
                       and not adjacency_mismatch_ids)
    # per-field legality readiness: `ready` only when decoded high (class b/c proven diffs stay ready;
    # a/d undecoded stay unresolved). row/col are cosmetic layout, never gating.
    legality_readiness = {f: ("ready" if field_ready(f) else "unresolved") for f in _REQUIRED_LEGALITY}
    layout_readiness = {"row": "ready" if field_ready("row") else "unresolved",
                        "col": "ready" if field_ready("col") else "unresolved"}
    full_builder_retirement_ready = (
        attribution_ready and ownership_ready and adjacency_ready
        and all(v == "ready" for v in legality_readiness.values()))

    readiness = {
        "attribution_ready": attribution_ready,
        "ownership_ready": ownership_ready,
        "adjacency_ready": adjacency_ready,
        "legality": legality_readiness,
        "layout": layout_readiness,
        # raw essence progression is undecoded in M1.14B: a SEPARATE M1.15 leveling gate that never
        # blocks any max-level dimension or full_builder_retirement_ready.
        "leveling_progression_ready": False,
        "full_builder_retirement_ready": full_builder_retirement_ready,
    }

    # flat diagnostic list of the specific unmet conditions (mirrors readiness; NOT itself a gate)
    blockers: list[str] = []
    if not coa_nodes:
        blockers.append("empty_client_input")
    if not builder_entries:
        blockers.append("empty_builder_input")
    if class_types is not None and sum(1 for c in class_types.values() if c.kind == "coa_class") != 21:
        blockers.append("playable_class_count")
    if class_types is not None and (class_types.get(35) is not None
                                    and class_types.get(35).kind == "coa_class"):
        blockers.append("sentinel_not_excluded")
    if not count_ok:
        blockers.append("builder_record_count")
    if builder_only_ids:
        blockers.append("builder_only_node_instances")
    if client_only_ids:
        blockers.append("client_only_node_instances")
    if identity_mismatch_ids:
        blockers.append("identity_mismatch")
    if adjacency_mismatch_ids:
        blockers.append("adjacency_mismatch")
    blockers += [f"low_confidence:{f}" for f in low_confidence_fields]
    blockers += [f"unresolved_layout_column:{c}" for c in unresolved_layout_columns]

    report = {
        "schema_version": "coa-builder-parity-v2",
        "builder_records": len(builder_entries),
        "client_nodes": len(coa_nodes),
        "unique_spell_recall": round(len(client_spells & builder_spells) / len(builder_spells), 4)
                               if builder_spells else 1.0,
        "ownership_recall": ownership_recall,
        "ownership_precision": ownership_precision,
        "builder_only_records": len(builder_only_ids),
        "client_only_records": len(client_only_ids),
        "builder_only_sample": builder_only_ids[:20],
        "client_only_sample": client_only_ids[:20],
        "identity_mismatches": len(identity_mismatch_ids),
        "identity_mismatch_sample": sorted(identity_mismatch_ids)[:20],
        "per_class": per_class,
        "per_tab": per_tab,
        "adjacency_mismatches": len(adjacency_mismatch_ids),
        "adjacency_mismatch_sample": sorted(adjacency_mismatch_ids)[:20],
        "legality_diffs": legality_diffs,
        "readiness": readiness,
        "blockers": blockers,
    }
    if provenance:
        report["provenance"] = dict(provenance)   # Decision 10 reproducibility pins
    return report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_parity.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/parity.py tests/test_client_extract_parity.py
git commit -m "M1.14B: crosswalk Builder-parity report + scoped per-responsibility/per-field readiness"
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
    ess = _pos_dbc([{0: 1, 1: 60, 2: 26}], 9, 36)               # raw progression row (semantics undecoded)
    sla = _pos_dbc([], 14, 56)                                  # empty SkillLineAbility (fallback unused)
    return ca, ct, tt, ess, sla
```

In `_fake_backend()`, add the five tables to `entries` (all supplied by `common.MPQ` like the spell family):

```python
    ca, ct, tt, ess, sla = _ca_tables()
    entries["DBFilesClient\\CharacterAdvancement.dbc"] = [(Path("common.MPQ"), ca)]
    entries["DBFilesClient\\CharacterAdvancementClassTypes.dbc"] = [(Path("common.MPQ"), ct)]
    entries["DBFilesClient\\CharacterAdvancementTabTypes.dbc"] = [(Path("common.MPQ"), tt)]
    entries["DBFilesClient\\CharacterAdvancementEssence.dbc"] = [(Path("common.MPQ"), ess)]
    entries["DBFilesClient\\SkillLineAbility.dbc"] = [(Path("common.MPQ"), sla)]
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
    assert spell["memberships"][0]["class_display"] == "Venomancer"   # stable memberships[] attached
    adv = [json.loads(l) for l in (out / "coa_client_advancement.jsonl").read_text().splitlines()]
    assert adv[0]["schema_version"] == "coa-client-advancement-v1"
    assert adv[0]["class"]["display"] == "Venomancer" and adv[0]["name"] == "Adrenal Venom"
    assert adv[0]["coa_attribution"]["is_coa"] is True
    assert adv[0]["raw"]["cols"]["0"] == 6086       # index-keyed audit map (JSON stringifies int keys)
    assert (out / "coa_client_class_types.jsonl").is_file()
    tabs = [json.loads(l) for l in (out / "coa_client_tab_types.jsonl").read_text().splitlines()]
    assert tabs[0]["schema_version"] == "coa-client-tab-types-v1" and tabs[0]["name"] == "Class"
    ess = [json.loads(l) for l in (out / "coa_client_essence.jsonl").read_text().splitlines()]
    assert ess[0]["schema_version"] == "coa-client-essence-v1"      # raw progression, undecoded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_cli.py -v`
Expected: FAIL — `regenerate` does not yet read CharacterAdvancement / emit `coa_client_advancement.jsonl`, and the updated `is_coa` assertion is unmet.

- [ ] **Step 3: Extend `regenerate` in `cli.py`**

In `coa_client_extract/cli.py`, after the existing spell/content extraction and before writing outputs, add the advancement pipeline. Read the companion tables through the backend (effective chain), resolve class/tab types, read + validate the advancement graph, attribute spells, and write the new artifacts:

```python
# --- inside regenerate(), after content_records is built, before out_dir writes ---
import hashlib
from .class_types import resolve_class_types, resolve_tab_types, assert_playable_cardinality
from .advancement import read_advancement, validate_semantics
from .attribution import attribute, derive_coa_skill_lines, build_skill_line_index
from .artifacts import (
    build_advancement_records, build_class_type_records, build_tab_type_records,
    build_essence_raw_records, fill_spell_attribution,
)
from .decode_advancement import load_resolved_layout
from .wdbc import parse_dbc, parse_positional
from .dbc_layouts import (
    CHARACTER_ADVANCEMENT_CLASS_TYPES, CHARACTER_ADVANCEMENT_TAB_TYPES, CHARACTER_ADVANCEMENT,
    CHARACTER_ADVANCEMENT_ESSENCE, CHARACTER_ADVANCEMENT_SKILL_LINE_ABILITY,
)

# CANONICAL emission parses STRICT: a structural header mismatch raises before anything is written,
# so no canonical artifact is ever emitted with header drift. (Non-strict parsing lives only in the
# exploratory decode-advancement command.)
def read_named(name, layout):
    m = backend.read_effective_file(root, attach, f"DBFilesClient\\{name}.dbc")
    return m, parse_dbc(m.data, layout, strict=True)          # named columns incl. "name" (col 1)

def read_positional(name, fc, rs):
    m = backend.read_effective_file(root, attach, f"DBFilesClient\\{name}.dbc")
    return m, parse_positional(m.data, fc, rs, strict=True)   # {index: value} rows

ct_member, ct_tbl = read_named("CharacterAdvancementClassTypes", CHARACTER_ADVANCEMENT_CLASS_TYPES)
tt_member, tt_tbl = read_named("CharacterAdvancementTabTypes", CHARACTER_ADVANCEMENT_TAB_TYPES)
# The layout is the PROVEN one from the committed decode report (self-applying, no hand-edit); tests
# inject a synthetic layout; the anchors-only constant is only a last resort.
ca_layout = ((load_resolved_layout(ca_decode_report) if ca_decode_report else None)
             or (layouts.get("CharacterAdvancementLayout") if layouts else None)
             or CHARACTER_ADVANCEMENT)
ca_member, ca_raw = read_positional("CharacterAdvancement",
                                    ca_layout.header_field_count, ca_layout.header_record_size)
ess_member, ess_raw = read_positional("CharacterAdvancementEssence",
                                      CHARACTER_ADVANCEMENT_ESSENCE.expected_field_count,
                                      CHARACTER_ADVANCEMENT_ESSENCE.expected_record_size)
sla_member, sla_raw = read_positional("SkillLineAbility",
                                      CHARACTER_ADVANCEMENT_SKILL_LINE_ABILITY.expected_field_count,
                                      CHARACTER_ADVANCEMENT_SKILL_LINE_ABILITY.expected_record_size)

# CharacterAdvancement is now a canonical CoA-overridden table too: fail closed before writing if
# StormLib's applied order disagrees with the plan's declared load order (same rule as Spell).
validate_load_order(plan, ca_member)

class_types = resolve_class_types(ct_tbl)
tab_types = resolve_tab_types(tt_tbl)
assert_playable_cardinality(class_types)         # exactly 21 playable CoA classes (raises otherwise)

nodes = read_advancement(ca_raw, class_types, tab_types, ca_layout)
validate_semantics(nodes, class_types, tab_types)   # FK/adjacency/range + graph invariants; fail closed
# skill-line fallback set is PROVEN from the graph's own CoA spells (per-spec lines, not a fixed range)
coa_spell_ids = {n.spell_id for n in nodes if n.class_kind == "coa_class" and n.spell_id}
coa_skill_lines = derive_coa_skill_lines(sla_raw.rows, coa_spell_ids)
skill_index = build_skill_line_index(sla_raw.rows, coa_skill_lines)
spell_attr = attribute(nodes, class_types, skill_line_index=skill_index)

adv_provenance = {
    "client_build": _client_build(plan),
    "source_dbcs": {"CharacterAdvancement": ca_member.effective_archive.name,
                    "CharacterAdvancementClassTypes": ct_member.effective_archive.name,
                    "CharacterAdvancementTabTypes": tt_member.effective_archive.name,
                    "Spell": spell_member.effective_archive.name},
    "supersedes": {"source_file": "CharacterAdvancementData.json"},
    "extraction_date": date.today().isoformat(),
}
essence_provenance = {                           # names its OWN source table, not CharacterAdvancement
    "client_build": _client_build(plan),
    "source_dbcs": {"CharacterAdvancementEssence": ess_member.effective_archive.name},
    "semantics": "undecoded_per_level_progression",
    "extraction_date": date.today().isoformat(),
}
# current names come from the already-extracted spell records (Spell.dbc), not the CA string block
spell_names = {r["spell_id"]: r.get("name", "") for r in spell_records}
adv_records = build_advancement_records(nodes, provenance=adv_provenance,
                                        spell_names=spell_names, attribution=spell_attr)
class_type_records = build_class_type_records(class_types)
tab_type_records = build_tab_type_records(tab_types)
essence_records = build_essence_raw_records(ess_raw, provenance=essence_provenance)  # raw; undecoded
spell_records = fill_spell_attribution(spell_records, spell_attr)
```

Then add the outputs (the raw essence artifact is always emitted, even if its per-level semantics
are undecoded — the raw cells plus provenance are the deliverable; its decode is an M1.15 leveling item that only sets `leveling_progression_ready`, never a blocker):

```python
outputs["coa_client_advancement.jsonl"] = write_jsonl(adv_records, out_dir / "coa_client_advancement.jsonl")
outputs["coa_client_class_types.jsonl"] = write_jsonl(class_type_records, out_dir / "coa_client_class_types.jsonl")
outputs["coa_client_tab_types.jsonl"] = write_jsonl(tab_type_records, out_dir / "coa_client_tab_types.jsonl")
outputs["coa_client_essence.jsonl"] = write_jsonl(essence_records, out_dir / "coa_client_essence.jsonl")
```

If a `--builder-entries` path is provided, also build and write the parity report. `build_parity_report`
**computes** ownership/identity/adjacency/legality itself; `flip_gate_inputs` only surfaces which layout
columns are unresolved or low-confidence so the report can score per-field readiness. The report emits the
scoped `readiness` object: `attribution_ready`/`ownership_ready` rest on the anchored class-type FK and the
node-id crosswalk (independent of legality), each unresolved legality field stays `unresolved` (Builder
fallback, blocks only that field + `full_builder_retirement_ready`), and `leveling_progression_ready`/
cosmetic `layout` never block (Decision 21/22):

```python
if builder_entries_path:
    from .parity import build_parity_report, flip_gate_inputs, EXPECTED_BUILDER_RECORDS
    builder_path = Path(builder_entries_path)
    builder_entries = [json.loads(l) for l in builder_path.read_text().splitlines()]
    low_conf, unresolved_cols = flip_gate_inputs(ca_layout)          # 2-tuple; adjacency folded in
    pins = {
        "client_build": _client_build(plan),
        "extractor_commit": _extractor_commit(),                    # git HEAD of this extractor tree
        "source_dbc_sha256": {
            "CharacterAdvancement": hashlib.sha256(ca_member.data).hexdigest(),
            "CharacterAdvancementClassTypes": hashlib.sha256(ct_member.data).hexdigest(),
            "CharacterAdvancementTabTypes": hashlib.sha256(tt_member.data).hexdigest(),
            "CharacterAdvancementEssence": hashlib.sha256(ess_member.data).hexdigest(),
            "Spell": hashlib.sha256(spell_member.data).hexdigest(),
        },
        "builder_entries_file": builder_path.name,
        "builder_entries_sha256": hashlib.sha256(builder_path.read_bytes()).hexdigest(),
        "builder_record_count": len(builder_entries),
        "builder_build_slugs": sorted({e.get("build_slug") for e in builder_entries
                                       if e.get("build_slug")}),
        "decode_report_sha256": (hashlib.sha256(Path(ca_decode_report).read_bytes()).hexdigest()
                                 if ca_decode_report and Path(ca_decode_report).is_file() else None),
        "resolved_class_set": sorted(c.class_type_id for c in class_types.values()
                                     if c.kind == "coa_class"),
        "layout_version": "m1-14-b",
        "extraction_date": date.today().isoformat(),
    }
    report = build_parity_report(
        nodes, builder_entries, class_types=class_types,
        low_confidence_fields=low_conf, unresolved_layout_columns=unresolved_cols,
        expected_builder_records=EXPECTED_BUILDER_RECORDS, provenance=pins,
    )
    outputs["coa_builder_parity_report.json"] = write_json(
        report, out_dir / "coa_builder_parity_report.json")
```

Add the `--builder-entries` argument to the `regenerate` subparser (and the `builder_entries_path`
parameter to `regenerate(...)`, default `None`) and thread it through. Also add `--decode-report`
(→ `ca_decode_report` parameter). **Split the defaults so tests are not clobbered:** the `regenerate(...)`
parameter defaults to `None` (a direct call with an injected synthetic `layouts` uses that injected
layout, never a committed report), while the argparse `--decode-report` default is the committed
`reports/client_extract/coa_ca_decode_report.json` so a real CLI run loads the proven layout rather than
the anchors-only fallback. `ExtractedMember.data` carries the raw bytes for the sha256 pins.
`_extractor_commit()` is a small best-effort helper:

```python
def _extractor_commit():
    """Best-effort git HEAD of the extractor tree, for parity/artifact provenance."""
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True,
            cwd=str(Path(__file__).resolve().parent), stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"
```

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

- [ ] **Step 2: Write `docs/data/client-class-types-schema.md` (also covering tab-types + raw essence)**

Document `coa-client-class-types-v1`: `class_type_id`, `internal`, `display`, `kind` (`coa_class`/`coa_system`/`reborn`/`stock`/`meta`), `display_source` (`client`|`curated_alias`), `display_evidence`. State the bands (14–34 playable, 35 sentinel, 36–46 Reborn) and the three curated aliases with provenance. In the same file, document the two companion metadata artifacts emitted alongside it: `coa-client-tab-types-v1` (`tab_type_id`, `name`) and `coa-client-essence-v1` (index-keyed `cols` + `provenance` naming `CharacterAdvancementEssence` as its own source) — stating explicitly that the essence artifact is the raw per-level *progression* table with undecoded semantics. Its undecoded state sets the parity report's `readiness.leveling_progression_ready` to `false` and **never** blocks any max-level readiness dimension or `full_builder_retirement_ready` (an M1.15 leveling gate — Decision 21/22). Per-class essence *caps* are the documented constants AE 26 / TE 25, a versioned `verified_constant` (Decision 21 fallback provenance, to be corroborated against the client UI), not a decoded DBC value.

- [ ] **Step 3: Update `client-spell-schema.md` and `client-content-schema.md`**

In `client-spell-schema.md`, replace the M1.14A `coa_attribution.status: "unknown"` description with the filled participation block (`is_coa`/`modes`/`exclusive_mode`/`confidence`), and note the alpha→display rename does not affect the client `class_type_id`. In `client-content-schema.md`, note the loose `CharacterAdvancementData.json` is superseded by `CharacterAdvancement.dbc` and retained only as a QA drift signal.

- [ ] **Step 4: Update `docs/DECISIONS.md`**

Amend Decision 18 (archive-family mechanism replaced by the `CharacterAdvancement.dbc` registry; principle unchanged). Add Decision 21 (staged, per-field Decision 1 supersession, gated on node-level parity + semantic validation) and Decision 22 (client DBC = canonical offline legality source; live corrections via user-reported verified overrides; Builder removed from the authority chain; four-way discrepancy classification with only extraction/unresolved blocking). Copy the precedence and classification wording verbatim from the spec's Decision impacts section.

- [ ] **Step 5: Update the umbrella spec + roadmap status + add the M1.15 leveling sub-milestone**

In the M1.14 umbrella spec, update the M1.14B row/section: attribution source is `CharacterAdvancement.dbc` (not archive family), and it also carries the graph/legality (staged to M1.15). In `docs/ROADMAP.md`, mark M1.14B status and link this spec + plan. In the same `docs/ROADMAP.md` edit, add an **M1.15 sub-milestone: "Level-by-level build validation"** — decode `CharacterAdvancementEssence` per-level progression (the feature that flips `readiness.leveling_progression_ready` to `true`) and validate a build's AE/TE spend against per-level essence availability rather than only the max-level caps. Note that M1.14B deliberately leaves this gated: it emits the raw essence table and reports `leveling_progression_ready: false` without blocking any max-level readiness dimension. Also note M1.15's **per-field Builder supersession** (Decision 21): each `readiness.legality[field]` that reached `ready` may independently supersede the Builder, while `unresolved` fields keep the Builder fallback until decoded — `full_builder_retirement_ready` is the roll-up that gates full retirement.

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

The acceptance test drives the **real `regenerate` API** (the same entry point M1.14A's acceptance
test uses — `regenerate(CLIENT_ROOT, tmp_path, ...)`), not hand-assembled fixtures. It reads the
emitted artifacts and the parity report. The M1.14B bar is the **scoped readiness** model:
**`readiness.attribution_ready is True` and `readiness.ownership_ready is True`** (these rest on the
structurally-anchored `spell_id`/`class_type` and the node-id crosswalk, independent of any legality
decode), with `readiness.leveling_progression_ready is False`. Every OTHER dimension
(`adjacency_ready`, per-field `legality[...]`, cosmetic `layout`, and the `full_builder_retirement_ready`
roll-up) reports its **honest, evidence-backed state** — the test asserts the readiness object's
*structure and internal consistency* against the decode evidence, **not** a hard-coded all-green (the
real loose JSON leaves most legality unresolved, so forcing them green would be dishonest). A broken
`attribution_ready`/`ownership_ready` is the real finding: a cardinality/count guard trip, or a node-set
/ anchored-identity mismatch (`builder_only_node_instances` / `client_only_node_instances` /
`identity_mismatch`) — an extraction defect. **Decision 22 note:** an ownership mismatch always blocks
ownership; "client wins" applies ONLY to a legality *value* difference on an already-matched node (class
(b) — the field stays `ready`), never to a node-set disagreement, and never promotes an undecoded field.

```python
# append to tests/test_client_extract_acceptance.py
# (module already sets `pytestmark = pytest.mark.client` and defines CLIENT_ROOT)


@pytest.mark.skipif(not CLIENT_ROOT.is_dir(), reason="Ascension client not installed at COA_CLIENT_ROOT")
def test_real_client_advancement_parity(tmp_path):
    from coa_client_extract.cli import regenerate
    from coa_client_extract.errors import BackendUnavailable

    builder_path = Path("coa_scraper/dist/coa_entries.jsonl")
    try:
        regenerate(CLIENT_ROOT, tmp_path, builder_entries_path=str(builder_path))
    except BackendUnavailable:
        pytest.skip("StormLib not available")

    # --- class taxonomy: exactly 21 playable CoA classes, ConquestOfAzeroth (35) sentinel excluded ---
    class_types = [json.loads(l) for l in
                   (tmp_path / "coa_client_class_types.jsonl").read_text().splitlines()]
    playable = [c for c in class_types if c["kind"] == "coa_class"]
    assert len(playable) == 21
    assert all(c["class_type_id"] != 35 for c in playable)

    # --- node-id crosswalk Builder-parity: EXACT ownership (recall AND precision) after rename ---
    report = json.loads((tmp_path / "coa_builder_parity_report.json").read_text())
    assert report["unique_spell_recall"] == 1.0
    assert report["ownership_recall"] == 1.0 and report["ownership_precision"] == 1.0
    assert report["builder_only_records"] == 0 and report["client_only_records"] == 0
    assert report["identity_mismatches"] == 0
    assert report["provenance"]["source_dbc_sha256"]["CharacterAdvancement"]   # reproducibility pins
    assert report["provenance"]["resolved_class_set"] == list(range(14, 35))   # 21 playable CoA ids

    # --- scoped readiness: attribution + ownership are earned (anchor-based, independent of legality);
    #     every other dimension reports its HONEST decode-backed state (not forced green) ---
    r = report["readiness"]
    assert r["attribution_ready"] is True
    assert r["ownership_ready"] is True
    assert r["leveling_progression_ready"] is False
    assert set(r["legality"]) == {"required_level", "ae_cost", "te_cost",
                                  "required_tab_ae", "required_tab_te", "max_rank"}
    assert set(r["layout"]) == {"row", "col"}
    assert all(v in ("ready", "unresolved") for v in r["legality"].values())
    assert all(v in ("ready", "unresolved") for v in r["layout"].values())
    # the roll-up is EXACTLY its parts — never hand-forced true
    assert r["full_builder_retirement_ready"] == (
        r["attribution_ready"] and r["ownership_ready"] and r["adjacency_ready"]
        and all(v == "ready" for v in r["legality"].values()))
    # honesty cross-check: any legality field the decode left unresolved is named in `blockers`
    for field, state in r["legality"].items():
        if state == "unresolved":
            assert any(field in b for b in report["blockers"])

    # --- 805775 is current "Adrenal Venom" on a Venomancer node; attribution filled ---
    adv = [json.loads(l) for l in
           (tmp_path / "coa_client_advancement.jsonl").read_text().splitlines()]
    venom = [n for n in adv if n["spell_id"] == 805775]
    assert venom and any(n["class"]["display"] == "Venomancer" for n in venom)
    assert any(n["name"] == "Adrenal Venom" for n in venom)
    assert all(n["coa_attribution"]["is_coa"] is True for n in venom)

    # --- shared spell 503748 = two distinct Witch Doctor nodes (node identity != spell identity) ---
    assert len([n for n in adv if n["spell_id"] == 503748]) == 2
    spells = {json.loads(l)["spell_id"]: json.loads(l) for l in
              (tmp_path / "coa_client_spell.jsonl").read_text().splitlines()}
    assert 503748 in spells and len(spells[503748]["memberships"]) == 2
    assert all(m["class_display"] == "Witch Doctor" for m in spells[503748]["memberships"])
```

- [ ] **Step 3: Run the acceptance test against the real client**

Run: `COA_CLIENT_ROOT="$HOME/Games/ascension-wow/drive_c/Program Files/Ascension Launcher/resources/ascension-live/Data" python -m pytest tests/test_client_extract_acceptance.py -m client -v`
Expected: PASS. If `ownership_recall`/`ownership_precision` < 1.0, inspect `builder_only_sample`/`client_only_sample` — a builder-only node id is an undecoded/mis-attributed node (an extraction defect — fix it); a client-only id is an over-attributed or mis-renamed node (also an extraction defect). Note: unlike a legality *value* difference (class (b), client wins per Decision 22), a node-set disagreement is never "client wins" — it always blocks.

- [ ] **Step 4: Regenerate the real artifacts + parity report**

```bash
python -m coa_client_extract regenerate \
  --client-root "$HOME/Games/ascension-wow/drive_c/Program Files/Ascension Launcher/resources/ascension-live/Data" \
  --out reports/client_extract \
  --builder-entries coa_scraper/dist/coa_entries.jsonl
```
Confirm `reports/client_extract/` contains `coa_client_advancement.jsonl`, `coa_client_class_types.jsonl`, `coa_client_tab_types.jsonl`, `coa_client_essence.jsonl`, `coa_client_spell.jsonl` (attribution filled), and `coa_builder_parity_report.json` with `ownership_recall: 1.0` / `ownership_precision: 1.0` and `readiness.attribution_ready: true` / `readiness.ownership_ready: true`, `readiness.leveling_progression_ready: false`, and the per-field `readiness.legality` / `readiness.full_builder_retirement_ready` reflecting their honest decode-backed state.

- [ ] **Step 5: Full suite + commit**

Run: `python -m pytest` (default tier — must be green without StormLib/client) then the marked tiers if available (`-m stormlib`, `-m client`).

```bash
git add tests/test_client_extract_acceptance.py tests/test_client_extract_integration_stormlib.py
git commit -m "M1.14B: stormlib-tier CA override + client-tier acceptance (exact ownership; scoped readiness attribution/ownership ready)"
```

---

## Self-Review Notes (for the executor)

- **Decode dependency:** Tasks 4–10 reference the `CHARACTER_ADVANCEMENT` layout constant produced by Task 3 Step 6 (client tier). Synthetic unit tests supply their own `CharacterAdvancementLayout`, so Tasks 4–8 are fully testable *without* the client; only Task 3 Step 6 and Task 10 require the real install. Do Task 3's client decode before Task 10.
- **Reader split in `regenerate`:** M1.14A's `regenerate` has a local `read_table(name)` for the spell family. Task 8 adds `read_named(name, layout)` (named columns — companion `*Types` tables, whose `name` is the verified col 1, no decode needed) and `read_positional(name, fc, rs)` (index-keyed cells — the wide `CharacterAdvancement`/`Essence` tables). Keep `read_table` for the spell family untouched.
- **Only `high`-confidence fields are emitted into `legality`/adapter.** A field left `None` in the layout is simply absent from `legality`; that is intended (it becomes Builder-fallback in M1.15), not a bug.
- **Essence: caps are constants, the table is extracted raw, progression never blocks readiness.** Per-class essence *caps* are the documented uniform constants (AE 26 / TE 25), a versioned `verified_constant` (Decision 21 fallback provenance, corroborate against client UI later) living in the existing `coa_scraper/dist/coa_essence_caps.json`; M1.14B does **not** decode caps from a DBC. `CharacterAdvancementEssence` is per-level *progression* data: `build_essence_raw_records` emits it raw (index-keyed cells + provenance naming its own source table) as `coa-client-essence.jsonl`. Its undecoded state sets `readiness.leveling_progression_ready` to `false` and **never** blocks any max-level readiness dimension or `full_builder_retirement_ready` — per Decision 21/22 the max-level responsibilities do not depend on per-level leveling data. Level-by-level build validation is a separate M1.15 sub-milestone. Do not add an essence-cap column layout or fabricate cap column indices.
- **Do not rewire `coa_meta`.** If any task tempts you to touch `repository.py` or reports, stop — that is M1.15.
