# Development Roadmap

This roadmap defines production-sized phases. A phase is ready to ship only when every milestone in that phase is complete, documented, tested, and usable by a non-author through the public CLI, API, addon, or web interface for that phase.

## Phase 1: Theorycrafting Meta Release

Purpose: produce a production-usable theorycrafting tool that ranks projected builds and rotations from structured Ascension CoA builder data. This phase must prioritize the scraped/HAR-analyzed JSON and reports as the source of truth. It must not claim observed DPS or definitive live meta.

Primary output: projected meta reports with legal top builds, rotation scaffolds, confidence labels, assumptions, and machine-readable JSON.

### Milestone 1.1: Reproducible Builder Data Pipeline

Requirements:

- Convert `coa_scraper/` into a reproducible capture and extraction module.
- Keep Playwright/HAR capture out of the optimizer.
- Document the full command sequence from browser capture to `coa_entries.jsonl`.
- Produce an artifact manifest for each capture with builder slug, builder id, max level, capture date, source URL, script versions, and checksum of each generated artifact.
- Preserve raw payload data alongside normalized records.
- Add schema drift checks for the Next Flight extraction and builder payload shape.

Exit criteria:

- A fresh capture can regenerate `coa_builder_payload.json`, `coa_classes.json`, `coa_entries.jsonl`, `coa_essence_caps.json`, and reports without manual edits.
- Missing class, missing tab, and unknown essence-kind counts are explicitly reported.
- A future agent can identify whether a change is from Ascension data drift or local parser changes.

### Milestone 1.2: Versioned Normalized Domain Schema

Requirements:

- Define a JSON schema for normalized class, tab, node, essence cap, and payload provenance records.
- Include required fields for build legality: `class_id`, `class_name`, `tab_id`, `tab_name`, `entry_id`, `spell_id`, `entry_type`, `essence_kind`, `ae_cost`, `te_cost`, `required_tab_ae`, `required_tab_te`, `required_level`, `max_rank`, `required_ids`, `connected_node_ids`, row/column, passive/start state, tags, damage schools, resources, and raw record.
- Split inferred fields from source fields. Tags, damage schools, resources, coefficients, target caps, and role hints must record how they were inferred.
- Add validation tests using the currently captured Vol'Jin Alpha data.

Exit criteria:

- The optimizer refuses invalid or unversioned normalized data unless explicitly run in an unsafe inspection mode.
- Schema docs describe which fields are source-provided and which are inferred.

### Milestone 1.3: Legal Build Engine

Requirements:

- Split build legality out of `coa_optimizer_extensible.py` into a dedicated package module.
- Model AE/TE budgets, required level, required node IDs, tab AE/TE gates, free starting/passive closure, class-tab ownership, and rank spending.
- Validate build legality against exported builder data and spot-checked builder UI examples.
- Represent legal build state as serializable data, not CLI text.

Exit criteria:

- Given a selected build, the engine can explain why it is legal or list every failed rule.
- Beam search and direct build validation use the same legality implementation.
- Tests cover prerequisite failures, tab-gate failures, budget failures, zero-cost closure, and multi-rank spending.

### Milestone 1.4: Theory Scoring Engine

Requirements:

- Replace hard-coded Stalker-only scoring with data-driven scoring profiles.
- Add role and encounter profile templates: single-target DPS, 2-target cleave, 5-target AoE, solo, tank, healer/support.
- Score source features separately: tab investment, role tags, damage schools, resources, explicit named synergies, inferred coefficients, cooldowns, DoTs, target count, summon/pet behavior, defensive value, and utility value.
- Produce a projected DPS index, not raw DPS.
- Produce confidence and uncertainty fields for every result.
- Include score explanations so users can see why a node or build ranked highly.

Exit criteria:

- Every class/spec profile can be scored without custom code.
- Stalker Venomancer can still have a curated profile, but that profile is data plus rules, not logic embedded in the optimizer.
- Reports label results as "theorycraft projection" and print assumptions.

### Milestone 1.5: Rotation and APL Scaffold Generator

