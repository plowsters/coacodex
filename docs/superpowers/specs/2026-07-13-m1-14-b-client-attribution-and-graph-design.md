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
   - **100% unique-spell class attribution** — once the alpha→display class rename (below) is applied,
     every *distinct* Builder spell maps to the expected client class (3,611/3,611 unique spell IDs).
     Without the rename it *looks* like 85.5%; the 523-spell "gap" was exactly the three renamed
     classes. This is unique-spell, **not** node-level: full node-level parity — an exact node-id
     (`entry_id`↔`node_id`) crosswalk over the **3,612** Builder records, proving ownership, identity,
     adjacency, and legality per node — is an M1.14B acceptance deliverable (see §Node-level
     Builder-parity validation), not yet established.
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

**The rename is curated presentation metadata, not a client-native fact.** A client-native derivation
was attempted and does not work by the obvious path: advancement nodes share spells with the *spec*
skill lines (e.g. Venomancer → Stalking/Rot), not the class-band skill lines 475–495, so the
`CharacterAdvancement` internal name cannot be linked to the `SkillLine` display name through shared
spells. The three aliases are therefore recorded as curated aliases with explicit provenance (see
§Attribution model, and Decision boundary in §Decision impacts), and the raw client
`class_type_id` + internal name remain the independently-recoverable attribution identity.

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
3,611 unique spell IDs. Discovery *suggests* `ConnectedNodes` and `RequiredIDs` reference the node-id
domain (col 0) rather than the spell-id domain, but this is a hypothesis: the implementation must
prove the domain **independently for each** of the two fields (they are not assumed to share a domain)
and reject the layout if the adjacency values do not resolve into the proven set.

## Layout decode and semantic validation

Because a matching WDBC header cannot validate column *meaning*, the `CharacterAdvancement` layout is
finalized by decode-plus-proof, not declared. `dbc_layouts.py` records the resolved column map with a
per-field `confidence`, and canonical emission is blocked for any identity/ownership/cost/gate/
adjacency field that does not pass:

1. **Foreign keys resolve** — class-type and tab-type values resolve into their companion tables; a
   value outside the known bands is flagged, not bucketed.
2. **Adjacency resolves in the right domain** — every `ConnectedNodes`/`RequiredIDs` value resolves
   to an existing `node_id` (col 0); zero/padding slots normalize to empty; no dangling references.
3. **Scalars fall in valid ranges** — AE/TE cost, ranks, tab-investment gates within documented
   bounds (non-negative costs); required level in `{0} ∪ [1, 60]`, where `0` normalizes to "no level
   requirement" (available immediately), not "unknown" or padding. The normalization rule is recorded
   with the field.
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

**The loose `CharacterAdvancementData.json` is only a *partial* decode reference.** A real decode run
(2026-07-14) showed it is stale and stripped: `MaxRank`/`Row` are absent from it entirely, `Tab`/`Type`
are display-name strings not ids, and adjacency/cost/investment fields appear in only a small minority
of entries, so only a few columns (e.g. `required_level`, `col`) prove `high` from it alone. Each field
is therefore decoded from whatever *independent* evidence proves it — name-mediated FK resolution for
`tab_type` (loose-JSON `Tab` name → `CharacterAdvancementTabTypes` id), a robust majority numeric→string
mapping for `entry_type`, and node-id-domain + graph-invariant proof for adjacency. Where the Builder
`entry_id` crosswalk is used to *propose* a mapping, that field carries `mapping_discovery_source:
builder_crosswalk` and is accepted only after passing the independent checks above (never Builder
agreement alone; Builder values are never copied in). Fields no independent evidence can yet prove stay
`unresolved` and keep the Builder fallback — that is the expected, honest M1.14B outcome, not a failure.

## Attribution model

Attribution answers **participation**, not exclusive ownership — M1.14C needs "does this spell
participate in CoA?", not "does CoA own it alone." `attribution.py` emits, per spell, `is_coa` +
`modes[]` + `exclusive_mode`, plus the stable `memberships[]` (below). `confidence` follows an
explicit evidence truth table (no informal "corroboration raises confidence"):

