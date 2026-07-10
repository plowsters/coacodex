# M1.14A Client Extraction Core Design

Sub-milestone of [M1.14 Client DBC Data Foundation](2026-07-06-m1-14-client-dbc-data-foundation-design.md).

## Purpose

M1.14A builds `coa_client_extract`: the module that reads the local Ascension CoA client's MPQ→DBC
files and loose `Data/Content/*.json` tier and turns them into versioned, provenanced JSONL
artifacts. It owns the mechanically hard, platform-specific, extraction-time-only machinery —
patch-chain resolution, DBC parsing with schema-drift detection, and provenance — and stops that
awkwardness at the artifact boundary. Everything downstream (attribution, reconciliation, modeling)
consumes only the artifacts.

M1.14A is the foundation for the rest of M1.14: M1.14B fills attribution onto its artifacts, M1.14C
reconciles them into `coa-mechanics-v1`, and M1.14D reuses its extraction machinery for GameTables.

## Non-Goals (deferred within M1.14)

- **CoA attribution logic** (M1.14B). M1.14A emits the `coa_attribution` block with
  `status: "unknown"` and the raw signals needed to compute it (effective archive family, spell ID),
  but assigns no confidence.
- **Reconciliation into `coa-mechanics-v1` and db sunset** (M1.14C).
- **GameTable / `coa-wow-constants-v1` extraction** (M1.14D) — A builds the reader; D declares the
  GameTable layouts and constants.
- **`Item`/`ItemDisplayInfo` DBCs** — deferred; icons come from M1.11D's AscensionDB assets and item
  stats are M1.18.
- **No `coa_meta`, report, or guide changes.** M1.14A produces artifacts and a CLI; nothing consumes
  them yet.

## Architecture

Principle: **use StormLib directly through the smallest replaceable boundary possible, and make the
versioned artifact — not the native library — the lasting architecture.** Responsibilities split as:
StormLib owns MPQ semantics, CoA Codex owns Ascension archive policy, Python owns orchestration and
WDBC parsing.

### Data flow

```
Ascension client (…/ascension-live/Data/)
        │
        ▼
coa_client_extract
  ├─ archive_plan   ── decides which archives, in what order (coa-client-archive-plan-v1)
  ├─ ArchiveBackend ── reads effective bytes + patch-chain provenance
  │     └─ stormlib_backend → stormlib_ctypes → libstorm   (or fake backend in tests)
  ├─ wdbc           ── parses DBC bytes; header-driven; drift detection
  ├─ content_json   ── reads loose Data/Content/*.json directly
  ├─ manifest       ── backend/versions/build/hashes
  └─ artifacts      ── writes JSONL
        │
        ▼
coa-client-spell-v1.jsonl        (DBC-joined mechanical fields, attribution=unknown)
coa-client-content-v1.jsonl      (loose JSON tier, attribution=unknown)
coa-client-archive-plan-v1.json  (auditable ordering + provenance)
coa-client-extract-manifest-v1.json
```

### Module layout

```
coa_client_extract/
├── __init__.py
├── cli.py                # `python -m coa_client_extract regenerate --client-root … [--stormlib …]`
├── errors.py             # ExtractError hierarchy (BackendUnavailable, ArchiveError, DbcDriftError…)
├── archive_backend.py    # ArchiveBackend Protocol, ExtractedMember, FakeArchiveBackend
├── archive_plan.py       # ArchivePlan discovery/ordering/validation
├── stormlib_ctypes.py    # narrow ctypes surface; context-managed handles
├── stormlib_backend.py   # ArchiveBackend impl over stormlib_ctypes
├── wdbc.py               # WDBC header parse, record decode, string block, drift check
├── dbc_layouts.py        # per-DBC field specs (expected 3.3.5a spell family)
├── content_json.py       # loose Content JSON reader/normalizer
├── manifest.py           # extraction manifest writer
└── artifacts.py          # coa-client-spell-v1 / coa-client-content-v1 writers
```

## Components

### `archive_backend.py` — the replaceable boundary

```python
@dataclass(frozen=True)
class ExtractedMember:
    logical_path: str          # e.g. "DBFilesClient\\Spell.dbc"
    data: bytes
    base_archive: Path
    patch_chain: tuple[Path, ...]   # ordered archives that participated
    effective_archive: Path         # the archive whose bytes won
    backend_name: str
    backend_version: str

class ArchiveBackend(Protocol):
    def read_effective_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> ExtractedMember: ...
    def list_files(
        self, base_archive: Path, patch_archives: tuple[Path, ...]
    ) -> list[str]: ...
```