Requirements:

- Model rotations as priority lists, following the SimulationCraft APL idea: check actions from top to bottom and execute the first action whose conditions are true.
- Generate baseline APLs from ability features: maintain DoTs, use cooldowns, build resources or marks, avoid overcapping, spend at thresholds, respect execute windows, and branch for target count.
- Keep APL generation separate from simulation. APLs should be serializable, inspectable, and editable.
- Support SimC-like text export and JSON export.

Exit criteria:

- For every generated meta build, the report includes an APL scaffold.
- Single-target and AoE APLs are generated independently.
- APL output includes confidence notes when a condition was inferred from tooltip text rather than source fields.

### Milestone 1.6: Meta Report Runner

Requirements:

- Add a `meta` command that runs all classes, all discovered spec tabs, and all supported encounter profiles.
- Rank builds by projected DPS index and confidence.
- Emit JSON, Markdown, and a static HTML report.
- Include top builds, selected nodes, projected score breakdown, APL, assumptions, data provenance, and warnings.
- Separate "spec ranking" from "build ranking" so the tool can show the best build per spec and also class-wide top builds.

Exit criteria:

- A single command can generate a complete theorycraft meta report from `coa_entries.jsonl`.
- Reports make it impossible to confuse theorycraft index with observed DPS.

### Milestone 1.7: Packaging, CLI, and Tests

Requirements:

- Split the Python prototype into an installable package.
- Keep CLI commands thin. The library should own business logic.
- Add unit tests for schema loading, legality, scoring, APL generation, and report output.
- Add fixture data from a small subset of current normalized records.
- Add a smoke test that runs the full Phase 1 pipeline against the current captured dist.

Exit criteria:

- `python -m coa_meta meta ...` or equivalent runs the release path.
- Tests pass without requiring browser automation.
- Browser capture tests are separate and can be skipped when Chromium is unavailable.

Implementation note:

- The release path is `python -m coa_meta meta ...`.
- Browser capture remains part of `coa_scraper/` and is not required for package tests.

### Milestone 1.8: Source Level and AscensionDB Enrichment

Status: complete in the current repo.

Requirements:

- Enrich normalized builder records with AscensionDB spell tooltip data where it is more canonical than builder-rendered text.
- Keep builder legality fields as the source of truth for AE/TE, prerequisites, and tree ownership.
- Record source categories, source confidence, effective required level, and enrichment warnings per record.
- Keep the default report path network-free after artifacts have been generated.

Exit criteria:

- `npm --prefix coa_scraper run pipeline:m1.8` regenerates normalized, enriched, and manifest artifacts.
- Validation reports identify source-level uncertainty instead of silently treating unknown levels as reliable.

### Milestone 1.9: Combat Engine and Theorycraft Completion

Status: complete as a first pass in the current repo.

Requirements:

- Add a deterministic combat engine scaffold with time, events, RNG, combat state, and APL execution boundaries.
- Add mechanics inference/repository hooks so tooltip-derived mechanics can be separated from hand-authored mechanics data.
- Add stat priority, gear recommendation, calibration, and simulation-result fields to the meta report schema.
- Add role-aware report generation so tank and healer/support specs are not forced through pure DPS scoring.
- Add P2 planning for Vercel free-tier personal upload/simulation APIs.

Exit criteria:

- Package tests cover the combat engine scaffold, mechanics schema, calibration hooks, role-aware reports, stat priorities, and gear recommendations.
- Reports remain labeled as theorycraft/simulated according to evidence source.

### Milestone 1.10: Static Guide Site and Player-Facing Report UX

Status: implemented as a first pass. M1.11 tracks correctness, parity, and calibration hardening discovered during guide review.

Purpose: turn the Phase 1 meta report from an analyst table into a GitHub Pages-friendly class/spec guide site for CoA players.

Requirements:

