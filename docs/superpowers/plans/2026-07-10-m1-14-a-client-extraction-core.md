# M1.14A Client Extraction Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `coa_client_extract` — the Python module that reads the local Ascension CoA client's MPQ→DBC files and loose `Data/Content/*.json` tier into versioned, provenanced artifacts (`coa-client-spell-v1`, `coa-client-content-v1`, `coa-client-archive-plan-v1`, and an extraction manifest).

**Architecture:** All extraction reads through a project-owned `ArchiveBackend` protocol. StormLib sits behind it via a narrow `stormlib_ctypes` surface wrapped by `stormlib_backend`; no raw C handle escapes the ctypes module. CoA Codex owns archive policy (an auditable `ArchivePlan`); StormLib applies patches. A header-driven WDBC reader detects schema drift. The default test suite runs entirely against a fake in-memory backend and synthetic fixtures; StormLib and the real client are only needed for marked integration/acceptance tiers. When StormLib is unavailable the regenerate command fails closed.

**Tech Stack:** Python 3.11+, standard library only (`ctypes`, `struct`, `hashlib`, `json`, `dataclasses`, `pathlib`), pytest. StormLib is an extraction-time-only native dependency (like Playwright for the scraper) and is never imported by `coa_meta`.

## Global Constraints

- **Spec:** [M1.14A Client Extraction Core](../specs/2026-07-10-m1-14-a-client-extraction-core-design.md). Umbrella: [M1.14](../specs/2026-07-06-m1-14-client-dbc-data-foundation-design.md). Decision 20 in `docs/DECISIONS.md`.
- **Package name:** `coa_client_extract` (sibling to `coa_meta`). Add it to `pyproject.toml` `[tool.setuptools] packages`.
- **Runtime deps stay empty.** Do not add anything to `pyproject.toml` `dependencies`. StormLib is documented, not declared.
- **No raw StormLib handle may escape `stormlib_ctypes.py`.** Only `stormlib_ctypes.py` imports `ctypes` or names StormLib symbols.
- **Fail closed.** The regenerate command writes **no** artifacts when the backend is unavailable; it never silently degrades to a lower-fidelity backend for canonical output.
- **Committed fixtures are synthetic/self-authored only** — never client asset bytes (redistribution boundary).
- **Client root (for local acceptance only):** `~/Games/ascension-wow/drive_c/Program Files/Ascension Launcher/resources/ascension-live/Data`.
- **Acid-test spell:** `805775` must resolve to current *Adrenal Venom* mechanical data, not stale *Fang Venom: Lifeblood*.
- **Test tiers:** default (no markers) must never need StormLib or the client. Native-integration tests are marked `@pytest.mark.stormlib`; local-client tests are marked `@pytest.mark.client`. The default `pytest` run excludes both.
- **Artifact `schema_version` strings (verbatim):** `coa-client-spell-v1`, `coa-client-content-v1`, `coa-client-archive-plan-v1`, `coa-client-extract-manifest-v1`. `wrapper_version`: `coa-stormlib-v1`.
- **Attribution is deferred to M1.14B.** Every emitted record carries `coa_attribution.status == "unknown"`; A assigns no confidence.

---

### Task 1: Package scaffold, error hierarchy, and pytest tiers

**Files:**
- Create: `coa_client_extract/__init__.py`
- Create: `coa_client_extract/errors.py`
- Modify: `pyproject.toml` (add package + pytest marker config)
- Test: `tests/test_client_extract_errors.py`

**Interfaces:**
- Produces: `ExtractError`, `BackendUnavailable(ExtractError)`, `ArchiveError(ExtractError)`, `DbcDriftError(ExtractError)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_extract_errors.py
import pytest

from coa_client_extract.errors import (
    ArchiveError,
    BackendUnavailable,
    DbcDriftError,
    ExtractError,
)


def test_error_hierarchy():
    for cls in (BackendUnavailable, ArchiveError, DbcDriftError):
        assert issubclass(cls, ExtractError)


def test_errors_carry_message():
    err = DbcDriftError("Spell.dbc: field_count 300 != expected 234")
    assert "expected 234" in str(err)


@pytest.mark.stormlib
def test_stormlib_marker_is_registered():
    # Presence of this test proves the marker is registered without error.
    assert True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_errors.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'coa_client_extract'`.

- [ ] **Step 3: Create the package and error hierarchy**

```python
# coa_client_extract/__init__.py
"""Extraction-time-only client capture module (MPQ/DBC/loose JSON → artifacts)."""
```

```python
# coa_client_extract/errors.py
from __future__ import annotations


class ExtractError(Exception):
    """Base class for all client-extraction failures."""


class BackendUnavailable(ExtractError):
    """The archive backend (e.g. StormLib) could not be loaded/opened."""


class ArchiveError(ExtractError):
    """An archive or logical file could not be resolved through the plan."""


class DbcDriftError(ExtractError):
    """A DBC header disagreed with its declared layout beyond tolerance."""
```

- [ ] **Step 4: Register the package and pytest tiers in `pyproject.toml`**

Add `coa_client_extract` to the packages list:

```toml
[tool.setuptools]
packages = ["coa_meta", "coa_meta.combat", "coa_client_extract"]
```

Append a pytest config section (the repo currently has none, so create it):

```toml
[tool.pytest.ini_options]
addopts = "-m 'not stormlib and not client'"
markers = [
  "stormlib: requires a built/installed StormLib shared library (native integration tier)",
  "client: requires the local Ascension client install (acceptance tier)",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_errors.py -q`
Expected: PASS for the two hierarchy tests; the `stormlib`-marked test is **deselected** by `addopts`.

Run: `python -m pytest tests/test_client_extract_errors.py -m stormlib -q`
Expected: PASS (marker resolves, 1 selected).

- [ ] **Step 6: Commit**

```bash
git add coa_client_extract/__init__.py coa_client_extract/errors.py pyproject.toml tests/test_client_extract_errors.py
git commit -m "M1.14A: scaffold coa_client_extract with error hierarchy and pytest tiers"
```

---

### Task 2: ArchiveBackend protocol, ExtractedMember, and FakeArchiveBackend

**Files:**
- Create: `coa_client_extract/archive_backend.py`
- Test: `tests/test_client_extract_backend.py`

**Interfaces:**
- Consumes: `ArchiveError` (Task 1).
- Produces:
  - `ExtractedMember` (frozen dataclass): `logical_path: str`, `data: bytes`, `base_archive: Path`, `patch_chain: tuple[Path, ...]`, `effective_archive: Path`, `backend_name: str`, `backend_version: str`.
  - `ArchiveBackend` Protocol: `read_effective_file(base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str) -> ExtractedMember`; `has_file(base_archive, patch_archives, logical_path) -> bool`.
  - `FakeArchiveBackend(entries: dict[str, list[tuple[Path, bytes | None]]])` — an in-memory backend for tests. Each logical path maps to load-ordered `(archive, bytes-or-None)` entries; `None` is a deletion marker.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_extract_backend.py
from pathlib import Path

import pytest

from coa_client_extract.archive_backend import ExtractedMember, FakeArchiveBackend
from coa_client_extract.errors import ArchiveError

BASE = Path("common.MPQ")
P1 = Path("patch.MPQ")
PC = Path("patch-C.MPQ")


def _backend():
    return FakeArchiveBackend(
        {
            "DBFilesClient\\Spell.dbc": [
                (BASE, b"base-bytes"),
                (PC, b"coa-bytes"),
            ],
            "DBFilesClient\\Deleted.dbc": [
                (BASE, b"present"),
                (PC, None),  # deletion marker
            ],
        }
    )


def test_effective_file_wins_from_latest_patch():
    member = _backend().read_effective_file(BASE, (P1, PC), "DBFilesClient\\Spell.dbc")
    assert isinstance(member, ExtractedMember)
    assert member.data == b"coa-bytes"
    assert member.effective_archive == PC
    assert member.patch_chain == (BASE, PC)
    assert member.base_archive == BASE
    assert member.backend_name == "fake"


def test_deletion_marker_raises_archive_error():
    with pytest.raises(ArchiveError):
        _backend().read_effective_file(BASE, (P1, PC), "DBFilesClient\\Deleted.dbc")


def test_has_file_reflects_deletion():
    backend = _backend()
    assert backend.has_file(BASE, (P1, PC), "DBFilesClient\\Spell.dbc") is True
    assert backend.has_file(BASE, (P1, PC), "DBFilesClient\\Deleted.dbc") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_backend.py -q`
Expected: FAIL with `ModuleNotFoundError` / attribute errors.

- [ ] **Step 3: Implement the backend boundary**

```python
# coa_client_extract/archive_backend.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .errors import ArchiveError


