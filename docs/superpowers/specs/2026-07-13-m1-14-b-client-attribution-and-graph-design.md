# M1.14B Client Attribution and CoA Advancement Graph Design

Sub-milestone of [M1.14 Client DBC Data Foundation](2026-07-06-m1-14-client-dbc-data-foundation-design.md).
Depends on [M1.14A Client Extraction Core](2026-07-10-m1-14-a-client-extraction-core-design.md).

> This spec supersedes the M1.14B scope sketched in the umbrella (archive-family + ID-range +
> skill-line attribution against the Builder oracle). A pre-implementation discovery pass against the
> real 44 GB client on 2026-07-13 disproved that plan's core premise and found a far better source.
> Revised 2026-07-13 after external design review: the parity model is now node-level (not spell-id),
> column semantics must be proven (not assumed from a matching header), the class taxonomy is
> resolved explicitly (21 playable + 1 sentinel, with alpha→display renames), the artifact contract
> is reconciled against `coa-normalized-v1`, and the client is authoritative for legality on conflict.

## Purpose

M1.14B answers "which records are Conquest of Azeroth, and what class/spec/node do they belong to?"
from client-native evidence, and fills the `coa_attribution` block that M1.14A left as `unknown`.

The discovery pass showed the answer is not a heuristic: the client ships
`DBFilesClient/CharacterAdvancement.dbc`, the DBC form of the CoA advancement graph. M1.14B extracts
it (plus its companion tables), proves it node-by-node against the CoA Builder oracle across all 21
CoA classes, and emits a `coa-client-advancement-v1` artifact carrying the full node graph and
legality fields. Per the agreed scope, M1.14B **extracts and proves**; it does not rewire the
legality or tree pipeline to consume the client graph — that staged supersession of Decision 1 is
M1.15's job, now substantially de-risked.

`CharacterAdvancement.dbc` is treated as the **candidate** canonical graph throughout M1.14B. It is
not declared authoritative or complete until the node-level parity report and the semantic-layout
validation below both pass.

## Discovery findings (measured against the real client, 2026-07-13)

Empirical results from `coa_client_extract` + StormLib against the live install, validated against
the Builder oracle (`coa_scraper/dist/coa_entries.jsonl`: 3,612 records, 3,611 unique spell IDs).

1. **Archive-family attribution is dead.** `patch-C*` contains only art (`Character/`, `Creature/`
   models/textures) — zero DBC files. The entire DBC tier is unified tables shared by all game modes,
   supplied by `patch-M` (`SkillLine`, `SkillLineAbility`, `Talent`, `ChrClasses`,
   `CharacterAdvancement`, GameTables), `patch-S` (spell side tables), and `patch-T` (`Spell.dbc`
   alone, 230,929 rows). One `Spell.dbc` holds stock, CoA, Reborn, and classless rows together, so
   `effective_archive` says nothing about which mode owns a row. Decision 18's primary signal cannot
   work.

2. **Weaker client-native signals top out ~66%.** `SkillLine.dbc` IDs 475–495 are the 21 CoA class
   display names; skill-line join gives 64.4% recall, the loose `CharacterAdvancementData.json`
   `Class` field 39.2%, union 65.7%. The residual ~1,240 Builder spells are ~86% talents.

3. **`CharacterAdvancement.dbc` closes the gap and is current.** An exhaustive residual-ID search of
   every DBC table and Content JSON found this one table contains all of them (12,037 rows,
   179 columns, from `patch-M`). Measured:
   - **100% unique-spell recall** — every one of the 3,611 Builder spell IDs appears in its spell
     column.
   - **100% node-level ownership** — once the alpha→display class rename (below) is applied, every
     Builder spell's client class matches its Builder class (3,611/3,611). Without the rename it
     *looks* like 85.5%; the 523-spell "gap" was exactly the three renamed classes. This is precisely
     why parity must be measured at node level, not by spell-id recall.
   - **Current** — its row for spell `805775` reads *Adrenal Venom*, while the loose
     `CharacterAdvancementData.json` (a stale 2026-02-08 export of this table) and db.ascension.gg
     still say *Fang Venom: Lifeblood*.