- Replace the dense landing table with a class/spec guide index, role filters, encounter filters, and prominent links into individual spec guides.
- Redesign the HTML report with a fel/void green-purple theme, wider responsive layouts, sticky guide navigation, readable cards, hover tooltips, and mobile-safe spacing.
- Use player-facing WoW guide language. Move CoA Meta Analyzer internals into concise tooltip explanations for metrics such as Confidence, Projected DPS Index, and data warnings.
- Generate individual spec guide pages with Overview, Builds, Talent Tree, Rotation, Stats, Gear, Abilities/Talents, Warnings, and Changelog-style data provenance sections.
- Integrate icons/images from normalized `icon` fields, scraper assets, AscensionDB links, and later class/spec media assets. Every spell/talent with a spell ID should link to its `db.ascension.gg` spell page.
- Render selected builds in a CoA-builder-like tree using normalized row/column, connection, rank, cost, level, and prerequisite fields. The tree should support hover tooltips and level/AE/TE legality feedback without requiring the live builder runtime.
- Order build recommendations by when abilities and talents become available while still showing the level-60 build target.
- Show the stat priority disclaimer once per spec, not once per stat entry.
- Split weapon and armor recommendations into "Best targets for this spec" and "Available to this class/spec", with icons where data exists.
- Replace category-only rotation summaries with a core repeatable loop, opener notes, cooldown usage, defensive/healing/support priorities, and reliability warnings.
- Hide the Warnings section entirely when there are no warnings.
- Expand role taxonomy to `melee_dps`, `caster_dps`, `tank`, `healer`, and `support`. Prefer authoritative CoA/Ascension source data if available; otherwise record metadata-inference provenance.
- Change default build selection from raw top three to two or three reliable, distinct playstyles selected from the top performance band.

P1 sub-milestones:

- M1.10A Guide information architecture: static route structure, guide page templates, navigation, player-facing copy rules, and metric tooltip definitions. Status: implemented. Design: [M1.10A/B Guide Information Architecture and Asset Integration](superpowers/specs/2026-07-05-m1-10-a-b-guide-ia-assets-design.md).
- M1.10B Asset and tooltip integration: icon resolver, class/spec media catalog, AscensionDB hotlinks, hover tooltip payloads, missing-asset fallback policy, and asset manifest updates. Status: implemented. Plan: [M1.10A/B Guide IA and Asset Integration](superpowers/plans/2026-07-05-m1-10-a-b-guide-ia-assets.md).
- M1.10C CoA-style talent tree renderer: static tree layout from normalized row/column/edges, rank/cost badges, level gating, AE/TE legality checks, hover tooltips, and lightweight JavaScript for interactions. Status: implemented. Design: [M1.10C/D Talent Tree Renderer and Build Diversity](superpowers/specs/2026-07-05-m1-10-c-d-tree-diversity-design.md).
- M1.10D Rotation and build diversity heuristics: playstyle fingerprints from selected nodes/APL actions, performance-band filtering, reliability scoring, and user-facing build comparison labels. Status: implemented. Plan: [M1.10C/D Talent Tree Renderer and Build Diversity](superpowers/plans/2026-07-05-m1-10-c-d-tree-diversity.md).
- M1.10E Role taxonomy refinement: source-backed role mapping where possible, metadata inference fallback, separate melee/caster/healer/support/tank UI roles, and broad engine-role routing for scoring/APL compatibility. Status: implemented. Design: [M1.10E/F Role Taxonomy and Gear/Stats Presentation](superpowers/specs/2026-07-05-m1-10-e-f-role-gear-stats-design.md).
- M1.10F Gear/stat presentation: single stat disclaimer, grouped stat sections, best-vs-available gear sections, icon support, and explicit source warnings for unsupported gear slots. Status: implemented. Plan: [M1.10E/F Role Taxonomy and Gear/Stats Presentation](superpowers/plans/2026-07-05-m1-10-e-f-role-gear-stats.md).

P2/P3 follow-ups:

- Sim/log-backed stat priorities, weapon/armor target weights, and rotation reliability should wait for Phase 2 data and Phase 3 simulations.
- Personal SimC-style upload and bounded simulations belong to Milestone 2.6.
- Cheap small/medium-model guide prose generation should wait until guide schemas are stable and can be constrained by strict templates, provenance, and review gates.
- Full dynamic build sharing, user account workflows, and large-scale comparison tools belong to Phase 4 or later.