@dataclass(frozen=True)
class ExtractedMember:
    logical_path: str
    data: bytes
    base_archive: Path
    patch_chain: tuple[Path, ...]
    effective_archive: Path
    backend_name: str
    backend_version: str


@runtime_checkable
class ArchiveBackend(Protocol):
    def read_effective_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> ExtractedMember: ...

    def has_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> bool: ...


class FakeArchiveBackend:
    """In-memory ArchiveBackend for tests. No native dependency."""

    name = "fake"
    version = "fake-v1"

    def __init__(self, entries: dict[str, list[tuple[Path, bytes | None]]]):
        self._entries = entries

    def _resolve(self, logical_path: str):
        history = self._entries.get(logical_path, [])
        chain: list[Path] = []
        winner: tuple[Path, bytes | None] | None = None
        for archive, payload in history:
            chain.append(archive)
            winner = (archive, payload)
        return chain, winner

    def read_effective_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> ExtractedMember:
        chain, winner = self._resolve(logical_path)
        if winner is None or winner[1] is None:
            raise ArchiveError(f"{logical_path}: not present in effective archive set")
        return ExtractedMember(
            logical_path=logical_path,
            data=winner[1],
            base_archive=base_archive,
            patch_chain=tuple(chain),
            effective_archive=winner[0],
            backend_name=self.name,
            backend_version=self.version,
        )

    def has_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> bool:
        _, winner = self._resolve(logical_path)
        return winner is not None and winner[1] is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_backend.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/archive_backend.py tests/test_client_extract_backend.py
git commit -m "M1.14A: add ArchiveBackend protocol, ExtractedMember, and fake backend"
```

---

### Task 3: Header-driven WDBC reader with drift detection

**Files:**
- Create: `coa_client_extract/wdbc.py`
- Create: `coa_client_extract/dbc_layouts.py`
- Test: `tests/test_client_extract_wdbc.py`

**Interfaces:**
- Consumes: `DbcDriftError` (Task 1).
- Produces:
  - `FieldSpec(index: int, kind: str)` where `kind in {"int32","uint32","float","str"}`.
  - `DbcLayout(name: str, expected_field_count: int, expected_record_size: int, columns: dict[str, FieldSpec])`.
  - `DbcTable(layout_name: str, field_count: int, record_size: int, record_count: int, rows: list[dict], drift: bool)`.
  - `parse_dbc(data: bytes, layout: DbcLayout, *, strict: bool = False) -> DbcTable`.
  - `dbc_layouts.SPELL_FAMILY: dict[str, DbcLayout]` with keys `Spell`, `SpellCastTimes`, `SpellDuration`, `SpellRange`.

**Note on real 3.3.5a indices:** The column indices in `dbc_layouts.py` are the stock 3.3.5a offsets. Ascension may shift or extend them, which is exactly what drift detection surfaces. The **acceptance test in Task 10 (spell 805775)** is the validation gate for these indices against the real client; adjust them there if the header shows drift. All unit tests below use **synthetic** layouts and are fully independent of the real numbers.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_extract_wdbc.py
import struct

import pytest

from coa_client_extract.errors import DbcDriftError
from coa_client_extract.wdbc import DbcLayout, FieldSpec, parse_dbc


def _build_dbc(rows, field_count, record_size, strings=b"\x00"):
    # rows: list of tuples of 4-byte-packable cells already encoded as bytes
    record_count = len(rows)
    header = struct.pack(
        "<4sIIII", b"WDBC", record_count, field_count, record_size, len(strings)
    )
    body = b"".join(rows)
    return header + body + strings


def _layout():
    return DbcLayout(
        name="Toy",
        expected_field_count=3,
        expected_record_size=12,
        columns={
            "id": FieldSpec(0, "uint32"),
            "name": FieldSpec(1, "str"),
            "value": FieldSpec(2, "int32"),
        },
    )


def test_parses_records_and_strings():
    strings = b"\x00Adrenal Venom\x00"
    name_offset = 1  # position of "Adrenal Venom" within the string block
    row = struct.pack("<IiI", 805775, name_offset, -5)
    data = _build_dbc([row], field_count=3, record_size=12, strings=strings)

    table = parse_dbc(data, _layout())

    assert table.record_count == 1
    assert table.drift is False
    assert table.rows[0] == {"id": 805775, "name": "Adrenal Venom", "value": -5}


def test_drift_flagged_when_header_field_count_differs():
    row = struct.pack("<IiI", 1, 0, 0)
    # header claims 4 fields / 16 bytes but layout expects 3 / 12
    data = _build_dbc([row + b"\x00\x00\x00\x00"], field_count=4, record_size=16)

    table = parse_dbc(data, _layout())
    assert table.drift is True  # tolerant read still returns the columns of interest

    with pytest.raises(DbcDriftError):
        parse_dbc(data, _layout(), strict=True)


def test_truncated_file_raises():
    row = struct.pack("<IiI", 1, 0, 0)
    data = _build_dbc([row], field_count=3, record_size=12)[:-6]  # chop string block + tail
    with pytest.raises(DbcDriftError):
        parse_dbc(data, _layout())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_wdbc.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the WDBC reader**

```python
# coa_client_extract/wdbc.py
from __future__ import annotations

import struct
from dataclasses import dataclass

from .errors import DbcDriftError

_HEADER = struct.Struct("<4sIIII")  # magic, records, fields, record_size, string_block_size
_MAGIC = b"WDBC"
_CELL = 4  # 3.3.5a DBC cells are 4 bytes


@dataclass(frozen=True)
class FieldSpec:
    index: int
    kind: str  # "int32" | "uint32" | "float" | "str"


@dataclass(frozen=True)
class DbcLayout:
    name: str
    expected_field_count: int
    expected_record_size: int
    columns: dict[str, FieldSpec]


@dataclass(frozen=True)
class DbcTable:
    layout_name: str
    field_count: int
    record_size: int
    record_count: int
    rows: list[dict]
    drift: bool


def _read_cstr(block: bytes, offset: int) -> str:
    end = block.find(b"\x00", offset)
    if end < 0:
        end = len(block)
    return block[offset:end].decode("utf-8", errors="replace")


def parse_dbc(data: bytes, layout: DbcLayout, *, strict: bool = False) -> DbcTable:
    if len(data) < _HEADER.size:
        raise DbcDriftError(f"{layout.name}: file smaller than DBC header")
    magic, record_count, field_count, record_size, string_size = _HEADER.unpack_from(data, 0)
    if magic != _MAGIC:
        raise DbcDriftError(f"{layout.name}: bad magic {magic!r}, expected WDBC")

    drift = field_count != layout.expected_field_count or record_size != layout.expected_record_size
    if drift and strict:
        raise DbcDriftError(
            f"{layout.name}: field_count {field_count} / record_size {record_size} "
            f"!= expected {layout.expected_field_count} / {layout.expected_record_size}"
        )

    records_start = _HEADER.size
    string_start = records_start + record_count * record_size
    expected_len = string_start + string_size
    if len(data) < expected_len:
        raise DbcDriftError(
            f"{layout.name}: truncated ({len(data)} bytes, expected >= {expected_len})"
        )
    string_block = data[string_start:string_start + string_size]

    rows: list[dict] = []
    for i in range(record_count):
        base = records_start + i * record_size
        row: dict = {}
        for col, spec in layout.columns.items():
            off = base + spec.index * _CELL
            if off + _CELL > string_start:
                raise DbcDriftError(f"{layout.name}: column {col!r} index out of record bounds")
            if spec.kind == "str":
                (soff,) = struct.unpack_from("<I", data, off)
                row[col] = _read_cstr(string_block, soff)
            elif spec.kind == "float":
                (row[col],) = struct.unpack_from("<f", data, off)
            elif spec.kind == "uint32":
                (row[col],) = struct.unpack_from("<I", data, off)
            else:  # int32
                (row[col],) = struct.unpack_from("<i", data, off)
        rows.append(row)

    return DbcTable(layout.name, field_count, record_size, record_count, rows, drift)
```

- [ ] **Step 4: Declare the real spell-family layouts**

```python
# coa_client_extract/dbc_layouts.py
from __future__ import annotations

from .wdbc import DbcLayout, FieldSpec