### Verified structural anchors (and what is NOT yet verified)

Only three columns are proven; everything else is a decode task gated by semantic validation (§Layout
decode and semantic validation):

- **col 0 = node id** — the advancement-row identity (unique 12,037/12,037; range 1–138,119). This,
  not the spell id, is the canonical node identity. Spell IDs repeat across nodes (see §Node identity).
- **col 5 = spell id** — 9,047 distinct; `0` when a node has no spell.
- **col 32 = class-type FK** → `CharacterAdvancementClassTypes` (100% ownership with the rename).
- **Everything else is unverified.** The AE/TE cost, required level, tab gates, row/col, and
  `ConnectedNodes`/`RequiredIDs` adjacency columns are *not* reliably located. A matching WDBC header
  does not prove column meaning: for spell `805775`, columns 48–97 all hold a repeated `24`, which is
  not a plausible connection list. The provisional correlations found during discovery
  (AE≈col17, TE≈col15, level≈col28) are decode leads, **not** contract.

### Class-type taxonomy (resolved)

`CharacterAdvancementClassTypes` (46 rows): 2–11 stock WotLK; 12 `General`; 13 `Hero`;
**14–34 = the 21 playable CoA classes**; **35 = `ConquestOfAzeroth`, a sentinel/umbrella, NOT a
playable class**; 36–46 `Reborn*`. Three playable classes are stored under scrapped-alpha internal
names and must be renamed to their current display names:

| class_type_id | client internal name | display name (Builder) |
|---|---|---|
| 22 | `SonOfArugal` | Bloodmage |
| 16 | `DemonHunter` | Felsworn |
| 21 | `Monk` | Templar |

(Confirmed by the project owner — these were alpha classes revamped into existing classes — and by
spell theme: SonOfArugal = blood, DemonHunter = fel, Monk = holy.) The band 14–35 spans 22 IDs; the
playable set is the 21 IDs 14–34 with 35 excluded as a sentinel.

## Non-Goals (staged, not dropped)

- **Rewiring the legality engine / tree renderer to consume the client graph, retiring the Builder
  scrape, and superseding Decision 1.** M1.14B proves parity and emits the artifact + adapter spec;
  the pipeline flip is M1.15. See Decision 21.
- **Reconciliation into `coa-mechanics-v1` and db mechanical sunset** — M1.14C.
- **GameTable / `coa-wow-constants-v1`** — M1.14D.
- **Full pixel-position layout parity** — cosmetic; M1.15 owns tree layout. M1.14B extracts whatever
  position/column fields decode and validate cleanly, and flags the rest.
- **Server-side computed numbers** (coefficients, scripted procs, scaling) — not in client DBC;
  scoped to the M1.14F spike and Phase 2.

## Architecture

M1.14B is additive to M1.14A and reuses all of its machinery (`ArchiveBackend`, the header-driven
`wdbc` reader with drift detection, `manifest`, provenance). No new native surface.

```
coa_client_extract/            (M1.14A machinery, unchanged)
├── advancement.py   (NEW)  CharacterAdvancement graph reader + companion-table resolvers
├── class_types.py   (NEW)  resolved, versioned class-type / tab-type classification + rename map
├── attribution.py   (NEW)  per-record CoA status + confidence from the deterministic truth table
├── parity.py        (NEW)  node-level Builder-parity report generator
├── dbc_layouts.py   (+)    CharacterAdvancement + *Types/Essence layouts, finalized + semantically
│                           validated (not header-only)
└── artifacts.py     (+)    coa-client-advancement-v1 + fills coa_attribution on coa-client-spell-v1
```

Each new module has one purpose and is unit-testable through the fake backend + synthetic fixtures,
exactly like M1.14A's readers.

