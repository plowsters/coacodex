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
- Join builder records with the published client generation's mechanics while preserving builder legality as the source of truth. (Through M1.11 this join carried optional AscensionDB tooltip enrichment; M1.14E0R **removed** it.)
- Emit validation reports.

Inputs:

- `coa_builder_payload.json`

Outputs:

- `coa_entries.jsonl`
- `coa_entries.pretty.json`
- `coa_classes.json`
- `coa_essence_caps.json`
- `coa_source_level_report.json`
- `coa_metadata_tab_report.json`
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

M1.11E guide-ready rotation files:

- `coa_meta/action_catalog.py`: ability/action catalog shared by rotation generation and simulation.
- `coa_meta/rotation_candidates.py`: bounded APL candidate generation.
- `coa_meta/rotation_simulation.py`: bounded APL simulation used to score candidates.
- `coa_meta/rotation_scoring.py`: role-objective scoring of simulated rotations.
- `coa_meta/rotation_guides.py`: guide-ready priority/opener/cooldown sections (`coa-rotation-guide-v1`).
- `coa_meta/rotation_loops.py`: compact core-loop/playstyle signatures.

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

## Backend Trust and QA Module

Current files:

- `coa_meta/backend_trust.py`
- `coa_meta/data/live_sanity_watchlist.json`

Responsibilities:

- Score coarse backend-only trust components (role certainty, mechanics coverage, rotation coverage, live-sanity watchlist) for report builds (M1.11G).
- Emit a maintainer-only `coa-backend-trust-v1` sidecar via `--write-backend-trust`, kept out of the player-facing guide.
- Carry low-confidence, `not_user_facing` watchlist entries for known theory/live mismatch risks until Phase 2 logs exist.

Non-responsibilities:

- Rendering trust scores or watchlist concerns in guide HTML.
- Claiming empirical DPS/HPS/mitigation before Phase 2 calibration.

## Simulator Module

Current status:

- M1.9 first-pass scaffold exists in `coa_meta/combat/`, `coa_meta/simulation.py`, and `coa_meta/apl_interpreter.py`.

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

- Implemented across M1.10 and M1.11 as a static GitHub Pages-friendly guide-site renderer over generated report JSON.

Current files:

- `coa_meta/guide_builder.py`, `coa_meta/guide_models.py`: assemble a guide-site model from `coa-meta-report-v1`.
- `coa_meta/guide_rendering.py`, `coa_meta/guide_writer.py`: render and write the index, meta report, and per-spec HTML plus static assets.
- `coa_meta/guide_tree.py`, `coa_meta/builder_tree_layout.py`: CoA-style talent-tree rendering and optional CoA Builder layout ingestion.
- `coa_meta/guide_assets.py`, `coa_meta/report_assets.py`, `coa_meta/guide_tooltips.py`: icon/asset resolution and hover-tooltip payloads.
- `coa_meta/display_names.py`: user-facing spec renames over preserved source names.

Responsibilities:

- Render a guide index and individual class/spec guide pages from `coa-meta-report-v1`.
- Provide player-facing Overview, Builds, Talent Tree, Rotation, Stats, Gear, Abilities/Talents, Warnings, and Data Notes sections.
- Use the client generation's icon catalog, normalized icon paths, and local scraper assets for spell/talent presentation. Remote AscensionDB spell links were **removed** by M1.14E0R; an unresolved icon renders an honest placeholder rather than an off-site image.
- Render CoA-style talent trees from row/column, edge, rank, cost, level, and prerequisite data.
- Provide hover tooltips, metric explanations, role filters, encounter filters, and responsive navigation.
- Compare builds by projected source: theory, empirical, simulated, or blended as later phases add them.
- Make confidence, assumptions, provenance, and warnings visible without making the main UX read like an implementation report.

Inputs:

- `coa-meta-report-v1` JSON.
- Normalized entries/classes artifacts when a richer static page needs spell/talent metadata not embedded in the report.
- Optional scraper asset manifests and local icon/media assets.

Outputs:

- Static HTML/CSS/JS reports suitable for GitHub Pages.
- Tooltip payloads and asset manifests.
- Shareable spec-guide pages.

Non-responsibilities:

- Owning legality, scoring, or simulation logic.
- Reusing the live CoA builder runtime.
- Fetching remote data at view time unless explicitly configured for a future dynamic app.

## Meta Report Runner

- `coa_meta.reporting`: expands class/spec scopes, applies eligibility rules, runs legal search, scoring, APL generation, and writes canonical report data.
- `coa_meta.report_assets`: resolves optional local scraper assets for static HTML output.
- `coa_meta.roles`, `coa_meta.objectives`: role resolution and role-specific objective indexes (M1.11B), backed by `coa_meta/data/spec_roles.json` and `coa_meta/data/role_overrides.json`.
- `coa_meta.leveling_path`, `coa_meta.build_diversity`: exact level-by-level build paths and playstyle-clustered build diversity (M1.11F).

M1.6 reports use `coa-meta-report-v1`. JSON is canonical; Markdown and HTML are derived views. M1.10 and M1.11 extend derived views into a guide-site presentation without making HTML the source of truth.

## CLI and Packaging

- `coa_meta.cli`: thin argparse command adapter. It constructs `MetaRunConfig`, calls `MetaReportRunner`, and writes requested report formats.
- `coa_meta.__main__`: enables `python -m coa_meta`.
- `pyproject.toml`: package metadata and package-data inclusion for built-in scoring/APL profiles.
