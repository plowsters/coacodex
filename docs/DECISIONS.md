# Architecture Decisions

This document records intentional decisions. If implementation differs from these decisions, the implementation should either be corrected or this document should be updated with a new decision.

## Decision 1: Structured Builder Data Is the Phase 1 Source of Truth

Status: accepted.

Phase 1 uses normalized data from the Ascension CoA builder payload, not scraped page text and not in-game logs. The scraper and payload extractor own web-specific brittleness. The optimizer consumes normalized JSON artifacts.

Reasoning:

- The current capture has 21 classes, 3,612 normalized records, no missing class records, no missing tab records, and no unknown essence-kind records.
- Structured fields are better than rendered text for legality, costs, prerequisites, and tab ownership.
- Scraping should be repeatable and auditable.

## Decision 2: Phase 1 Produces Projected DPS Index, Not Raw DPS

Status: accepted.

Theorycraft-only output must use projected indexes and confidence notes. It must not claim exact DPS.

Reasoning:

- Tooltip parsing and graph structure cannot prove hidden server formulas, proc normalization, target caps, resource starvation, or uptime.
- Raw DPS requires either empirical logs or a calibrated simulator.

## Decision 3: Optimizer Does Not Scrape

Status: accepted.

The optimizer must not open Ascension web pages, parse HAR files, or inspect Next Flight chunks. It loads normalized artifacts through a repository layer.

Reasoning:

- This keeps build logic testable without browser automation.
- It prevents schema drift from being confused with optimizer bugs.

## Decision 4: Current Python Optimizer Is a Prototype Monolith

Status: accepted.

`coa_optimizer_extensible.py` is a useful prototype, but Phase 1 should split it into modules for domain objects, repositories, legality, search, scoring, APL generation, logs, graph export, reports, and CLI.

Reasoning:

- The file already contains multiple conceptual modules.
- Production behavior needs smaller, tested units.

## Decision 5: APLs Are Data, Not Hard-Coded Rotation Text

Status: accepted.

APL generation should produce structured JSON plus SimC-like text. The structured form is the canonical internal representation.

Reasoning:

- Structured APLs can be simulated, edited, tested, and rendered.
- SimC-like text is useful for users and comparison to retail tooling, but text should not be the only internal format.

## Decision 6: Data-Driven Calibration Is Phase 2

Status: accepted.

Logs and addon data should calibrate theorycraft rankings after Phase 1 is stable. They should not be required to run the Phase 1 theorycraft release.

Reasoning:

- Users need value before a large log corpus exists.
- Calibration requires its own event schema, session metadata, and confidence model.

## Decision 7: Full Simulation Is Phase 3

Status: accepted.

A full event-driven simulator should come after theorycraft and empirical ingestion.

Reasoning:

- The simulator depends on stable normalized abilities, legal builds, APLs, and empirical tests for coefficients/procs.
- Building it before data contracts are stable would mix too many unknowns.

## Decision 8: Machine Learning Is Not a Foundation Phase

Status: accepted.

Do not use machine learning for Phase 1 or Phase 2 core logic. Use deterministic parsing, legality, scoring, APL generation, empirical calibration, and later simulation first.

Reasoning:

- There is not enough labeled data yet.
- ML would not replace legality rules, APL execution, or mechanics modeling.
- Later ML can help infer correction weights or player execution models after enough logs exist.

## Decision 9: Code Reuse From Retail Tools Requires License Review

Status: accepted.

Retail tools may guide architecture. Direct source copying requires an explicit license decision and attribution plan.

Reasoning:

- SimulationCraft uses GPL-3.0.
- WoWAnalyzer uses AGPL-3.0.
- Copying code without project-level license alignment can create avoidable legal and distribution constraints.

## Decision 10: Every Ranking Must Carry Provenance

Status: accepted.

Reports must include builder version, data capture date, source artifacts, scoring profile version, encounter profile, and evidence source.

Reasoning:

