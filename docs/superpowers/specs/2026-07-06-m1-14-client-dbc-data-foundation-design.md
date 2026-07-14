# M1.14 Client DBC Data Foundation Design (Umbrella)

> Refreshed 2026-07-10: decomposed into sub-milestones M1.14A–F, and the client-extraction
> architecture was hardened (project-owned `ArchiveBackend` behind a narrow StormLib ctypes binding,
> auditable archive plan, full patch-chain provenance, fail-closed regeneration). M1.14A now has its
> own detailed spec and plan; B–F are delineated here and get their own specs when next in line.

## Purpose

M1.14 establishes the local Ascension CoA game client as the authoritative source for mechanical
spell data and WoW systems constants. It extracts that data from the client's MPQ→DBC files and
`Data/Content/*.json` tier, attributes it to CoA using client-native heuristics, reconciles it with
the existing normalized Builder pipeline, and sunsets the stale db.ascension.gg mechanical
enrichment. It also delivers the "modeling inputs" (mechanical fields plus GameTable conversion
primitives and base resource/regen constants) that the M1.16 analytical player-power engine will
consume, and it hardens the test suite so later systems-correctness work stands on trustworthy tests.

M1.14 stays in Phase 1 and does not build the analytical engine, the simulator, or gear stat
modeling. It produces attributed, provenanced data artifacts and the tooling to regenerate them.

## Current State

- Mechanical enrichment (cast time, cost, cooldown, tooltip text) comes from db.ascension.gg via the
  M1.8/M1.11D scraper. This source is demonstrably stale (spell `805775` returns the outdated *Fang
  Venom: Lifeblood* rather than the current *Adrenal Venom*).
- The CoA Builder payload is authoritative for the talent graph, legality, tab ownership, AE/TE
  costs, prerequisites, and node descriptions (Decision 1, Decision 15).
- The mechanical data flow the client must reconcile with is: the Node scraper's
  `enrich-ascensiondb.mjs` → `coa_db_spell_tooltips.jsonl` → `apply-db-enrichment.mjs` →
  `coa_entries.enriched.jsonl`, and `build-mechanics-artifacts.mjs` → `coa_mechanics.jsonl`
  (schema `coa-mechanics-v1`), which `coa_meta`'s `MechanicsRepository` loads by spell ID. The
  `coa-mechanics-v1` provenance already carries a pluggable `source` field, so a `client_dbc` source
  slots in additively.
- No client data is currently ingested. The local install
  (`…/ascension-live/Data/`, ~44 GB) contains classic 3.3.5a MPQ archives and a loose
  `Data/Content/*.json` tier.

## Client Layout Findings

- **Archive-family partitioning attributes content to a game.** `patch-C*` (C, CA…CZ, CZZ — 29
  archives observed) map to Conquest of Azeroth; `Data/area-52/patch-D.MPQ` is Area-52, physically
  segregated; `patch-W*` (WA, WB, WC…) map to Warcraft Reborn/Bronzebeard; base game is
  `common/expansion/lichking/patch(-2/-3)`.
- **MPQ load order overrides.** Later patch archives override earlier ones; extraction must read the
  effective (latest CoA) record. StormLib resolves the patch chain; CoA Codex owns the *policy* for
  which archives participate and in what order.
- **Two data tiers, and the JSON tier is loose on disk.** DBC files live under `DBFilesClient/`
  inside the MPQs (needs StormLib). The `Data/Content/*.json` tier is loose files read directly —
  `SpellRankData.json`, `SpellToStatSuggestionData.json`, `SpellToRoleSuggestionData.json`,
  `SpellToSpellSuggestionData.json`, `EnchantmentToStatSuggestionData.json`, `ItemVariationData.json`,
  `CharacterAdvancementData.json`, and more. The loose tier needs no MPQ tooling.
- **Ascension likely extends DBC schemas** (extra columns); layout cannot be assumed to match stock
  3.3.5a and must be validated from the DBC header.
- **Custom numbers and item stats are partly server-side** and not fully present in client DBC.
  `Extensions.dll`/`MemoryBridge.log` indicate a memory bridge that could later read live-computed
  values.

## Sub-Milestone Decomposition