### Milestone 1.11: Report Correctness, Data Parity, and Simulation Hardening

Status: implemented as a first pass. All P1 sub-milestones (M1.11A–G) are implemented and merged to `main`. CoA Builder tree DOM/screenshot parity (originally an M1.11C exit item) was evaluated and judged unnecessary — the current normalized tree-generation method renders faithfully across specs — so its manual browser-capture check is an optional spot-check, not a blocker. The remaining first-pass areas (backend trust and rotation reliability) are intentionally Phase 2-gated on empirical logs. Design: [M1.11 Report Correctness and Data Parity](superpowers/specs/2026-07-05-m1-11-report-correctness-data-parity-design.md). Plan: [M1.11 Implementation Plan](superpowers/plans/2026-07-05-m1-11-report-correctness-data-parity.md).

Purpose: correct the guide output where M1.10 is visibly useful but not yet faithful enough to the CoA Builder, intended roles, or guide-site rotation expectations.

Requirements:

- Keep the front page grouped by Tank, Healer, Support, Caster DPS, Ranged DPS, and Melee DPS with multi-select role filters.
- Keep the front-page theorycraft disclaimer visible: outputs are based on CoA Builder and AscensionDB data, with AscensionLogs compatibility planned for more accurate tuning if CoA remains available.
- Preserve source spec names internally while applying user-facing legacy renames in JSON, Markdown, and HTML.
- Treat confidence as provenance/internal data unless it becomes genuinely sensitive enough to be useful to players.
- Replace DPS-only labels and sorting for tanks, healers, and support specs with role-specific objective indexes.
- Build an authoritative or curated role map with provenance before relying on inference for high-confidence role labels.
- Recreate CoA Builder tree structure accurately: separate Ability Essence class tree, Talent Essence spec tree, and automatic level passive lane.
- Generate exact level-by-level build paths from level 10 through 60, alternating Ability Essence and Talent Essence and respecting gates.
- Extend AscensionDB scraping to icons/images, items, weapons, armor, effects, and tooltip data with conditional requests, content hashing, and bounded concurrency.
- Render DB tooltip tables safely as tables.
- Upgrade rotation generation from category summaries to guide-ready priority output backed by APL execution and role-objective simulation.
- Improve recommended build diversity by clustering playstyle/rotation fingerprints and selecting one strong representative per meaningful playstyle.
- Add calibration hooks for known theory/live mismatches and prepare AscensionLogs/addon data integration.

P1 sub-milestones:

- M1.11A Report index and metadata quick fixes. Status: implemented.
- M1.11B Authoritative role map and role-specific objective indexes. Status: implemented as a first pass. Design: [M1.11B Role Map and Role-Specific Objective Indexes](superpowers/specs/2026-07-05-m1-11-b-role-objectives-design.md). Plan: [M1.11B Implementation Plan](superpowers/plans/2026-07-05-m1-11-b-role-objectives.md).
- M1.11C CoA Builder talent tree parity capture and renderer separation. Status: implemented. Renderer separation and normalized tree layout render faithfully across specs; CoA Builder DOM/screenshot parity was judged unnecessary (see [DECISIONS.md](DECISIONS.md) Decision 17), so the browser-capture checklist is an optional spot-check rather than a required exit item. Design: [M1.11C CoA Builder Talent Tree Parity](superpowers/specs/2026-07-05-m1-11-c-builder-tree-parity-design.md). Plan: [M1.11C Implementation Plan](superpowers/plans/2026-07-05-m1-11-c-builder-tree-parity.md). Checklist: [Tree Parity Checklist](tree-parity-checklist.md).
- M1.11D Cache-aware AscensionDB asset and canonical data scraper. Status: implemented as a first pass. Design: [M1.11D AscensionDB Asset and Canonical Data Cache](superpowers/specs/2026-07-06-m1-11-d-ascensiondb-asset-cache-design.md). Plan: [M1.11D Implementation Plan](superpowers/plans/2026-07-06-m1-11-d-ascensiondb-asset-cache.md).
- M1.11E Rotation simulation and guide-ready priority output. Status: implemented as a first pass. Design: [M1.11E Rotation Simulation and Guide-Ready Priority Output](superpowers/specs/2026-07-06-m1-11-e-rotation-simulation-guide-output-design.md). Plan: [M1.11E Implementation Plan](superpowers/plans/2026-07-06-m1-11-e-rotation-simulation-guide-output.md).
- M1.11F Exact leveling path and build diversity clustering. Status: implemented as a first pass. Design: [M1.11F Exact Leveling Path and Build Diversity Correctness](superpowers/specs/2026-07-06-m1-11-f-leveling-path-build-diversity-design.md). Plan: [M1.11F Implementation Plan](superpowers/plans/2026-07-06-m1-11-f-leveling-path-build-diversity.md).
- M1.11G Backend verification and trust heuristic. Status: implemented as a first pass; user-facing empirical calibration remains P2-gated. Design: [M1.11G Backend Verification and Trust Heuristic](superpowers/specs/2026-07-06-m1-11-g-backend-trust-heuristic-design.md). Plan: [M1.11G Implementation Plan](superpowers/plans/2026-07-06-m1-11-g-backend-trust-heuristic.md).