- CoA data can change.
- Meta rankings without provenance are hard to reproduce or debug.

## Decision 11: Rank Spending Uses Linear Cost Until Builder UI Proves Otherwise

Status: accepted.

Selected rank cost is modeled as node cost multiplied by selected rank. If official builder examples show a different per-rank model, the legal build engine should change and this decision should be superseded.

## Decision 12: Theory Scoring Profiles Are JSON Data

Status: accepted.

M1.4 scoring profiles live as JSON files so class/spec tuning can change without editing scoring code. The scorer owns mechanics for applying profile data, not individual class hard-coding.

## Decision 13: APL Generation Uses Structured Profiles

Status: accepted.

M1.5 APL generation uses `coa-apl-profile-v1` JSON profile data and emits `coa-apl-v1` structured JSON as the canonical artifact. SimC-like text is an export derived from structured APL data.

Reasoning:

- Every class/spec should use the same production APL generation engine.
- Class/spec behavior belongs in data profiles, not hard-coded Python branches.
- Phase 1 can generate theorycraft rotation scaffolds without SavedVariables, combat logs, gear snapshots, or simulator state.
- Structured APLs can later be edited, rendered, and executed by a simulator.

## Decision 14: M1.6 Meta Report Scope

Status: accepted.

- Default reports rank top 3 builds per reportable class/spec for one `baseline_single_target` encounter profile.
- Reportable specs are normalized non-shared talent trees with nodes.
- `Class` is a shared class pool included in each spec's legal node set.
- `None` and metadata-only tabs are not standalone report rows.
- Lower-level runs filter known `required_level` data and warn when class/trainer source data is incomplete.

## Decision 15: AscensionDB Enriches But Does Not Replace Builder Legality

Status: accepted.

M1.8 treats the CoA builder payload as authoritative for class/tab ownership, graph structure, prerequisites, AE/TE costs, and tab gates. AscensionDB is the preferred source for spell and item tooltip enrichment, buff/effect text, equipment text, linked spell/item IDs, and tooltip-level evidence.

Reasoning:

- The builder payload carries active builder graph data that DB pages do not expose as a coherent build graph.
- AscensionDB exposes richer spell and item tooltip payloads through `&power` endpoints.
- DB records can be missing, empty, permission-restricted, or named differently from builder nodes, so enrichment needs confidence and coverage rather than blind overwrites.

## Decision 16: Static Guides Render Canonical Data

Status: accepted.

M1.10 guide pages should be derived from canonical report JSON, normalized entries/classes, and asset manifests. HTML, CSS, and JavaScript may improve presentation, filtering, tooltips, and talent-tree interactions, but they must not become a separate source for legality, scoring, role inference, or simulation logic.

Reasoning:

- GitHub Pages requires a static-first presentation path.
- Player-facing guide UX should not make future data corrections harder to audit.
- CoA-style talent trees can be rendered from normalized row/column, edge, cost, rank, prerequisite, and level-gate fields without reusing the live builder runtime.
- Retail guide resources are useful information architecture references, but direct copying of layout, text, styling, or proprietary assets is out of scope.

## Decision 17: CoA Builder DOM/Screenshot Tree Parity Is Not Required

Status: accepted.

M1.11C separates the Ability Essence, Talent Essence, and level-passive lanes and renders talent trees from normalized row/column, edge, cost, rank, prerequisite, and level-gate data. Pixel- or DOM-level parity with the live CoA Builder was evaluated and judged unnecessary: the current normalized tree-generation method already renders faithfully across specs for desktop guide use. The manual browser-capture parity checklist (`tree-parity-checklist.md`) is retained only as an optional spot-check, not a required M1.11 exit item.

Reasoning:

- The normalized layout already produces correct, readable trees across all specs without the live builder runtime.
- Chasing exact builder DOM/screenshot parity adds capture and maintenance cost without improving guide usefulness.
- Keeping the checklist as an optional spot-check preserves a path to investigate if a future spec ever renders poorly.