| Evidence | contributes mode | `confidence` |
|---|---|---|
| CoA advancement membership (class-type 14–34) | `coa` | `high` |
| Reborn advancement membership (class-type 36–46) | `reborn` | `high` |
| Stock/classless advancement membership (class-type 2–12) | `stock` | `high` |
| ConquestOfAzeroth sentinel (class-type 35) | `coa_system` (marked non-playable) | `high` |
| No advancement row, but on a CoA skill line | `coa` | `medium` |
| No advancement row, high custom ID only | (no mode) | `low`, `is_coa: false` |
| Class-type outside known bands (possible new class / drift) | flagged, no mode asserted | flagged |

- `is_coa` is true iff any evidence contributes the `coa` mode. `modes[]` is the sorted set of all
  modes the spell participates in; `exclusive_mode` is the single mode when `len(modes) == 1`, else
  `null`. A spell in both CoA and Reborn (or CoA and stock) is legitimate multi-mode reuse:
  `is_coa: true`, `modes: ["coa", "reborn"]`, `exclusive_mode: null` — not an "unresolved conflict."
- **Primary signal = the advancement registry.** Skill-line and ID-range are only consulted for the
  small set of client records *absent* from the graph; ID range alone contributes no mode (it
  separates custom from stock, not CoA from Reborn).
- **The "CoA skill line" set is proven empirically, not the class-band range.** Discovery showed CoA
  advancement spells attach to per-**spec** `SkillLine`s (Venomancer → Stalking/Rot/…), not only the
  class-band display lines 475–495, so a 475–495-only fallback would miss most of them. The set is
  derived at extraction time as **the `SkillLine`s that carry ≥1 spell already attributed `coa` by the
  registry** (join `SkillLineAbility` → graph CoA spells → the skill lines those spells belong to);
  a graph-absent spell sharing one of those proven CoA lines is the only thing the medium-confidence
  fallback fires on. This keeps the fallback grounded in proven evidence rather than a guessed range.
- **`archive_family` is retained as raw provenance only** (known uninformative).
- **The Builder is never an input to membership or mode attribution.** It is the oracle used to
  *measure* this model. Absence from the Builder is never negative evidence.
- **Curated display aliases are presentation metadata, not attribution inputs.** The three alpha→
  display aliases are applied only to the human-readable `display` string, with explicit provenance;
  they never change the client `class_type_id` or any `is_coa`/`modes` result, so the raw client
  identity stays independently recoverable:

  ```json
  { "class_type_id": 22, "internal": "SonOfArugal", "display": "Bloodmage",
    "kind": "coa_class", "display_source": "curated_alias",
    "display_evidence": ["builder_class_name", "project_owner_confirmation"] }
  ```

### Stable multi-membership

Each advancement **node** record carries exactly one precise `(class, tab)` context. The **spell**
record aggregates those nodes into a stable `memberships[]` array — never scalar `class`/`spec` fields
that flip to arrays. A stock/classless membership never overwrites a CoA membership; both are retained
in `memberships[]`, and `is_coa` stays true.

