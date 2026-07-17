# M1.14D WoW Conversion Primitives Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the client-authoritative WoW GameTable conversion primitives plus documented, verification-labelled WotLK rules into a single versioned `coa-wow-constants-v1` snapshot (with a binding manifest), and ship a thin, non-computing `coa_meta` reader — the modeling-inputs layer for M1.16.

**Architecture:** Reuse the M1.14A extraction core (`ArchiveBackend`, patch-chain resolution, WDBC header parse, atomic-write + manifest-last helpers). Add a float ordinal-preserving DBC reader, a declarative GameTable axis policy, a reconnaissance pass that freezes real-client facts before canonical extraction is trusted, a strict canonical extractor that emits one JSON snapshot + hashed manifest, and a `WowConstantsRepository` that validates and looks up raw values without computing any formula.

**Tech Stack:** Python 3.11 (stdlib only — `struct`, `json`, `hashlib`, `dataclasses`); pytest with the existing `stormlib`/`client` markers; the M1.14A `coa_client_extract` module and `coa_meta` repository layer.

## Global Constraints

Copied verbatim from `docs/superpowers/specs/2026-07-17-m1-14-d-wow-constants-design.md`. Every task's requirements implicitly include these.

- **Artifact schema:** `coa-wow-constants-v1`; manifest schema `coa-wow-constants-manifest-v1`. The `coa_meta` reader hard-rejects any other `schema_version`.
- **No formulas.** No executable analytical engine. The reader returns raw looked-up values + provenance and may *name* a reference formula; it never evaluates one (no rating→%, GCD, crit, or regen math, no derived multiplier).
- **Native namespace only.** Class-indexed reader methods take a keyword-only `wow_class_id` in the stock `ChrClasses` namespace. The reader never accepts a CoA class-type id, never guesses an integer's namespace, and never maps between namespaces. Composite class-context readiness is M1.16's, not the reader's.
- **`class_context_resolution`** ∈ `{unproven, actor_wow_class_id, versioned_bridge}` — manifest field; default `unproven`. Any published CoA→`wow_class_id` bridge must be a complete, hashed mapping with a cardinality policy — never a Boolean.
- **Axis meaning is proven, not assumed.** Established from the pinned reference indexing contract and validated against physical form, explicit/implicit keys, coverage, holes/padding, and sampled anchors — never from record count alone. Class axis width is never derived from `len(ChrClasses)`.
- **Reference contract:** `level_stride = 100`; combat-rating index `rating_id * 100 + (level - 1)`; class scalar index `(wow_class_id - 1) * 32 + rating_id + 1` (`rating_storage_stride = 32`, `+1` offset); supported rating IDs `0–24`; rating→% reference formula (identified, not computed) `class_scalar / combat_rating`.
- **Manifest binds every authored input** with a version *and* a SHA-256: rules, rating enum, power-type enum, axis policy, reference anchors — plus the artifact hash + byte length and each source-DBC hash.
- **Rules are verification-labelled** (`authority`, `ascension_verification`, `applies_to`) and live in tracked declarative JSON; every rule ships `ascension_verification: unverified` until M1.14G/logs confirm. A stock assumption is never presented as verified Ascension truth.
- **Fail closed.** StormLib is an extraction-time dependency only; the `wow-constants` command writes nothing and exits non-zero when StormLib is unavailable. Canonical emission parses **strict** (drift → raise before any write).
- **Real-client tests gate on structure/sanity, not stock equality.** Structural/layout mismatch, impossible coordinates, duplicates, non-finite values, and unmapped IDs fail; a valid value differing from stock is a recorded `reference_comparison` deviation, not a failure.
- **Redistribution boundary.** The snapshot + manifest + recon report are client-derived → git-ignored; committed fixtures are synthetic; authored inputs (rules, enums, axis policy, anchors) are tracked. `coa_wow_constants.json` joins the M1.14C mandatory forward policy gate.

---

## File Structure

**Create:**
- `coa_client_extract/data/gt_axis_policy_v1.json` — declarative GameTable axis/index/stride/domain policy.
- `coa_client_extract/data/rating_enum_v1.json` — pinned `CombatRating` id→name map.
- `coa_client_extract/data/power_type_enum_v1.json` — power-type id→name map (same values as M1.14C).
- `coa_client_extract/data/wow_rules_v1.json` — authored verification-labelled rules.
- `coa_client_extract/data/wotlk_reference_anchors_v1.json` — named/hashed reference anchor set.
- `coa_client_extract/wow_constants.py` — authored-input loading, axis mapping, class axis, recon, reference comparison, snapshot assembly.
- `coa_meta/wow_constants.py` — `WowConstantsRepository` (load/validate/lookup; no computation).
- `docs/data/wow-constants-schema.md` — schema doc.
- Tests: `tests/test_wow_constants_gametable.py`, `tests/test_wow_constants_authored.py`, `tests/test_wow_constants_axis.py`, `tests/test_wow_constants_class_axis.py`, `tests/test_wow_constants_recon.py`, `tests/test_wow_constants_snapshot.py`, `tests/test_wow_constants_write.py`, `tests/test_wow_constants_cli.py`, `tests/test_wow_constants_repository.py`, `tests/test_wow_constants_oracles.py`, `tests/test_wow_constants_acceptance.py`.

**Modify:**
- `coa_client_extract/wdbc.py` — add `GameTable` + `parse_gametable`.
- `coa_client_extract/dbc_layouts.py` — add `CHR_CLASSES` named layout + `GameTableLayout` + `load_axis_policy`.
- `coa_client_extract/artifacts.py` — add `write_wow_constants`.
- `coa_client_extract/cli.py` — add the `wow-constants` subcommand (+ `--recon-only`).
- `pyproject.toml` — add `coa_client_extract` package-data for `data/*.json`.
- `.gitignore` — add the client-derived output ignore rules.
- `docs/DECISIONS.md` — register `coa_wow_constants.json` under the M1.14C forward policy gate.

---

## Task 1: Float ordinal-preserving GameTable reader

**Files:**
- Modify: `coa_client_extract/wdbc.py`
- Test: `tests/test_wow_constants_gametable.py`

**Interfaces:**
- Consumes: the module `_HEADER`/`_MAGIC`/`_CELL` constants and `DbcDriftError` already in `wdbc.py`.
- Produces: `GameTable(physical_form: str, field_count: int, record_size: int, record_count: int, rows: list[dict], drift: bool)` where each row is `{"ordinal": int, "value": float, "id": int | None}`; and `parse_gametable(data: bytes, *, physical_form: str, expected_field_count: int, expected_record_size: int, value_cell: int = 0, id_cell: int | None = None, strict: bool = False) -> GameTable`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wow_constants_gametable.py
import struct
import pytest
from coa_client_extract.errors import DbcDriftError
from coa_client_extract.wdbc import parse_gametable


def _gt(records: bytes, field_count: int, record_size: int) -> bytes:
    count = len(records) // record_size
    return struct.pack("<4sIIII", b"WDBC", count, field_count, record_size, 0) + records


def test_implicit_row_reads_floats_in_order():
    body = struct.pack("<fff", 1.5, 2.5, 3.5)  # single float column, 3 records
    data = _gt(body, field_count=1, record_size=4)
    table = parse_gametable(data, physical_form="implicit_row",
                            expected_field_count=1, expected_record_size=4)
    assert table.record_count == 3
    assert table.drift is False
    assert [(r["ordinal"], r["value"], r["id"]) for r in table.rows] == [
        (0, 1.5, None), (1, 2.5, None), (2, 3.5, None)]


def test_explicit_id_reads_id_and_float():
    body = struct.pack("<If", 7, 4.25) + struct.pack("<If", 9, 8.75)  # (id, value) x2
    data = _gt(body, field_count=2, record_size=8)
    table = parse_gametable(data, physical_form="explicit_id", expected_field_count=2,
                            expected_record_size=8, value_cell=1, id_cell=0)
    assert [(r["ordinal"], r["id"], r["value"]) for r in table.rows] == [
        (0, 7, 4.25), (1, 9, 8.75)]


def test_drift_flags_non_strict_and_raises_strict():
    body = struct.pack("<ff", 1.0, 2.0)
    data = _gt(body, field_count=2, record_size=8)  # header says 2/8, we expect 1/4
    table = parse_gametable(data, physical_form="implicit_row",
                            expected_field_count=1, expected_record_size=4)
    assert table.drift is True
    with pytest.raises(DbcDriftError):
        parse_gametable(data, physical_form="implicit_row",
                        expected_field_count=1, expected_record_size=4, strict=True)


def test_record_size_not_multiple_of_cell_raises():
    data = struct.pack("<4sIIII", b"WDBC", 0, 1, 6, 0)  # record_size 6 not multiple of 4
    with pytest.raises(DbcDriftError):
        parse_gametable(data, physical_form="implicit_row",
                        expected_field_count=1, expected_record_size=4)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wow_constants_gametable.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_gametable'`.

- [ ] **Step 3: Add `GameTable` + `parse_gametable` to `wdbc.py`**

Append to `coa_client_extract/wdbc.py`:

```python
@dataclass(frozen=True)
class GameTable:
    physical_form: str          # "implicit_row" | "explicit_id"
    field_count: int
    record_size: int
    record_count: int
    rows: list[dict]            # {"ordinal": int, "value": float, "id": int | None}
    drift: bool


def parse_gametable(data: bytes, *, physical_form: str, expected_field_count: int,
                    expected_record_size: int, value_cell: int = 0,
                    id_cell: int | None = None, strict: bool = False) -> GameTable:
    """Decode a GameTable DBC preserving row ordinal and reading the value cell as a 32-bit float.

    GameTables are single-float, implicit-row tables in stock 3.3.5a; Ascension may ship an
    explicit id column. This never decodes the value as an integer (contrast parse_positional)."""
    if physical_form not in ("implicit_row", "explicit_id"):
        raise ValueError(f"unknown physical_form {physical_form!r}")
    if len(data) < _HEADER.size:
        raise DbcDriftError("file smaller than DBC header")
    magic, record_count, field_count, record_size, string_size = _HEADER.unpack_from(data, 0)
    if magic != _MAGIC:
        raise DbcDriftError(f"bad magic {magic!r}, expected WDBC")
    if record_size % _CELL != 0:
        raise DbcDriftError(f"record_size {record_size} not a multiple of {_CELL}")
    drift = field_count != expected_field_count or record_size != expected_record_size
    if drift and strict:
        raise DbcDriftError(
            f"field_count {field_count} / record_size {record_size} != expected "
            f"{expected_field_count} / {expected_record_size}")
    records_start = _HEADER.size
    end = records_start + record_count * record_size
    if len(data) < end:
        raise DbcDriftError(f"truncated ({len(data)} bytes, expected >= {end})")
    cells = record_size // _CELL
    if value_cell >= cells or (id_cell is not None and id_cell >= cells):
        raise DbcDriftError(f"value/id cell index out of record bounds ({cells} cells)")
    rows: list[dict] = []
    for i in range(record_count):
        base = records_start + i * record_size
        (value,) = struct.unpack_from("<f", data, base + value_cell * _CELL)
        ident = None
        if id_cell is not None:
            (ident,) = struct.unpack_from("<I", data, base + id_cell * _CELL)
        rows.append({"ordinal": i, "value": value, "id": ident})
    return GameTable(physical_form, field_count, record_size, record_count, rows, drift)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wow_constants_gametable.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/wdbc.py tests/test_wow_constants_gametable.py
git commit -m "M1.14D Task 1: float ordinal-preserving GameTable reader (parse_gametable)"
```