# Stock WotLK 3.3.5a offsets. Ascension may shift/extend these; drift detection
# flags that, and the Task 10 acceptance test (spell 805775) validates/corrects them.
SPELL_FAMILY: dict[str, DbcLayout] = {
    "Spell": DbcLayout(
        name="Spell",
        expected_field_count=234,
        expected_record_size=234 * 4,
        columns={
            "id": FieldSpec(0, "uint32"),
            "category": FieldSpec(1, "uint32"),
            "school_mask": FieldSpec(139, "uint32"),
            "power_type": FieldSpec(110, "int32"),
            "casting_time_index": FieldSpec(28, "uint32"),
            "duration_index": FieldSpec(24, "uint32"),
            "range_index": FieldSpec(29, "uint32"),
            "spell_icon_id": FieldSpec(133, "uint32"),
            "name": FieldSpec(136, "str"),  # localized name, enUS column
        },
    ),
    "SpellCastTimes": DbcLayout(
        name="SpellCastTimes",
        expected_field_count=4,
        expected_record_size=4 * 4,
        columns={"id": FieldSpec(0, "uint32"), "base_ms": FieldSpec(1, "int32")},
    ),
    "SpellDuration": DbcLayout(
        name="SpellDuration",
        expected_field_count=4,
        expected_record_size=4 * 4,
        columns={"id": FieldSpec(0, "uint32"), "base_ms": FieldSpec(1, "int32")},
    ),
    "SpellRange": DbcLayout(
        name="SpellRange",
        expected_field_count=39,
        expected_record_size=39 * 4,
        columns={
            "id": FieldSpec(0, "uint32"),
            "min_yd": FieldSpec(1, "float"),
            "max_yd": FieldSpec(3, "float"),
        },
    ),
}


def test_layouts_are_self_consistent() -> bool:
    for layout in SPELL_FAMILY.values():
        assert layout.expected_record_size == layout.expected_field_count * 4
        assert all(spec.index < layout.expected_field_count for spec in layout.columns.values())
    return True
```

Add a test asserting layout self-consistency (append to `tests/test_client_extract_wdbc.py`):

```python
def test_real_spell_family_layouts_are_self_consistent():
    from coa_client_extract.dbc_layouts import SPELL_FAMILY

    for layout in SPELL_FAMILY.values():
        assert layout.expected_record_size == layout.expected_field_count * 4
        for spec in layout.columns.values():
            assert spec.index < layout.expected_field_count
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_wdbc.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add coa_client_extract/wdbc.py coa_client_extract/dbc_layouts.py tests/test_client_extract_wdbc.py
git commit -m "M1.14A: header-driven WDBC reader with drift detection and spell-family layouts"
```

---

### Task 4: Auditable archive plan (CoA owns ordering)

**Files:**
- Create: `coa_client_extract/archive_plan.py`
- Test: `tests/test_client_extract_archive_plan.py`

**Interfaces:**
- Consumes: `ArchiveBackend` (Task 2), `ArchiveError` (Task 1).
- Produces:
  - `ArchivePlan` (frozen dataclass): `client_root: Path`, `base_archives: tuple[Path, ...]`, `patch_archives: tuple[Path, ...]`, `excluded: dict[str, tuple[Path, ...]]`, `ordering_rule: str`.
  - `discover_plan(client_root: Path) -> ArchivePlan` — enumerates archives, filters families, orders them.
  - `ArchivePlan.to_dict() -> dict` — the `coa-client-archive-plan-v1` record.
  - `validate_ordering(plan: ArchivePlan, backend: ArchiveBackend, logical_path: str, expected_effective: Path) -> None` — raises `ArchiveError` if the plan does not resolve the given known-overridden file to the expected archive.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_extract_archive_plan.py
from pathlib import Path

import pytest

from coa_client_extract.archive_backend import FakeArchiveBackend
from coa_client_extract.archive_plan import ArchivePlan, discover_plan, validate_ordering
from coa_client_extract.errors import ArchiveError

FAMILY = [
    "common.MPQ", "common-2.MPQ", "expansion.MPQ", "lichking.MPQ",
    "patch.MPQ", "patch-2.MPQ", "patch-3.MPQ",
    "patch-A.MPQ", "patch-C.MPQ", "patch-CA.MPQ", "patch-CZZ.MPQ",
    "patch-WA.MPQ",
]


def _make_client(tmp_path: Path) -> Path:
    data = tmp_path / "Data"
    data.mkdir()
    for name in FAMILY:
        (data / name).write_bytes(b"MPQ\x1a")
    area = data / "area-52"
    area.mkdir()
    (area / "patch-D.MPQ").write_bytes(b"MPQ\x1a")
    return data


def test_discover_plan_partitions_families(tmp_path):
    plan = discover_plan(_make_client(tmp_path))
    names = {p.name for p in plan.patch_archives}
    assert "patch-C.MPQ" in names and "patch-CZZ.MPQ" in names
    assert "patch-WA.MPQ" not in names  # Reborn excluded
    assert all("patch-D.MPQ" != p.name for p in plan.patch_archives)  # Area-52 excluded
    assert {p.name for p in plan.base_archives} == {
        "common.MPQ", "common-2.MPQ", "expansion.MPQ", "lichking.MPQ"
    }
    assert "reborn" in plan.excluded and "area52" in plan.excluded


def test_patch_c_family_orders_after_numeric_patches(tmp_path):
    plan = discover_plan(_make_client(tmp_path))
    order = [p.name for p in plan.patch_archives]
    assert order.index("patch.MPQ") < order.index("patch-C.MPQ")
    assert order.index("patch-C.MPQ") < order.index("patch-CA.MPQ")
    assert order.index("patch-CA.MPQ") < order.index("patch-CZZ.MPQ")


def test_plan_to_dict_shape(tmp_path):
    plan = discover_plan(_make_client(tmp_path))
    doc = plan.to_dict()
    assert doc["schema_version"] == "coa-client-archive-plan-v1"
    assert doc["ordering_rule"] == "coa-archive-order-v1"
    assert isinstance(doc["patch_archives"], list)


def test_validate_ordering_detects_wrong_effective(tmp_path):
    plan = discover_plan(_make_client(tmp_path))
    backend = FakeArchiveBackend(
        {"DBFilesClient\\Spell.dbc": [(Path("common.MPQ"), b"a"), (Path("patch-CA.MPQ"), b"b")]}
    )
    validate_ordering(plan, backend, "DBFilesClient\\Spell.dbc", Path("patch-CA.MPQ"))
    with pytest.raises(ArchiveError):
        validate_ordering(plan, backend, "DBFilesClient\\Spell.dbc", Path("patch-C.MPQ"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_archive_plan.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the archive plan**

```python
# coa_client_extract/archive_plan.py
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .archive_backend import ArchiveBackend
from .errors import ArchiveError

ORDERING_RULE = "coa-archive-order-v1"
_BASE = ("common", "common-2", "expansion", "lichking")
_NUMERIC_PATCH = re.compile(r"^patch(-\d+)?$", re.IGNORECASE)
_COA_PATCH = re.compile(r"^patch-C[A-Z]*$", re.IGNORECASE)   # patch-C, patch-CA … patch-CZZ
_REBORN_PATCH = re.compile(r"^patch-W[A-Z]*$", re.IGNORECASE)  # Warcraft Reborn/Bronzebeard
_ANY_PATCH = re.compile(r"^patch(-[0-9A-Za-z]+)?$", re.IGNORECASE)


@dataclass(frozen=True)
class ArchivePlan:
    client_root: Path
    base_archives: tuple[Path, ...]
    patch_archives: tuple[Path, ...]
    excluded: dict[str, tuple[Path, ...]]
    ordering_rule: str = ORDERING_RULE

    def to_dict(self) -> dict:
        return {
            "schema_version": "coa-client-archive-plan-v1",
            "client_root": str(self.client_root),
            "ordering_rule": self.ordering_rule,
            "base_archives": [p.name for p in self.base_archives],
            "patch_archives": [p.name for p in self.patch_archives],
            "excluded": {k: [p.name for p in v] for k, v in self.excluded.items()},
        }


def _patch_sort_key(name: str) -> tuple:
    stem = name.rsplit(".", 1)[0]
    if _NUMERIC_PATCH.match(stem):
        # group 0: base patches — plain "patch" first, then patch-2, patch-3
        parts = stem.split("-")
        num = int(parts[1]) if len(parts) > 1 else 0
        return (0, num, "")
    if _COA_PATCH.match(stem):
        # group 2: CoA family loads last (highest priority) — C, CA, CB … CZ < CZZ
        letters = stem.split("-", 1)[1][1:]  # drop the leading 'C'
        return (2, len(letters), letters.upper())
    # group 1: other Ascension patches (patch-A, patch-B, patch-I, patch-M, …)
    suffix = stem.split("-", 1)[1] if "-" in stem else ""
    return (1, len(suffix), suffix.upper())