No other module imports ctypes or references StormLib. `FakeArchiveBackend` (constructed from an
in-memory `{logical_path: (bytes, patch_chain)}` map) drives every unit test.

### `stormlib_ctypes.py` — narrow ctypes surface

Contains **only**: shared-library discovery (`--stormlib` arg → `STORMLIB_PATH` env →
`ctypes.util.find_library("storm")` → documented common paths), C typedefs, function signatures for
the minimal set (`SFileOpenArchive`, `SFileOpenPatchArchive`, `SFileHasFile`, `SFileOpenFileEx`,
`SFileGetFileInfo` for the patch chain, `SFileGetFileSize`, `SFileReadFile`, `SFileCloseFile`,
`SFileCloseArchive`), raw error retrieval (`GetLastError`), and context managers for archive/file
handles. **No raw handle escapes this module.** Wrong `argtypes` can crash the process, so the
surface is kept tiny, handles are RAII-managed, and the tested StormLib version range is pinned.

### `stormlib_backend.py` — `ArchiveBackend` over StormLib

Opens the base archive with `SFileOpenArchive`, attaches each patch with `SFileOpenPatchArchive` in
the plan's order, reads the effective file, and queries `SFileGetFileInfo` for the participating
patch chain to populate `ExtractedMember`. Translates StormLib errors into the `errors.py` hierarchy.
Raises `BackendUnavailable` (not a silent fallback) when the library cannot be loaded.

### `archive_plan.py` — CoA owns the policy

Discovers archives under the client root and produces an `ArchivePlan` (schema
`coa-client-archive-plan-v1`): base archives (`common`, `common-2`, `expansion`, `lichking`), ordered
patch archives (`patch`, `patch-2`, `patch-3`, then the `patch-C*` family), and excluded families
(`area-52/*`, `patch-W*`) with the `ordering_rule` name. StormLib *applies* patches; this module
*decides which and in what order*. The ordering is validated empirically against at least one
known-overridden file (a file present in a base archive and overridden by a `patch-C*` archive must
resolve to the `patch-C*` bytes) before the plan is treated as canonical.

### `wdbc.py` + `dbc_layouts.py` — header-driven DBC parse with drift detection

`wdbc.py` parses the WDBC header (magic `WDBC`, record count, field count, record size, string-block
size), then decodes fixed-width records against a declared layout and resolves string-block offsets.
`dbc_layouts.py` declares the expected 3.3.5a layout (field count, record size, typed columns) for
the spell family. Before decoding, the reader compares the header's field count and record size to
the declared layout; a mismatch raises/records a `DbcDriftError`/drift warning (with expected vs.
actual) rather than misreading. Trailing unparsed columns from Ascension extensions are surfaced,
not swallowed.

Spell-family DBCs parsed in A: `Spell`, `SpellCastTimes`, `SpellDuration`, `SpellRange`,
`SpellRadius`, `SpellCategory`, `SpellRuneCost`, `SpellIcon`, `SpellDescriptionVariables`. The reader
is generic; M1.14D adds GameTable layouts without touching the reader.

### `content_json.py` — loose JSON tier

Reads the loose `Data/Content/*.json` files directly (no MPQ). Normalizes the priority files
(`SpellRankData`, `SpellToStatSuggestionData`, `SpellToRoleSuggestionData`, `ItemVariationData`) into
`coa-client-content-v1` records keyed by spell/item ID, each carrying its source filename and file
`sha256`. `CharacterAdvancementData` is recorded as `investigate` pending M1.14B attribution (may be
the classless/Area-52 system).

### `manifest.py` + `artifacts.py` — provenance and outputs

`manifest.py` writes `coa-client-extract-manifest-v1`: `backend` (`stormlib_ctypes` /
`fake` / `mpyq_diagnostic`), `stormlib_version`, `wrapper_version` (`coa-stormlib-v1`), `client_root`,
`client_build` (read from the client version where available), `extraction_date`, the archive-plan
reference, and a `sha256` for every output. `artifacts.py` writes the two JSONL artifacts.

## Artifacts and schemas

New schema docs in `docs/data/`: `client-spell-schema.md`, `client-content-schema.md`,
`client-archive-plan-schema.md`.

### `coa-client-spell-v1` (one record per client spell)