Following the M1.10/M1.11 precedent, M1.14 is split into lettered sub-milestones, each with its own
spec and implementation plan.

| Sub | Scope | Purpose | Depends on |
|-----|-------|---------|------------|
| **M1.14A** | extraction core | `coa_client_extract` module: `ArchiveBackend` protocol + narrow StormLib ctypes backend, auditable `ArchivePlan`, header-driven WDBC reader with schema-drift detection, loose Content-JSON reader, patch-chain provenance + manifest, and the `coa-client-spell-v1` / `coa-client-content-v1` artifacts (attribution deferred). Committed **synthetic** fixtures; three test tiers. | — |
| **M1.14B** | attribution + advancement graph | Extracts `CharacterAdvancement.dbc` — the client's own CoA advancement graph, discovered to supersede the archive-family/ID-range/skill-line attribution plan sketched below — as `coa-client-advancement-v1` (node-level, 100% unique-spell recall/attribution against the Builder oracle), plus `coa-client-class-types-v1`/`coa-client-tab-types-v1`/`coa-client-essence-v1` and the filled `coa_attribution` participation block on `coa-client-spell-v1`. Node-level Builder-parity report (`coa-builder-parity-v2`) with a scoped, per-field `readiness` object (Decision 21). M1.14B **extracts and proves** the graph and legality; it does not rewire the legality/tree pipeline to consume it — that staged, per-field Decision 1 supersession is **M1.15**'s job (Decision 21/22). See [M1.14B design](2026-07-13-m1-14-b-client-attribution-and-graph-design.md). | A |
| **M1.14C** | reconciliation + sunset | Reconcile `coa-client-spell-v1` into `coa-mechanics-v1` via a source-precedence policy in the Node mechanics builder (client mechanical > verified Builder > AscensionDB fallback > inferred tooltip), retaining every competing value + selected-source reason; demote db mechanical enrichment to fallback-only. | A, B |
| **M1.14D** | wow constants | `coa-wow-constants-v1` — GameTable conversion primitives and documented WotLK constants for the M1.16 engine. | A |
| **M1.14E** | test audit | Test-suite integrity audit, tooltip-HTML regression test, and modeling-test standards. | — |
| **M1.14F** | spike | Time-boxed memory-bridge/API investigation with a viable/not-viable/defer recommendation. | — |

A→B→C is a dependency chain. D depends only on A's extraction machinery. E and F are independent and
can proceed in parallel. **M1.14A** and **M1.14B** are now fully specced (see
[M1.14A Client Extraction Core](2026-07-10-m1-14-a-client-extraction-core-design.md) and
[M1.14B Client Attribution and CoA Advancement Graph Design](2026-07-13-m1-14-b-client-attribution-and-graph-design.md)); C–F are
delineated below.

## Scope

M1.14 includes:

- **A. Extraction core** — MPQ patch-chain resolution behind a project-owned backend, DBC parsing
  with drift detection, loose Content-JSON ingestion, provenance, and the client artifacts.
- **B. Client-native CoA attribution and advancement graph** — the `CharacterAdvancement.dbc`
  registry, node-level Builder-oracle parity, and per-record confidence. Extracts and proves the
  graph and legality; does not rewire the legality/tree pipeline to consume it (staged to M1.15).
- **C. Reconciliation** into the mechanics artifact and sunset of stale db mechanical enrichment.
- **D. WoW conversion primitives** (GameTables and documented constants) for the modeling engine.
- **E. Test-suite integrity audit** and modeling-test standards.
- **F. Investigation spike** into the memory bridge and the Ascension API.

M1.14 does not include:

- The analytical player-power engine (M1.16).
- Item stat ingestion/ranking (M1.18) beyond icon/type/display captured incidentally.
- Extraction of server-side custom scaling/proc numbers (scouted by the spike; not solved).
- Any visual/report changes beyond consuming richer mechanical fields where already rendered.
- Rewiring the legality/tree pipeline to consume the client advancement graph and retiring the
  Builder scrape (the staged, per-field Decision 1 supersession) — that is **M1.15** (Decision 21/22).

## Design

### Extraction architecture (M1.14A)