## Decision 18: The WoW Client Is the Authoritative Mechanical Source; CoA Attribution Is Client-Native

Status: accepted (planned for M1.14).

The local Ascension CoA game client (MPQ→DBC plus `Data/Content/*.json`) is the authoritative source
for mechanical spell data and WoW systems constants, layered additively onto the existing pipeline.
db.ascension.gg is demoted from a canonical enrichment source to fallback-only for mechanical fields,
because it is demonstrably stale (spell `805775` returns the outdated *Fang Venom: Lifeblood* rather
than the current *Adrenal Venom*). The CoA Builder payload remains authoritative for the talent
graph, legality, and node descriptions (extends Decision 1 and Decision 15).

CoA attribution is derived from client-native signals — primarily archive-family membership
(`patch-C*` = CoA, `area-52/` = Area-52, `patch-W*` = Reborn), plus ID range and specialization/
skill-line markers. The CoA Builder payload is used only as a cross-validation oracle to measure the
attribution heuristic's precision/recall. It is never a whitelist gate.

**Amended (M1.14B, 2026-07-13).** The archive-family mechanism above does not work: `patch-C*`
contains only art assets (`Character/`, `Creature/` models/textures) — zero DBC files. The entire DBC
tier is unified tables shared by all game modes, so `effective_archive` says nothing about which mode
owns a row. CoA attribution is replaced with the **`CharacterAdvancement.dbc` registry** — the client's
own CoA advancement graph — as the primary signal: it achieves 100% unique-spell recall and, once the
alpha→display class rename is applied, 100% unique-spell class attribution against the Builder oracle
(see [client-advancement-schema.md](data/client-advancement-schema.md) and
[client-class-types-schema.md](data/client-class-types-schema.md)). `archive_family` is demoted to raw
provenance only (known uninformative for CoA-vs-other partitioning); skill-line membership and ID
range are retained only as a medium/low-confidence fallback for the small set of records absent from
the advancement graph. The principle is unchanged: the client is authoritative and current, and the
Builder is used only as a cross-validation oracle, never a whitelist gate.

Reasoning:

- Using the Builder as a whitelist would silently make it canonical over the client, discard the
  richer client-only data the Builder never exposed, and leave the tool dependent on a source that
  can drift or go offline.
- The client is current (CoA patch archives are updated in real time) and richer than any web source.
- Custom server-side scaling/proc numbers and 3.3.5 item stats are not fully present in client DBC;
  those gaps are scoped to a memory-bridge/API investigation spike and to later gear milestones.

**Redistribution (M1.14D, 2026-07-17).** `coa_wow_constants.json` and its manifest are client-derived
GameTable outputs and fall under the **same mandatory forward policy gate M1.14C records**: before
M1.16 consumes any client-derived output, or before any canonical public release, one explicit policy
decision must cover them consistently with `coa_client_spell_coa.jsonl` and `coa_mechanics.jsonl`. The
authored inputs D layers on top (rules, enum maps, axis policy, reference anchors, the class-axis
adjudication) are self-authored and tracked; only the merged client-derived snapshot is git-ignored.

## Decision 19: Phase 1 Uses a Deterministic Analytical Player-Power Model

Status: accepted (planned for M1.16).

Phase 1 replaces the current keyword/constant heuristics with a deterministic analytical model of WoW
player power — rating→% conversions at level, coefficient-based per-cast damage/heal, haste→GCD and
resource regen, crit/hit/expertise/armor, and DoT/HoT — labeled as projection. The full event-driven
Monte-Carlo simulator remains Phase 3 (Decision 7). The modeling core is split: its inputs
(mechanical fields and conversion primitives) are delivered by the client data foundation (M1.14),
and the engine that consumes them is a dedicated milestone (M1.16), with talent-tree correctness
(M1.15) between them.

Reasoning:

- A tool that presents authoritative-looking numbers from a mechanically hollow model is worse than
  no tool; the analytical model makes Phase 1 numbers defensible without a full simulator.