---

## Task 2: Authored data files + loader with version/hash binding

**Files:**
- Create: `coa_client_extract/data/gt_axis_policy_v1.json`, `coa_client_extract/data/rating_enum_v1.json`, `coa_client_extract/data/power_type_enum_v1.json`, `coa_client_extract/data/wow_rules_v1.json`, `coa_client_extract/data/wotlk_reference_anchors_v1.json`
- Create: `coa_client_extract/wow_constants.py`
- Modify: `pyproject.toml`
- Test: `tests/test_wow_constants_authored.py`

**Interfaces:**
- Produces: `AuthoredInput(name: str, payload: dict, version: str, sha256: str)`; `load_authored_input(name: str, *, root: Path | None = None) -> AuthoredInput` (reads `coa_client_extract/data/<name>_v1.json`, hashes the exact on-disk bytes, reads the `version` key); `AUTHORED_INPUTS = ("wow_rules", "rating_enum", "power_type_enum", "gt_axis_policy", "wotlk_reference_anchors")`.

- [ ] **Step 1: Create the five authored data files**

`coa_client_extract/data/rating_enum_v1.json` (stock 3.3.5a `CombatRating` enum, ids 0–24):

```json
{
  "version": "cr-3.3.5a-v1",
  "storage_stride": 32,
  "supported": {
    "0": "weapon_skill", "1": "defense_skill", "2": "dodge", "3": "parry", "4": "block",
    "5": "hit_melee", "6": "hit_ranged", "7": "hit_spell", "8": "crit_melee", "9": "crit_ranged",
    "10": "crit_spell", "11": "hit_taken_melee", "12": "hit_taken_ranged", "13": "hit_taken_spell",
    "14": "crit_taken_melee", "15": "crit_taken_ranged", "16": "crit_taken_spell",
    "17": "haste_melee", "18": "haste_ranged", "19": "haste_spell", "20": "weapon_skill_mainhand",
    "21": "weapon_skill_offhand", "22": "weapon_skill_ranged", "23": "expertise",
    "24": "armor_penetration"
  }
}
```

`coa_client_extract/data/power_type_enum_v1.json` (same values as the M1.14C `client-spell-schema.md` map):

```json
{
  "version": "m1.14c-power-v1",
  "map": {"-2": "health", "0": "mana", "1": "rage", "2": "focus", "3": "energy",
          "4": "happiness", "5": "runes", "6": "runic_power"}
}
```

`coa_client_extract/data/gt_axis_policy_v1.json`:

```json
{
  "version": "gt-layout-v1",
  "level_stride": 100,
  "rating_stride": 32,
  "tables": {
    "combat_ratings": {"source_dbc": "gtCombatRatings", "physical_form": "implicit_row",
      "index_kind": "rating_by_level", "axes": ["rating_id", "level"], "class_indexed": false,
      "supported": {"rating_id": {"min": 0, "max": 24}, "level": {"min": 1, "max": 100}}},
    "class_combat_rating_scalar": {"source_dbc": "gtOCTClassCombatRatingScalar",
      "physical_form": "implicit_row", "index_kind": "class_rating_scalar", "index_offset": 1,
      "axes": ["wow_class_id", "rating_id"], "class_indexed": true,
      "supported": {"rating_id": {"min": 0, "max": 24}}},
    "melee_crit_per_agi": {"source_dbc": "gtChanceToMeleeCrit", "physical_form": "implicit_row",
      "index_kind": "class_by_level", "axes": ["wow_class_id", "level"], "class_indexed": true,
      "supported": {"level": {"min": 1, "max": 100}}},
    "melee_crit_base": {"source_dbc": "gtChanceToMeleeCritBase", "physical_form": "implicit_row",
      "index_kind": "class_only", "axes": ["wow_class_id"], "class_indexed": true, "supported": {}},
    "spell_crit_per_int": {"source_dbc": "gtChanceToSpellCrit", "physical_form": "implicit_row",
      "index_kind": "class_by_level", "axes": ["wow_class_id", "level"], "class_indexed": true,
      "supported": {"level": {"min": 1, "max": 100}}},
    "spell_crit_base": {"source_dbc": "gtChanceToSpellCritBase", "physical_form": "implicit_row",
      "index_kind": "class_only", "axes": ["wow_class_id"], "class_indexed": true, "supported": {}},
    "mana_regen_per_spirit": {"source_dbc": "gtRegenMPPerSpt", "physical_form": "implicit_row",
      "index_kind": "class_by_level", "axes": ["wow_class_id", "level"], "class_indexed": true,
      "supported": {"level": {"min": 1, "max": 100}}}
  },
  "class_axis": {"namespace": "chr_classes", "reference_expected_ids": [1,2,3,4,5,6,7,8,9,11],
                 "reference_holes": [10]},
  "recon_gated": {
    "base_mana_by_class": {"source_dbc": "gtOCTBaseMPByClass", "physical_form": "implicit_row",
      "index_kind": "class_by_level", "axes": ["wow_class_id", "level"], "class_indexed": true,
      "supported": {"level": {"min": 1, "max": 100}}, "semantics": "unproven"},
    "base_hp_by_class": {"source_dbc": "gtOCTBaseHPByClass", "physical_form": "implicit_row",
      "index_kind": "class_by_level", "axes": ["wow_class_id", "level"], "class_indexed": true,
      "supported": {"level": {"min": 1, "max": 100}}, "semantics": "unproven"},
    "oct_regen_mp": {"source_dbc": "gtOCTRegenMP", "physical_form": "implicit_row",
      "index_kind": "class_by_level", "axes": ["wow_class_id", "level"], "class_indexed": true,
      "supported": {"level": {"min": 1, "max": 100}}, "semantics": "unproven"}
  }
}
```

`coa_client_extract/data/wow_rules_v1.json`:

```json
{
  "version": "wow-rules-v1",
  "rules": {
    "base_energy": {"value": 100, "unit": "energy", "authority": "wotlk_reference",
      "ascension_verification": "unverified", "applies_to": ["energy_users"],
      "source_ref": "WotLK 3.3.5a base energy pool", "notes": "before aura/talent modifiers"},
    "energy_regen_per_sec": {"value": 10, "unit": "energy_per_sec", "authority": "wotlk_reference",
      "ascension_verification": "unverified", "applies_to": ["energy_users"],
      "source_ref": "WotLK 3.3.5a energy regen", "notes": "flat; not affected by haste in the stock path"},
    "rage_bounds": {"value": {"min": 0, "max": 100}, "unit": "rage_display",
      "authority": "wotlk_reference", "ascension_verification": "unverified",
      "applies_to": ["rage_users"], "source_ref": "WotLK 3.3.5a rage",
      "notes": "display units (internal are x10); event-generated, decays out of combat"},
    "runic_power_bounds": {"value": {"min": 0, "max": 100}, "unit": "runic_power_display",
      "authority": "wotlk_reference", "ascension_verification": "unverified",
      "applies_to": ["runic_power_users"], "source_ref": "WotLK 3.3.5a runic power",
      "notes": "display units; event-generated, decays out of combat"},
    "gcd_floor_ms": {"value": 1000, "unit": "ms", "authority": "wotlk_reference",
      "ascension_verification": "unverified", "applies_to": ["all_spells"],
      "source_ref": "WotLK 3.3.5a GCD haste floor", "notes": "haste reduces spell GCD to this floor"},
    "standard_spell_gcd_base_ms": {"value": 1500, "unit": "ms", "authority": "wotlk_reference",
      "ascension_verification": "unverified", "applies_to": ["most_spells"],
      "source_ref": "WotLK 3.3.5a standard GCD",
      "notes": "standard default only; real base is per-spell StartRecoveryTime (M1.14E), not a ceiling"}
  }
}
```

`coa_client_extract/data/wotlk_reference_anchors_v1.json` (documented published references; frozen/verified at the Task 6 checkpoint):

```json
{
  "version": "wotlk-335a-anchors-v1",
  "anchors": [
    {"kind": "derived_rating_per_percent", "rating_id": 10, "rating_name": "crit_spell",
     "wow_class_id": 8, "level": 60, "rating_per_percent": 14.0, "tolerance": 1.0,
     "source_ref": "WotLK 3.3.5a published: ~14 crit rating = 1% at level 60"},
    {"kind": "derived_rating_per_percent", "rating_id": 10, "rating_name": "crit_spell",
     "wow_class_id": 8, "level": 80, "rating_per_percent": 45.90574, "tolerance": 1.0,
     "source_ref": "WotLK 3.3.5a published: 45.90574 crit rating = 1% at level 80"}
  ]
}
```

- [ ] **Step 2: Add `coa_client_extract` package-data to `pyproject.toml`**

In `pyproject.toml` under `[tool.setuptools.package-data]`, add a `coa_client_extract` entry beside the existing `coa_meta` one:

```toml
coa_client_extract = ["data/*.json"]
```

Also confirm `coa_client_extract` is already in `[tool.setuptools] packages` (it is).

- [ ] **Step 3: Write the failing test**