The core principle: **use StormLib directly through the smallest replaceable boundary possible, and
make the versioned artifact — not the native library — the lasting architecture.** StormLib owns MPQ
semantics; CoA Codex owns Ascension archive policy; Python owns extraction orchestration and WDBC
parsing.

- **`ArchiveBackend` protocol.** All extraction reads through a project-owned interface,
  `read_effective_file(base_archive, patch_archives, logical_path) -> ExtractedMember`, where
  `ExtractedMember` carries `logical_path`, `data`, `patch_chain`, `effective_archive`,
  `backend_name`, and `backend_version`. The rest of the module never imports ctypes or knows what
  StormLib is, so a fake in-memory backend drives unit tests and a future Rust backend is a drop-in.
- **Narrow ctypes surface.** `stormlib_ctypes.py` contains only shared-library discovery, C typedefs,
  function signatures (~`SFileOpenArchive`, `SFileOpenPatchArchive`, `SFileOpenFileEx`,
  `SFileGetFileInfo`, `SFileGetFileSize`, `SFileReadFile`, `SFileCloseFile`, `SFileCloseArchive`,
  error retrieval), and context-managed handles. **No raw C handle escapes this module.**
  `stormlib_backend.py` translates those primitives into project objects and exceptions.
- **Auditable archive plan.** An `ArchivePlan` artifact (`coa-client-archive-plan-v1`) records the
  base archives, the ordered patch archives, the excluded `area-52`/`patch-W*` families, and the
  `ordering_rule`. CoA Codex decides which patches participate and in what order; StormLib applies
  them. The ordering is empirically validated against known-overridden files before it is called
  canonical (never a blind `sorted(glob("patch-C*"))`).
- **Full patch-chain provenance.** Because a patched file's effective bytes may come from several
  incremental patches, each extracted record records `base_archive`, `patch_chain[]`,
  `effective_archive`, `sha256`, and `byte_length`, plus a manifest `{backend, stormlib_version,
  wrapper_version, client_build, extraction_date}` against a pinned StormLib release range.
- **Fail closed.** StormLib is an extraction-time dependency only — never imported by optimizer,
  report, or guide-rendering paths (it parallels Playwright-for-capture). If StormLib is unavailable,
  the regenerate command writes **nothing** and says so; it does not silently degrade. **mpyq is
  demoted** to an optional diagnostic backend for simple archives and may never produce canonical
  artifacts; external CLI tools are likewise diagnostic/cross-validation only.

### DBC parsing with drift detection (M1.14A)