- Accurate modeling depends on accurate ability data, so it must follow the client data foundation.

## Decision 20: Client Extraction Uses a Replaceable Backend Behind a Narrow StormLib ctypes Binding

Status: accepted (planned for M1.14A).

Client MPQ extraction (`coa_client_extract`) reads through a project-owned `ArchiveBackend` protocol.
StormLib sits behind it via a narrow `stormlib_ctypes` surface (library discovery, minimal function
signatures, context-managed handles) wrapped by `stormlib_backend`; no raw C handle escapes the
ctypes module. Ascension-specific archive discovery, family filtering (`patch-C*` in; `area-52` and
`patch-W*` out), load order, and provenance live in an auditable `ArchivePlan` owned by CoA Codex —
StormLib applies patches, CoA Codex decides which and in what order. Every extracted record carries
full patch-chain provenance (`base_archive`, `patch_chain`, `effective_archive`, `sha256`), and the
manifest pins the tested StormLib version range.

StormLib is an extraction-time dependency only: it is never imported by the optimizer, report, or
guide-rendering paths, and it is not required by the default test suite (which runs against a fake
in-memory backend and synthetic fixtures), mirroring how Playwright is confined to capture. When
StormLib is unavailable the regenerate command **fails closed** — it writes no artifacts rather than
degrading. `mpyq` and external CLI tools are permitted only as diagnostic/cross-validation backends
and may never produce canonical client artifacts.

Reasoning:

- The correctness claims of M1.14 (correct load order, per-archive provenance, DBC schema-drift
  detection) require owning the parse in-process, not delegating it to an opaque tool.
- A replaceable backend keeps the versioned artifact — not the native library — as the lasting
  architecture, so a future Rust or other backend can be swapped in without changing DBC parsing or
  downstream contracts.
- A lower-confidence artifact is not acceptable when the missing capability is fundamental
  patch/decompression correctness, so silent fallback is disallowed.
- StormLib is MIT-licensed, so a system install or pinned source build carries no restrictive
  project-wide license obligation (contrast Decision 9).

## Decision 21: Decision 1 Supersession Is Staged and Per-Field, Not Wholesale

Status: accepted (planned for M1.15).

The CoA client advancement graph (`CharacterAdvancement.dbc`, extracted as `coa-client-advancement-v1`
— see [client-advancement-schema.md](data/client-advancement-schema.md)) is the candidate canonical
source for the talent graph and legality, superseding Decision 1's "Builder is the Phase 1 source of
truth" **by responsibility, one field at a time** (see the adapter field matrix in the
[M1.14B design](superpowers/specs/2026-07-13-m1-14-b-client-attribution-and-graph-design.md)), not
wholesale. The flip is **gated** on: (a) the node-level parity report, and (b) the semantic-layout
validation, both passing for the fields being flipped. Fields the client cannot yet supply keep their
existing source, explicitly marked. Until M1.15 performs the flip, the Builder remains the operative
graph authority and the client artifact is validated-but-not-consumed.

**Builder-as-discovery-aid boundary.** The Builder `entry_id` crosswalk is valuable for *generating* a
column-mapping hypothesis, but Builder agreement can **never** be the sole proof that decodes a field
and then "independently" validates parity against itself — that is circular. A Builder-proposed
mapping is recorded as `mapping_discovery_source: builder_crosswalk` and is only accepted when it also
passes evidence that does not reduce to the Builder: client-wide semantic ranges/distributions,
node-id-domain validation, graph invariants, current in-game UI/tooltip spot-checks, and
current-client-values winning on disagreement. **Builder values are never copied into the client
artifact** — only the client's own decoded cells are emitted.

Reasoning:

- A field the client has genuinely proven should not wait on every other field to decode before it can
  supersede the Builder; conversely, an undecoded field must not be silently promoted just because
  neighboring fields are ready.