Exit criteria:

- The generated guide no longer presents non-DPS specs through DPS-specific labels.
- Recommended-build talent trees render faithfully across specs from normalized layout data. Pixel-level CoA Builder DOM/screenshot parity was evaluated and judged unnecessary (see [DECISIONS.md](DECISIONS.md) Decision 17); the manual browser-capture check in [tree-parity-checklist.md](tree-parity-checklist.md) is retained as an optional spot-check.
- Icons and canonical DB tooltip/item records are generated from local cached assets without page-load network calls.
- Recommended builds are meaningfully distinct and remain inside a documented performance/reliability band.
- Rotation sections are concise player guidance, not full-kit category dumps.
- Full tests pass and the real artifact smoke command can generate JSON, Markdown, and HTML reports.

### Phase 1 Continuation: Public Release and Systems Correctness (M1.12–M1.20)

The M1.11 first pass is useful but not yet a defensible public resource: it depends on a stale
db.ascension.gg source, its calculators do not model WoW's actual power systems, and it has visible
correctness/UX gaps. Milestones M1.12–M1.20 take the tool to a public GitHub Pages release whose
numbers are grounded in the real game systems. Full decomposition, findings, and strategic decisions
are in [M1.12–M1.20 Public-Release and Systems-Correctness Roadmap](superpowers/specs/2026-07-06-m1-12-to-m1-20-public-release-roadmap-design.md).

- **M1.12 Public-Release UI Quick Fixes.** Status: implemented. Icons on nodes and spec cards
  (AscensionDB hotlink), select-to-include role filter, updated disclaimer, header GitHub link,
  footer, and removal of leveling-path boilerplate. No engine/data changes. Design:
  [M1.12 UI Quick Fixes](superpowers/specs/2026-07-06-m1-12-public-release-ui-quick-fixes-design.md).
  Plan: [M1.12 Implementation Plan](superpowers/plans/2026-07-06-m1-12-public-release-ui-quick-fixes.md).
- **M1.13 Fel/Void Site Redesign.** Status: planned. Externally sourced Claude Design fel/void
  redesign; M1.12 wiring is inherited and restyled. Assets land later in an uncommitted project-root
  folder.