```python
# tests/test_wow_constants_authored.py
import hashlib
import json
import pytest
from coa_client_extract.wow_constants import AUTHORED_INPUTS, load_authored_input


def test_all_authored_inputs_load_with_version_and_hash():
    for name in AUTHORED_INPUTS:
        ai = load_authored_input(name)
        assert ai.name == name
        assert isinstance(ai.version, str) and ai.version
        assert len(ai.sha256) == 64
        assert isinstance(ai.payload, dict)


def test_hash_is_over_exact_on_disk_bytes(tmp_path):
    src = tmp_path / "wow_rules_v1.json"
    src.write_text(json.dumps({"version": "x", "rules": {}}))
    ai = load_authored_input("wow_rules", root=tmp_path)
    assert ai.sha256 == hashlib.sha256(src.read_bytes()).hexdigest()
    assert ai.version == "x"


def test_missing_version_key_raises(tmp_path):
    (tmp_path / "wow_rules_v1.json").write_text(json.dumps({"rules": {}}))
    with pytest.raises(ValueError):
        load_authored_input("wow_rules", root=tmp_path)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_wow_constants_authored.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'coa_client_extract.wow_constants'`.

- [ ] **Step 5: Create `wow_constants.py` with the loader**

```python
# coa_client_extract/wow_constants.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

AUTHORED_INPUTS = ("wow_rules", "rating_enum", "power_type_enum",
                   "gt_axis_policy", "wotlk_reference_anchors")
_DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class AuthoredInput:
    name: str
    payload: dict
    version: str
    sha256: str


def load_authored_input(name: str, *, root: Path | None = None) -> AuthoredInput:
    path = (root or _DATA_DIR) / f"{name}_v1.json"
    raw = path.read_bytes()
    payload = json.loads(raw)
    version = payload.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"{path.name}: missing string 'version'")
    return AuthoredInput(name=name, payload=payload, version=version,
                         sha256=hashlib.sha256(raw).hexdigest())
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_wow_constants_authored.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add coa_client_extract/data/ coa_client_extract/wow_constants.py \
        tests/test_wow_constants_authored.py pyproject.toml
git commit -m "M1.14D Task 2: authored data files (rules/enums/axis-policy/anchors) + hashing loader"
```

---

## Task 3: GameTableLayout + axis mapping

**Files:**
- Modify: `coa_client_extract/dbc_layouts.py`
- Modify: `coa_client_extract/wow_constants.py`
- Test: `tests/test_wow_constants_axis.py`

**Interfaces:**
- Consumes: `AuthoredInput` (Task 2); `GameTable` + `parse_gametable` (Task 1).
- Produces: `GameTableLayout` dataclass (`key: str, source_dbc: str, physical_form: str, index_kind: str, axes: tuple[str, ...], class_indexed: bool, supported: dict, index_offset: int`); `load_axis_policy(payload: dict) -> tuple[dict[str, GameTableLayout], int, int]` returning `(layouts, level_stride, rating_stride)`; `map_table_entries(layout, table, *, class_roster, level_stride, rating_stride) -> tuple[list[dict], dict]` returning `(entries, counts)` where `counts = {"source_records", "emitted_entries", "padding_records"}` and each entry is `{axis: int, ..., "value": float}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wow_constants_axis.py
import struct
import pytest
from coa_client_extract.wow_constants import load_authored_input, load_axis_policy, map_table_entries
from coa_client_extract.wdbc import parse_gametable


def _implicit(values):
    body = b"".join(struct.pack("<f", v) for v in values)
    return struct.pack("<4sIIII", b"WDBC", len(values), 1, 4, 0) + body


def _policy():
    layouts, level_stride, rating_stride = load_axis_policy(
        load_authored_input("gt_axis_policy").payload)
    return layouts, level_stride, rating_stride


def test_rating_by_level_maps_ordinal_and_drops_padding():
    layouts, level_stride, rating_stride = _policy()
    layout = layouts["combat_ratings"]
    # 32 ratings * 100 levels storage; only rating 0..24 emitted -> padding = 7*100
    values = [float(i) for i in range(32 * 100)]
    table = parse_gametable(_implicit(values), physical_form="implicit_row",
                            expected_field_count=1, expected_record_size=4)
    entries, counts = map_table_entries(layout, table, class_roster=[],
                                        level_stride=level_stride, rating_stride=rating_stride)
    assert counts == {"source_records": 3200, "emitted_entries": 2500, "padding_records": 700}
    # ordinal for rating_id=6, level=60 is 6*100 + 59 = 659
    hit = next(e for e in entries if e["rating_id"] == 6 and e["level"] == 60)
    assert hit["value"] == 659.0


def test_class_rating_scalar_applies_plus_one_offset_and_sparse_roster():
    layouts, level_stride, rating_stride = _policy()
    layout = layouts["class_combat_rating_scalar"]
    values = [float(i) for i in range(12 * 32)]  # room for classes 1..11 with +1 offset
    table = parse_gametable(_implicit(values), physical_form="implicit_row",
                            expected_field_count=1, expected_record_size=4)
    entries, counts = map_table_entries(layout, table, class_roster=[1, 2, 11],
                                        level_stride=level_stride, rating_stride=rating_stride)
    # ordinal for class 1, rating 6 = (1-1)*32 + 6 + 1 = 7
    hit = next(e for e in entries if e["wow_class_id"] == 1 and e["rating_id"] == 6)
    assert hit["value"] == 7.0
    # class 10 is not in the roster -> its slots are padding, never emitted
    assert all(e["wow_class_id"] != 10 for e in entries)


def test_class_by_level_uses_raw_class_id_hole_is_padding():
    layouts, level_stride, rating_stride = _policy()
    layout = layouts["melee_crit_per_agi"]
    values = [float(i) for i in range(12 * 100)]
    table = parse_gametable(_implicit(values), physical_form="implicit_row",
                            expected_field_count=1, expected_record_size=4)
    entries, counts = map_table_entries(layout, table, class_roster=[1, 11],
                                        level_stride=level_stride, rating_stride=rating_stride)
    # class 11, level 1 -> (11-1)*100 + 0 = 1000
    hit = next(e for e in entries if e["wow_class_id"] == 11 and e["level"] == 1)
    assert hit["value"] == 1000.0
    assert counts["emitted_entries"] == 200  # 2 classes * 100 levels


def test_class_only_indexes_by_class_minus_one():
    layouts, level_stride, rating_stride = _policy()
    layout = layouts["melee_crit_base"]
    values = [float(i) for i in range(12)]
    table = parse_gametable(_implicit(values), physical_form="implicit_row",
                            expected_field_count=1, expected_record_size=4)
    entries, _ = map_table_entries(layout, table, class_roster=[1, 11],
                                   level_stride=level_stride, rating_stride=rating_stride)
    hit = next(e for e in entries if e["wow_class_id"] == 11)
    assert hit["value"] == 10.0  # ordinal 11-1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wow_constants_axis.py -v`
Expected: FAIL with `ImportError: cannot import name 'load_axis_policy'`.

- [ ] **Step 3: Add `GameTableLayout` to `dbc_layouts.py`**

Append to `coa_client_extract/dbc_layouts.py`:

```python
@dataclass(frozen=True)
class GameTableLayout:
    key: str
    source_dbc: str
    physical_form: str          # "implicit_row" | "explicit_id"
    index_kind: str             # rating_by_level | class_rating_scalar | class_by_level | class_only
    axes: tuple[str, ...]
    class_indexed: bool
    supported: dict             # {axis: {"min": int, "max": int}}
    index_offset: int = 0
    semantics: str = "proven"


# ChrClasses is a normal named DBC (id, power_type, name), NOT a GameTable. Stock 3.3.5a
# ChrClasses has the class id in col 0 and PowerType in col 3; the enUS name column follows.
CHR_CLASSES = DbcLayout(
    name="ChrClasses", expected_field_count=60, expected_record_size=60 * 4,
    columns={"id": FieldSpec(0, "uint32"), "power_type": FieldSpec(3, "int32"),
             "name": FieldSpec(4, "str")},
)
```

- [ ] **Step 4: Add `load_axis_policy` + `map_table_entries` to `wow_constants.py`**

```python
# coa_client_extract/wow_constants.py  (append)
from .dbc_layouts import GameTableLayout
from .wdbc import GameTable


def load_axis_policy(payload: dict) -> tuple[dict[str, GameTableLayout], int, int]:
    level_stride = int(payload["level_stride"])
    rating_stride = int(payload["rating_stride"])
    layouts: dict[str, GameTableLayout] = {}
    for group in ("tables", "recon_gated"):
        for key, spec in payload.get(group, {}).items():
            layouts[key] = GameTableLayout(
                key=key, source_dbc=spec["source_dbc"], physical_form=spec["physical_form"],
                index_kind=spec["index_kind"], axes=tuple(spec["axes"]),
                class_indexed=bool(spec["class_indexed"]), supported=spec.get("supported", {}),
                index_offset=int(spec.get("index_offset", 0)),
                semantics=spec.get("semantics", "proven"))
    return layouts, level_stride, rating_stride


def _in_supported(layout: GameTableLayout, axis: str, value: int) -> bool:
    dom = layout.supported.get(axis)
    return dom is None or (dom["min"] <= value <= dom["max"])


def map_table_entries(layout: GameTableLayout, table: GameTable, *, class_roster: list[int],
                      level_stride: int, rating_stride: int) -> tuple[list[dict], dict]:
    """Invert the reference index for one table into explicit-coordinate entries, dropping
    padding/unsupported/off-roster ordinals. Never derives class width from a count."""
    by_ordinal = {r["ordinal"]: r["value"] for r in table.rows}
    entries: list[dict] = []

    def emit(ordinal: int, coords: dict) -> None:
        if ordinal in by_ordinal:
            entries.append({**coords, "value": by_ordinal[ordinal]})

    if layout.index_kind == "rating_by_level":
        for rating_id in range(layout.supported["rating_id"]["min"],
                               layout.supported["rating_id"]["max"] + 1):
            for level in range(layout.supported["level"]["min"],
                               layout.supported["level"]["max"] + 1):
                emit(rating_id * level_stride + (level - 1),
                     {"rating_id": rating_id, "level": level})
    elif layout.index_kind == "class_rating_scalar":
        for wow_class_id in class_roster:
            for rating_id in range(layout.supported["rating_id"]["min"],
                                   layout.supported["rating_id"]["max"] + 1):
                emit((wow_class_id - 1) * rating_stride + rating_id + layout.index_offset,
                     {"wow_class_id": wow_class_id, "rating_id": rating_id})
    elif layout.index_kind == "class_by_level":
        for wow_class_id in class_roster:
            for level in range(layout.supported["level"]["min"],
                               layout.supported["level"]["max"] + 1):
                emit((wow_class_id - 1) * level_stride + (level - 1),
                     {"wow_class_id": wow_class_id, "level": level})
    elif layout.index_kind == "class_only":
        for wow_class_id in class_roster:
            emit(wow_class_id - 1, {"wow_class_id": wow_class_id})
    else:
        raise ValueError(f"unknown index_kind {layout.index_kind!r}")

    counts = {"source_records": table.record_count, "emitted_entries": len(entries),
              "padding_records": table.record_count - len(entries)}
    return entries, counts
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_wow_constants_axis.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add coa_client_extract/dbc_layouts.py coa_client_extract/wow_constants.py \
        tests/test_wow_constants_axis.py
git commit -m "M1.14D Task 3: GameTableLayout + declarative axis mapping (four index kinds)"
```