- Per-field staging keeps the migration honest and auditable: `readiness.legality[field]` (Decision 22)
  and `full_builder_retirement_ready` in the parity report (`coa-builder-parity-v3`) expose exactly
  which responsibilities have flipped and which still fall back to the Builder.
- Allowing the Builder to validate a decode it also proposed would be circular; requiring independent
  evidence (ranges, graph invariants, UI spot-checks) keeps the client the true source of the proof.

## Decision 22: Client DBC Is the Canonical Offline Legality Source; Live Corrections Come From User-Reported Overrides, Not the Builder

Status: accepted (planned for M1.15).

The current client DBC is the canonical offline source for legality (AE/TE cost, gates,
prerequisites, level, rank), extending Decision 18 from mechanics to legality. It is **not** assumed
identical to live server enforcement — the server can hotfix costs, hidden prerequisites, scripted
rank behavior, or level gates the client does not reflect — so the precedence is:

    user-reported, reproducibly-verified live override
      >  current client DBC
      >  (Builder / stale JSON / AscensionDB — informational only, never authoritative)

The Builder is removed from the legality authority chain entirely: it is itself an offline,
possibly-stale source of unknown fidelity to the server, so a Builder disagreement is informational,
never authoritative, and never value-blocking. Live corrections are captured through a versioned,
reviewable **manual-override layer fed by user-reported inaccuracies** (the mechanism the public site
will expose; its implementation is a later milestone, not M1.14B). A proven client value is used until
such an override supersedes it.

Each client-vs-Builder legality difference is classified as: **(a) extraction/layout defect** — the
client field is not proven decoded correctly → that field stays **`unresolved`** (keeps the Builder
fallback, blocks flipping that field and `full_builder_retirement_ready`); **(b) verified
client-current difference** — client decoded to `high` confidence and simply differs from the Builder
→ accepted, client wins offline, field **`ready`**; **(c) representation difference** — same value,
different encoding → normalized, field **`ready`**; **(d) unresolved** — not yet decoded/classified →
field **`unresolved`**. Only (a) and (d) leave a field unresolved (per-field, not a global flip); a
genuine proven difference (b) is `ready`. An unresolved field never blocks `attribution_ready` or
`ownership_ready`.

Reasoning:

- The Builder is itself an unauthoritative scrape of unknown fidelity to the live server; keeping it
  in the legality authority chain would let a stale or wrong Builder value silently override a proven
  current client value.
- A four-way classification (rather than a binary match/mismatch) is what lets the parity report
  distinguish "we haven't decoded this yet" (blocks) from "the client is simply right and current"
  (does not block) — collapsing them would either stall the flip on values that are already correct,
  or ship an undecoded field as if it were proven.
- Routing live corrections through a versioned, user-reported override layer (rather than falling back
  to the Builder) keeps the authority chain honest: the client is default-canonical offline, and only a
  reproducibly-verified live report — not another offline scrape — can override it.

**Amended (M1.14B, 2026-07-14): generalized to OWNERSHIP — a client-only node adjudication, not just
legality values.** The real-client acceptance run proved `ownership_recall == 1.0`/
`unique_spell_recall == 1.0` (the Builder is fully covered, `builder_only_records == 0`) but found 2
CoA nodes only the current client has: `18821` (new spell 674, Witch Doctor) and `34451` (an
additional Guardian placement of existing spell 300534) — `raw_ownership_precision == 0.9994`. These
are not defects; per this Decision the client is already the canonical current source, so a
client-only node is adjudicated against the same four-way shape as the legality classes above,
renamed for ownership and applied to node *existence* rather than field *value*: **extraction_defect**
(↔ (a), blocks), **verified_client_current** (↔ (b), accepted — the client legitimately leads a stale
oracle), **representation_difference** (↔ (c), normalize+accept), **unresolved** (↔ (d), the default
for anything not curated — blocks). Classification is curated by hand in
`reports/client_extract/client_only_adjudication.json` (schema `coa-client-only-adjudication-v1`;
today it holds exactly the two records above, both `verified_client_current`), loaded by `regenerate`
via `--client-only-adjudication` and consumed by `build_parity_report`'s `client_only_classification`
(`{verified_client_current, representation_difference, extraction_defect, unresolved}`, each a list of
`{node_id, spell_id, class, reason}`). `ownership_ready` is now:

    ownership_ready = builder_only_records == 0
                      AND hard_identity_mismatches == 0
                      AND every client_only record classified verified_client_current | representation_difference
                      AND taxonomy/count/non-empty guards