- **M1.14 Client DBC Data Foundation.** Status: planned; decomposed into sub-milestones M1.14A–F.
  Extract authoritative mechanical spell data and WoW conversion primitives from the CoA client
  (MPQ→DBC and loose `Data/Content/*.json`); client-native CoA attribution with the Builder payload
  as a cross-validation oracle; sunset stale db mechanical enrichment; test-suite integrity audit;
  memory-bridge/API spike. Extraction reads through a project-owned `ArchiveBackend` behind a narrow
  StormLib ctypes binding, fails closed without StormLib, and keeps the versioned artifact as the
  architecture (Decision 20). Umbrella design:
  [M1.14 Client DBC Data Foundation](superpowers/specs/2026-07-06-m1-14-client-dbc-data-foundation-design.md).
  - **M1.14A Client Extraction Core.** Status: planned; specced. `coa_client_extract` module,
    `coa-client-spell-v1` / `coa-client-content-v1` artifacts, header-driven WDBC reader with
    schema-drift detection, auditable archive plan, and synthetic-fixture test tiers. Design:
    [M1.14A Client Extraction Core](superpowers/specs/2026-07-10-m1-14-a-client-extraction-core-design.md).
  - **M1.14B Client Attribution and CoA Advancement Graph.** Status: code-complete (native StormLib
    integration and local-client acceptance tests pending). Supersedes the
    archive-family/ID-range attribution sketch in the umbrella: extracts `CharacterAdvancement.dbc`
    (the client's own CoA advancement graph) as `coa-client-advancement-v1`, node-level Builder-parity
    proven (100% unique-spell recall/attribution against the Builder oracle), plus
    `coa-client-class-types-v1`/`coa-client-tab-types-v1`/`coa-client-essence-v1` and the filled
    `coa_attribution` participation block on `coa-client-spell-v1`. Emits the node-level parity report
    (`coa-builder-parity-v2`) with the scoped, per-field `readiness` object (Decision 21). Extracts and
    proves the graph/legality; does not rewire the legality/tree pipeline to consume it — that's
    M1.15 (Decision 21/22). Schema docs:
    [client-advancement-schema.md](data/client-advancement-schema.md),
    [client-class-types-schema.md](data/client-class-types-schema.md). Design:
    [M1.14B Client Attribution and CoA Advancement Graph](superpowers/specs/2026-07-13-m1-14-b-client-attribution-and-graph-design.md).
    Plan: [M1.14B Implementation Plan](superpowers/plans/2026-07-13-m1-14-b-client-attribution-and-graph.md).
  - **M1.14C** reconciliation + db sunset · **M1.14D** WoW constants · **M1.14E** test-suite audit ·
    **M1.14F** memory-bridge/API spike. Delineated in the umbrella; each gets its own spec when next
    in line.
- **M1.15 Talent-Tree Correctness.** Status: planned. Full AE/TE essence spend to the target level;
  granular 10–60 level slider; consistent level-gating across all sections; mutually exclusive
  shared-node choices; leveling path never skips a level. **Per-field Builder supersession (Decision
  21):** M1.15 consumes the M1.14B `coa-client-advancement-v1` graph and its `coa-builder-parity-v2`
  parity report — each `readiness.legality[field]` that reached `ready` may independently supersede
  the Builder for that field alone, while a field still `unresolved` keeps the Builder fallback until
  decoded; `full_builder_retirement_ready` is the roll-up that gates full Builder retirement, staying
  false while any required attribution/ownership/adjacency/legality responsibility is unresolved.
  - **M1.15 sub-milestone: Level-by-level build validation.** Decode `CharacterAdvancementEssence`
    (extracted raw, undecoded semantics, as `coa-client-essence-v1` in M1.14B — see
    [client-class-types-schema.md](data/client-class-types-schema.md)) per-level progression — the
    feature that flips `readiness.leveling_progression_ready` to `true` — and validate a build's AE/TE
    spend against per-level essence availability at each level, rather than only the max-level caps
    (AE 26 / TE 25). M1.14B deliberately leaves this gated: it emits the raw essence table and reports
    `leveling_progression_ready: false` without blocking any max-level readiness dimension or
    `full_builder_retirement_ready`.
- **M1.16 Analytical Player-Power Model.** Status: planned. Deterministic engine: rating→% at level,
  coefficient-based per-cast damage/heal, haste→GCD and resource regen, crit/hit/expertise/armor,
  DoT/HoT. Rewire scoring and rotation simulation to consume real numbers. Full event-driven
  simulation remains Phase 3.
- **M1.17 Rotation Quality.** Status: planned. Derive true core loops from the model; build-archetype
  taxonomy beyond "DoT loop"; concise opener/priority/cooldown/role sections.
- **M1.18 Gear/Stat Interaction and Breakpoints.** Status: planned. Model-derived stat weights per
  level; haste/other breakpoints that flip build ranking; leveling stat scaling; item stat sourcing
  where AtlasLoot lacks Ascension gear.
- **M1.19 Multi-Build Selection Re-tune.** Status: planned. Revisit the "too strict" performance-band
  and diversity selection once model-backed scores exist.
- **M1.20 Public-Resource Hardening.** Status: planned. GitHub Pages deploy pipeline, CI, regression
  snapshots, changelog-as-currency drift verification, contribution docs.

## Phase 2: Data-Driven Calibration Release

Purpose: make the tool learn from real combat data. Phase 2 uses combat logs and addon snapshots to calibrate the Phase 1 theorycraft model. It still should not require a full simulator, but it should correct weights, proc assumptions, uptime assumptions, and target-count behavior from evidence.

Primary output: data-calibrated meta reports labeled by data source, sample size, encounter type, build version, gear/stat profile, and confidence.

### Milestone 2.1: Addon Data Collection v1

Requirements:

- Expand `CoADataLogger/` into a supported addon module.
- Add a bounded AscensionLogsCompanion compatibility probe before building a full adapter: collect one CoA `WoWCombatLog.txt`, search for `ALC_CI_v1` payloads, decode one payload if present, and verify whether it contains CoA class/spec/essence state rather than only legacy Ascension CharacterAdvancement data.
- Capture sessions with player, realm, timestamp, level, current build identifier if available, selected talents if exposed by the client, gear links, base/effective stats, combat ratings, AP/RAP/SP/crit, and combat events.
- Capture player pets and guardians when they can be reliably attributed to the player.
- Add event sampling controls and session labels so users can run repeatable target dummy tests.
- Document install, commands, SavedVariables path, and privacy considerations.

Exit criteria:

- A user can capture one labeled fight, reload/logout, and produce a parseable SavedVariables export.
- The AscensionLogsCompanion probe is documented as viable, not viable for CoA, or deferred pending a sample log.
- The exported data can be mapped to Phase 1 normalized spells by spell ID or normalized spell name.

### Milestone 2.2: Combat Log and SavedVariables Ingestion

Requirements:

- Split log parsing into dedicated adapters.
- Parse `WoWCombatLog.txt` and addon JSON/SavedVariables exports into a common event schema.
- If the Milestone 2.1 probe proves viable, add an `AscensionLogsCompanionAdapter` that reassembles embedded combatant-info chunks from combat log rows and normalizes them to the same snapshot schema as `CoADataLogger`.
- Segment fights by combat boundaries, target dummy labels, boss encounters, or manual session labels.
- Normalize spell names, spell IDs, source GUIDs, pet ownership, damage events, aura applications/removals, misses, interrupts, absorbs, crits, periodic ticks, and resource events when present.
- Preserve raw event references for auditability.

Exit criteria:

- The same analysis code can consume built-in combat logs and addon exports.
- Parser output has tests for spell damage, periodic damage, swings, misses, aura events, and pet attribution.

### Milestone 2.3: Empirical Metrics Store

Requirements:

- Add a local data store for parsed fights, actor snapshots, spell summaries, build selections, and provenance.
- Track data by CoA builder version, capture date, class, spec/tab, selected build, gear/stat profile, encounter label, target count, and source type.
- Support import, deduplication, and re-analysis.
- Keep personally identifying data optional or redacted.

Exit criteria:

- Multiple logs can be imported without overwriting each other.
- Reports can filter by class, spec, encounter, player, target count, and date.

### Milestone 2.4: Calibration Engine

Requirements:

- Calibrate Phase 1 theory features from observed logs: spell damage share, cast frequency, crit rate, DoT uptime, tick interval, proc rate, target hits, resource starvation, cooldown usage, and dead-time.
- Distinguish model corrections from player execution quality.
- Produce per-spell and per-build confidence scores based on sample size and variance.
- Keep calibration additive: theorycraft results still work when no data is available.

Exit criteria:

- A build scored with logs shows which theory assumptions were corrected by evidence.
- The tool can explain when a result is data-poor rather than silently overfitting.

### Milestone 2.5: Data-Driven Meta Reports

Requirements:

- Extend the `meta` command to support `--source theory`, `--source logs`, and `--source blended`.
- Generate rankings stratified by encounter type, target count, fight duration bucket, gear/stat band, and player execution quality.
- Include sample size, median, mean, variance, confidence interval or equivalent uncertainty, and outlier handling notes.
- Keep theory, simulation, and empirical rankings visually and semantically distinct.

Exit criteria:

- The user can generate a data-driven Stalker Venomancer report from local logs.
- The same report format can later scale to all classes and specs.

### Milestone 2.6: Personal Simulation Upload API

Requirements:

- Add a serverless API target suitable for Vercel free-tier deployment.
- Accept uploaded SimC-style text exports for a user's own character, gear, build, and APL inputs.
- Parse uploads into the same local profile/build/gear DTOs used by the CLI.
- Run bounded personal simulations with strict request size, duration, iteration, timeout, and concurrency limits.
- Return JSON results that the GitHub Pages frontend can render without requiring account state.
- Keep uploads ephemeral by default; do not persist character text, combat logs, or personally identifying data unless a later explicit consent workflow is added.

Exit criteria:

- A user can paste or upload SimC-style text in the web UI and receive a bounded personal simulation result from a Vercel-hosted function.
- The backend rejects oversized, malformed, or unsupported inputs with clear machine-readable errors.
- Free-tier constraints are documented, including expected timeout and iteration limits.

## Phase 3: Event-Driven Simulator Release

Purpose: add a deterministic and Monte Carlo-capable simulator for projected DPS numbers. This phase should model mechanics directly instead of relying only on tooltip heuristics or logs.

Milestones:

- Ability parser for coefficients, flat damage, weapon damage, duration, tick interval, cooldown, cost, cast time, charges, target caps, and proc text.
- Combat state engine for time, GCD, cooldowns, resources, buffs, debuffs, DoT ticks, pets, target count, movement assumptions, and encounter events.
- APL interpreter compatible with Phase 1 generated APL JSON and SimC-like text output.
- Repeated simulation iterations with variance reporting.
- Rotation search that mutates priorities, thresholds, cooldown alignment, and opener rules.
- Calibration bridge that uses Phase 2 data to correct tooltip-derived assumptions.

Exit criteria:

- Reports can emit simulated DPS under stated gear/stat and encounter assumptions.
- Simulated DPS remains labeled separately from empirical DPS.

## Phase 4: Web Product and Workflow Release

Purpose: provide a usable UI for browsing data, running reports, comparing builds, importing logs, and sharing outputs.

Milestones:

- Web frontend for class/spec exploration, build graph inspection, APL display, and meta reports.
- Backend API for normalized data, legal build validation, meta runs, imports, and report retrieval.
- Build import/export support for Ascension builder links if the format can be extracted.
- Static report publishing for shareable theorycraft and data-driven reports.
- User workflow docs for "I have only followed guides" use cases.

Exit criteria:

- A non-developer can inspect Stalker Venomancer, compare single-target versus AoE builds, and understand why the tool recommends each build.

## Phase 5: Community Meta Operations Release

Purpose: make the project sustainable as CoA data changes and community logs grow.

Milestones:

- Scheduled capture jobs or documented manual recapture process for each Ascension builder update.
- Regression dashboard for schema drift, class counts, missing fields, and score shifts.
- Community log import workflow with consent and anonymization.
- Versioned release notes for model changes and data changes.
- Reviewer workflow for curated spec profiles and APL corrections.

Exit criteria:

- New builder data can be ingested without breaking historical reports.
- Meta shifts can be traced to data changes, model changes, or empirical evidence.