### Node identity

The canonical node identity is the advancement-row id (`node_id`, col 0), **not** the spell id. Spell
IDs are many-to-one with nodes: Builder spell `503748` is one spell realized as two Witch Doctor
nodes (Brewing/Talent and Class/Ability), which is exactly why the Builder holds 3,612 records over
3,611 unique spell IDs. `ConnectedNodes` and `RequiredIDs` reference the node-id domain (col 0), not
the spell-id domain; the implementation must prove this during decode and reject the layout if the
adjacency values do not resolve into the node-id set.

## Layout decode and semantic validation

Because a matching WDBC header cannot validate column *meaning*, the `CharacterAdvancement` layout is
finalized by decode-plus-proof, not declared. `dbc_layouts.py` records the resolved column map with a
per-field `confidence`, and canonical emission is blocked for any identity/ownership/cost/gate/
adjacency field that does not pass:

1. **Foreign keys resolve** — class-type and tab-type values resolve into their companion tables; a
   value outside the known bands is flagged, not bucketed.
2. **Adjacency resolves in the right domain** — every `ConnectedNodes`/`RequiredIDs` value resolves
   to an existing `node_id` (col 0); zero/padding slots normalize to empty; no dangling references.
3. **Scalars fall in valid ranges** — AE/TE cost, required level, ranks, tab-investment gates within
   documented bounds (e.g. required level 1–60, non-negative costs).
4. **Field-by-field spot-check** — multiple known nodes per class are compared field-by-field against
   the Builder *and* against the in-game UI/tooltip for at least one spec, confirming the columns
   carry the meaning claimed.
5. **Per-spec graph invariants** — each spec's node set forms the expected gated/connected structure
   (roots reachable, no orphan prerequisites).
6. **Raw slots retained** — every raw column value is retained in the artifact's `raw` block for
   audit, so a later mis-mapping is recoverable without re-extraction.

A field that cannot be resolved to `confidence: high` blocks canonical emission of that field rather
than shipping a nominally complete artifact marked `schema_match_confidence: low`. `schema_match_
confidence: low` remains reserved for structural WDBC drift, a separate condition.

## Attribution model

`attribution.py` assigns a deterministic `coa_attribution` block per record from an explicit evidence
truth table (no informal "corroboration raises confidence"):

| Evidence | `status` | `confidence` |
|---|---|---|
| CoA advancement membership (class-type 14–34) | `coa` | `high` |
| Reborn advancement membership (class-type 36–46) | `reborn` | `high` |
| ConquestOfAzeroth sentinel (class-type 35) | `coa_system` | `high` (marked non-playable) |
| No advancement row, but on a CoA skill line | `coa` | `medium` |
| No advancement row, high custom ID only | `unknown` | `low` |
| Conflicting CoA + Reborn memberships | preserve both memberships; `status` unresolved, flagged | — |
| Class-type outside known bands (possible new class / drift) | `unknown` | flagged |

- **Primary signal = the advancement registry.** Skill-line and ID-range are only consulted for the
  small set of client records *absent* from the graph; ID range alone yields `unknown` (it separates
  custom from stock, not CoA from Reborn).
- **`archive_family` is retained as raw provenance only** (known uninformative), so the artifact stays
  honest about what was and wasn't used.
- **The Builder is never an input.** It is the oracle used to *measure* this model. Absence from the
  Builder is never negative evidence; client-only CoA nodes the Builder never exposed are retained.

### Stable multi-membership

A spell that appears on multiple nodes (different class/spec/context) is represented with a stable
`memberships[]` array on the spell artifact, never with scalar `class`/`spec` fields that flip to
arrays. Each advancement **node** record carries exactly one precise `(class, tab)` context; the
**spell** record aggregates the nodes' contexts into `memberships[]`. A stock/classless membership
never overwrites a legitimate CoA membership with `status: non_coa` — both are retained and the
CoA membership wins for attribution.

