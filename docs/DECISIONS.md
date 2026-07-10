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

Reasoning:

- Using the Builder as a whitelist would silently make it canonical over the client, discard the
  richer client-only data the Builder never exposed, and leave the tool dependent on a source that
  can drift or go offline.
- The client is current (CoA patch archives are updated in real time) and richer than any web source.
- Custom server-side scaling/proc numbers and 3.3.5 item stats are not fully present in client DBC;
  those gaps are scoped to a memory-bridge/API investigation spike and to later gear milestones.

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