Readiness comes from adjudication, never from recall alone — an unadjudicated client-only node still
blocks, preserving the parity safety net, while a curated one no longer forces a stale oracle over an
authoritative client. The raw counts stay visible regardless (`raw_ownership_precision`,
`builder_coverage_recall`), and `builder_refresh_recommended: true` flags whenever any client-only node
exists, signaling the Builder scrape should be refreshed against the current client.

**Identity canonicalization (M1.14B, 2026-07-14).** The node-identity check (the anchored
`(spell_id, class)` tuple, Decision 21) generalizes the same way: 708 of 3,612 matched nodes had a
class-label difference that is pure formatting — client CamelCase vs Builder spaced (`WitchDoctor`/
`Witch Doctor` 159, `WitchHunter`/`Witch Hunter` 191, `KnightOfXoroth`/`Knight of Xoroth` 156,
`SunCleric`/`Sun Cleric` 202) — zero spell-ID divergence among them. The class label is canonicalized
with a versioned, narrow, deterministic transform before the identity comparison:
`canonical_class_label(v) = "".join(unicodedata.normalize("NFKC", v).split()).casefold()`, version
string `class_label_normalization: "nfkc-casefold-remove-whitespace-v1"`. So `WitchDoctor` and
`Witch Doctor` canonicalize equal — a `representation_difference` (class (c) above): normalized for
comparison, accepted, and kept visible (`raw_identity_mismatches`, `representation_differences`,
`representation_difference_pairs` as `{"Client → Builder": count}`). A semantic class change (e.g.
`SunCleric` vs a hypothetical `Moon Cleric`) or any spell-ID divergence still canonicalizes unequal and
is a **hard identity mismatch** (`hard_identity_mismatches`, sampled in `hard_identity_mismatch_sample`)
that blocks ownership. This is distinct from, and narrower than, the 3 curated *semantic* aliases
(Bloodmage/Felsworn/Templar — [client-class-types-schema.md](data/client-class-types-schema.md)): the
canonicalizer only strips whitespace and case/Unicode-normalization form, never punctuation, and never
fuzzy-matches. It is comparison-only — the client artifact always ships its own native label (e.g.
`WitchDoctor`); only the Builder's spaced form is normalized for parity, never rewritten into the
artifact.

With both generalizations, `ownership_ready` can now be `true` on the real-client capture while
`full_builder_retirement_ready` stays `false` — the roll-up (Decision 21) also requires
`adjacency_ready` and every required `legality[field]` to reach `ready`, which remain gated on their
own per-field decode-confidence proof and are unaffected by ownership/identity adjudication. The
parity report schema is now `coa-builder-parity-v3` (was `-v2`): `client_only_classification`,
`builder_refresh_recommended`, `raw_identity_mismatches`, `hard_identity_mismatches`,
`representation_differences`, `class_label_normalization`, `representation_difference_pairs`, and
`hard_identity_mismatch_sample` replace the old `identity_mismatches`/`identity_mismatch_sample`; the
raw `builder_coverage_recall` and `raw_ownership_precision` fields are added alongside the retained
`ownership_recall`/`ownership_precision` (never hidden or redefined).

Reasoning (amendment):

- A client-only node needs the same non-collapsing four-way treatment as a legality value difference:
  an unexplained client-only node could be a genuine extraction defect (e.g. a mis-scoped join) just as
  easily as the client legitimately outrunning a stale Builder scrape — collapsing both into "ownership
  fails" would block a healthy client forever, while collapsing both into "ownership passes" would hide
  a real defect.