```json
{
  "spell_id": 503748,
  "coa_attribution": { "status": "coa", "confidence": "high" },
  "memberships": [
    { "mode": "coa", "class_type_id": 15, "class_name": "Witch Doctor",
      "tab_type_id": 49, "tab_name": "Brewing", "node_id": 7131, "entry_type": "Talent" },
    { "mode": "coa", "class_type_id": 15, "class_name": "Witch Doctor",
      "tab_type_id": 1,  "tab_name": "Class",   "node_id": 12264, "entry_type": "Ability" }
  ]
}
```

## Artifacts and schemas

New schema docs: `docs/data/client-advancement-schema.md`, `docs/data/client-class-types-schema.md`;
updates to `client-spell-schema.md` (attribution filled) and `client-content-schema.md` (JSON
supersede/QA note).

### `coa-client-advancement-v1` (one record per advancement node)

The artifact is faithful to the client (its own `node_id`, internal-plus-display class names, and
`raw` block). It does **not** silently pretend to be `coa-normalized-v1`: the field-name reconciliation
to the Builder contract is an explicit adapter (below), because the current `coa_meta` repository
(`repository.py:37`) requires a numeric `entry_id`, reads `col` (not `column`), and needs
`class_id`/`tab_id`/`node_type`/`is_passive`/`is_starting_node`.

```json
{
  "schema_version": "coa-client-advancement-v1",
  "node_id": 6086,
  "spell_id": 805775,
  "name": "Adrenal Venom",
  "class": { "class_type_id": 33, "internal": "Venomancer", "display": "Venomancer", "kind": "coa_class" },
  "tab":   { "tab_type_id": 1, "name": "Class" },
  "entry_type": "Ability",
  "essence_kind": "ability",
  "legality": {
    "ae_cost": 1, "te_cost": 0, "required_level": 0,
    "required_tab_ae": 0, "required_tab_te": 0,
    "required_ids": [], "connected_node_ids": [6096, 7235],
    "row": 5, "col": 3, "max_rank": 1
  },
  "field_confidence": { "ae_cost": "high", "connected_node_ids": "high", "row": "medium" },
  "raw": { "cols": [ /* all 179 raw column values, for audit */ ] },
  "provenance": {
    "source_dbcs": {
      "CharacterAdvancement": { "effective_archive": "patch-M.MPQ", "schema_match_confidence": "high" },
      "CharacterAdvancementClassTypes": { "effective_archive": "patch-M.MPQ", "schema_match_confidence": "high" },
      "Spell": { "effective_archive": "patch-T.MPQ", "schema_match_confidence": "high" }
    },
    "supersedes": { "source_file": "CharacterAdvancementData.json", "field_drift": ["name"] },
    "client_build": "3.3.5a+patch-CZZ", "extraction_date": "2026-07-13"
  },
  "coa_attribution": { "status": "coa", "confidence": "high" }
}
```

Legality field names are chosen to *ease* the M1.15 adapter, but each carries a `field_confidence`;
only `high` fields are eligible to feed the adapter.

### `coa-client-class-types-v1` and tab/essence metadata

Node records alone cannot retire the Builder pipeline, which also consumes class/tab metadata
(`coa_classes.json`) and essence caps (`coa_essence_caps.json`). M1.14B emits the resolved
class-type and tab-type tables (with `kind`, internal name, display name, rename provenance) and an
essence-cap table derived from `CharacterAdvancementEssence`, so M1.15 has the full set of inputs.

### M1.15 adapter (specified here, implemented in M1.15)

The mapping from `coa-client-advancement-v1` → `coa-normalized-v1` is written down now so the
transition is not hand-waved as a "direct field map":