---

## Task 4: Class axis (reference-expected vs observed)

**Files:**
- Modify: `coa_client_extract/wow_constants.py`
- Test: `tests/test_wow_constants_class_axis.py`

**Interfaces:**
- Consumes: `DbcTable` rows from `parse_dbc` over `CHR_CLASSES`.
- Produces: `build_class_axis(chr_rows: list[dict], *, reference_expected_ids: list[int], reference_holes: list[int]) -> dict` returning `{"namespace": "chr_classes", "reference_expected_ids", "reference_holes", "observed_client_ids", "comparison"}` where `comparison ∈ {"exact","extended","changed","ambiguous"}`; and `class_roster(class_axis: dict) -> list[int]` returning the observed ids.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wow_constants_class_axis.py
from coa_client_extract.wow_constants import build_class_axis, class_roster

REF = [1, 2, 3, 4, 5, 6, 7, 8, 9, 11]


def _rows(ids):
    return [{"id": i, "power_type": 0, "name": f"C{i}"} for i in ids]


def test_exact_when_observed_matches_reference():
    axis = build_class_axis(_rows(REF), reference_expected_ids=REF, reference_holes=[10])
    assert axis["comparison"] == "exact"
    assert axis["observed_client_ids"] == REF
    assert class_roster(axis) == REF


def test_extended_when_superset():
    axis = build_class_axis(_rows(REF + [12]), reference_expected_ids=REF, reference_holes=[10])
    assert axis["comparison"] == "extended"


def test_changed_when_reference_id_missing():
    axis = build_class_axis(_rows([1, 2, 3]), reference_expected_ids=REF, reference_holes=[10])
    assert axis["comparison"] == "changed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wow_constants_class_axis.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_class_axis'`.

- [ ] **Step 3: Implement `build_class_axis` + `class_roster`**

```python
# coa_client_extract/wow_constants.py  (append)
def build_class_axis(chr_rows: list[dict], *, reference_expected_ids: list[int],
                     reference_holes: list[int]) -> dict:
    observed = sorted({int(r["id"]) for r in chr_rows})
    ref = sorted(reference_expected_ids)
    ref_set, obs_set = set(ref), set(observed)
    if obs_set == ref_set:
        comparison = "exact"
    elif obs_set > ref_set:
        comparison = "extended"
    elif obs_set < ref_set:
        comparison = "changed"          # a reference id disappeared — must be adjudicated
    else:
        comparison = "ambiguous"        # overlap with both additions and removals
    return {"namespace": "chr_classes", "reference_expected_ids": ref,
            "reference_holes": sorted(reference_holes), "observed_client_ids": observed,
            "comparison": comparison}


def class_roster(class_axis: dict) -> list[int]:
    return list(class_axis["observed_client_ids"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wow_constants_class_axis.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/wow_constants.py tests/test_wow_constants_class_axis.py
git commit -m "M1.14D Task 4: class axis (reference-expected vs observed) + roster"
```

---

## Task 5: Reconnaissance pass + report

**Files:**
- Modify: `coa_client_extract/wow_constants.py`
- Test: `tests/test_wow_constants_recon.py`

**Interfaces:**
- Consumes: `ArchiveBackend` (M1.14A), `parse_gametable`, `parse_dbc` + `CHR_CLASSES`, `load_axis_policy`, `build_class_axis`, `load_authored_input`.
- Produces: `recon(backend, root, attach, *, axis_policy, rating_enum, chr_layout=CHR_CLASSES) -> dict` — the recon report (no canonical write): per-table `{available, header, physical_form, source_records, drift}`, `class_axis`, `enum_coverage`, and `class_context_resolution` (default `"unproven"`). Reader of a `DBFilesClient\\<name>.dbc` logical path via `backend.read_effective_file`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wow_constants_recon.py
import struct
from pathlib import Path
from coa_client_extract.archive_backend import FakeArchiveBackend
from coa_client_extract.wow_constants import recon, load_authored_input, load_axis_policy


def _implicit(values):
    body = b"".join(struct.pack("<f", v) for v in values)
    return struct.pack("<4sIIII", b"WDBC", len(values), 1, 4, 0) + body


def _chr_classes(ids):
    # ChrClasses: 60 cells; col0 id, col3 power_type, col4 name offset
    strings = b"\x00" + b"".join(f"C{i}".encode() + b"\x00" for i in ids)
    rows = []
    off = 1
    for i in ids:
        cells = [0] * 60
        cells[0] = i
        cells[3] = 0
        cells[4] = off
        off += len(f"C{i}") + 1
        rows.append(struct.pack("<" + "I" * 60, *cells))
    return struct.pack("<4sIIII", b"WDBC", len(ids), 60, 240, len(strings)) + b"".join(rows) + strings


def _backend():
    entries = {
        "DBFilesClient\\gtCombatRatings.dbc": [(Path("patch-M.MPQ"), _implicit([float(i) for i in range(3200)]))],
        "DBFilesClient\\gtOCTClassCombatRatingScalar.dbc": [(Path("patch-M.MPQ"), _implicit([1.0] * (12 * 32)))],
        "DBFilesClient\\gtChanceToMeleeCrit.dbc": [(Path("patch-M.MPQ"), _implicit([0.05] * (12 * 100)))],
        "DBFilesClient\\gtChanceToMeleeCritBase.dbc": [(Path("patch-M.MPQ"), _implicit([0.01] * 12))],
        "DBFilesClient\\gtChanceToSpellCrit.dbc": [(Path("patch-M.MPQ"), _implicit([0.05] * (12 * 100)))],
        "DBFilesClient\\gtChanceToSpellCritBase.dbc": [(Path("patch-M.MPQ"), _implicit([0.01] * 12))],
        "DBFilesClient\\gtRegenMPPerSpt.dbc": [(Path("patch-M.MPQ"), _implicit([0.1] * (12 * 100)))],
        "DBFilesClient\\ChrClasses.dbc": [(Path("patch-M.MPQ"), _chr_classes([1,2,3,4,5,6,7,8,9,11]))],
    }
    return FakeArchiveBackend(entries), Path("common.MPQ"), (Path("patch-M.MPQ"),)


