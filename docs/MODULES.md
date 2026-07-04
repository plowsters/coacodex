# Module Responsibilities

Each module should own one concern and communicate through versioned files, typed Python objects, or HTTP/API contracts. Current scripts can be moved into these modules incrementally.

## Scraper and Capture Module

Current files:

- `coa_scraper/scrape-coa-network.mjs`
- `coa_scraper/data/`
- `coa_scraper/data/snapshots/`
- `coa_scraper/data/raw/`

Responsibilities:

- Open the official Ascension CoA builder.
- Capture HAR, interesting network responses, raw JavaScript/HTML/JSON, and page snapshots.
- Record browser/capture metadata.
- Avoid interpreting talent legality or scoring.

Inputs:

- Builder URL.
- Capture configuration, including viewport and manual or automated class/tab navigation plan.

Outputs:

- HAR file.
- Raw response files.
- Initial/final page HTML.
- Runtime dumps.
- Capture manifest.

Non-responsibilities:

- Normalized schema design.
- Build scoring.
- Combat log parsing.
- Web frontend rendering.

## Payload Extraction Module

Current files:

- `coa_scraper/scripts/extract-coa-builder-payload.mjs`
- `coa_scraper/scripts/summarize-coa-payload.mjs`
- `coa_scraper/scripts/inspect-coa-payload-shape.mjs`

Responsibilities:

- Extract Next Flight chunks from captured HTML.
- Locate the builder payload.
- Persist the raw builder payload.
- Generate payload shape and summary reports.
- Detect schema drift early.

Inputs:

- Captured HTML and runtime dumps.

Outputs:

- `coa_builder_payload.json`
- `coa_builder_summary.json`
- `coa_payload_shape.json`
- human-readable shape reports

Non-responsibilities:

- Tag inference.
- Scoring.
- Combat mechanics.

## Normalization Module

Current files:

- `coa_scraper/scripts/export-coa-normalized.mjs`
- `coa_scraper/scripts/build-class-profile-input.mjs`
- `coa_scraper/dist/`

Responsibilities:

- Convert raw builder records into normalized, versioned domain records.
- Preserve raw source records.
- Infer secondary features such as tags, damage schools, resources, and text-derived hints.
- Emit validation reports.

Inputs:

- `coa_builder_payload.json`

Outputs:

- `coa_entries.jsonl`
- `coa_entries.pretty.json`
- `coa_classes.json`
- `coa_essence_caps.json`
- normalization report
- class profile input summary

Non-responsibilities:

- Deciding optimal builds.
- Parsing combat logs.
- Running simulations.

## Schema and Analyzer Module

Current files:

- `coa_scraper/scripts/coa-rg-json-summary.mjs`
- `coa_scraper/scripts/coa-diagnose.sh`
- `coa_scraper/scripts/extract-class-roster.mjs`
- `coa_scraper/scripts/extract-rendered-node-labels.mjs`

Responsibilities:

- Validate normalized data completeness.
- Compare payload-derived class/tab data with rendered labels.
- Detect missing classes, tabs, unknown essence kinds, duplicate IDs, broken prerequisites, and schema drift.
- Generate reports for future maintainers.

Inputs:

- Raw payload.
- Normalized dist artifacts.
- Rendered page snapshots.

Outputs:

- Diagnostic Markdown or text reports.
- JSON summaries suitable for CI checks.

Non-responsibilities:

- Build scoring.
- Web UI.

## Domain Repository Module

Current files:

- `TalentRepository` and `TalentNode` in `coa_optimizer_extensible.py`

Target package:

- `coa_meta/domain/`
- `coa_meta/repository/`

Responsibilities:

- Load versioned normalized records.
- Provide typed access to classes, tabs, nodes, and essence caps.
- Hide JSONL/JSON storage details from higher-level modules.
- Validate schema version before use.

Inputs:

- Normalized artifacts.

Outputs:

- Typed domain objects.
- Lookup indexes by class, tab, node ID, spell ID, name, and dependency graph.

Non-responsibilities:

- Legal build search.
- Scoring.

## Build Legality and Search Module

Current files:

- `BuildRules`, `BuildState`, `SearchConfig`, and `BuildOptimizer` in `coa_optimizer_extensible.py`
- most of `coa_graph_optimizer.py`

Target package:

- `coa_meta/builds/`

M1.3 implementation files:

- `coa_meta/domain.py`
- `coa_meta/repository.py`
- `coa_meta/builds.py`
- `coa_meta/search.py`
- `coa_meta/explain.py`

Responsibilities:

- Validate selected builds.
- Generate legal build candidates.
- Explain legality failures.
- Run beam search or other deterministic search strategies.
- Export graph data for analysis.

Inputs:

- Domain repository objects.
- Level, AE/TE budgets, encounter constraints, selected nodes.

Outputs:

- Legal build states.
- Validation explanations.
- Graph exports.

Non-responsibilities:

- Combat simulation.
- Empirical calibration.
- UI rendering.

## Theory Scoring Module

Current files:

- `WeightProfile`, `HeuristicScoringStrategy`, `generic_profile`, and `stalker_profile` in `coa_optimizer_extensible.py`

Target package:

- `coa_meta/scoring/`

M1.4 implementation files:

- `coa_meta/profiles.py`
- `coa_meta/scoring.py`
- `coa_meta/data/scoring_profiles/*.json`

Responsibilities:

- Convert build features into projected score components.
- Keep profiles data-driven and inspectable.
- Generate score explanations.
- Emit projected DPS index with confidence and uncertainty.

Inputs:

- Legal build states.
- Encounter profile.
- Spec profile.
- Optional empirical corrections.

Outputs:

- Score breakdowns.
- Ranked builds.
- Confidence notes.

Non-responsibilities:

- Deciding whether a build is legal.
- Parsing raw HTML or logs.

## Rotation and APL Module

Current files:

- `APLRule`, `GenericRotationStrategy`, `StalkerRotationStrategy`, and helpers in `coa_optimizer_extensible.py`

Target package:

- `coa_meta/apl/`

M1.5 implementation files:

- `coa_meta/apl.py`
- `coa_meta/apl_profiles.py`
- `coa_meta/data/apl_profiles/*.json`

Responsibilities:

- Generate baseline priority lists for selected builds.
- Export SimC-like APL text and structured JSON.
- Support encounter branches, target-count checks, spender thresholds, cooldown alignment hints, and opener sections.
- Accept user-edited APLs later.

Inputs:

- Selected build nodes.
- Encounter profile.
- Spec profile.

Outputs:

- APL JSON.
- SimC-like text.
- Rotation confidence notes.

Non-responsibilities:

- Executing the APL. That belongs to the simulator.

## Log Ingestion Module

Current files:

- `Wow335CombatLogAdapter`, `CustomAddonJSONAdapter`, and helpers in `coa_optimizer_extensible.py`

Target package:

- `coa_meta/logs/`

Responsibilities:

- Parse `WoWCombatLog.txt`.
- Parse addon SavedVariables exports converted to JSON.
- Normalize events into a common schema.
- Segment fights.
- Attribute pets and guardians when possible.
- Preserve raw events for audit.

Inputs:

- Built-in combat logs.
- Addon exports.
- Player/session filters.

Outputs:

- Normalized events.
- Fight summaries.
- Spell metrics.

Non-responsibilities:

- Build legality.
- Theory scoring without calibration.

## Addon Module

Current files:

- `CoADataLogger/CoADataLogger.lua`
- `CoADataLogger/CoADataLogger.toc`

Responsibilities:

- Capture player and pet combat events available to the 3.3.5 client.
- Capture session labels, gear, stats, combat ratings, and talent data exposed by the client.
- Store data in SavedVariables.
- Keep in-game overhead low.

Inputs:

- In-game slash commands.
- Client combat log events.

Outputs:

- `CoADataLoggerDB` SavedVariables table.

Non-responsibilities:

- Running optimizations in game.
- Producing final rankings.

## Empirical Store and Calibration Module

Current files:

- Prototype metrics are embedded in `CombatMetrics`.

Target package:

- `coa_meta/data_store/`
- `coa_meta/calibration/`

Responsibilities:

- Persist imported fights and snapshots.
- Derive empirical spell/build metrics.
- Calibrate theory scores and simulator assumptions.
- Track sample size, variance, and confidence.

Inputs:

- Normalized log events.
- Character snapshots.
- Selected build data.

Outputs:

- Calibration tables.
- Empirical rankings.
- Blended model corrections.

Non-responsibilities:

- Browser capture.
- Web UI controls.

## Simulator Module

Current status:

- Not implemented.

Target package:

- `coa_meta/sim/`

Responsibilities:

- Model combat time, GCD, cooldowns, casts, resources, buffs, debuffs, periodic ticks, procs, pets, target count, and encounter events.
- Execute structured APLs.
- Run deterministic and Monte Carlo simulations.
- Emit DPS, variance, cast timelines, stat weights, and rotation diagnostics.

Inputs:

- Ability model.
- Character stats.
- Legal build.
- APL.
- Encounter profile.

Outputs:

- Simulated DPS reports.
- Timelines.
- Rotation issue diagnostics.

Non-responsibilities:

- Capturing data from Ascension's website.
- Collecting logs in game.

## Web Frontend Module

Current status:

- Not implemented.

Responsibilities:

- Browse classes, tabs, nodes, builds, APLs, and reports.
- Import normalized artifacts and logs through backend APIs.
- Compare builds by source: theory, empirical, simulated, blended.
- Make confidence and assumptions visible.

Inputs:

- Backend API responses.

Outputs:

- Interactive reports.
- Shareable static report exports.

Non-responsibilities:

- Owning legality, scoring, or simulation logic.