| `coa-normalized-v1` | source in client artifact |
|---|---|
| `entry_id` (numeric, required) | `node_id` |
| `class_id`, `class_name` | `class.class_type_id`, `class.display` |
| `tab_id`, `tab_name`, `tab_sort_order` | `tab.tab_type_id`, `tab.name`, from tab-types table |
| `spell_id`, `spell_ids` | `spell_id`, plus rank-chain members |
| `col`, `row` | `legality.col`, `legality.row` |
| `ae_cost`/`te_cost`/`required_tab_ae`/`required_tab_te`/`required_level`/`max_rank` | `legality.*` (only `high`-confidence fields) |
| `required_ids`, `connected_node_ids` | `legality.*` (node-id domain) |
| `node_type`, `is_passive`, `is_starting_node` | derived from `entry_type` + essence/graph position |

## Node-level Builder-parity validation

`parity.py` produces `reports/client_extract/coa_builder_parity_report.json` over all 21 CoA classes.
It measures node-level, not spell-level:

- **Node counts**: advancement nodes per class/spec vs Builder records; client-only and Builder-only
  node instances enumerated.
- **Unique-spell recall** and **spell multiplicity** per class/spec (so shared nodes like `503748`
  are counted, not collapsed).
- **Compound-key ownership**: agreement on `(spell_id, class, tab, entry_type)` after the alpha→
  display rename, with every mismatch listed.
- **Adjacency parity**: `ConnectedNodes`/`RequiredIDs` sets compared per node (in the node-id domain).
- **Legality comparison**: AE/TE cost, level, gates — reported as differences, **not** pass/fail,
  because the client is authoritative on conflict (Decision 22). Each difference is classified as an
  extraction/layout defect (blocks; see gate) or a legitimate client-authoritative value difference
  (accepted, client wins).
- **Currency corroboration**: the `805775` acid test plus a changelog spot-check confirm the client
  is live — used to corroborate that the client is current, not to override it.
- **Report provenance pins** (Decision 10 reproducibility): client build, per-contributing-DBC
  sha256, Builder artifact manifest/checksum + capture date + slug, extractor commit, the resolved
  class-type set, and the resolved layout version.

## Decision impacts

- **Amend Decision 18.** Replace the archive-family attribution mechanism with the
  `CharacterAdvancement.dbc` registry as the primary CoA signal (archive family demoted to raw
  provenance; skill-line/ID-range only for graph-absent records). The principle is unchanged.
- **New Decision 21 (staged Decision 1 supersession).** The CoA client advancement graph is the
  candidate canonical source for the talent graph and legality, superseding Decision 1's "Builder is
  the Phase 1 source of truth," **gated** on: (a) the node-level parity report, and (b) the
  semantic-layout validation, both passing. Until M1.15 performs the pipeline flip, the Builder
  remains the operative graph authority and the client artifact is validated-but-not-consumed.
- **New Decision 22 (client authoritative for legality on conflict).** Where the client and Builder
  disagree on a *value* (AE/TE cost, gate, prerequisite, level, rank), the client wins — it reflects
  real in-game implementation (extends Decision 18 from mechanics to legality, per project-owner
  directive). This makes the flip gate a test of *extraction correctness*, not of value agreement:
  legitimate client-vs-Builder value differences never block; unresolved column semantics, unresolved
  ID domains, dangling adjacency, or ownership/identity defects do.

## Flip-gate pass/fail (consumed by M1.15)

M1.15 may flip the canonical source only when, for all 21 CoA classes:

- Every advancement field feeding the adapter (identity, ownership, cost, gate, prerequisite,
  adjacency, rank) is decoded at `confidence: high` and passes semantic validation.
- Node-level ownership agreement is 100% after the alpha→display rename; the playable-class set has
  cardinality exactly 21 and the sentinel is excluded.
- All adjacency references resolve in the node-id domain (no dangling/unresolved).
- Class/tab/essence metadata artifacts are present and resolve.
- Remaining client-vs-Builder differences are all classified as legitimate client-authoritative value
  differences (Decision 22), with zero unresolved extraction/layout discrepancies.

## Error handling