```json
{
  "schema_version": "coa-client-spell-v1",
  "spell_id": 805775,
  "name": "Adrenal Venom",
  "mechanics": {
    "school": 8, "power_type": 3,
    "cast_time_ms": 0, "cooldown_ms": 0, "category_cooldown_ms": 0,
    "range_min_yd": 0, "range_max_yd": 5,
    "duration_ms": 18000,
    "rune_cost": null,
    "effects": [{ "index": 0, "type": 2, "base_points": 0, "coefficient": 0.0, "aura": 3 }]
  },
  "provenance": {
    "base_archive": "common.MPQ",
    "patch_chain": ["patch.MPQ", "patch-C.MPQ", "patch-CA.MPQ"],
    "effective_archive": "patch-CA.MPQ",
    "source_dbcs": { "Spell": "patch-CA.MPQ", "SpellCastTimes": "patch.MPQ" },
    "schema_match_confidence": "high",
    "extraction_date": "2026-07-10"
  },
  "coa_attribution": { "status": "unknown", "archive_family": "patch-C", "id_range": "high" }
}
```

`mechanics` fields are named to line up with `coa-mechanics-v1` so M1.14C's precedence merge is a
direct field map. `schema_match_confidence` is `high` when no drift, `low` when drift was detected
for a contributing DBC. `coa_attribution.status` stays `unknown` in A (filled by B).

### `coa-client-content-v1` (loose JSON tier)

```json
{
  "schema_version": "coa-client-content-v1",
  "content_kind": "spell_role_suggestion",
  "spell_id": 78,
  "values": { "DamageScore": 220, "HealerScore": 4, "TankScore": 69 },
  "provenance": { "source_file": "SpellToRoleSuggestionData.json", "file_sha256": "…",
                  "extraction_date": "2026-07-10" },
  "coa_attribution": { "status": "unknown" }
}
```

### `coa-client-archive-plan-v1`

Records base/patch archives, excluded families, `ordering_rule`, `client_root`, and the
known-overridden validation file used to confirm ordering.

## Error handling

- `BackendUnavailable` when StormLib can't load — the CLI prints a clear message and writes **no**
  artifacts (fail closed). It never falls back to a lower-fidelity backend for canonical output.
- `DbcDriftError` / drift warnings when a header disagrees with the declared layout — recorded on the
  affected records as `schema_match_confidence: "low"` and surfaced in the manifest.
- `ArchiveError` for missing archives / missing logical files, with the resolved plan in the message.

## Testing strategy (three tiers)

All committed fixtures are **synthetic / self-authored** — never client asset bytes (redistribution
boundary).

1. **Default unit tests** (no client, no StormLib; run by `python -m pytest`). Drive everything
   through `FakeArchiveBackend` and synthetic byte fixtures:
   - `wdbc`: hand-built WDBC headers/records with known field counts, record sizes, and string-block
     offsets; extra-field drift; truncated files; record-size mismatch.
   - `archive_plan`: family filtering (`patch-C*` in, `area-52`/`patch-W*` out), ordering rule,
     override resolution against the fake backend, provenance shape.
   - `content_json`: trimmed synthetic JSON fixtures → normalized `coa-client-content-v1`.
   - `artifacts`/`manifest`: schema validation of emitted records; `attribution.status == "unknown"`.
2. **Native integration test** (pinned StormLib + tiny self-authored miniature MPQs; separate/marked
   CI job, `@pytest.mark.stormlib`). Base archive contains `Test.dbc`; patch 1 overrides it; patch 2
   incrementally changes it; assert effective bytes + patch-chain provenance, deleted-file behavior,
   and patch-prefix behavior.
3. **Local-client acceptance test** (requires the real install; `@pytest.mark.client`, not in CI).
   Enumerate the expected archive families, extract the spell-family DBCs, record `client_build`,
   write the artifacts, and assert spell `805775` resolves to current *Adrenal Venom* mechanical data
   (not stale *Fang Venom: Lifeblood*). Fails closed rather than degrading.

The package's default `dependencies` stay empty; StormLib is a documented extraction-time dependency
like Playwright. `pyproject.toml` marker registration for `stormlib`/`client` keeps the default
`pytest` run green without the library or the client.

## Exit Criteria

- `python -m coa_client_extract regenerate --client-root <path>` produces `coa-client-spell-v1`,
  `coa-client-content-v1`, `coa-client-archive-plan-v1`, and the manifest, with full patch-chain
  provenance and a pinned-StormLib backend record.
- The archive plan's ordering is validated against a known-overridden file before it is canonical.
- The WDBC reader emits a schema-drift warning (not a misread) when a header disagrees with its
  declared layout; affected records carry `schema_match_confidence: "low"`.
- Without StormLib, the regenerate command writes nothing and reports `BackendUnavailable`; the
  default `pytest` run is fully green through the fake backend.
- The acceptance test confirms spell `805775` carries current mechanical data from the live client.
- New schema docs exist for all three artifacts; `coa_attribution.status` is `unknown` pending
  M1.14B; no downstream consumer is wired yet.