def discover_plan(client_root: Path) -> ArchivePlan:
    archives = sorted(p for p in client_root.glob("*.MPQ"))
    archives += sorted(p for p in client_root.glob("*.mpq"))
    by_name = {p.name.rsplit(".", 1)[0].lower(): p for p in archives}

    base = tuple(by_name[n] for n in _BASE if n in by_name)
    patches: list[Path] = []
    reborn: list[Path] = []
    for p in archives:
        stem = p.name.rsplit(".", 1)[0]
        if stem.lower() in _BASE:
            continue
        if _REBORN_PATCH.match(stem):
            reborn.append(p)  # Warcraft Reborn — excluded from the CoA chain
        elif _ANY_PATCH.match(stem):
            patches.append(p)  # base Ascension + CoA patches load together; attribution is M1.14B
    patches.sort(key=lambda p: _patch_sort_key(p.name))

    area52 = tuple(sorted((client_root / "area-52").glob("*.MPQ"))) if (client_root / "area-52").is_dir() else ()

    return ArchivePlan(
        client_root=client_root,
        base_archives=base,
        patch_archives=tuple(patches),
        excluded={"area52": area52, "reborn": tuple(reborn)},
    )


def validate_ordering(
    plan: ArchivePlan, backend: ArchiveBackend, logical_path: str, expected_effective: Path
) -> None:
    member = backend.read_effective_file(plan.base_archives[0], plan.patch_archives, logical_path)
    if member.effective_archive.name != expected_effective.name:
        raise ArchiveError(
            f"archive-plan ordering mismatch for {logical_path}: resolved "
            f"{member.effective_archive.name}, expected {expected_effective.name}"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_archive_plan.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/archive_plan.py tests/test_client_extract_archive_plan.py
git commit -m "M1.14A: auditable archive plan with family filtering and ordering validation"
```

---

### Task 5: Loose Content JSON reader

**Files:**
- Create: `coa_client_extract/content_json.py`
- Test: `tests/test_client_extract_content_json.py`
- Test fixtures: `tests/fixtures/client_content/SpellToRoleSuggestionData.json`, `tests/fixtures/client_content/SpellRankData.json`

**Interfaces:**
- Produces:
  - `read_content_records(content_dir: Path, *, files: dict[str, str] | None = None) -> list[dict]` returning `coa-client-content-v1` records. Default `files` maps filename → `content_kind`:
    - `SpellRankData.json` → `spell_rank`
    - `SpellToStatSuggestionData.json` → `spell_stat_suggestion`
    - `SpellToRoleSuggestionData.json` → `spell_role_suggestion`
    - `ItemVariationData.json` → `item_variation`
    - `CharacterAdvancementData.json` → `character_advancement` (marked `investigate`)
  - Each record: `{schema_version, content_kind, spell_id|item_id, values, provenance{source_file,file_sha256,extraction_date}, coa_attribution{status:"unknown"}}`.

- [ ] **Step 1: Create synthetic fixtures**

```json
// tests/fixtures/client_content/SpellToRoleSuggestionData.json
[{"DamageScore":220,"HealerScore":4,"Spell":78,"TankScore":69},
 {"DamageScore":449,"HealerScore":14,"Spell":100,"TankScore":288}]
```

```json
// tests/fixtures/client_content/SpellRankData.json
[{"Spell":805775,"Rank":1,"ScalingValue":1.0}]
```

(These are hand-authored, not client bytes.)

- [ ] **Step 2: Write the failing test**

```python
# tests/test_client_extract_content_json.py
from pathlib import Path

from coa_client_extract.content_json import read_content_records

FIXTURES = Path(__file__).parent / "fixtures" / "client_content"


def test_reads_role_suggestions_with_provenance():
    records = read_content_records(FIXTURES, files={"SpellToRoleSuggestionData.json": "spell_role_suggestion"})
    assert len(records) == 2
    first = records[0]
    assert first["schema_version"] == "coa-client-content-v1"
    assert first["content_kind"] == "spell_role_suggestion"
    assert first["spell_id"] == 78
    assert first["values"]["TankScore"] == 69
    assert first["provenance"]["source_file"] == "SpellToRoleSuggestionData.json"
    assert len(first["provenance"]["file_sha256"]) == 64
    assert first["coa_attribution"]["status"] == "unknown"


def test_missing_file_is_skipped_not_fatal():
    records = read_content_records(FIXTURES, files={"DoesNotExist.json": "whatever"})
    assert records == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_content_json.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement the reader**

```python
# coa_client_extract/content_json.py
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

DEFAULT_FILES: dict[str, str] = {
    "SpellRankData.json": "spell_rank",
    "SpellToStatSuggestionData.json": "spell_stat_suggestion",
    "SpellToRoleSuggestionData.json": "spell_role_suggestion",
    "ItemVariationData.json": "item_variation",
    "CharacterAdvancementData.json": "character_advancement",
}
_INVESTIGATE = {"character_advancement"}


def _id_fields(entry: dict) -> dict:
    out: dict = {}
    if "Spell" in entry:
        out["spell_id"] = entry["Spell"]
    if "Item" in entry:
        out["item_id"] = entry["Item"]
    return out


def read_content_records(content_dir: Path, *, files: dict[str, str] | None = None) -> list[dict]:
    files = files if files is not None else DEFAULT_FILES
    today = date.today().isoformat()
    records: list[dict] = []
    for filename, kind in files.items():
        path = content_dir / filename
        if not path.is_file():
            continue
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        payload = json.loads(raw.decode("utf-8"))
        entries = payload if isinstance(payload, list) else payload.get("data", [])
        for entry in entries:
            ids = _id_fields(entry)
            values = {k: v for k, v in entry.items() if k not in ("Spell", "Item")}
            record = {
                "schema_version": "coa-client-content-v1",
                "content_kind": kind,
                **ids,
                "values": values,
                "provenance": {
                    "source_file": filename,
                    "file_sha256": digest,
                    "extraction_date": today,
                },
                "coa_attribution": {"status": "unknown"},
            }
            if kind in _INVESTIGATE:
                record["coa_attribution"]["note"] = "investigate: may be classless/Area-52 system"
            records.append(record)
    return records
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_content_json.py -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add coa_client_extract/content_json.py tests/test_client_extract_content_json.py tests/fixtures/client_content/
git commit -m "M1.14A: loose Content JSON reader with per-file provenance"
```

---

### Task 6: Spell-record assembly, artifact + manifest writers, and schema docs

**Files:**
- Create: `coa_client_extract/artifacts.py`
- Create: `coa_client_extract/manifest.py`
- Create: `docs/data/client-spell-schema.md`
- Create: `docs/data/client-content-schema.md`
- Create: `docs/data/client-archive-plan-schema.md`
- Test: `tests/test_client_extract_artifacts.py`

**Interfaces:**
- Consumes: `DbcTable` (Task 3), `ExtractedMember`/`ArchiveBackend` (Task 2), `ArchivePlan` (Task 4).
- Produces:
  - `build_client_spell_records(spell: DbcTable, cast_times: DbcTable, durations: DbcTable, ranges: DbcTable, *, provenance: dict) -> list[dict]` — joins the spell family into `coa-client-spell-v1` records; `coa_attribution.status == "unknown"`.
  - `write_jsonl(records: list[dict], path: Path) -> str` (returns sha256).
  - `write_json(doc: dict, path: Path) -> str` (returns sha256).
  - `manifest.build_manifest(*, backend_name, backend_version, stormlib_version, client_root, client_build, outputs: dict[str, str], archive_plan: dict) -> dict` with `schema_version == "coa-client-extract-manifest-v1"`, `wrapper_version == "coa-stormlib-v1"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_extract_artifacts.py
import json
import struct
from pathlib import Path

from coa_client_extract.artifacts import build_client_spell_records, write_json, write_jsonl
from coa_client_extract.manifest import build_manifest
from coa_client_extract.wdbc import DbcLayout, FieldSpec, parse_dbc


def _dbc(rows, field_count, record_size, strings=b"\x00"):
    header = struct.pack("<4sIIII", b"WDBC", len(rows), field_count, record_size, len(strings))
    return header + b"".join(rows) + strings


def _spell_table():
    strings = b"\x00Adrenal Venom\x00"
    row = struct.pack("<IIII", 805775, 1, 3, 5)  # id, name_off, cast_idx, dur_idx
    layout = DbcLayout("Spell", 4, 16, {
        "id": FieldSpec(0, "uint32"),
        "name": FieldSpec(1, "str"),
        "casting_time_index": FieldSpec(2, "uint32"),
        "duration_index": FieldSpec(3, "uint32"),
    })
    return parse_dbc(_dbc([row], 4, 16, strings), layout)


def _index_table(idx, base_ms):
    row = struct.pack("<II", idx, base_ms)
    layout = DbcLayout("X", 2, 8, {"id": FieldSpec(0, "uint32"), "base_ms": FieldSpec(1, "int32")})
    return parse_dbc(_dbc([row], 2, 8), layout)


def test_build_spell_records_joins_family_and_defers_attribution():
    records = build_client_spell_records(
        _spell_table(), _index_table(3, 1500), _index_table(5, 18000), None,
        provenance={"effective_archive": "patch-CA.MPQ", "extraction_date": "2026-07-10"},
    )
    rec = records[0]
    assert rec["schema_version"] == "coa-client-spell-v1"
    assert rec["spell_id"] == 805775
    assert rec["name"] == "Adrenal Venom"
    assert rec["mechanics"]["cast_time_ms"] == 1500
    assert rec["mechanics"]["duration_ms"] == 18000
    assert rec["coa_attribution"]["status"] == "unknown"


def test_write_jsonl_returns_sha256(tmp_path):
    out = tmp_path / "spell.jsonl"
    digest = write_jsonl([{"a": 1}, {"b": 2}], out)
    assert len(digest) == 64
    lines = out.read_text().strip().splitlines()
    assert json.loads(lines[0]) == {"a": 1}


def test_manifest_shape(tmp_path):
    doc = build_manifest(
        backend_name="fake", backend_version="fake-v1", stormlib_version=None,
        client_root="/x", client_build="unknown",
        outputs={"coa_client_spell.jsonl": "deadbeef"}, archive_plan={"schema_version": "coa-client-archive-plan-v1"},
    )
    assert doc["schema_version"] == "coa-client-extract-manifest-v1"
    assert doc["wrapper_version"] == "coa-stormlib-v1"
    assert doc["outputs"]["coa_client_spell.jsonl"] == "deadbeef"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_artifacts.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement artifacts and manifest**

```python
# coa_client_extract/artifacts.py
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .wdbc import DbcTable


def _index_lookup(table: DbcTable | None, value_key: str) -> dict[int, int]:
    if table is None:
        return {}
    return {row["id"]: row[value_key] for row in table.rows}


def build_client_spell_records(
    spell: DbcTable,
    cast_times: DbcTable | None,
    durations: DbcTable | None,
    ranges: DbcTable | None,
    *,
    provenance: dict,
) -> list[dict]:
    cast_by_idx = _index_lookup(cast_times, "base_ms")
    dur_by_idx = _index_lookup(durations, "base_ms")
    range_max = {row["id"]: row.get("max_yd") for row in ranges.rows} if ranges else {}
    range_min = {row["id"]: row.get("min_yd") for row in ranges.rows} if ranges else {}

    records: list[dict] = []
    for row in spell.rows:
        mechanics = {
            "school_mask": row.get("school_mask"),
            "power_type": row.get("power_type"),
            "cast_time_ms": cast_by_idx.get(row.get("casting_time_index")),
            "duration_ms": dur_by_idx.get(row.get("duration_index")),
            "range_min_yd": range_min.get(row.get("range_index")),
            "range_max_yd": range_max.get(row.get("range_index")),
            "category": row.get("category"),
            "spell_icon_id": row.get("spell_icon_id"),
        }
        records.append({
            "schema_version": "coa-client-spell-v1",
            "spell_id": row["id"],
            "name": row.get("name", ""),
            "mechanics": mechanics,
            "provenance": {
                **provenance,
                "schema_match_confidence": "low" if spell.drift else "high",
            },
            "coa_attribution": {"status": "unknown"},
        })
    return records


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_jsonl(records: list[dict], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records)
    data = payload.encode("utf-8")
    path.write_bytes(data)
    return _sha256_bytes(data)


def write_json(doc: dict, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(data)
    return _sha256_bytes(data)
```

```python
# coa_client_extract/manifest.py
from __future__ import annotations

from datetime import date


def build_manifest(
    *,
    backend_name: str,
    backend_version: str,
    stormlib_version: str | None,
    client_root: str,
    client_build: str,
    outputs: dict[str, str],
    archive_plan: dict,
) -> dict:
    return {
        "schema_version": "coa-client-extract-manifest-v1",
        "wrapper_version": "coa-stormlib-v1",
        "backend": backend_name,
        "backend_version": backend_version,
        "stormlib_version": stormlib_version,
        "client_root": client_root,
        "client_build": client_build,
        "extraction_date": date.today().isoformat(),
        "archive_plan": archive_plan,
        "outputs": outputs,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_artifacts.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Write the schema docs**

Create `docs/data/client-spell-schema.md`:

```markdown
# Client Spell Schema

Records use schema version `coa-client-spell-v1`, produced by `coa_client_extract` (M1.14A) from the
CoA client's MPQ→DBC spell family. Attribution is deferred to M1.14B (`coa_attribution.status`
is `unknown` until then); reconciliation into `coa-mechanics-v1` is M1.14C.

## Required Fields
- `schema_version`: always `coa-client-spell-v1`
- `spell_id`: DBC spell id
- `name`: localized spell name from `Spell.dbc`
- `mechanics`: object with `school_mask`, `power_type`, `cast_time_ms`, `duration_ms`,
  `range_min_yd`, `range_max_yd`, `category`, `spell_icon_id` (any may be null when the source row is
  absent)
- `provenance`: `base_archive`, `patch_chain`, `effective_archive`, `source_dbcs`,
  `schema_match_confidence` (`high`|`low`), `extraction_date`
- `coa_attribution`: `status` (`unknown` in M1.14A), plus raw signals (`archive_family`, `id_range`)

## Consumer Rules
- `schema_match_confidence: "low"` means DBC drift was detected for a contributing table; downstream
  consumers must not treat those mechanical fields as high-confidence.
- Fields may be null; consumers tolerate partial records.
```

Create `docs/data/client-content-schema.md`:

```markdown
# Client Content Schema

Records use schema version `coa-client-content-v1`, produced by `coa_client_extract` (M1.14A) from the
loose `Data/Content/*.json` tier.

## Required Fields
- `schema_version`: always `coa-client-content-v1`
- `content_kind`: `spell_rank` | `spell_stat_suggestion` | `spell_role_suggestion` |
  `item_variation` | `character_advancement`
- `spell_id` and/or `item_id`: whichever the source entry keys on
- `values`: the remaining source fields verbatim
- `provenance`: `source_file`, `file_sha256`, `extraction_date`
- `coa_attribution`: `status` (`unknown` in M1.14A); `character_advancement` carries an `investigate`
  note pending attribution.
```

Create `docs/data/client-archive-plan-schema.md`:

```markdown
# Client Archive Plan Schema

The archive plan (`coa-client-archive-plan-v1`) records how `coa_client_extract` (M1.14A) partitions
and orders the client's MPQ archives. CoA Codex owns this policy; StormLib only applies patches.

## Fields
- `schema_version`: always `coa-client-archive-plan-v1`
- `client_root`: absolute path to the client `Data/` directory
- `ordering_rule`: `coa-archive-order-v1`
- `base_archives`: ordered base archive filenames (`common`, `common-2`, `expansion`, `lichking`)
- `patch_archives`: ordered patch filenames (numeric patches, then the `patch-C*` CoA family)
- `excluded`: `{area52: [...], reborn: [...]}` — archives deliberately not loaded

The ordering is validated against a known-overridden file before it is treated as canonical.
```

- [ ] **Step 6: Commit**

```bash
git add coa_client_extract/artifacts.py coa_client_extract/manifest.py docs/data/client-spell-schema.md docs/data/client-content-schema.md docs/data/client-archive-plan-schema.md tests/test_client_extract_artifacts.py
git commit -m "M1.14A: spell-record assembly, artifact/manifest writers, and schema docs"
```

---

### Task 7: Narrow StormLib ctypes surface and backend

**Files:**
- Create: `coa_client_extract/stormlib_ctypes.py`
- Create: `coa_client_extract/stormlib_backend.py`
- Test: `tests/test_client_extract_stormlib_backend.py`

**Interfaces:**
- Consumes: `ArchiveBackend`/`ExtractedMember` (Task 2), `BackendUnavailable`/`ArchiveError` (Task 1).
- Produces:
  - `stormlib_ctypes.load_stormlib(explicit_path: str | None = None) -> ctypes.CDLL` — discovery order: explicit path → `STORMLIB_PATH` env → `ctypes.util.find_library("storm")` → documented common names; raises `BackendUnavailable` if none load.
  - `stormlib_ctypes.STORMLIB_FUNCTIONS` (the minimal symbol set) and context managers `open_archive(...)`, `open_file(...)`.
  - `stormlib_backend.StormLibBackend(stormlib_path: str | None = None)` implementing `ArchiveBackend`; `name == "stormlib_ctypes"`, `version == "coa-stormlib-v1"`.

**Note:** The unit test here must NOT require a real StormLib. It only asserts the fail-closed discovery path. Real reads are exercised in Task 9 (`@pytest.mark.stormlib`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_extract_stormlib_backend.py
import pytest

from coa_client_extract.errors import BackendUnavailable
from coa_client_extract.stormlib_ctypes import load_stormlib
from coa_client_extract.stormlib_backend import StormLibBackend


def test_load_stormlib_raises_backend_unavailable_for_bad_path():
    with pytest.raises(BackendUnavailable):
        load_stormlib("/nonexistent/libstorm.so.999")


def test_backend_construction_fails_closed_without_library():
    with pytest.raises(BackendUnavailable):
        StormLibBackend(stormlib_path="/nonexistent/libstorm.so.999")


def test_backend_identity_constants():
    assert StormLibBackend.name == "stormlib_ctypes"
    assert StormLibBackend.version == "coa-stormlib-v1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_stormlib_backend.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the narrow ctypes surface**

```python
# coa_client_extract/stormlib_ctypes.py
from __future__ import annotations

import ctypes
import ctypes.util
import os
from contextlib import contextmanager

from .errors import ArchiveError, BackendUnavailable

_CANDIDATES = ("storm", "libstorm.so", "libstorm.so.9", "libStorm.dylib", "StormLib.dll")


def load_stormlib(explicit_path: str | None = None) -> ctypes.CDLL:
    tried: list[str] = []
    ordered: list[str] = []
    if explicit_path:
        ordered.append(explicit_path)
    if os.environ.get("STORMLIB_PATH"):
        ordered.append(os.environ["STORMLIB_PATH"])
    found = ctypes.util.find_library("storm")
    if found:
        ordered.append(found)
    ordered.extend(_CANDIDATES)
    for name in ordered:
        try:
            lib = ctypes.CDLL(name)
        except OSError:
            tried.append(name)
            continue
        _bind(lib)
        return lib
    raise BackendUnavailable(
        "StormLib shared library not found. Install StormLib (MIT) or pass --stormlib PATH / "
        f"set STORMLIB_PATH. Tried: {', '.join(tried)}"
    )


def _bind(lib: ctypes.CDLL) -> None:
    b = ctypes.c_bool
    h = ctypes.c_void_p
    dw = ctypes.c_uint32
    lib.SFileOpenArchive.argtypes = [ctypes.c_char_p, dw, dw, ctypes.POINTER(h)]
    lib.SFileOpenArchive.restype = b
    lib.SFileOpenPatchArchive.argtypes = [h, ctypes.c_char_p, ctypes.c_char_p, dw]
    lib.SFileOpenPatchArchive.restype = b
    lib.SFileHasFile.argtypes = [h, ctypes.c_char_p]
    lib.SFileHasFile.restype = b
    lib.SFileOpenFileEx.argtypes = [h, ctypes.c_char_p, dw, ctypes.POINTER(h)]
    lib.SFileOpenFileEx.restype = b
    lib.SFileGetFileSize.argtypes = [h, ctypes.POINTER(dw)]
    lib.SFileGetFileSize.restype = dw
    lib.SFileReadFile.argtypes = [h, ctypes.c_void_p, dw, ctypes.POINTER(dw), ctypes.c_void_p]
    lib.SFileReadFile.restype = b
    lib.SFileCloseFile.argtypes = [h]
    lib.SFileCloseFile.restype = b
    lib.SFileCloseArchive.argtypes = [h]
    lib.SFileCloseArchive.restype = b


@contextmanager
def open_archive(lib: ctypes.CDLL, path: str):
    handle = ctypes.c_void_p()
    if not lib.SFileOpenArchive(path.encode("utf-8"), 0, 0x00000100, ctypes.byref(handle)):
        raise ArchiveError(f"SFileOpenArchive failed for {path} (err {ctypes.get_errno()})")
    try:
        yield handle
    finally:
        lib.SFileCloseArchive(handle)


@contextmanager
def open_file(lib: ctypes.CDLL, archive: ctypes.c_void_p, logical_path: str):
    fh = ctypes.c_void_p()
    if not lib.SFileOpenFileEx(archive, logical_path.encode("utf-8"), 0, ctypes.byref(fh)):
        raise ArchiveError(f"SFileOpenFileEx failed for {logical_path}")
    try:
        yield fh
    finally:
        lib.SFileCloseFile(fh)


def read_all(lib: ctypes.CDLL, file_handle: ctypes.c_void_p) -> bytes:
    size = ctypes.c_uint32(0)
    lib.SFileGetFileSize(file_handle, ctypes.byref(size))
    buffer = ctypes.create_string_buffer(size.value)
    read = ctypes.c_uint32(0)
    if not lib.SFileReadFile(file_handle, buffer, size.value, ctypes.byref(read), None):
        # SFileReadFile returns false at EOF even on success; accept when all bytes read
        if read.value != size.value:
            raise ArchiveError("SFileReadFile short read")
    return buffer.raw[: read.value or size.value]
```

- [ ] **Step 4: Implement the backend over the ctypes surface**

```python
# coa_client_extract/stormlib_backend.py
from __future__ import annotations

from pathlib import Path

from .archive_backend import ExtractedMember
from .errors import ArchiveError
from . import stormlib_ctypes as sl


class StormLibBackend:
    name = "stormlib_ctypes"
    version = "coa-stormlib-v1"

    def __init__(self, stormlib_path: str | None = None):
        # Raises BackendUnavailable (fail closed) if the library cannot be loaded.
        self._lib = sl.load_stormlib(stormlib_path)

    def _open_chain(self, base_archive: Path, patch_archives: tuple[Path, ...]):
        cm = sl.open_archive(self._lib, str(base_archive))
        handle = cm.__enter__()
        for patch in patch_archives:
            if not self._lib.SFileOpenPatchArchive(handle, str(patch).encode("utf-8"), b"", 0):
                # A patch that does not apply to this base is skipped by StormLib returning false;
                # only raise if none applied and the file is later missing.
                continue
        return cm, handle

    def read_effective_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> ExtractedMember:
        cm, handle = self._open_chain(base_archive, patch_archives)
        try:
            if not self._lib.SFileHasFile(handle, logical_path.encode("utf-8")):
                raise ArchiveError(f"{logical_path}: not found in patched archive chain")
            with sl.open_file(self._lib, handle, logical_path) as fh:
                data = sl.read_all(self._lib, fh)
            # Provenance: StormLib resolves the effective bytes across the attached chain.
            # The full participating chain is the attached patch set plus the base.
            chain = (base_archive, *patch_archives)
            return ExtractedMember(
                logical_path=logical_path,
                data=data,
                base_archive=base_archive,
                patch_chain=chain,
                effective_archive=patch_archives[-1] if patch_archives else base_archive,
                backend_name=self.name,
                backend_version=self.version,
            )
        finally:
            cm.__exit__(None, None, None)

    def has_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> bool:
        cm, handle = self._open_chain(base_archive, patch_archives)
        try:
            return bool(self._lib.SFileHasFile(handle, logical_path.encode("utf-8")))
        finally:
            cm.__exit__(None, None, None)
```

**Refinement deferred to Task 9:** precise per-file `effective_archive` via `SFileGetFileInfo(SFileInfoPatchChain)` is validated against real archives in the integration test; if the returned chain differs from the attached order, Task 9 tightens `effective_archive`/`patch_chain` to the reported chain.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_stormlib_backend.py -q`
Expected: PASS (3 tests) — all exercise the fail-closed path without a real library.

- [ ] **Step 6: Commit**

```bash
git add coa_client_extract/stormlib_ctypes.py coa_client_extract/stormlib_backend.py tests/test_client_extract_stormlib_backend.py
git commit -m "M1.14A: narrow StormLib ctypes surface and fail-closed backend"
```

---

### Task 8: CLI regenerate command (fail closed)

**Files:**
- Create: `coa_client_extract/cli.py`
- Create: `coa_client_extract/__main__.py`
- Test: `tests/test_client_extract_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `cli.regenerate(client_root: Path, out_dir: Path, *, backend: ArchiveBackend | None = None, stormlib_path: str | None = None) -> dict` — orchestrates plan → backend → DBC parse → assembly → artifacts → manifest; returns the manifest. Injecting `backend` (used by tests) bypasses StormLib; when `backend is None` it constructs `StormLibBackend` and **fails closed** on `BackendUnavailable`.
  - `cli.main(argv: list[str] | None = None) -> int` — argparse front end; prints the `BackendUnavailable` message to stderr and returns exit code `2` without writing artifacts.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_extract_cli.py
import json
from pathlib import Path

from coa_client_extract.archive_backend import FakeArchiveBackend
from coa_client_extract.cli import main, regenerate


def _client(tmp_path: Path) -> Path:
    data = tmp_path / "Data"
    data.mkdir()
    for name in ("common.MPQ", "patch.MPQ", "patch-C.MPQ"):
        (data / name).write_bytes(b"MPQ\x1a")
    (data / "Content").mkdir()
    (data / "Content" / "SpellRankData.json").write_text('[{"Spell":805775,"Rank":1}]')
    return data


def _fake_backend():
    import struct
    strings = b"\x00Adrenal Venom\x00"
    spell = struct.pack("<IIII", 805775, 1, 3, 5)
    cast = struct.pack("<II", 3, 1500)
    dur = struct.pack("<II", 5, 18000)

    def dbc(rows, fc, rs, s=b"\x00"):
        return struct.pack("<4sIIII", b"WDBC", len(rows), fc, rs, len(s)) + b"".join(rows) + s

    from coa_client_extract import dbc_layouts  # noqa: F401 (ensure importable)
    entries = {
        "DBFilesClient\\Spell.dbc": [(Path("common.MPQ"), dbc([spell], 4, 16, strings))],
        "DBFilesClient\\SpellCastTimes.dbc": [(Path("common.MPQ"), dbc([cast], 2, 8))],
        "DBFilesClient\\SpellDuration.dbc": [(Path("common.MPQ"), dbc([dur], 2, 8))],
        "DBFilesClient\\SpellRange.dbc": [(Path("common.MPQ"), dbc([struct.pack("<I", 1) + b"\x00" * 152], 39, 156))],
    }
    return FakeArchiveBackend(entries)


def test_regenerate_writes_artifacts_with_injected_backend(tmp_path):
    # The CLI uses simplified synthetic layouts injected via the backend; the real layouts are
    # exercised by the acceptance test. Here we assert orchestration + fail-open-with-injection.
    out = tmp_path / "out"
    manifest = regenerate(_client(tmp_path), out, backend=_fake_backend(), spell_layouts="synthetic")
    assert manifest["schema_version"] == "coa-client-extract-manifest-v1"
    assert (out / "coa_client_spell.jsonl").is_file()
    assert (out / "coa_client_content.jsonl").is_file()
    assert (out / "coa_client_archive_plan.json").is_file()
    assert (out / "coa_client_extract_manifest.json").is_file()
    spell = json.loads((out / "coa_client_spell.jsonl").read_text().splitlines()[0])
    assert spell["spell_id"] == 805775
    assert spell["coa_attribution"]["status"] == "unknown"


def test_main_fails_closed_without_stormlib(tmp_path, capsys):
    out = tmp_path / "out"
    code = main([
        "regenerate", "--client-root", str(_client(tmp_path)), "--out", str(out),
        "--stormlib", "/nonexistent/libstorm.so.999",
    ])
    assert code == 2
    assert not out.exists() or not any(out.iterdir())
    err = capsys.readouterr().err
    assert "StormLib" in err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_extract_cli.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the CLI orchestration**

```python
# coa_client_extract/cli.py
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .archive_backend import ArchiveBackend
from .archive_plan import discover_plan
from .artifacts import build_client_spell_records, write_json, write_jsonl
from .content_json import read_content_records
from .dbc_layouts import SPELL_FAMILY
from .errors import BackendUnavailable
from .manifest import build_manifest
from .wdbc import DbcLayout, FieldSpec, parse_dbc

# Synthetic layouts used only when a fake backend injects test-shaped DBC bytes.
_SYNTHETIC = {
    "Spell": DbcLayout("Spell", 4, 16, {
        "id": FieldSpec(0, "uint32"), "name": FieldSpec(1, "str"),
        "casting_time_index": FieldSpec(2, "uint32"), "duration_index": FieldSpec(3, "uint32"),
    }),
    "SpellCastTimes": DbcLayout("SpellCastTimes", 2, 8, {"id": FieldSpec(0, "uint32"), "base_ms": FieldSpec(1, "int32")}),
    "SpellDuration": DbcLayout("SpellDuration", 2, 8, {"id": FieldSpec(0, "uint32"), "base_ms": FieldSpec(1, "int32")}),
    "SpellRange": DbcLayout("SpellRange", 39, 156, {"id": FieldSpec(0, "uint32")}),
}


def _layouts(which: str) -> dict[str, DbcLayout]:
    return _SYNTHETIC if which == "synthetic" else SPELL_FAMILY


def regenerate(
    client_root: Path,
    out_dir: Path,
    *,
    backend: ArchiveBackend | None = None,
    stormlib_path: str | None = None,
    spell_layouts: str = "real",
) -> dict:
    if backend is None:
        from .stormlib_backend import StormLibBackend
        backend = StormLibBackend(stormlib_path=stormlib_path)  # may raise BackendUnavailable

    plan = discover_plan(client_root)
    layouts = _layouts(spell_layouts)

    def read_table(name: str):
        member = backend.read_effective_file(
            plan.base_archives[0], plan.patch_archives, f"DBFilesClient\\{name}.dbc"
        )
        return member, parse_dbc(member.data, layouts[name])

    spell_member, spell = read_table("Spell")
    _, cast = read_table("SpellCastTimes")
    _, dur = read_table("SpellDuration")
    _, rng = read_table("SpellRange")

    provenance = {
        "base_archive": spell_member.base_archive.name,
        "patch_chain": [p.name for p in spell_member.patch_chain],
        "effective_archive": spell_member.effective_archive.name,
        "source_dbcs": {"Spell": spell_member.effective_archive.name},
        "extraction_date": None,  # filled by build_client_spell_records provenance merge below
    }
    from datetime import date
    provenance["extraction_date"] = date.today().isoformat()

    spell_records = build_client_spell_records(spell, cast, dur, rng, provenance=provenance)
    content_records = read_content_records(client_root / "Content")

    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "coa_client_spell.jsonl": write_jsonl(spell_records, out_dir / "coa_client_spell.jsonl"),
        "coa_client_content.jsonl": write_jsonl(content_records, out_dir / "coa_client_content.jsonl"),
        "coa_client_archive_plan.json": write_json(plan.to_dict(), out_dir / "coa_client_archive_plan.json"),
    }
    manifest = build_manifest(
        backend_name=getattr(backend, "name", "unknown"),
        backend_version=getattr(backend, "version", "unknown"),
        stormlib_version=None,
        client_root=str(client_root),
        client_build="unknown",
        outputs=outputs,
        archive_plan=plan.to_dict(),
    )
    write_json(manifest, out_dir / "coa_client_extract_manifest.json")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coa_client_extract")
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("regenerate", help="extract client artifacts")
    reg.add_argument("--client-root", required=True, type=Path)
    reg.add_argument("--out", required=True, type=Path)
    reg.add_argument("--stormlib", default=None)
    args = parser.parse_args(argv)

    if args.command == "regenerate":
        try:
            regenerate(args.client_root, args.out, stormlib_path=args.stormlib)
        except BackendUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0
    return 1
```

```python
# coa_client_extract/__main__.py
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_extract_cli.py -q`
Expected: PASS (2 tests). The fail-closed test asserts exit code 2 and no artifacts written.

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/cli.py coa_client_extract/__main__.py tests/test_client_extract_cli.py
git commit -m "M1.14A: regenerate CLI that fails closed without StormLib"
```

---

### Task 9: Native integration test (StormLib patch-chain semantics)

**Files:**
- Create: `tests/test_client_extract_integration_stormlib.py`
- Create: `tests/helpers/build_mpq.py` (StormLib-backed miniature-MPQ builder; only imported under the `stormlib` marker)

**Interfaces:**
- Consumes: `StormLibBackend` (Task 7).
- Produces: `tests/helpers/build_mpq.build_mpq(path, files: dict[str, bytes | None])` — creates a tiny MPQ from self-authored bytes using StormLib's create API (`None` value writes a deletion marker via `SFileRemoveFile` after add). This helper adds create-only symbols locally; it must NOT touch `coa_client_extract/stormlib_ctypes.py` (production surface stays read-only).

**Note:** This tier requires a built/installed StormLib and is marked `@pytest.mark.stormlib`, so it is excluded from the default run. Miniature MPQs are built from self-authored bytes (no client assets).

- [ ] **Step 1: Write the miniature-MPQ helper**

```python
# tests/helpers/build_mpq.py
from __future__ import annotations

import ctypes
from pathlib import Path

from coa_client_extract.stormlib_ctypes import load_stormlib


def build_mpq(path: Path, files: dict[str, bytes]) -> Path:
    lib = load_stormlib()
    lib.SFileCreateArchive.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
    lib.SFileCreateArchive.restype = ctypes.c_bool
    lib.SFileAddFileEx.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
    lib.SFileAddFileEx.restype = ctypes.c_bool

    handle = ctypes.c_void_p()
    assert lib.SFileCreateArchive(str(path).encode(), 0, 0x1000, ctypes.byref(handle)), "create failed"
    try:
        for logical, payload in files.items():
            tmp = path.parent / (logical.replace("\\", "_"))
            tmp.write_bytes(payload)
            assert lib.SFileAddFileEx(handle, str(tmp).encode(), logical.encode(), 0x0200, 0x02, 0), f"add {logical} failed"
    finally:
        lib.SFileCloseArchive(handle)
    return path
```

- [ ] **Step 2: Write the failing integration test**

```python
# tests/test_client_extract_integration_stormlib.py
import struct
from pathlib import Path

import pytest

pytestmark = pytest.mark.stormlib

from coa_client_extract.stormlib_backend import StormLibBackend  # noqa: E402


def _dbc(value: int) -> bytes:
    row = struct.pack("<II", 1, value)
    return struct.pack("<4sIIII", b"WDBC", 1, 2, 8, 1) + row + b"\x00"


def test_patch_overrides_base(tmp_path):
    from tests.helpers.build_mpq import build_mpq

    base = build_mpq(tmp_path / "common.MPQ", {"DBFilesClient\\Test.dbc": _dbc(100)})
    patch = build_mpq(tmp_path / "patch-C.MPQ", {"DBFilesClient\\Test.dbc": _dbc(999)})

    backend = StormLibBackend()
    member = backend.read_effective_file(base, (patch,), "DBFilesClient\\Test.dbc")

    # the patched value (999) must win over the base value (100)
    _, _, _, _, _ = struct.unpack_from("<4sIIII", member.data, 0)
    (value,) = struct.unpack_from("<I", member.data, 24)  # header(20)+id(4) -> value cell
    assert value == 999
    assert member.effective_archive == patch
    assert base in member.patch_chain and patch in member.patch_chain
```

- [ ] **Step 3: Run the integration tier (requires StormLib)**

Run: `python -m pytest tests/test_client_extract_integration_stormlib.py -m stormlib -q`
Expected (with StormLib installed): PASS. Without StormLib: the test errors at `load_stormlib` with `BackendUnavailable` — install StormLib (Arch: `stormlib` from AUR; Debian/CI: build from source, MIT) and re-run. The **default** `pytest` run never selects this test.

- [ ] **Step 4: Tighten backend provenance if the reported chain differs**

If StormLib's effective-file resolution reports a different participating chain than the attached order (verify by extending the test to read `SFileGetFileInfo`), update `stormlib_backend.read_effective_file` so `patch_chain`/`effective_archive` reflect StormLib's reported chain rather than the attached list. Re-run Step 3 to green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_client_extract_integration_stormlib.py tests/helpers/build_mpq.py
git commit -m "M1.14A: native StormLib integration test for patch-chain override semantics"
```

---

### Task 10: Local-client acceptance test and full-suite verification

**Files:**
- Create: `tests/test_client_extract_acceptance.py`
- Create: `coa_client_extract/README.md` (regenerate + tier instructions)
- Test: the whole default suite plus the acceptance tier.

**Interfaces:**
- Consumes: `cli.regenerate` (Task 8) with the **real** `SPELL_FAMILY` layouts and `StormLibBackend`.

**Note:** Marked `@pytest.mark.client`; requires the real install and StormLib. Not run in CI. This is the gate that validates the real 3.3.5a indices in `dbc_layouts.py` — adjust them here if the header shows Ascension drift.

- [ ] **Step 1: Write the acceptance test**

```python
# tests/test_client_extract_acceptance.py
import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.client

CLIENT_ROOT = Path(os.environ.get(
    "COA_CLIENT_ROOT",
    str(Path.home() / "Games/ascension-wow/drive_c/Program Files/Ascension Launcher/resources/ascension-live/Data"),
))


@pytest.mark.skipif(not CLIENT_ROOT.is_dir(), reason="Ascension client not installed at COA_CLIENT_ROOT")
def test_spell_805775_is_current_adrenal_venom(tmp_path):
    from coa_client_extract.cli import regenerate

    manifest = regenerate(CLIENT_ROOT, tmp_path)  # real StormLib backend, real layouts
    assert manifest["schema_version"] == "coa-client-extract-manifest-v1"

    rows = [json.loads(line) for line in (tmp_path / "coa_client_spell.jsonl").read_text().splitlines()]
    by_id = {r["spell_id"]: r for r in rows}
    assert 805775 in by_id, "spell 805775 not extracted"
    venom = by_id[805775]
    assert "Adrenal Venom" in venom["name"]
    assert "Fang Venom" not in venom["name"]  # not the stale db value
    assert venom["provenance"]["schema_match_confidence"] in ("high", "low")
    assert venom["coa_attribution"]["status"] == "unknown"  # attribution is M1.14B
```

- [ ] **Step 2: Run the acceptance tier locally**

Run: `python -m pytest tests/test_client_extract_acceptance.py -m client -q`
Expected (client installed + StormLib): PASS. If `805775` extracts but `name` is wrong/empty, the real `Spell.dbc` layout differs from stock 3.3.5a — inspect the header (`field_count`/`record_size`) and correct the indices in `coa_client_extract/dbc_layouts.py`, then re-run until the name resolves to *Adrenal Venom*.

- [ ] **Step 3: Write the module README**

```markdown
# coa_client_extract

Extraction-time-only capture of the local Ascension CoA client (M1.14A). Reads MPQ→DBC and loose
`Data/Content/*.json` into versioned artifacts. Never imported by `coa_meta`.

## Regenerate

    python -m coa_client_extract regenerate \
      --client-root "$HOME/Games/ascension-wow/drive_c/Program Files/Ascension Launcher/resources/ascension-live/Data" \
      --out reports/client_extract

Requires StormLib (MIT). Without it the command fails closed and writes nothing.

## Test tiers

- Default (`python -m pytest`): fake backend + synthetic fixtures. No StormLib, no client.
- `python -m pytest -m stormlib`: native StormLib patch-chain integration (miniature MPQs).
- `python -m pytest -m client`: acceptance against the real install (`COA_CLIENT_ROOT` overrides path).
```

- [ ] **Step 4: Run the full default suite (must be green without StormLib/client)**

Run: `python -m pytest -q`
Expected: PASS; the `stormlib`- and `client`-marked tests are deselected by `addopts`. Confirm the pre-existing `coa_meta` suite is unaffected.

- [ ] **Step 5: Commit**

```bash
git add tests/test_client_extract_acceptance.py coa_client_extract/README.md
git commit -m "M1.14A: local-client acceptance test (805775) and module README"
```

---

## Self-Review

- **Spec coverage:**
  - `ArchiveBackend` protocol + fake backend → Task 2. Narrow ctypes surface + backend → Task 7. No raw handle escapes `stormlib_ctypes` (only Task 7's module imports ctypes for production; Task 9's helper is test-only). ✔
  - Auditable `ArchivePlan` with family filtering, ordering, override validation → Task 4. ✔
  - Header-driven WDBC reader + drift detection + spell-family layouts → Task 3. ✔
  - Loose Content JSON reader → Task 5. ✔
  - `coa-client-spell-v1` / `coa-client-content-v1` / `coa-client-archive-plan-v1` / manifest + patch-chain provenance + `schema_match_confidence` → Tasks 4, 6, 8. ✔
  - Fail-closed regenerate CLI → Task 8. ✔
  - Three test tiers with synthetic fixtures (default), native integration (Task 9), acceptance/805775 (Task 10). ✔
  - Attribution deferred (`status:"unknown"`) throughout. ✔
  - Schema docs → Task 6. Decision 20 already recorded in `docs/DECISIONS.md`. ✔
- **Placeholder scan:** every code/test step contains complete code and exact commands. The real 3.3.5a DBC indices in `dbc_layouts.py` are concrete values with an explicit acceptance-test validation gate (Task 10 Step 2), not a TODO. No "add error handling"/"similar to"/"TBD".
- **Type consistency:** `ExtractedMember` fields (`logical_path`, `data`, `base_archive`, `patch_chain`, `effective_archive`, `backend_name`, `backend_version`) are identical across Tasks 2, 7, 8. `parse_dbc`/`DbcTable`/`DbcLayout`/`FieldSpec` signatures match across Tasks 3, 6, 8. `regenerate(...)`/`main(...)` signatures in Task 8 match their test usage. `write_jsonl`/`write_json` return sha256 strings used by the manifest in Tasks 6 and 8. Backend `name`/`version` constants (`stormlib_ctypes`/`coa-stormlib-v1`, `fake`/`fake-v1`) are consistent.

## Execution Handoff

Handled by the calling session — see the two execution options offered after this plan is saved.