A generic `WDBC` reader parses the header (magic, record count, field count, record size, string
block size) and reads fixed-width records plus the string block. Per-DBC field layouts are declared
as specs in `dbc_layouts.py`. Because Ascension may extend schemas, the reader validates the header's
field count and record size against the expected 3.3.5a layout and emits a **schema-drift warning**
(mirroring the existing pipeline's drift checks) rather than misreading silently. M1.14A proves the
machinery end-to-end on the spell family: `Spell`, `SpellCastTimes`, `SpellDuration`, `SpellRange`,
`SpellRadius`, `SpellCategory`, `SpellRuneCost`, `SpellIcon`, and `SpellDescriptionVariables`.
`Item`/`ItemDisplayInfo` are deferred (icons already come from M1.11D's AscensionDB assets; item
stats are M1.18).

### Content JSON ingestion (M1.14A)

Ingest the loose `Data/Content/*.json` tier via direct file reads through the same provenance
pipeline (no MPQ tooling). Priority files are those relevant to systems correctness: `SpellRankData`
(rank scaling), `SpellToStatSuggestionData` and `SpellToRoleSuggestionData` (stat-interaction and
role signals), and `ItemVariationData`. `CharacterAdvancementData` is investigated for whether it is
CoA or the classless/Area-52 system before any use. Records land in `coa-client-content-v1` with
source file and provenance; attribution confidence is filled by M1.14B.

### Client-native CoA attribution and advancement graph (M1.14B)

> **Superseded by discovery.** The archive-family/ID-range/skill-line plan originally sketched in this
> section (below) was disproven by a pre-implementation discovery pass against the real client on
> 2026-07-13: `patch-C*` contains only art assets, zero DBC files, so archive-family membership cannot
> attribute a DBC row to CoA. The discovery pass found a far better source — see the
> [M1.14B design](2026-07-13-m1-14-b-client-attribution-and-graph-design.md) for the full, current
> design. This subsection is retained for history; the paragraphs immediately below describe what
> actually shipped.

M1.14B's real primary signal is **`DBFilesClient/CharacterAdvancement.dbc`** — the client's own CoA
advancement graph (12,037 rows), extracted as `coa-client-advancement-v1` (one record per advancement
*node*, not per spell; see [client-advancement-schema.md](../../data/client-advancement-schema.md)).
Measured against the Builder oracle (3,612 records, 3,611 unique spell IDs): 100% unique-spell recall,
and — once the three alpha→display class renames are applied (see
[client-class-types-schema.md](../../data/client-class-types-schema.md)) — 100% unique-spell class
attribution. Archive family is demoted to raw provenance only (known uninformative); skill-line
membership and ID range remain only as a medium/low-confidence fallback for the small set of records
absent from the advancement graph (Decision 18, amended).

Attribution answers **participation**, not exclusive ownership: `attribution.py` emits, per spell,
`is_coa`/`modes[]`/`exclusive_mode`/`confidence` plus a stable `memberships[]` array, from an explicit
evidence truth table (advancement membership by class-type band is `high` confidence; skill-line-only
is `medium`; ID-range-only with no advancement/skill-line signal is `low` and `is_coa: false`). The CoA
Builder payload remains a cross-validation oracle only, never a whitelist gate.

M1.14B also proves the graph node-by-node against the Builder via the node-level parity report
(`coa-builder-parity-v2`) and emits a scoped, per-field `readiness` object (`attribution_ready`,
`ownership_ready`, `adjacency_ready`, per-field `legality`, `leveling_progression_ready`,
`full_builder_retirement_ready` — Decision 21). Per the agreed scope, M1.14B **extracts and proves**
the graph and legality; it does **not** rewire the legality/tree pipeline to consume the client
graph — that staged, per-field Decision 1 supersession, gated on this parity report and semantic-layout
validation passing, is **M1.15**'s job (Decision 21/22).

Acid test: spell `805775` is attributed to CoA (Venomancer, `high` confidence) and its advancement-graph
row carries the current *Adrenal Venom* name, while the loose `CharacterAdvancementData.json` and
db.ascension.gg still say the stale *Fang Venom: Lifeblood* — confirming the client is both correct
and current.

<details>
<summary>Original (superseded) sketch, retained for history</summary>

Attribution answers "is this record CoA?" from client-derived signals, producing a confidence and
provenance per record. Signals, in priority order:

1. **Archive-family membership** — the record's effective source archive is in the `patch-C*` family
   (CoA) versus `area-52/` (Area-52) or `patch-W*` (Reborn). Primary signal.
2. **ID range** — CoA custom content uses high ID ranges distinct from stock 3.3.5a and from the
   other games' ranges; the observed ranges are learned during implementation and recorded.
3. **Specialization/skill-line markers** — CoA specialization spells and their skill-line/family
   associations tag related content.

The **CoA Builder payload is a cross-validation oracle only**: the ~3,612 Builder spell IDs are a
labeled positive set used to measure the attribution heuristic's precision and recall and to tune
thresholds. It is never used to filter ingestion, so client-only records the Builder never exposed
are retained (with their attribution confidence). Records attributed to CoA below a confidence
threshold are ingested but flagged, not dropped.

Acid test: spell `805775` is attributed to CoA by client-native signals, its client mechanical data
matches the current *Adrenal Venom*, and the Builder cross-check confirms the heuristic caught it.
Additionally, a spot-check confirms that CoA-attributed spells *not* present in the Builder are
genuinely CoA.

</details>

### Artifacts and reconciliation (M1.14C)

Reconciliation joins client records to normalized Builder entries by spell ID. **Builder stays
authoritative for the talent graph and node descriptions** (per the primary-source decision); the
**client becomes authoritative for mechanical fields**; db.ascension.gg mechanical enrichment is
demoted to fallback-only for spells the client does not cover.

The Node/Python seam is preserved: Python extraction produces `coa-client-spell-v1`; the existing
Node `build-mechanics-artifacts.mjs` gains a **source-precedence policy** — client mechanical field
> verified Builder field > AscensionDB fallback > inferred tooltip value — and remains the producer
of `coa-mechanics-v1`, which `coa_meta`'s `MechanicsRepository` loads unchanged. Disagreements are
recorded with all competing values and the selected-source reason rather than silently overwritten.
The default report path remains network-free after artifacts are generated.

Changelog currency spot-check: a small sample of recently changed spells from
`ascension.gg/en/changelog/4` is verified to be reflected in the extracted client data, confirming
the client is current. This uses the changelog as a verification signal, not a parser.

### WoW conversion primitives (M1.14D)

Extract and normalize the GameTables and base constants into `coa-wow-constants-v1`:

- `gtCombatRatings` and the crit tables (`gtChanceToMeleeCrit(Base)`, `gtChanceToSpellCrit(Base)`) —
  rating→% conversions at level.
- Regen tables (`gtRegenMPPerSpt`, `gtOCTRegenMP/HP`) and base HP/MP by class/level
  (`gtOCTBaseHP/MPByClass`, `ChrClasses`).
- Documented game constants not in DBC: base energy (100) and regen (10/sec), focus behavior, GCD
  rules and the WotLK GCD floor, and haste's effect on GCD and resource regen.

Every constant records its source (DBC/GameTable name or "documented WotLK ruleset") and flags where
Ascension may deviate, so the M1.16 engine can treat them as inputs with stated assumptions.

### Test-suite integrity audit (M1.14E)

Review every existing test for assertions that lock in incidental or wrong behavior rather than
intended behavior. The canonical example is commit `84ad112` ("Fix tooltips rendering raw AscensionDB
HTML as literal text"), where a test asserted the escaped-HTML output and thereby ossified a
rendering bug. Deliverables:

- A test-audit findings report enumerating suspect tests (especially golden/snapshot assertions) and
  their disposition.
- A rendering-correctness test that would have caught the tooltip HTML-escaping regression (tooltips
  render as HTML tables, not escaped text).
- Testing standards for the modeling milestones: formulas checked against known WotLK reference
  values (e.g. rating conversions at levels 60/80, known coefficient results), monotonicity property
  tests (more haste → not fewer casts), and provenance/schema-drift/attribution tests for extraction.

### Investigation spike (M1.14F)

A time-boxed spike, producing a viable/not-viable/defer recommendation with evidence, for two avenues
that could later supply the server-side custom numbers M1.14 cannot:

- **Memory bridge** — whether `Extensions.dll`/`MemoryBridge` exposes live-computed spell/stat values
  in a readable form and whether reading them is technically and ethically appropriate for this tool.
- **Ascension API** — whether `data.project-ascension.com/api/spells/{id}/tooltip.html` and the db
  `&power` endpoints are current (unlike the stale db HTML) and worth using as a convenience source.

The spike does not implement either integration; it scopes their value for a later milestone.

## Module Layout

```
coa_client_extract/                # Python. Depends on StormLib at extraction time only.
├── __init__.py
├── cli.py                         # regenerate command; fails closed without StormLib
├── errors.py
├── archive_backend.py             # ArchiveBackend protocol + ExtractedMember + fake backend
├── archive_plan.py                # ArchivePlan: family filtering, load order, provenance
├── stormlib_ctypes.py             # narrow ctypes surface; no raw handle escapes
├── stormlib_backend.py            # ArchiveBackend impl over stormlib_ctypes
├── wdbc.py                        # header-driven DBC reader + drift detection
├── dbc_layouts.py                 # per-DBC field specs (expected 3.3.5a layouts)
├── content_json.py                # loose Data/Content/*.json reader
├── manifest.py                    # extraction manifest (backend, versions, build, hashes)
└── artifacts.py                   # coa-client-spell-v1 / coa-client-content-v1 writers
```

- `coa_meta` repository layer — loads the reconciled `coa-mechanics-v1` (unchanged loader) and, in
  M1.14D, the new `coa-wow-constants-v1` artifact with provenance.
- `coa_scraper/scripts/build-mechanics-artifacts.mjs` — gains the source-precedence policy in M1.14C.
- `docs/data/` — schema docs for the new artifacts (`client-spell-schema.md`,
  `client-content-schema.md`, `client-advancement-schema.md`, `client-class-types-schema.md`,
  `wow-constants-schema.md`).
- `docs/DECISIONS.md` — Decision 18 (client-authoritative mechanics, amended in M1.14B for
  advancement-registry attribution), Decision 20 (client extraction architecture), Decision 21
  (staged per-field Decision 1 supersession), and Decision 22 (client DBC canonical offline legality).

## Cross-Cutting Principles

- **Additive, not destructive.** The Builder graph pipeline and normalized artifacts remain. New
  client-sourced data is layered with provenance and confidence; existing consumers keep working.
- **The versioned artifact is the architecture, not the native library.** StormLib lives behind a
  replaceable backend; downstream code depends only on versioned JSONL contracts.
- **Provenance and attribution on every record.** Every client-sourced field records its source
  archive/DBC/JSON, patch chain, extraction date, client build, CoA-attribution confidence, and
  schema-match confidence (extends Decision 10).
- **Capture is isolated from analysis.** MPQ/DBC/JSON extraction lives in `coa_client_extract`; the
  optimizer never reads client archives (extends Decision 3). StormLib is not required to run the
  optimizer or the default test suite.
- **Fail closed on missing capability.** A lower-confidence artifact is not acceptable when the
  missing capability is fundamental patch/decompression correctness.
- **Tests assert intended behavior, not incidental output** (M1.14E), and modeling milestones test
  formulas against known WotLK reference values.
- **Redistribution boundary.** Extracting from the user's own client is in scope; committed fixtures
  are **synthetic** (self-authored), never client asset bytes. The public site hotlinks or uses
  permissibly sourced assets.

## Risks and Boundaries

- **Schema drift:** Ascension DBC extensions could break naive parsing; mitigated by header-driven
  layout and drift warnings.
- **ctypes FFI safety:** a bad binding can crash the process; mitigated by keeping the ctypes surface
  tiny, context-managing handles, letting no raw handle escape, and pinning a tested StormLib range.
- **StormLib install friction:** a native dependency for maintainers; mitigated by the fail-closed
  regenerate path plus synthetic fixtures so tests and ordinary reports never need it.
- **Attribution error:** archive-family membership was assumed strong but turned out uninformative
  (the entire DBC tier is unified across game modes); mitigated by switching the primary signal to the
  `CharacterAdvancement.dbc` registry itself, measured against Builder cross-validation with confidence
  flags rather than hard drops (M1.14B).
- **Server-side gaps:** custom scaling/proc numbers and item stats are not fully in client DBC; scoped
  to the spike and to M1.18, and documented as a known limitation.

## Exit Criteria

- `coa-client-spell-v1` regenerates from a fresh MPQ read via `coa_client_extract`, with the
  StormLib-backed backend, an auditable archive plan, and full patch-chain provenance.
- Spell `805775` is CoA-attributed by client-native signals and carries current mechanical data
  matching the live client, not the stale db *Fang Venom: Lifeblood*.
- CoA is separated from Area-52 and Reborn using client-derived signals — primarily
  `CharacterAdvancement.dbc` registry membership — with attribution confidence measured against the
  Builder oracle and reported. The node-level parity report (`coa-builder-parity-v2`) and its scoped
  `readiness` object (Decision 21) are produced, with `attribution_ready`/`ownership_ready` true and
  every other dimension reporting its honest, evidence-backed state.
- `coa-wow-constants-v1` is produced with sourced conversion tables and documented constants.
- Schema-drift detection warns on DBC layout deviations rather than misreading, and the regenerate
  command fails closed when StormLib is unavailable.
- The test-suite integrity audit is complete, its findings addressed, and the new
  regression/correctness/modeling-standard tests are in place.
- db.ascension.gg mechanical enrichment is demoted to fallback-only; the Builder graph is unchanged.
- The memory-bridge/API spike has produced a documented recommendation.