- Reuses M1.14A's drift path for structural WDBC drift on the new tables.
- **Semantic-validation failure blocks canonical emission** of the affected field (distinct from
  structural drift), with the failing field, expected domain/range, and offending values reported.
- A class-type/tab-type FK outside known bands is flagged (possible new CoA class or drift).
- Fail-closed and effective-chain rules (Decision 20) unchanged: read the effective patch-chain copy
  of every table (not `patch-M` directly), and write nothing without StormLib.

## Testing strategy

Same three tiers as M1.14A; all committed fixtures synthetic/self-authored (redistribution boundary).

1. **Default unit tests** (no client, no StormLib):
   - `class_types`: 21-class cardinality assertion; sentinel (35) excluded from playable; alpha→
     display rename applied; unknown-band FK flagged.
   - `advancement`: synthetic `CharacterAdvancement` + companion fixtures → node join, node-id
     identity, class/tab resolution; **semantic validation** — FK resolution, adjacency resolves in
     node-id domain, zero/padding slots normalize, dangling prerequisite rejected, out-of-range
     scalar rejected, column-semantic misassignment rejected *despite a matching WDBC header*.
   - `attribution`: the full truth table incl. CoA/Reborn/sentinel, skill-line medium, ID-only
     unknown, conflicting CoA+Reborn preserved-both, and a spell present in CoA and another mode not
     overwritten to `non_coa`.
   - `artifacts`: `coa-client-advancement-v1` schema incl. `field_confidence`, `raw`, per-table
     provenance; stable `memberships[]` for a shared spell (503748 shape); `supersedes` present.
   - `parity`: synthetic mini-oracle vs synthetic graph → node counts, unique-spell recall, spell
     multiplicity, compound-key ownership, adjacency parity, and a required extraction-defect
     discrepancy flagged as flip-blocking while a client-authoritative value difference is not.
   - missing class/tab/essence companion rows handled.
2. **Native integration test** (`@pytest.mark.stormlib`, miniature MPQs): a base `CharacterAdvancement.dbc`
   overridden by a patch; assert effective-chain resolution and per-table provenance.
3. **Local-client acceptance test** (`@pytest.mark.client`, real install): extract the real graph;
   assert 100% node-level ownership after rename, exactly 21 playable classes, shared node `503748`
   yields two Witch Doctor memberships, `805775` → `coa`/Venomancer/*Adrenal Venom*, adjacency
   resolves in the node-id domain, and the parity report generates with all provenance pins.

Testing standards follow M1.14E: assertions check intended behavior (ownership, semantic validity,
parity math), never incidental output.

## Exit Criteria

- `CharacterAdvancement.dbc` + companion tables are extracted through the M1.14A backend from the
  effective patch chain, with the column layout finalized by decode **and semantic validation**, not
  header match alone.
- `coa-client-advancement-v1` regenerates with node-id identity, resolved class/tab (alpha→display
  renamed), `high`-confidence legality fields, `raw` audit slots, `memberships[]` for shared spells,
  and per-table provenance. `coa-client-class-types-v1` + tab/essence metadata are emitted.
- `coa_attribution` on `coa-client-spell-v1` is filled from the truth table; `805775` is
  `coa`/Venomancer/`high` with current mechanical data.
- The node-level parity report covers all 21 CoA classes: 100% node-level ownership after rename,
  node counts + spell multiplicity + adjacency parity reported, every discrepancy classified as
  extraction defect vs client-authoritative difference, with all Decision 10 provenance pins.
- The playable-CoA class set is asserted to have cardinality exactly 21; the `ConquestOfAzeroth`
  sentinel is excluded from playable classes.
- The loose `CharacterAdvancementData.json` is retained only as a QA drift signal; nothing downstream
  reads its values.
- Decisions 18 (amended), 21 (staged flip + gate), and 22 (client-authoritative legality) are
  recorded.
- Default `pytest` stays green through the fake backend; no legality/tree pipeline is rewired (M1.15).