def test_recon_reports_tables_class_axis_and_default_context():
    backend, root, attach = _backend()
    layouts, ls, rs = load_axis_policy(load_authored_input("gt_axis_policy").payload)
    rating_enum = load_authored_input("rating_enum").payload
    report = recon(backend, root, attach, axis_policy=(layouts, ls, rs), rating_enum=rating_enum)
    assert report["tables"]["combat_ratings"]["available"] is True
    assert report["tables"]["combat_ratings"]["source_records"] == 3200
    assert report["tables"]["combat_ratings"]["drift"] is False
    assert report["class_axis"]["comparison"] == "exact"
    assert report["class_context_resolution"] == "unproven"
    # recon-gated tables absent in this fixture are reported unavailable, not fatal
    assert report["tables"]["oct_regen_mp"]["available"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wow_constants_recon.py -v`
Expected: FAIL with `ImportError: cannot import name 'recon'`.

- [ ] **Step 3: Implement `recon`**

```python
# coa_client_extract/wow_constants.py  (append)
from .archive_backend import ArchiveBackend
from .dbc_layouts import CHR_CLASSES
from .errors import ArchiveError
from .wdbc import parse_dbc, parse_gametable


def _read_gametable(backend, root, attach, layout):
    member = backend.read_effective_file(root, attach, f"DBFilesClient\\{layout.source_dbc}.dbc")
    # non-strict during recon: drift is diagnostic, not fatal
    table = parse_gametable(member.data, physical_form=layout.physical_form,
                            expected_field_count=1, expected_record_size=4)
    return member, table


def recon(backend: ArchiveBackend, root, attach, *, axis_policy, rating_enum,
          chr_layout=CHR_CLASSES) -> dict:
    layouts, level_stride, rating_stride = axis_policy
    tables: dict[str, dict] = {}
    for key, layout in layouts.items():
        try:
            member, table = _read_gametable(backend, root, attach, layout)
        except ArchiveError:
            tables[key] = {"available": False, "source_dbc": layout.source_dbc}
            continue
        tables[key] = {"available": True, "source_dbc": layout.source_dbc,
                       "physical_form": table.physical_form, "field_count": table.field_count,
                       "record_size": table.record_size, "source_records": table.record_count,
                       "drift": table.drift, "class_indexed": layout.class_indexed,
                       "semantics": layout.semantics}

    chr_member = backend.read_effective_file(root, attach, "DBFilesClient\\ChrClasses.dbc")
    chr_tbl = parse_dbc(chr_member.data, chr_layout)
    policy_axis = _axis_policy_class_meta(axis_policy)
    class_axis = build_class_axis(chr_tbl.rows, **policy_axis)

    supported_ids = set(rating_enum.get("supported", {}))
    return {"tables": tables, "class_axis": class_axis,
            "enum_coverage": {"rating_supported_count": len(supported_ids)},
            "class_context_resolution": "unproven"}


def _axis_policy_class_meta(axis_policy) -> dict:
    # class_axis metadata is stored alongside the layouts on the raw policy payload; the caller
    # passes the parsed layouts, so re-read the reference roster from the authored file.
    payload = load_authored_input("gt_axis_policy").payload["class_axis"]
    return {"reference_expected_ids": payload["reference_expected_ids"],
            "reference_holes": payload["reference_holes"]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wow_constants_recon.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/wow_constants.py tests/test_wow_constants_recon.py
git commit -m "M1.14D Task 5: reconnaissance pass (headers/availability/class-axis/context evidence)"
```

---

## Task 6: Real-client recon adjudication checkpoint (HARD HOLD POINT — manual)

> **This task gates every canonical-extraction task below (7–9, 13).** No canonical `coa_wow_constants.json` may be generated or trusted until the real-client recon is reviewed and the authored data frozen. It requires the local Ascension client and a built StormLib; it produces no code, only frozen/adjudicated authored data. If you cannot run the real client here, STOP and hand this checkpoint to the maintainer before proceeding to Task 7.

**Files:**
- Modify (freeze/adjudicate to observed reality): `coa_client_extract/data/gt_axis_policy_v1.json`, `coa_client_extract/data/rating_enum_v1.json`, `coa_client_extract/data/wotlk_reference_anchors_v1.json`
- Create (git-ignored, real): `reports/client_extract/coa_wow_constants_recon.json`

- [ ] **Step 1: Run recon against the real client** (requires the Task 8 CLI `--recon-only`; if Task 8 is not yet implemented, run recon via a short REPL using `discover_plan` + `recon`)

```bash
COA_CLIENT_ROOT=/path/to/ascension-live/Data \
python -m coa_client_extract wow-constants --client-root "$COA_CLIENT_ROOT" \
  --out reports/client_extract --recon-only
```

- [ ] **Step 2: Review the recon report and adjudicate**

Open `reports/client_extract/coa_wow_constants_recon.json` and confirm/adjust:
- **Physical form** of each `gt*.dbc` (`implicit_row` vs `explicit_id`) — update `physical_form` in `gt_axis_policy_v1.json` if the client uses an explicit id column, and set `parse_gametable` `id_cell`/`value_cell` accordingly in Task 8's reader wiring.
- **Observed class roster** and `class_axis.comparison`. If `exact`, proceed. If `extended`/`changed`/`ambiguous`, record the decision in a short note appended to the recon report and adjust `reference_expected_ids` only if the reference itself was wrong (never to hide a real Ascension change).
- **Table availability**: confirm the proven-required tables are present. For each recon-gated table (`oct_regen_mp`, `base_mana_by_class`, `base_hp_by_class`) that is present AND whose role you can establish, flip its `semantics` from `unproven` to `proven` in `gt_axis_policy_v1.json`; leave the rest `unproven` (they will be extracted but labelled, and excluded from exit-required assertions).
- **Rating enum coverage**: confirm every observed rating id is in `rating_enum_v1.json.supported`; add any observed-but-undefined id (that is a real coverage gap) and bump the enum `version`.
- **`class_context_resolution`**: leave `unproven` unless the recon surfaces a concrete client-native bridge; document any candidate in the report.
- **Reference anchors**: verify the level-60/80 `rating_per_percent` values against the real client's derived multiplier; keep them as documented references (record match/deviation — do not delete an anchor merely because the client differs).

- [ ] **Step 3: Commit the frozen authored data**

```bash
git add coa_client_extract/data/gt_axis_policy_v1.json coa_client_extract/data/rating_enum_v1.json \
        coa_client_extract/data/wotlk_reference_anchors_v1.json
git commit -m "M1.14D Task 6: freeze GameTable axis policy/enums/anchors from real-client recon"
```

---

## Task 7: Reference comparison + snapshot assembly

**Files:**
- Modify: `coa_client_extract/wow_constants.py`
- Test: `tests/test_wow_constants_snapshot.py`

**Interfaces:**
- Consumes: `map_table_entries`, `build_class_axis`, `load_authored_input`, the rules/enum payloads.
- Produces: `reference_comparison(entries: list[dict], anchors: list[dict], *, anchor_set_version: str, anchor_set_sha256: str) -> dict` (`scope: "anchors"`, `checked`/`equal`/`different`/`status`); `build_snapshot(*, client_build, provenance, class_axis, game_tables, rules, rating_enum, power_type_enum) -> dict` producing the `coa-wow-constants-v1` document.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wow_constants_snapshot.py
from coa_client_extract.wow_constants import reference_comparison, build_snapshot


def test_reference_comparison_is_anchor_scoped():
    entries = [{"rating_id": 10, "level": 60, "value": 14.0},
               {"rating_id": 10, "level": 80, "value": 40.0}]
    anchors = [{"rating_id": 10, "level": 60, "expected": 14.0, "tolerance": 0.5},
               {"rating_id": 10, "level": 80, "expected": 45.9, "tolerance": 0.5}]
    rc = reference_comparison(entries, anchors, anchor_set_version="v1", anchor_set_sha256="ab")
    assert rc["scope"] == "anchors"
    assert rc["checked"] == 2 and rc["equal"] == 1 and rc["different"] == 1
    assert rc["status"] == "differs_on_checked_anchors"


def test_build_snapshot_has_required_top_level_shape():
    snap = build_snapshot(
        client_build="3.3.5a+patch-M",
        provenance={"backend": "fake", "source_dbcs": {}},
        class_axis={"namespace": "chr_classes", "comparison": "exact",
                    "observed_client_ids": [1], "reference_expected_ids": [1], "reference_holes": []},
        game_tables={"combat_ratings": {"source_dbc": "gtCombatRatings", "axes": ["rating_id", "level"],
                     "class_indexed": False, "drift": False,
                     "counts": {"source_records": 1, "emitted_entries": 1, "padding_records": 0},
                     "entries": [{"rating_id": 0, "level": 1, "value": 1.0}]}},
        rules={"base_energy": {"value": 100}},
        rating_enum={"version": "cr-3.3.5a-v1", "supported": {"0": "weapon_skill"}},
        power_type_enum={"version": "m1.14c-power-v1", "map": {"0": "mana"}})
    assert snap["schema_version"] == "coa-wow-constants-v1"
    assert snap["client_build"] == "3.3.5a+patch-M"
    assert set(snap) >= {"schema_version", "client_build", "provenance", "class_axis",
                         "enum_maps", "game_tables", "rules"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wow_constants_snapshot.py -v`
Expected: FAIL with `ImportError: cannot import name 'reference_comparison'`.

- [ ] **Step 3: Implement `reference_comparison` + `build_snapshot`**

```python
# coa_client_extract/wow_constants.py  (append)
import math

WOW_CONSTANTS_SCHEMA = "coa-wow-constants-v1"


def reference_comparison(entries: list[dict], anchors: list[dict], *,
                         anchor_set_version: str, anchor_set_sha256: str) -> dict:
    index = {tuple(sorted((k, v) for k, v in e.items() if k != "value")): e["value"]
             for e in entries}
    checked = equal = different = 0
    for anchor in anchors:
        key = tuple(sorted((k, v) for k, v in anchor.items()
                           if k not in ("expected", "tolerance")))
        if key not in index:
            continue
        checked += 1
        if abs(index[key] - anchor["expected"]) <= anchor.get("tolerance", 0.0):
            equal += 1
        else:
            different += 1
    status = ("matches_on_checked_anchors" if different == 0 and checked
              else "differs_on_checked_anchors" if checked else "no_anchors_checked")
    return {"scope": "anchors", "anchor_set_version": anchor_set_version,
            "anchor_set_sha256": anchor_set_sha256, "checked": checked, "equal": equal,
            "different": different, "status": status}


def build_snapshot(*, client_build: str, provenance: dict, class_axis: dict, game_tables: dict,
                   rules: dict, rating_enum: dict, power_type_enum: dict) -> dict:
    for key, table in game_tables.items():
        for entry in table.get("entries", []):
            if not math.isfinite(entry["value"]):
                raise ValueError(f"{key}: non-finite value in entries")
    return {"schema_version": WOW_CONSTANTS_SCHEMA, "client_build": client_build,
            "provenance": provenance, "class_axis": class_axis,
            "enum_maps": {"rating_enum": rating_enum, "power_type": power_type_enum},
            "game_tables": game_tables, "rules": rules}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wow_constants_snapshot.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/wow_constants.py tests/test_wow_constants_snapshot.py
git commit -m "M1.14D Task 7: anchor-scoped reference comparison + snapshot assembly"
```

---

## Task 8: `write_wow_constants` — manifest-last with hashed authored inputs

**Files:**
- Modify: `coa_client_extract/artifacts.py`
- Test: `tests/test_wow_constants_write.py`

**Interfaces:**
- Consumes: `_atomic_write_bytes`, `_sha256_bytes` (already in `artifacts.py`); `AuthoredInput` list (Task 2).
- Produces: `write_wow_constants(snapshot: dict, out_dir: Path, *, authored_inputs: list, source_dbc_sha256: dict, class_context_resolution: str, extractor_commit: str, client_build: str, table_summary: dict) -> dict` — writes `coa_wow_constants.json` then `coa_wow_constants.manifest.json` last (validity marker) and returns the manifest.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wow_constants_write.py
import hashlib
import json
from pathlib import Path
import pytest
from coa_client_extract.artifacts import write_wow_constants


class _AI:
    def __init__(self, name, version, sha256):
        self.name, self.version, self.sha256 = name, version, sha256


def _write(out: Path):
    snap = {"schema_version": "coa-wow-constants-v1", "client_build": "3.3.5a+patch-M"}
    ai = [_AI("wow_rules", "wow-rules-v1", "a" * 64), _AI("rating_enum", "cr-3.3.5a-v1", "b" * 64),
          _AI("power_type_enum", "m1.14c-power-v1", "c" * 64),
          _AI("gt_axis_policy", "gt-layout-v1", "d" * 64),
          _AI("wotlk_reference_anchors", "wotlk-335a-anchors-v1", "e" * 64)]
    return write_wow_constants(snap, out, authored_inputs=ai,
                               source_dbc_sha256={"gtCombatRatings": "f" * 64},
                               class_context_resolution="unproven", extractor_commit="deadbeef",
                               client_build="3.3.5a+patch-M", table_summary={})


def test_manifest_binds_artifact_and_every_authored_input(tmp_path):
    manifest = _write(tmp_path)
    art = tmp_path / "coa_wow_constants.json"
    assert manifest["artifact"]["sha256"] == hashlib.sha256(art.read_bytes()).hexdigest()
    ai = manifest["authored_inputs"]
    assert set(ai) == {"rules", "rating_enum", "power_type_enum", "axis_layout_policy",
                       "reference_anchors"}
    assert ai["rules"] == {"version": "wow-rules-v1", "sha256": "a" * 64}
    assert manifest["class_context_resolution"] == "unproven"


def test_manifest_written_last_as_validity_marker(tmp_path):
    _write(tmp_path)
    # A subsequent write removes the old manifest before rewriting the artifact.
    (tmp_path / "coa_wow_constants.manifest.json").unlink()
    (tmp_path / "coa_wow_constants.json").write_text("STALE")
    _write(tmp_path)
    assert (tmp_path / "coa_wow_constants.manifest.json").is_file()
    assert json.loads((tmp_path / "coa_wow_constants.json").read_text())["schema_version"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wow_constants_write.py -v`
Expected: FAIL with `ImportError: cannot import name 'write_wow_constants'`.

- [ ] **Step 3: Implement `write_wow_constants`**

```python
# coa_client_extract/artifacts.py  (append)
from datetime import date

_AUTHORED_MANIFEST_KEYS = {"wow_rules": "rules", "rating_enum": "rating_enum",
                           "power_type_enum": "power_type_enum",
                           "gt_axis_policy": "axis_layout_policy",
                           "wotlk_reference_anchors": "reference_anchors"}


def write_wow_constants(snapshot: dict, out_dir: Path, *, authored_inputs, source_dbc_sha256: dict,
                        class_context_resolution: str, extractor_commit: str, client_build: str,
                        table_summary: dict) -> dict:
    art_path = out_dir / "coa_wow_constants.json"
    manifest_path = out_dir / "coa_wow_constants.manifest.json"
    body = (json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    authored = {}
    for ai in authored_inputs:
        authored[_AUTHORED_MANIFEST_KEYS[ai.name]] = {"version": ai.version, "sha256": ai.sha256}

    manifest = {
        "schema_version": "coa-wow-constants-manifest-v1",
        "artifact": {"path": art_path.name, "sha256": _sha256_bytes(body), "byte_length": len(body)},
        "source_dbc_sha256": dict(source_dbc_sha256),
        "authored_inputs": authored,
        "class_context_resolution": class_context_resolution,
        "table_summary": dict(table_summary),
        "extractor_commit": extractor_commit, "client_build": client_build,
        "extraction_date": date.today().isoformat(),
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    out_dir.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        manifest_path.unlink()                 # remove stale marker first
    _atomic_write_bytes(body, art_path)         # write artifact
    _atomic_write_bytes(manifest_bytes, manifest_path)  # write marker last
    return manifest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wow_constants_write.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/artifacts.py tests/test_wow_constants_write.py
git commit -m "M1.14D Task 8: write_wow_constants (manifest-last, hashed authored inputs)"
```

---

## Task 9: CLI `wow-constants` subcommand (recon-only + strict canonical + fail-closed)

**Files:**
- Modify: `coa_client_extract/cli.py`
- Modify: `coa_client_extract/wow_constants.py` (add the `extract` orchestrator)
- Test: `tests/test_wow_constants_cli.py`

**Interfaces:**
- Consumes: `discover_plan`, `validate_load_order`, `ArchivePlan.open_chain` (M1.14A); `recon`, `map_table_entries`, `build_class_axis`, `build_snapshot`, `reference_comparison`, `load_authored_input`, `load_axis_policy`; `write_wow_constants`; `_client_build`/`_extractor_commit` in `cli.py`.
- Produces: `wow_constants_extract(client_root: Path, out_dir: Path, *, backend=None, stormlib_path=None, recon_only=False) -> dict`; a `wow-constants` subparser wired into `main`. Strict canonical parse; fails closed (exit 2) on `BackendUnavailable`.

- [ ] **Step 1: Write the failing test** (reuses the recon fixture pattern; drives the full extract with a fake backend)

```python
# tests/test_wow_constants_cli.py
import json
import struct
from pathlib import Path
import pytest
from coa_client_extract.archive_backend import FakeArchiveBackend
from coa_client_extract.cli import main, wow_constants_extract
from coa_client_extract.errors import BackendUnavailable


def _client(tmp_path: Path) -> Path:
    data = tmp_path / "Data"
    data.mkdir()
    for name in ("common.MPQ", "patch.MPQ", "patch-M.MPQ"):
        (data / name).write_bytes(b"MPQ\x1a")
    return data


def _implicit(values):
    body = b"".join(struct.pack("<f", v) for v in values)
    return struct.pack("<4sIIII", b"WDBC", len(values), 1, 4, 0) + body


def _chr_classes(ids):
    strings = b"\x00" + b"".join(f"C{i}".encode() + b"\x00" for i in ids)
    rows, off = [], 1
    for i in ids:
        cells = [0] * 60
        cells[0], cells[3], cells[4] = i, 0, off
        off += len(f"C{i}") + 1
        rows.append(struct.pack("<" + "I" * 60, *cells))
    return struct.pack("<4sIIII", b"WDBC", len(ids), 60, 240, len(strings)) + b"".join(rows) + strings


def _backend():
    ids = [1,2,3,4,5,6,7,8,9,11]
    entries = {
        "DBFilesClient\\gtCombatRatings.dbc": [(Path("patch-M.MPQ"), _implicit([float(i) for i in range(3200)]))],
        "DBFilesClient\\gtOCTClassCombatRatingScalar.dbc": [(Path("patch-M.MPQ"), _implicit([1.0] * (12 * 32)))],
        "DBFilesClient\\gtChanceToMeleeCrit.dbc": [(Path("patch-M.MPQ"), _implicit([0.05] * (12 * 100)))],
        "DBFilesClient\\gtChanceToMeleeCritBase.dbc": [(Path("patch-M.MPQ"), _implicit([0.01] * 12))],
        "DBFilesClient\\gtChanceToSpellCrit.dbc": [(Path("patch-M.MPQ"), _implicit([0.05] * (12 * 100)))],
        "DBFilesClient\\gtChanceToSpellCritBase.dbc": [(Path("patch-M.MPQ"), _implicit([0.01] * 12))],
        "DBFilesClient\\gtRegenMPPerSpt.dbc": [(Path("patch-M.MPQ"), _implicit([0.1] * (12 * 100)))],
        "DBFilesClient\\ChrClasses.dbc": [(Path("patch-M.MPQ"), _chr_classes(ids))],
    }
    return FakeArchiveBackend(entries)


def test_extract_writes_snapshot_and_manifest(tmp_path):
    out = tmp_path / "out"
    manifest = wow_constants_extract(_client(tmp_path), out, backend=_backend())
    assert (out / "coa_wow_constants.json").is_file()
    assert (out / "coa_wow_constants.manifest.json").is_file()
    snap = json.loads((out / "coa_wow_constants.json").read_text())
    assert snap["schema_version"] == "coa-wow-constants-v1"
    assert snap["class_axis"]["comparison"] == "exact"
    # rating_id=6, level=60 -> ordinal 659 -> value 659.0 (from the fixture)
    ct = snap["game_tables"]["combat_ratings"]
    hit = next(e for e in ct["entries"] if e["rating_id"] == 6 and e["level"] == 60)
    assert hit["value"] == 659.0
    assert manifest["class_context_resolution"] == "unproven"


def test_recon_only_writes_report_not_snapshot(tmp_path):
    out = tmp_path / "out"
    report = wow_constants_extract(_client(tmp_path), out, backend=_backend(), recon_only=True)
    assert report["class_axis"]["comparison"] == "exact"
    assert (out / "coa_wow_constants_recon.json").is_file()
    assert not (out / "coa_wow_constants.json").exists()


def test_cli_fails_closed_without_stormlib(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise BackendUnavailable("StormLib not found")
    monkeypatch.setattr("coa_client_extract.stormlib_backend.StormLibBackend", boom, raising=False)
    rc = main(["wow-constants", "--client-root", str(_client(tmp_path)), "--out", str(tmp_path / "o")])
    assert rc == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wow_constants_cli.py -v`
Expected: FAIL with `ImportError: cannot import name 'wow_constants_extract'`.

- [ ] **Step 3: Implement `wow_constants_extract` in `wow_constants.py`**

```python
# coa_client_extract/wow_constants.py  (append)
import hashlib
import json as _json
from pathlib import Path


def wow_constants_extract(client_root, out_dir, *, backend, plan, recon_only: bool = False,
                          extractor_commit: str = "unknown", client_build: str = "3.3.5a") -> dict:
    """Orchestrate recon and (unless recon_only) the strict canonical snapshot. `plan` is the
    discovered ArchivePlan; `backend` reads the effective DBC bytes."""
    root, attach = plan.open_chain
    axis_input = load_authored_input("gt_axis_policy")
    rating_input = load_authored_input("rating_enum")
    power_input = load_authored_input("power_type_enum")
    rules_input = load_authored_input("wow_rules")
    anchors_input = load_authored_input("wotlk_reference_anchors")
    layouts, level_stride, rating_stride = load_axis_policy(axis_input.payload)

    report = recon(backend, root, attach, axis_policy=(layouts, level_stride, rating_stride),
                   rating_enum=rating_input.payload)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if recon_only:
        (out_dir / "coa_wow_constants_recon.json").write_text(
            _json.dumps(report, indent=2, sort_keys=True) + "\n")
        return report

    roster = class_roster(report["class_axis"])
    anchors = anchors_input.payload["anchors"]
    game_tables: dict = {}
    source_dbc_sha: dict = {}
    table_summary: dict = {}
    for key, layout in layouts.items():
        if not report["tables"][key]["available"]:
            continue
        if layout.semantics == "unproven":
            continue                              # recon-gated + unproven -> not emitted canonically
        member = backend.read_effective_file(root, attach, f"DBFilesClient\\{layout.source_dbc}.dbc")
        table = parse_gametable(member.data, physical_form=layout.physical_form,
                                expected_field_count=1, expected_record_size=4, strict=True)
        entries, counts = map_table_entries(layout, table, class_roster=roster,
                                            level_stride=level_stride, rating_stride=rating_stride)
        rc = reference_comparison(entries, [a for a in anchors if _anchor_matches(a, key)],
                                  anchor_set_version=anchors_input.version,
                                  anchor_set_sha256=anchors_input.sha256)
        game_tables[key] = {"source_dbc": layout.source_dbc, "physical_form": layout.physical_form,
                            "axes": list(layout.axes), "class_indexed": layout.class_indexed,
                            "drift": table.drift, "counts": counts, "reference_comparison": rc,
                            "entries": entries}
        source_dbc_sha[layout.source_dbc] = hashlib.sha256(member.data).hexdigest()
        table_summary[key] = {**counts, "drift": table.drift,
                              "reference_comparison_status": rc["status"]}

    chr_member = backend.read_effective_file(root, attach, "DBFilesClient\\ChrClasses.dbc")
    source_dbc_sha["ChrClasses"] = hashlib.sha256(chr_member.data).hexdigest()

    provenance = {"backend": getattr(backend, "name", "unknown"),
                  "backend_version": getattr(backend, "version", "unknown"),
                  "source_dbcs": {k: {"sha256": v} for k, v in source_dbc_sha.items()}}
    snapshot = build_snapshot(client_build=client_build, provenance=provenance,
                              class_axis=report["class_axis"], game_tables=game_tables,
                              rules=rules_input.payload["rules"], rating_enum=rating_input.payload,
                              power_type_enum=power_input.payload)

    from .artifacts import write_wow_constants
    return write_wow_constants(
        snapshot, out_dir,
        authored_inputs=[rules_input, rating_input, power_input, axis_input, anchors_input],
        source_dbc_sha256=source_dbc_sha,
        class_context_resolution=report["class_context_resolution"],
        extractor_commit=extractor_commit, client_build=client_build, table_summary=table_summary)


def _anchor_matches(anchor: dict, table_key: str) -> bool:
    # In-artifact reference_comparison only uses RAW-value anchors tagged with their table (coord +
    # expected raw value). The shipped anchor set holds only DERIVED per-1% anchors (a test-only
    # oracle, computed in the tests), so canonical tables report "no_anchors_checked" until raw
    # anchors are frozen at the Task 6 checkpoint — never a false match against a derived value.
    return anchor.get("table") == table_key
```

- [ ] **Step 4: Wire the `wow-constants` subcommand into `cli.py`**

Add a thin wrapper `wow_constants_extract` in `cli.py` that discovers the plan and delegates, plus the subparser:

```python
# coa_client_extract/cli.py  (add near regenerate)
def wow_constants_extract(client_root: Path, out_dir: Path, *, backend: ArchiveBackend | None = None,
                          stormlib_path: str | None = None, recon_only: bool = False) -> dict:
    if backend is None:
        from .stormlib_backend import StormLibBackend
        backend = StormLibBackend(stormlib_path=stormlib_path)  # may raise BackendUnavailable
    plan = discover_plan(client_root)
    from .wow_constants import wow_constants_extract as _run
    return _run(client_root, out_dir, backend=backend, plan=plan, recon_only=recon_only,
                extractor_commit=_extractor_commit(), client_build=_client_build(plan))
```

In `main`, add the subparser and dispatch (mirroring the `regenerate` block):

```python
    wc = sub.add_parser("wow-constants", help="extract coa-wow-constants-v1 GameTable primitives")
    wc.add_argument("--client-root", required=True, type=Path)
    wc.add_argument("--out", required=True, type=Path)
    wc.add_argument("--stormlib", default=None)
    wc.add_argument("--recon-only", action="store_true")
```

```python
    if args.command == "wow-constants":
        try:
            wow_constants_extract(args.client_root, args.out, stormlib_path=args.stormlib,
                                  recon_only=args.recon_only)
        except BackendUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_wow_constants_cli.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add coa_client_extract/wow_constants.py coa_client_extract/cli.py tests/test_wow_constants_cli.py
git commit -m "M1.14D Task 9: wow-constants CLI (recon-only + strict canonical + fail-closed)"
```

---

## Task 10: `WowConstantsRepository` — native-namespace reader, no computation

**Files:**
- Create: `coa_meta/wow_constants.py`
- Test: `tests/test_wow_constants_repository.py`

**Interfaces:**
- Consumes: a `coa-wow-constants-v1` snapshot dict/file.
- Produces: `WowConstantsRepository` with `from_dict(doc) -> WowConstantsRepository` / `load(path) -> WowConstantsRepository`; methods `combat_rating_ratio(rating_id: int, level: int) -> float`; `class_combat_rating_scalar(*, wow_class_id: int, rating_id: int) -> float`; `rule(key: str) -> dict`; `rating_name(rating_id: int) -> str`. Raises `WowConstantsLoadError` on bad schema/structure and `LookupError` on missing coordinates or a rejected id namespace.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wow_constants_repository.py
import math
import pytest
from coa_meta.wow_constants import WowConstantsRepository, WowConstantsLoadError

COA_CLASS_TYPE_ID = 33  # a CoA class-type id (14..34), NOT a wow_class_id


def _doc(**over):
    doc = {
        "schema_version": "coa-wow-constants-v1", "client_build": "3.3.5a+patch-M",
        "class_axis": {"namespace": "chr_classes", "observed_client_ids": [1, 8, 11]},
        "enum_maps": {"rating_enum": {"version": "cr-3.3.5a-v1",
                                      "supported": {"10": "crit_spell"}},
                      "power_type": {"version": "m1.14c-power-v1", "map": {"0": "mana"}}},
        "game_tables": {
            "combat_ratings": {"axes": ["rating_id", "level"], "class_indexed": False,
                "entries": [{"rating_id": 10, "level": 60, "value": 14.0}]},
            "class_combat_rating_scalar": {"axes": ["wow_class_id", "rating_id"], "class_indexed": True,
                "entries": [{"wow_class_id": 8, "rating_id": 10, "value": 1.0}]},
        },
        "rules": {"gcd_floor_ms": {"value": 1000}},
    }
    doc.update(over)
    return doc


def test_rejects_wrong_schema_version():
    with pytest.raises(WowConstantsLoadError):
        WowConstantsRepository.from_dict(_doc(schema_version="coa-wow-constants-v2"))


def test_level_only_lookup_is_context_free():
    repo = WowConstantsRepository.from_dict(_doc())
    assert repo.combat_rating_ratio(10, 60) == 14.0


def test_class_lookup_requires_keyword_wow_class_id():
    repo = WowConstantsRepository.from_dict(_doc())
    assert repo.class_combat_rating_scalar(wow_class_id=8, rating_id=10) == 1.0
    with pytest.raises(TypeError):
        repo.class_combat_rating_scalar(8, 10)  # positional not allowed


def test_rejects_coa_class_type_id_as_out_of_namespace():
    repo = WowConstantsRepository.from_dict(_doc())
    with pytest.raises(LookupError):
        repo.class_combat_rating_scalar(wow_class_id=COA_CLASS_TYPE_ID, rating_id=10)


def test_missing_coordinate_raises_not_returns_zero():
    repo = WowConstantsRepository.from_dict(_doc())
    with pytest.raises(LookupError):
        repo.combat_rating_ratio(10, 61)


def test_non_finite_value_is_rejected_at_load():
    with pytest.raises(WowConstantsLoadError):
        WowConstantsRepository.from_dict(_doc(game_tables={
            "combat_ratings": {"axes": ["rating_id", "level"], "class_indexed": False,
                "entries": [{"rating_id": 10, "level": 60, "value": math.inf}]}}))


def test_duplicate_coordinate_is_rejected_at_load():
    with pytest.raises(WowConstantsLoadError):
        WowConstantsRepository.from_dict(_doc(game_tables={
            "combat_ratings": {"axes": ["rating_id", "level"], "class_indexed": False,
                "entries": [{"rating_id": 10, "level": 60, "value": 1.0},
                            {"rating_id": 10, "level": 60, "value": 2.0}]}}))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wow_constants_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'coa_meta.wow_constants'`.

- [ ] **Step 3: Implement `WowConstantsRepository`**

```python
# coa_meta/wow_constants.py
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

WOW_CONSTANTS_SCHEMA_VERSION = "coa-wow-constants-v1"


class WowConstantsLoadError(ValueError):
    pass


class WowConstantsRepository:
    """Loads coa-wow-constants-v1, validates structure, and looks up RAW values by coordinate.
    It performs no calculation (no rating->%, GCD, crit, or regen math) and never maps a CoA
    class-type id into a wow_class_id."""

    def __init__(self, tables: dict, class_axis: dict, rules: dict, rating_enum: dict):
        self._tables = tables
        self._class_axis = class_axis
        self._rules = rules
        self._rating_enum = rating_enum

    @classmethod
    def load(cls, path: str | Path) -> "WowConstantsRepository":
        return cls.from_dict(json.loads(Path(path).read_text()))

    @classmethod
    def from_dict(cls, doc: dict) -> "WowConstantsRepository":
        if doc.get("schema_version") != WOW_CONSTANTS_SCHEMA_VERSION:
            raise WowConstantsLoadError(
                f"unsupported schema_version {doc.get('schema_version')!r}")
        class_axis = doc.get("class_axis") or {}
        rating_enum = (doc.get("enum_maps") or {}).get("rating_enum") or {}
        indexed: dict[str, dict] = {}
        for key, table in (doc.get("game_tables") or {}).items():
            axes = tuple(table.get("axes") or ())
            if not axes:
                raise WowConstantsLoadError(f"{key}: missing axes")
            seen: dict[tuple, float] = {}
            for entry in table.get("entries") or []:
                value = entry.get("value")
                if value is None or not math.isfinite(value):
                    raise WowConstantsLoadError(f"{key}: non-finite/missing value")
                coord = tuple(entry[a] for a in axes)
                if coord in seen:
                    raise WowConstantsLoadError(f"{key}: duplicate coordinate {coord}")
                seen[coord] = float(value)
            indexed[key] = {"axes": axes, "class_indexed": bool(table.get("class_indexed")),
                            "by_coord": seen}
        return cls(indexed, class_axis, doc.get("rules") or {}, rating_enum)

    def _observed_class_ids(self) -> set[int]:
        return set(self._class_axis.get("observed_client_ids") or [])

    def _lookup(self, key: str, coord: tuple) -> float:
        table = self._tables.get(key)
        if table is None:
            raise LookupError(f"no table {key!r}")
        try:
            return table["by_coord"][coord]
        except KeyError:
            raise LookupError(f"{key}: no value at {dict(zip(table['axes'], coord))}")

    def combat_rating_ratio(self, rating_id: int, level: int) -> float:
        return self._lookup("combat_ratings", (rating_id, level))

    def class_combat_rating_scalar(self, *, wow_class_id: int, rating_id: int) -> float:
        self._require_wow_class(wow_class_id)
        return self._lookup("class_combat_rating_scalar", (wow_class_id, rating_id))

    def _require_wow_class(self, wow_class_id: int) -> None:
        # Reject any id that is not in the observed stock ChrClasses namespace. This catches a
        # CoA class-type id (14..34) or any out-of-domain integer; the reader never maps namespaces.
        if wow_class_id not in self._observed_class_ids():
            raise LookupError(
                f"wow_class_id {wow_class_id} is not in the ChrClasses namespace "
                f"{sorted(self._observed_class_ids())}; class context is M1.16's to resolve")

    def rule(self, key: str) -> dict:
        if key not in self._rules:
            raise LookupError(f"no rule {key!r}")
        return dict(self._rules[key])

    def rating_name(self, rating_id: int) -> str:
        name = (self._rating_enum.get("supported") or {}).get(str(rating_id))
        if name is None:
            raise LookupError(f"unmapped rating_id {rating_id}")
        return name
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wow_constants_repository.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add coa_meta/wow_constants.py tests/test_wow_constants_repository.py
git commit -m "M1.14D Task 10: WowConstantsRepository (native-namespace reader, no computation)"
```

---

## Task 11: Modeling-standard synthetic oracle tests

**Files:**
- Test: `tests/test_wow_constants_oracles.py`

**Interfaces:**
- Consumes: `WowConstantsRepository`; `map_table_entries` + `parse_gametable` + `load_axis_policy`.

- [ ] **Step 1: Write the tests (these ARE the deliverable — test-only oracles, never repository behavior)**

```python
# tests/test_wow_constants_oracles.py
import struct
from coa_client_extract.wow_constants import load_authored_input, load_axis_policy, map_table_entries
from coa_client_extract.wdbc import parse_gametable
from coa_meta.wow_constants import WowConstantsRepository


def _implicit(values):
    body = b"".join(struct.pack("<f", v) for v in values)
    return struct.pack("<4sIIII", b"WDBC", len(values), 1, 4, 0) + body


def test_rating_to_percent_reference_formula_at_60_and_80():
    # Construct a fixture whose class_scalar / combat_rating reproduces a known multiplier.
    # combat_rating ratio at (crit_spell=10, level 60)=14.0, (…, level 80)=45.9; scalar=1.0.
    doc = {
        "schema_version": "coa-wow-constants-v1", "client_build": "t",
        "class_axis": {"observed_client_ids": [8]},
        "enum_maps": {"rating_enum": {"supported": {"10": "crit_spell"}}, "power_type": {"map": {}}},
        "game_tables": {
            "combat_ratings": {"axes": ["rating_id", "level"], "class_indexed": False,
                "entries": [{"rating_id": 10, "level": 60, "value": 14.0},
                            {"rating_id": 10, "level": 80, "value": 45.9}]},
            "class_combat_rating_scalar": {"axes": ["wow_class_id", "rating_id"], "class_indexed": True,
                "entries": [{"wow_class_id": 8, "rating_id": 10, "value": 1.0}]}},
        "rules": {}}
    repo = WowConstantsRepository.from_dict(doc)
    # test-only oracle: divide operands here, never in the repository
    scalar = repo.class_combat_rating_scalar(wow_class_id=8, rating_id=10)
    assert abs(scalar / repo.combat_rating_ratio(10, 60) - 1 / 14.0) < 1e-6
    assert abs(scalar / repo.combat_rating_ratio(10, 80) - 1 / 45.9) < 1e-6


def test_raw_divisor_is_nondecreasing_within_a_rating_id():
    layouts, ls, rs = load_axis_policy(load_authored_input("gt_axis_policy").payload)
    layout = layouts["combat_ratings"]
    # rating 10 rises with level (plateau allowed); other ratings are independent columns
    values = [0.0] * 3200
    for level in range(1, 101):
        values[10 * 100 + (level - 1)] = float(level // 2)  # nondecreasing, with plateaus
    table = parse_gametable(_implicit(values), physical_form="implicit_row",
                            expected_field_count=1, expected_record_size=4)
    entries, _ = map_table_entries(layout, table, class_roster=[], level_stride=ls, rating_stride=rs)
    r10 = sorted((e["level"], e["value"]) for e in entries if e["rating_id"] == 10)
    assert all(b >= a for (_, a), (_, b) in zip(r10, r10[1:]))  # nondecreasing within rating 10
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_wow_constants_oracles.py -v`
Expected: PASS (2 passed).

- [ ] **Step 3: Commit**

```bash
git add tests/test_wow_constants_oracles.py
git commit -m "M1.14D Task 11: modeling-standard oracles (rating->% at 60/80, within-rating monotonicity)"
```

---

## Task 12: Schema doc, ignore rules, and policy-gate registration

**Files:**
- Create: `docs/data/wow-constants-schema.md`
- Modify: `.gitignore`
- Modify: `docs/DECISIONS.md`

- [ ] **Step 1: Write the schema doc**

Create `docs/data/wow-constants-schema.md` documenting: the `coa-wow-constants-v1` top-level shape (`schema_version`, `client_build`, `provenance`, `class_axis`, `enum_maps`, `game_tables`, `rules`); the `game_tables[key]` fields (`source_dbc`, `physical_form`, `axes`, `class_indexed`, `drift`, `counts` = `source_records`/`emitted_entries`/`padding_records`, `reference_comparison`, `entries` with explicit coordinates); the `class_axis` block (`reference_expected_ids`, `reference_holes`, `observed_client_ids`, `comparison`); the `rules` label schema (`authority`, `ascension_verification`, `applies_to`, `source_ref`, `notes`); and the manifest (`coa-wow-constants-manifest-v1`: `artifact`, `source_dbc_sha256`, `authored_inputs` version+sha256, `class_context_resolution`, `table_summary`). State the reference indexing contract (`level_stride=100`, scalar `+1` offset, `rating_storage_stride=32`, supported `0–24`) and that rating→% (`class_scalar / combat_rating`) is identified, not computed here. Cross-reference `client-spell-schema.md` for the shared `power_type` map.

- [ ] **Step 2: Add ignore rules to `.gitignore`**

Append:

```
# M1.14D client-derived WoW constants — regenerate from your own client
reports/client_extract/coa_wow_constants_recon.json
coa_scraper/dist/coa_wow_constants.json
coa_scraper/dist/coa_wow_constants.manifest.json
```

- [ ] **Step 3: Register the artifact under the M1.14C forward policy gate in `docs/DECISIONS.md`**

In Decision 18 (or the M1.14C redistribution note), add one sentence: `coa_wow_constants.json` and its manifest are client-derived outputs and fall under the same mandatory forward policy gate M1.14C records (before M1.16 consumes any client-derived output, or any canonical public release, one policy decision must cover them consistently with `coa_client_spell_coa.jsonl` and `coa_mechanics.jsonl`).

- [ ] **Step 4: Verify no tracked client-derived bytes and commit**

Run: `git status --porcelain` and confirm no `coa_wow_constants.json`/recon report is staged.

```bash
git add docs/data/wow-constants-schema.md .gitignore docs/DECISIONS.md
git commit -m "M1.14D Task 12: wow-constants schema doc, ignore rules, policy-gate registration"
```

---

## Task 13: Client-tier acceptance + full-suite green

**Files:**
- Test: `tests/test_wow_constants_acceptance.py`

**Interfaces:**
- Consumes: `wow_constants_extract` (CLI), the real client at `COA_CLIENT_ROOT`, `WowConstantsRepository`.

- [ ] **Step 1: Write the `client`-marked acceptance test** (gates on structure/sanity; records deviations, never asserts stock equality)

```python
# tests/test_wow_constants_acceptance.py
import os
from pathlib import Path
import pytest
from coa_client_extract.cli import wow_constants_extract
from coa_meta.wow_constants import WowConstantsRepository

CLIENT_ROOT = Path(os.environ.get("COA_CLIENT_ROOT", "/nonexistent"))


@pytest.mark.client
@pytest.mark.skipif(not CLIENT_ROOT.is_dir(), reason="Ascension client not installed at COA_CLIENT_ROOT")
def test_real_client_snapshot_is_structurally_sound(tmp_path):
    out = tmp_path / "out"
    manifest = wow_constants_extract(CLIENT_ROOT, out)
    repo = WowConstantsRepository.load(out / "coa_wow_constants.json")
    # structure/sanity gates (never a stock-equality gate)
    assert manifest["class_context_resolution"] in ("unproven", "actor_wow_class_id", "versioned_bridge")
    # a proven-required, context-free lookup resolves
    assert repo.combat_rating_ratio(10, 60) > 0
    # deviations are recorded, not fatal
    import json
    snap = json.loads((out / "coa_wow_constants.json").read_text())
    rc = snap["game_tables"]["combat_ratings"]["reference_comparison"]
    assert rc["scope"] == "anchors" and rc["status"] in (
        "matches_on_checked_anchors", "differs_on_checked_anchors", "no_anchors_checked")
```

- [ ] **Step 2: Run the default suite (client tier deselected) and confirm green**

Run: `pytest tests/test_wow_constants_*.py -v`
Expected: PASS for all default-tier tests; `test_wow_constants_acceptance.py` deselected by `-m 'not stormlib and not client'` (the repo default `addopts`).

- [ ] **Step 3: Run the full package suite to confirm no regressions**

Run: `pytest -q`
Expected: PASS (existing suite + the new M1.14D default-tier tests); env-gated tiers deselected.

- [ ] **Step 4: Commit**

```bash
git add tests/test_wow_constants_acceptance.py
git commit -m "M1.14D Task 13: client-tier acceptance (structure/sanity gate) + full-suite green"
```

---

## Self-Review

**1. Spec coverage** — every design section maps to a task:
- Class-axis viability gate → Tasks 4 (axis), 10 (native-namespace reader rejecting CoA ids), manifest `class_context_resolution` (Tasks 8–9).
- Reconnaissance-first + reference indexing contract → Tasks 3, 5, 6 (hard hold point).
- GameTable layout + float reader → Tasks 1, 3.
- Tiered scope (proven-required / recon-gated / deferred / excluded) → Task 2 policy + Task 9 (`semantics=="unproven"` not emitted) + Task 6 (flip after recon).
- Enum maps versioned/hashed → Tasks 2, 8.
- Single JSON snapshot + manifest-last + hashed authored inputs → Tasks 7, 8.
- Verification-labelled rules (energy/rage/RP/focus/GCD floor+standard-base) → Task 2.
- Thin reader, no computation → Task 10.
- Testing (synthetic/`stormlib`/`client`; 60/80 oracle; monotonicity; NaN/Inf; missing-vs-zero; sparse class 10; +1 offset; native-namespace enforcement; hash-change) → Tasks 1–5, 8, 10, 11, 13.
- Redistribution boundary + policy gate → Task 12.

**2. Placeholder scan** — no "TBD/TODO/handle edge cases"; every code step shows complete code; Task 6 is intentionally a manual checkpoint with concrete adjudication steps.

**3. Type consistency** — `GameTable`/`parse_gametable` (Task 1) consumed unchanged in 3/5/9/11; `GameTableLayout`/`load_axis_policy`/`map_table_entries` signatures identical across 3/5/9; `AuthoredInput` fields (`name`/`version`/`sha256`/`payload`) identical across 2/8/9; `build_class_axis`/`class_roster` identical across 4/5/9; `WowConstantsRepository.from_dict`/`load` + method signatures identical across 10/11/13.

> **Note for the executor:** Task 6 is a hard hold point requiring the real Ascension client + StormLib. Tasks 1–5 build the recon tool and can complete without the client; Tasks 7–9 and 13's real run must not be trusted until Task 6 freezes the authored data against observed reality. If the client is unavailable in this environment, complete Tasks 1–5, then surface Task 6 to the maintainer before continuing.