- Curation (a small human-reviewed JSON file) rather than an automatic heuristic is deliberate: telling
  "new client content" apart from "extraction bug" is a judgment call that needs a reason recorded per
  node, not a rule that could rubber-stamp a defect as `verified_client_current`.
- Canonicalizing identity narrowly (NFKC + whitespace-strip + casefold only) keeps the safety net for
  real drift intact: it absorbs exactly the CamelCase-vs-spaced formatting difference the current
  client and Builder happen to use, while a semantic rename or spell-ID divergence — the cases that
  actually matter — still hard-blocks, unlike a fuzzy-matching approach that could mask a real mismatch.

## Decision 23: Client Mechanics Are Extracted Under a Proven, Client-Bound Policy With Per-Value Proof, and Published Transactionally

Status: accepted (M1.14E0).

Client spell mechanics are extracted from raw `RecordView` cells under a human-reviewed spell-layout
policy (`coa_client_extract/data/spell_layout_v1.json`) that is **bound to the exact client bytes it
was proven against**, and published as an immutable, hash-bound generation. Records are
`coa-client-spell-v2`; the v1 records and their table-level `schema_match_confidence_by_dbc` field
certification are retired.

- **Proven + hash-bound + client-bound policy.** The policy carries, per emitted value,
  `{cell, kind, layout, interpretation, promotion, evidence}`, plus `anchor_set`/`enum_policy` (each
  self-hashed), a `bound` block (`client_build` + per-DBC sha256), and an explicit `reviewed` flag. A
  loader validates schema/identity, proof-state and `kind` domains, in-bounds + per-table-unique cells,
  `normalized ⇒ verified`, distinct power-of-two school bits, and hash self-consistency.
- **Recon proposes, never writes.** `mechanics-recon` discovers every emitted column by scanning
  (never echoing the policy's cell), and emits a `proposed_policy_delta`. Its lifecycle is
  `blocked (3) → review_required (4) → verified (0)`. A human applies the delta and flips `reviewed` —
  recon never self-approves. See [spell-mechanics-recon-schema.md](data/spell-mechanics-recon-schema.md).
- **Non-bypassable client-binding hold.** `regenerate` re-opens the client, re-hashes `Spell.dbc`, and
  emits canonical v2 artifacts only when the policy is `reviewed` and its `bound` matches the opened
  client (`ClientBindingError` → exit 3 otherwise). It never promotes values proven against a different
  client.
- **Two decode gates.** A value is decoded only when its proof is `semantic_promotion_eligible`
  (integrity ∧ layout ∧ interpretation all `verified`) AND, for enums/masks, the specific value is
  in-domain. The **raw is always retained.** The unknown-symbol amendment: an unseen `power_type` or
  school bit sets `decoded_reason: "value_out_of_domain"`, withholds the normalized value, and is
  tallied in the extract's `unknown_symbol_inventory` — masks accept any valid bit combination
  (`20 == 4|16` passes); the artifact stays valid.
- **Join observations, honestly stated.** A side-table-joined value is a `JoinObservation` with a
  composed proof over all parts and honest states (`resolved` / `not_applicable` / `unresolved`). A
  plain FK-validity scan cannot uniquely resolve the join index columns on the real client, so E0 ships
  the joins un-adjudicated (raw-only, null cells); value-anchor disambiguation is M1.14E1.
- **Transactional publication.** `regenerate` (producer) publishes a UUID generation
  (`gen-<uuid4>/`, `exist_ok=False`) with a binding manifest (superset of the ten v1 fields + generation
  identity + `predecessor_generation_id` + `published_at` + source/policy/anchor/enum hashes +
  `unknown_symbol_inventory`) and a validated pointer written last. Both a Python and a Node resolver
  re-validate pointer schema, containment, manifest hash, and every child's path/sha256/bytes/records/
  schema. The Node build (consumer) **requires** `--client-extract-pointer`; the fixed-path projection
  is fallback-only. Retention is a separate best-effort maintenance op — publish never prunes. See
  [client-extract-generation-schema.md](data/client-extract-generation-schema.md).

Reasoning:

- The real client's current `Spell.dbc` offsets differ from stock 3.3.5a (`power_type@41` not `@110`,
  `school_mask@225` not `@139`), so an assumed layout silently emits wrong values — a policy proven by
  scanning against ground-truth anchors and bound to the client bytes is the only safe substrate.