```json
{
  "spell_id": 503748,
  "coa_attribution": { "is_coa": true, "modes": ["coa"], "exclusive_mode": "coa", "confidence": "high" },
  "memberships": [
    { "mode": "coa", "class_type_id": 15, "class_internal": "WitchDoctor", "class_display": "Witch Doctor",
      "tab_type_id": 49, "tab_name": "Brewing", "node_id": 7131, "entry_type": "Talent" },
    { "mode": "coa", "class_type_id": 15, "class_internal": "WitchDoctor", "class_display": "Witch Doctor",
      "tab_type_id": 1,  "tab_name": "Class",   "node_id": 12264, "entry_type": "Ability" }
  ]
}
```
(`tab_type_id` values are illustrative; the tab-type IDs are resolved from
`CharacterAdvancementTabTypes` during decode.)

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
  "class": { "class_type_id": 33, "internal": "Venomancer", "display": "Venomancer",
             "kind": "coa_class" },
  "tab":   { "tab_type_id": 1, "name": "Class" },
  "entry_type": "Ability",
  "essence_kind": "ability",
  "legality": {
    "ae_cost": 1, "te_cost": 0, "required_level": 0,
    "required_tab_ae": 0, "required_tab_te": 0,
    "required_ids": [], "connected_node_ids": [6096, 7235],
    "row": 5, "col": 3, "max_rank": 1
  },
  "field_confidence": { "ae_cost": "high", "connected_node_ids": "high", "row": "high" },
  "raw": { "cols": { } },
  "provenance": {
    "source_dbcs": {
      "CharacterAdvancement": { "effective_archive": "patch-M.MPQ", "schema_match_confidence": "high" },
      "CharacterAdvancementClassTypes": { "effective_archive": "patch-M.MPQ", "schema_match_confidence": "high" },
      "Spell": { "effective_archive": "patch-T.MPQ", "schema_match_confidence": "high" }
    },
    "supersedes": { "source_file": "CharacterAdvancementData.json", "field_drift": ["name"] },
    "client_build": "3.3.5a+patch-CZZ", "extraction_date": "2026-07-13"
  },
  "coa_attribution": { "is_coa": true, "modes": ["coa"], "exclusive_mode": "coa", "confidence": "high" }
}
```

This is an illustrative *post-validation* record: every field shown is `high` confidence and the
`raw.cols` block (elided here) is the index-keyed `{cell_index: value}` map of all raw columns for
audit (the `display_source`/`display_evidence` of the class name live in `coa-client-class-types-v1`,
joined by `class_type_id`, not duplicated per node). Legality field names are
chosen to *ease* the M1.15 adapter, but each carries a `field_confidence`; only `high` fields are
eligible to feed the adapter.

### `coa-client-class-types-v1` and tab/essence metadata

Node records alone cannot retire the Builder pipeline, which also consumes class/tab metadata
(`coa_classes.json`) and essence caps (`coa_essence_caps.json`). M1.14B emits the resolved class-type
and tab-type tables (with `kind`, internal name, display name, rename provenance).

**Essence — two distinct quantities, two distinct readiness states (resolved with the project owner):**

- **Caps** (max Ability Essence 26 / Talent Essence 25) are the pool sizes that gate a *completed
  max-level build*. They are uniform across classes and are carried as a **versioned
  `verified_constant`** (currently the values in `coa_essence_caps.json`), **not decoded from
  `CharacterAdvancementEssence`** — the design must never imply they were. Under Decision 21's
  per-field rule they are an explicitly-retained fallback source with honest provenance
  (`source: verified_constant`, `corroboration: pending_client_ui`) until corroborated against the
  live client UI / behavior. Because CoA Codex validates max-level builds, the caps are the only
  essence quantity the legality flip needs, and they are already available.
- **Per-level/per-tier progression** — the `CharacterAdvancementEssence` table (5,440 rows; columns
  `1..80 × 1..32`) — is *leveling* data: how much essence is available at each level/tier. It is a
  separate capability (level-by-level build validation, a new **M1.15 sub-milestone**), **not** a
  prerequisite for replacing the Builder as the max-level ownership/graph/legality source. M1.14B
  **extracts it raw with provenance** into `coa-client-essence-v1` (semantics documented as undecoded)
  so it is present and auditable, and reports **`leveling_progression_ready: false`** — but this
  **never blocks** any max-level readiness dimension or `full_builder_retirement_ready`. Coupling a
  proven max-level graph to an unfinished leveling feature would be a scope error.

Accordingly `leveling_progression_ready` is one entry in the scoped `readiness` object (see below): it
stays `false` in M1.14B (the per-level essence table is extracted raw but not decoded), separate from
and never blocking the max-level dimensions (`attribution_ready`/`ownership_ready`/`adjacency_ready`/
per-field `legality`) or `full_builder_retirement_ready`. Level-by-level build validation gets its own
future gate and cannot claim readiness until the progression table is decoded + validated.

### Decision 1 supersession is per-field, not wholesale (M1.15 adapter)

The Builder is retired **by responsibility**, one field at a time, not all at once. The adapter maps
`coa-client-advancement-v1` → `coa-normalized-v1` with an explicit source, gate, and fallback per
field, so a field the client cannot yet supply keeps its existing source, explicitly marked, rather
than being fabricated:

| `coa-normalized-v1` field(s) | source | gate / fallback |
|---|---|---|
| `entry_id` (numeric, required) | `node_id` | anchored (proven) |
| `class_id`, `class_name` | `class.class_type_id`, `class.display` | anchored; `class_name` uses curated alias, provenance retained |
| `tab_id`, `tab_name`, `tab_sort_order` | tab-types table | gated on tab-type decode |
| `spell_id`, `spell_ids` | `spell_id` + rank-chain members | anchored |
| `ae_cost`/`te_cost`/`required_tab_ae`/`required_tab_te`/`required_level`/`max_rank` | `legality.*` | only `high`-confidence fields feed; else Builder fallback, marked |
| `required_ids`, `connected_node_ids` | `legality.*` (proven adjacency domain) | gated on adjacency-domain proof |
| `col`, `row` | `legality.col`/`row` | gated; cosmetic, M1.15 layout may override |
| `node_type`, `is_passive`, `is_starting_node` | client `NodeType`/`Flags`/`Spell.dbc` attributes **if a proven column exists** | **not inferable from `entry_type`+position**; if unproven, retain the existing inference/Builder source, explicitly marked |
| `icon`, `description_html`/`description_text` | client `Spell.dbc` / spell artifact where available | else retain existing enrichment source, marked |
| `tags`, `resources`, `damage_schools`, `inferred`, `field_sources`, `source_category` | existing inference pipeline (unchanged) | client does not supply these; not a Builder-legality concern |

The guiding split: **client advancement graph** owns ownership + proven legality; **client spell
artifact** owns name/mechanics/descriptions where available; the **existing inference pipeline** keeps
owning tags/resources/schools; the **Builder is a fallback only for fields not yet replaced, and every
such field is explicitly marked** so the remaining Builder surface is auditable and shrinks over time.

## Node-level Builder-parity validation

`parity.py` produces `reports/client_extract/coa_builder_parity_report.json` over all 21 CoA classes.
It measures node-level, not spell-level, and it **actually computes** every comparison it reports —
adjacency and legality diffs are derived inside the report from a real crosswalk, never accepted as
pre-computed inputs a caller might leave empty.

**Node-identity crosswalk (the foundation).** Each Builder record carries `entry_id` — the
advancement-row node id — plus `connected_node_ids`, `required_ids`, and every legality field
(measured: 3,612 records, 3,612 unique `entry_id`s; Builder adjacency references `entry_id`s). The DBC
node identity is `CharacterAdvancement` col 0. The report crosswalks **client `node_id` ↔ Builder
`entry_id`** directly, then *proves the id spaces align* rather than assuming it: for every matched id
it checks the semantic tuple `(spell_id, class_display, tab_name, entry_type)` agrees. A high match
rate with agreeing tuples proves the shared numbering; near-zero agreement means the crosswalk itself
is unresolved (a flip-blocker), which is caught loudly instead of silently reporting 100%.

- **Ownership (exact set over node ids):** `builder_only = entry_ids − client_coa_node_ids` and
  `client_only = client_coa_node_ids − entry_ids`. Both must be empty. A client graph that covers
  every Builder node but adds extra/wrongly-attributed CoA nodes is **not** flip-ready (`client_only`
  ≠ 0 blocks — precision as well as recall). `identity_mismatches` = matched ids whose semantic tuple
  disagrees (a decode/attribution defect; blocks).
- **Per class AND per tab/spec counts:** node counts, `client_only`, `builder_only`, and mismatch
  tallies are broken out by class and by `(class, tab)`, not class alone, so the duplicated spell
  `503748` (two Witch Doctor nodes on different tabs) and per-tab multiplicity are visible.
- **Adjacency parity (computed):** for every matched node, compare the client `connected_node_ids`
  set vs the Builder's, and `required_ids` vs the Builder's, each in the shared node-id domain.
  `adjacency_mismatches` is the count of nodes whose either set differs; each is listed. Any mismatch
  blocks.
- **Legality parity (computed, Decision-22 classified):** for every matched node and every adapter
  legality field (`ae_cost`, `te_cost`, `required_level`, `required_tab_ae`, `required_tab_te`,
  `max_rank`, `row`, `col`), compare after normalization and classify: **(a)** the client field is
  present but not proven `high` → extraction/layout defect → field **`unresolved`**; **(b)** client is
  `high` and the normalized values differ → verified client-current difference → recorded, client wins,
  field **`ready`**; **(c)** equal after normalization → representation difference, normalized away,
  field **`ready`**; **(d)** the field is undecoded on the client side while the Builder supplies it, or
  any difference that cannot be classified → field **`unresolved`**. The class drives that field's
  `readiness.legality[field]` (a/d → `unresolved`; b/c/proven-equal → `ready`); `row`/`col` map to
  cosmetic `readiness.layout` and block nothing. Every difference is listed with its class; the report
  never claims "no legality discrepancies" merely because no comparison ran.
- **Currency corroboration:** the `805775` acid test plus a changelog spot-check confirm the client is
  live — used to corroborate that the client is current, not to override it.
- **Report provenance pins** (Decision 10 reproducibility): client build, per-contributing-DBC sha256
  (CharacterAdvancement, ClassTypes, TabTypes, Essence, Spell), Builder artifact manifest/checksum +
  capture date + slug, extractor commit, the resolved class-type set, the resolved layout version, and
  the decode-report checksum.
- **Scoped, per-responsibility + per-field readiness (no single boolean).** A single `flip_ready`
  boolean does not fit the evidence: a real client decode showed the loose `CharacterAdvancementData.json`
  proves only some columns (e.g. `required_level`, `col`) while `max_rank`/`row` are absent from it
  entirely and adjacency/`tab_type`/`entry_type` need dedicated decode paths — so ownership can be
  canonical long before every legality scalar is. Per Decision 21 (per-field supersession) the report
  instead exposes a `readiness` object, each dimension independently earned:

      "readiness": {
        "attribution_ready":  true|false,   # from the anchored class_type FK (col 32) — no legality dependency
        "ownership_ready":     true|false,   # exact node-id ownership + zero identity_mismatches + cardinality/count guards
        "adjacency_ready":     true|false,   # BOTH edge domains (connected + required) AND their meanings independently proven + zero adjacency_mismatches
        "legality": { "<field>": "ready"|"unresolved", ... },   # per legality field (required_level, ae_cost, te_cost, required_tab_ae, required_tab_te, max_rank)
        "layout":   { "row": "ready"|"unresolved", "col": "ready"|"unresolved" },   # cosmetic — NEVER blocks anything
        "leveling_progression_ready": false,   # essence per-level table (M1.15), separate, never blocks max-level
        "full_builder_retirement_ready": true|false   # roll-up: attribution+ownership+adjacency ready AND every REQUIRED legality field ready
      }

  Rules: **a proven field supersedes the Builder for that field alone; an unresolved field keeps the
  Builder fallback with explicit per-field provenance.** Unresolved legality **does** block flipping
  *that* legality field (and `full_builder_retirement_ready`) — it does **not** block `attribution_ready`
  or `ownership_ready`. `layout.row`/`layout.col` are cosmetic and block nothing. The raw essence
  progression table sets `leveling_progression_ready: false` separately and never blocks max-level
  ownership. `full_builder_retirement_ready` stays false while any required responsibility is unresolved,
  so M1.15 cannot claim full Builder retirement prematurely. The goal is honesty: progress is retained,
  uncertainty stays visible, and no weak oracle is promoted into authority to make a global checkbox green.

## Decision impacts

- **Amend Decision 18.** Replace the archive-family attribution mechanism with the
  `CharacterAdvancement.dbc` registry as the primary CoA signal (archive family demoted to raw
  provenance; skill-line/ID-range only for graph-absent records). The principle is unchanged.
- **New Decision 21 (staged Decision 1 supersession, per-field).** The CoA client advancement graph
  is the candidate canonical source for the talent graph and legality, superseding Decision 1's
  "Builder is the Phase 1 source of truth" **by responsibility, one field at a time** (see the adapter
  field matrix), not wholesale. The flip is **gated** on: (a) the node-level parity report, and (b) the
  semantic-layout validation, both passing for the fields being flipped. Fields the client cannot yet
  supply keep their existing source, explicitly marked. Until M1.15 performs the flip, the Builder
  remains the operative graph authority and the client artifact is validated-but-not-consumed.
  **Builder-as-discovery-aid boundary.** The Builder `entry_id` crosswalk is valuable for *generating*
  a column-mapping hypothesis, but Builder agreement can **never** be the sole proof that decodes a
  field and then "independently" validates parity against itself — that is circular. A Builder-proposed
  mapping is recorded as `mapping_discovery_source: builder_crosswalk` and is only accepted when it also
  passes evidence that does not reduce to the Builder: client-wide semantic ranges/distributions, node-id-domain
  validation, graph invariants, current in-game UI/tooltip spot-checks, and current-client-values winning
  on disagreement. **Builder values are never copied into the client artifact** — only the client's own
  decoded cells are emitted.
- **New Decision 22 (client DBC is the canonical *offline* legality source; live corrections come
  from user-reported overrides, not the Builder).** The current client DBC is the canonical offline
  source for legality (AE/TE cost, gates, prerequisites, level, rank), extending Decision 18 from
  mechanics to legality. It is **not** assumed identical to live server enforcement — the server can
  hotfix costs, hidden prerequisites, scripted rank behavior, or level gates the client does not
  reflect — so the precedence is:

      user-reported, reproducibly-verified live override
        >  current client DBC
        >  (Builder / stale JSON / AscensionDB — informational only, never authoritative)

  The Builder is removed from the legality authority chain entirely: it is itself an offline,
  possibly-stale source of unknown fidelity to the server, so a Builder disagreement is informational,
  never authoritative, and never value-blocking. Live corrections are captured through a versioned,
  reviewable **manual-override layer fed by user-reported inaccuracies** (the mechanism the public site
  will expose; its implementation is a later milestone, not M1.14B). A proven client value is used
  until such an override supersedes it.

  Each client-vs-Builder legality difference is classified as: **(a) extraction/layout defect** — the
  client field is not proven decoded correctly → that field stays **`unresolved`** (keeps the Builder
  fallback, blocks flipping that field and `full_builder_retirement_ready`); **(b) verified
  client-current difference** — client decoded to `high` confidence and simply differs from the Builder
  → accepted, client wins offline, field **`ready`**; **(c) representation difference** — same value,
  different encoding → normalized, field **`ready`**; **(d) unresolved** — not yet decoded/classified →
  field **`unresolved`**. Only (a) and (d) leave a field unresolved (per-field, not a global flip); a
  genuine proven difference (b) is `ready`. An unresolved field never blocks `attribution_ready` or
  `ownership_ready`.

## Readiness gates (consumed by M1.15)

M1.15 supersedes the Builder **per responsibility, and within legality per field** (Decision 21), each
gate earned independently on its own evidence. No global boolean; each dimension below is what turns its
`readiness` entry `true`/`ready`.

- **`attribution_ready`** (for all 21 CoA classes): the class-type FK (col 32, structurally anchored)
  resolves, the playable-CoA set has cardinality exactly 21 with the sentinel (35) excluded, and the
  participation model (`is_coa`/`modes`/`memberships`) is populated from it. Attribution rests on the
  anchor, **not** on any decoded legality column, so it can be ready while legality is not.
- **`ownership_ready`**: node-identity ownership is exact after the alpha→display rename — the client
  CoA `node_id` set equals the Builder `entry_id` set (both `builder_only` and `client_only` empty),
  zero `identity_mismatches` (matched ids whose `(spell_id, class, tab, entry_type)` tuple disagrees),
  the playable set is exactly 21 with 35 excluded, the Builder record count equals the pinned total
  (3,612), and client and Builder inputs are both non-empty. Independent of legality decode.
- **`adjacency_ready`**: **both** edge domains AND their **meanings** are independently proven — the
  `connected` and `required` blocks each resolve in the node-id domain (no dangling/unresolved), their
  meaning (which block is ConnectedNodes vs RequiredIDs) is established by evidence that does **not**
  reduce to Builder agreement alone (graph invariants: connected edges reachable from roots, required
  edges acyclic; plus current-client-wins on disagreement), and they match the Builder per node (zero
  `adjacency_mismatches`). The Builder crosswalk may *propose* the block→meaning hypothesis
  (`mapping_discovery_source: builder_crosswalk`) but never be its sole proof.
- **Per-field `legality[field]`** ∈ {`ready`, `unresolved`}: a field is `ready` only when its column
  decoded to `confidence: high`, its values pass independent semantic validation (client-wide range /
  distribution, node-id-domain for reference fields), and its Decision-22 classification is not (a) or
  (d). An `unresolved` field is **not** promoted: it keeps the Builder fallback with explicit per-field
  provenance and **blocks flipping that field** (and `full_builder_retirement_ready`), while never
  blocking attribution or ownership. `tab_type`/`entry_type` are confidence-gated for emission exactly
  like legality scalars; the numeric `entry_type` → string mapping is proven in the decode report, not
  hard-coded.
- **`layout.row`/`layout.col`** ∈ {`ready`, `unresolved`}: cosmetic position fields, recorded for
  completeness; they **block nothing** (not legality, not attribution, not retirement).
- **`full_builder_retirement_ready`**: the roll-up — `true` only when `attribution_ready`,
  `ownership_ready`, `adjacency_ready`, and every **required** legality field (`required_level`,
  `ae_cost`, `te_cost`, `required_tab_ae`, `required_tab_te`, `max_rank`) are all ready, and the
  per-class/per-tab subgraphs satisfy the graph invariants (roots exist, all nodes reachable, no
  dangling prerequisites, no forbidden cycles, no orphans). While any required responsibility is
  unresolved this stays `false`, so M1.15 cannot claim full Builder retirement prematurely. The verified
  essence **caps (26/25)** are a versioned `verified_constant`/retained fallback (Decision 21), not a
  decoded value and not part of this roll-up.

The raw `coa-client-essence-v1` progression table being undecoded sets **`leveling_progression_ready:
false`** separately; it never blocks max-level ownership or `full_builder_retirement_ready`. Level-by-level
build validation is a separate M1.15 sub-milestone with its own gate (decode + validate the progression
table) that consumes `leveling_progression_ready`.

## Error handling

- **Canonical regeneration parses strict.** Every contributing table read for a *canonical* artifact
  is parsed with `strict=True` (`parse_dbc(..., strict=True)` for the named `*Types` tables,
  `parse_positional(..., strict=True)` for the wide `CharacterAdvancement`/`Essence` tables), so a
  structural header mismatch raises before any artifact is written — a canonical artifact is never
  emitted with `header_drift: true`. Non-strict parsing is confined to the diagnostic
  `decode-advancement` command, which is exploratory and writes no canonical output.
- **Semantic-validation failure blocks canonical emission** of the affected field (distinct from
  structural drift), with the failing field, expected domain/range, and offending values reported.
- **Graph-invariant failure blocks canonical emission**: per class/tab, the reader checks for at least
  one root, reachability of every node from the roots, no dangling prerequisites, no cycles in the
  prerequisite (`RequiredIDs`) graph, and no orphaned nodes, raising `DbcSemanticError` on violation.
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
   - `attribution`: the full truth table incl. CoA/Reborn/stock/sentinel; skill-line medium; ID-only
     no-mode/`is_coa: false`; a CoA+Reborn spell → `is_coa: true`, `modes: ["coa","reborn"]`,
     `exclusive_mode: null` (multi-mode reuse, not "unresolved"); a CoA+stock spell keeps `is_coa:
     true` with the stock membership retained, not overwritten.
   - `artifacts`: `coa-client-advancement-v1` schema incl. `field_confidence`, `raw`, per-table
     provenance; stable `memberships[]` for a shared spell (503748 shape); `supersedes` present.
   - `parity`: synthetic mini-oracle vs synthetic graph exercising the real crosswalk — node-id
     ownership (builder-only AND client-only both block `ownership_ready`), a semantic-tuple
     `identity_mismatch`, a computed `adjacency_mismatch` (connected/required differ per node), a
     computed legality diff of each Decision-22 class (a/b/c/d) driving per-field `legality[field]`
     readiness (only (a)/(d) leave a field `unresolved`), per-class and per-tab counts, the
     cardinality/expected-count/non-empty gates, and the scoped `readiness` object: `attribution_ready`
     and `ownership_ready` earned independently of legality, an `unresolved` legality field blocking
     `full_builder_retirement_ready` but NOT ownership/attribution, `layout.row`/`layout.col` blocking
     nothing, and `leveling_progression_ready: false` separate.
   - `graph invariants`: synthetic subgraphs exercising a missing root, an unreachable node, a
     prerequisite cycle, and an orphan — each rejected.
   - missing class/tab/essence companion rows handled.
2. **Native integration test** (`@pytest.mark.stormlib`, miniature MPQs): a base `CharacterAdvancement.dbc`
   overridden by a patch; assert effective-chain resolution and per-table provenance.
3. **Local-client acceptance test** (`@pytest.mark.client`, real install): extract the real graph via
   the real `regenerate` API; assert exact node-id ownership over the 3,612 Builder records after
   rename (both `builder_only` and `client_only` zero), exactly 21 playable classes (sentinel
   excluded), shared node `503748` yields two Witch Doctor memberships, `805775` →
   `is_coa: true`/Venomancer/*Adrenal Venom*, the parity report generates with all provenance pins,
   and the scoped `readiness` reads `attribution_ready: true` and `ownership_ready: true`, with
   `leveling_progression_ready: false` and `full_builder_retirement_ready: false` while required
   legality/adjacency remain unresolved. Each `readiness.legality[field]` and `adjacency_ready` value
   matches what the committed decode report actually proved (the test asserts the *structure and
   consistency* of the readiness object against the decode evidence, not a hard-coded all-green).

Testing standards follow M1.14E: assertions check intended behavior (ownership, semantic validity,
parity math), never incidental output.

## Exit Criteria

- `CharacterAdvancement.dbc` + companion tables are extracted through the M1.14A backend from the
  effective patch chain, with the column layout finalized by decode **and semantic validation**, not
  header match alone.
- `coa-client-advancement-v1` regenerates with node-id identity, resolved class/tab (alpha→display
  renamed), `high`-confidence legality fields, `raw` audit slots, `memberships[]` for shared spells,
  and per-table provenance. `coa-client-class-types-v1`, `coa-client-tab-types-v1`, and the raw
  `coa-client-essence-v1` metadata are emitted.
- `coa_attribution` on `coa-client-spell-v1` is filled from the truth table; `805775` is
  `is_coa: true`/Venomancer/`high` with current mechanical data.
- The node-level parity report covers all 21 CoA classes and **computes** every comparison it reports:
  exact node-id ownership over the 3,612 Builder records after rename (`builder_only` and `client_only`
  both zero, zero `identity_mismatches`), per-class and per-tab node counts, per-node adjacency parity
  (`connected_node_ids` and `required_ids` matched against the Builder), every legality discrepancy
  classified into the Decision 22 categories (with (a)/(d) leaving that field `unresolved`), and all
  Decision 10 provenance pins (including extractor commit, Builder capture/slug/manifest, resolved class
  set, decode-report checksum, and per-Builder-proposed-mapping `mapping_discovery_source`).
- The report emits the scoped `readiness` object (Decision 21): `attribution_ready` and `ownership_ready`
  earned from the structural anchors independently of legality; `adjacency_ready` only when both edge
  domains and their meanings are independently proven; per-field `legality[...]` and cosmetic
  `layout.row`/`layout.col`; `leveling_progression_ready: false` (essence raw, deferred to M1.15, never
  blocking); and `full_builder_retirement_ready` false while any required responsibility is unresolved.
  M1.14B targets `attribution_ready: true` and `ownership_ready: true`; every other dimension reports
  its honest, evidence-backed state rather than being forced green.
- The playable-CoA class set is asserted to have cardinality exactly 21; the `ConquestOfAzeroth`
  sentinel is excluded from playable classes.
- The loose `CharacterAdvancementData.json` is retained only as a QA drift signal; nothing downstream
  reads its values.
- Decisions 18 (amended), 21 (staged per-field flip + gate), and 22 (client DBC canonical offline
  legality; live corrections via user-reported overrides, not the Builder) are recorded.
- Default `pytest` stays green through the fake backend; no legality/tree pipeline is rewired (M1.15).
