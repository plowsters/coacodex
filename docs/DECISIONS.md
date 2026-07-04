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