- Withholding a normalized value while retaining its raw keeps the artifact honest and valid in the
  presence of CoA custom resources (unseen power types) without guessing their meaning — their live
  resolution is deferred (M1.14G), the static substrate is proven here.
- Transactional generations make regeneration collision-safe and every consumed byte re-validated,
  so a half-written or drifted extract can never be silently consumed as canonical.

## M1.14E0R — correctness & AscensionDB sunset

- **Evidence ≠ authorization.** A field's proof (integrity/layout/interpretation) is evidence only;
  emission is authorized separately by `promotion == "normalized"` in the reviewed policy. A `raw_only`
  field retains its raw substrate but never populates a normalized value, and the Node consumer
  independently re-derives the biconditional (eligible ⇔ populated) from the pinned policy, so a producer
  bug cannot smuggle an unauthorized value past the boundary.
- **The generation manifest is authoritative — and it is not a child.** `gen-<uuid>/manifest.json` **is**
  `coa-client-extract-manifest-v3`; it holds the child registry and is hashed by the pointer, so it cannot
  list or hash itself. Publication is transactional: stage → **candidate** manifest (never
  pointer-resolvable) carrying a `candidate_trust_sha256` over every trust-critical field → validate the
  candidate by path in **both** Python and Node (per-child + a streaming cross-child merge-join) → **final**
  manifest that reproduces the identical trust digest (only `publication_state`/`validation`/`budget` may
  move) → pointer written **last** under a process lock.
- **One full-topology hard hold, shared by recon and regenerate.** A single verifier opens every required
  table (sha256 + full 5-field header + member/archive/patch-chain + density + key-uniqueness) and the
  expected-absent set, and matches the reviewed policy's structured `bound` **facet-for-facet**. A canonical
  build never promotes values proven against a different client, and recon and regenerate can never diverge
  on "the client we proved against."
- **AscensionDB is not a canonical source.** `db.ascension.gg` is removed from the canonical mechanics
  pipeline entirely (the `ascension_db` reconciliation tier, the enrichment/apply scripts, the DB identity
  gate, and every guide-layer link). A canonical build is **pointer-only and network-free**; the only
  surviving touch is an opt-in, image-download-only utility (`download-spell-icons.mjs`) a human runs by
  hand. A network-trap test enforces this.
- **Missing ≠ default.** A not-yet-extracted cost/cooldown/gcd is `null` (unknown), never a fabricated
  `0`/`1500`/`{}`. `coa-mechanics-v2` carries `field_readiness` (see
  [field-readiness-schema.md](data/field-readiness-schema.md)); the consumer interlock fails **closed**
  (`QuantitativeScopeUnready`) unless heuristic estimates are explicitly authorized.
- **Streaming within a real three-part budget.** The producer streams record-by-record; `within_budget`
  requires ALL of serialized bytes + subprocess peak RSS + elapsed under ceiling. A full real-client
  `regenerate` (not just recon) is measured and recorded within budget.
- **Client-native icons.** Guide icons resolve only from the client `coa-client-spell-icons-v1` catalog by
  spell_id (a converted row renders its bundle asset; anything else a placeholder) — never a remote or
  cached-DB image.
- **Explicit versioning.** Every touched artifact carries an explicit schema version that hard-rejects the
  prior one: `coa-client-spell-v3`, `coa-client-spell-projection-v3`, `coa-client-extract-manifest-v3`,
  `coa-mechanics-v2`, `coa-spell-layout-v2`.
