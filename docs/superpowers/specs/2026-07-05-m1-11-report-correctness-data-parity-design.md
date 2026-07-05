# M1.11 Report Correctness and Data Parity Design

Date: 2026-07-05

Status: quick fixes implemented; deeper parity and simulation work planned

## Goal

M1.11 hardens the M1.10 guide site from "player-facing first pass" into a more correct guide system. The milestone exists because several M1.10 outputs are visually useful but not yet faithful enough to the CoA Builder, live role intent, or guide-site rotation expectations.

M1.11 should fix low-risk presentation defects immediately and split the complex issues into dedicated data and algorithm work:

- Report index roles and filtering.
- User-facing spec renames.
- Tooltip HTML table rendering.
- Front-page theorycraft disclaimer.
- Authoritative or curated role taxonomy, including `ranged_dps`.
- Role-specific scoring indexes instead of ranking every role by DPS.
- CoA Builder talent tree parity.
- Exact level-by-level talent path generation.
- Respectful, cache-aware AscensionDB asset scraping.
- Better build diversity selection.
- Rotation generation that behaves like a guide-ready APL/simulation output rather than a category summary.

## Current Quick-Fix Status

Implemented in the current M1.11 branch:

- Main guide index groups specs under Tank, Healer, Support, Caster DPS, Ranged DPS, and Melee DPS.
- Role filter buttons are multi-select and visually active/inactive.
- Front page includes a theorycrafting disclaimer that names CoA Builder, `db.ascension.gg`, and future AscensionLogs compatibility.
- Visible "medium confidence" badges were removed from cards and spec hero sections. Confidence remains machine/provenance data.
- Tooltip sanitizer allows safe table tags from AscensionDB tooltip HTML.
- Legacy user-facing spec renames are applied in JSON/MD/HTML serialization while preserving source spec names for internal joins.
- `ranged_dps` was added to role taxonomy, stats, gear, rotation wording, CLI choices, and report filters.
- Curated role overrides now keep Harvest Reaper and Soul Reaper as DPS.

## Research Summary

### Local Findings

The current report has enough structure to support better guides, but several fields are still heuristics:

- `coa_meta.roles` resolves a player-facing role and broad engine role, but the role data source is local curated/inferred data, not an authoritative CoA role table.
- `projected_dps_index` still names the primary score for every role, even when the role is healer, tank, or support.
- `coa_meta.guide_tree` uses normalized row/column/connection fields, but the rendered trees do not match the CoA Builder layout closely enough. The Builder separates class ability essence, spec talent essence, and automatic level passives.
- The current leveling path orders selected nodes by required level and grid position. That is not the same as a level-by-level recommendation from 10 to 60.
- `coa_scraper/scripts/enrich-ascensiondb.mjs` fetches spell tooltip payloads, but icon/image asset capture is still incomplete.
- `coa_meta.rotation_loops` turns APL categories into readable text. It does not yet simulate many viable sequences or produce an Icy Veins/Archon-style priority guide.

### External Tooling Patterns

SimulationCraft's APL model remains the best architecture reference for rotation logic: actions are priority lists evaluated from top to bottom until an available action is found, with support for sub-action-lists and conditions. CoA should model APL semantics, not hard-code rotations in report rendering.

WoWAnalyzer is useful as a separation-of-concerns reference. Its value is not in copying AGPL code, but in the model: ingest logs, compute metrics, and produce gameplay suggestions separate from the simulator.

Icy Veins and Method explain rotations as compact priority systems with opener, cooldown, maintenance, and conditional rules. They do not show every ability in the kit.

Archon is a useful data-presentation reference: guide claims are tied to context, update recency, parse population, and content filters. CoA does not have that empirical data yet, so the report must be clear when output is theory-only.

### Source Priority

Use sources in this order:

1. CoA Builder payload/runtime data for legality, tree ownership, node coordinates, connections, rank costs, prerequisites, essence type, and level gates.
2. AscensionDB for canonical spell/item names, tooltip HTML/text, icons, item/weapon/armor details, effects, and linked records.
3. Curated local metadata for roles/spec renames/live sanity corrections when no authoritative source exists.
4. Inference from tags, tooltips, APL categories, damage schools, resources, and mechanics records.
5. Logs/AscensionLogs/addon data in Phase 2 for tuning and confidence.

## M1.11 Sub-Milestones

### M1.11A: Report Index and User-Facing Metadata Quick Fixes

Status: implemented.

Scope:

- Six role headers in requested order.
- Multi-select role filters.
- Front-page disclaimer.
- Remove visible confidence badges from default guide cards.
- User-facing legacy spec renames.
- Tooltip table rendering.

Exit criteria:

- Static guide index shows all six role sections.
- Filter buttons can show combined role sets, such as healer + support.
- JSON/MD/HTML use renamed spec names while preserving `source_spec_name`.
- Tooltip tables render as tables, not escaped `<tr>`/`<td>` text.

### M1.11B: Authoritative Role Map and Role-Specific Objective Indexes

Status: planned.

Scope:

- Create a role map artifact with provenance per class/spec.
- Distinguish `melee_dps`, `ranged_dps`, `caster_dps`, `tank`, `healer`, and `support`.
- Replace player-facing "Projected DPS Index" with role-specific names:
  - DPS: Projected Damage Index.
  - Healer: Projected Healing Index.
  - Tank: Projected Survival/Threat Index.
  - Support: Projected Support Index.
- Keep the current numeric score field backward-compatible during a schema transition, but add `primary_index`, `primary_index_label`, and `objective_breakdown`.

Role objective features:

- DPS: damage effects, uptime, cooldown efficiency, target count, resource loops, proc conversion.
- Healer: healing throughput, recovery cooldowns, HoT/shield uptime, mana efficiency, ally targeting.
- Tank: mitigation uptime, effective health, self-healing, threat tags, control, defensive cooldown coverage.
- Support: buff/debuff uptime, group resource effects, crowd control, damage/healing amplification, utility density.

Exit criteria:

- Healers, tanks, and support specs are not sorted, labeled, or explained as DPS specs.
- Every role resolution has source, confidence, and evidence.
- Known incorrect roles, including Harvest and Soul Reaper, are covered by tests.

### M1.11C: CoA Builder Talent Tree Parity

Status: planned.

Scope:

- Capture Builder layout data and screenshots for representative class/spec pairs.
- Recreate three separate visual lanes:
  - Ability Essence class tree.
  - Talent Essence spec tree.
  - Automatic level-gated passives in a straight line.
- Compare Stalking Venomancer in the local report against CoA Builder Stalker Venomancer as the first parity target.
- Preserve exact node spacing, row/column assignment, and connections when source coordinates exist.

Implementation direction:

- Use normalized source row/column only if it is proven to match Builder output.
- If the Builder runtime computes layout from a richer graph, scrape that layout payload directly.
- Store parity fixtures as JSON plus screenshots outside generated report commits unless a small fixture is needed for tests.
- Add a visual-parity checklist with screenshot paths and source capture dates.

Exit criteria:

- Stalking Venomancer tree matches CoA Builder structure closely enough for manual screenshot comparison.
- The renderer can show class tree, spec tree, and level passives separately.
- Build legality feedback uses the same tree ownership and prerequisite rules as the optimizer.

### M1.11D: AscensionDB Asset and Canonical Data Scraper

Status: planned.

Scope:

- Extend scraper enrichment to capture icons/images and richer spell/item records from `db.ascension.gg`.
- Use conditional refresh and content hashing to avoid unnecessary requests.
- Respect AscensionDB resources with bounded concurrency, backoff, and manifest-driven skips.

Cache policy:

- Store a manifest per URL with URL, parser version, fetched timestamp, HTTP status, ETag, Last-Modified, content hash, parsed record hash, and output asset paths.
- Send `If-None-Match` and `If-Modified-Since` when previous headers exist.
- If headers are absent, compare content hashes and only rewrite outputs when parsed data changes.
- Add `--stale-days`, `--force`, `--limit`, and `--concurrency` options.
- Default concurrency should be conservative for public refreshes.

Exit criteria:

- Spell/talent icons render from local static assets when DB data exposes them.
- Item, weapon, armor, effect, and tooltip records have stable schema outputs.
- Re-running the scraper does not rewrite unchanged large artifacts.
- The default report generator never calls AscensionDB at page load or hover time.

### M1.11E: Rotation Simulation and Guide-Ready Priority Output

Status: planned.

Scope:

- Evolve generated APLs into executable rotation candidates.
- Simulate many high-performing action permutations under role-specific objectives.
- Emit one concise guide rotation per build: usually 4-12 abilities/rules, with opener, core loop, cooldowns, proc/status conditions, and role-specific defensive/healing/support rules.

Architecture:

- Keep `coa_meta.apl` as the canonical priority-list representation.
- Extend the combat engine/APL interpreter to model buffs, debuffs, cooldowns, resources, procs, target count, and GCD windows.
- Add a rotation candidate generator that mutates priority order, thresholds, and opener sequence inside legal APL constraints.
- Score rotation candidates with role objectives, not only damage.
- Keep raw APL JSON available for audit, but render a player-facing rotation guide.

Exit criteria:

- Rotation sections no longer read like category lists.
- The report can explain why a smaller subset of abilities is in the core loop.
- Rotation reliability reflects mechanics data quality, proc uncertainty, and simulation coverage.

### M1.11F: Leveling Path and Build Diversity Correctness

Status: planned.

Scope:

- Generate exact talent/ability learn order from level 10 through 60.
- Alternate essence awards starting with Ability Essence at level 10, then Talent Essence, continuing through level 60.
- Treat level passives as automatic unlocks that do not spend essence.
- Prioritize the most valuable legal choices for the selected build as early as possible.
- Choose two or three recommended builds by playstyle cluster, not by near-duplicate score rank.

Build diversity rules:

- Compute a playstyle fingerprint from active abilities, role objective contributions, APL actions, damage schools, resource loops, stealth/burst/summon/pet/DoT/melee/ranged/caster/control tags, and major cooldown structure.
- Keep only one representative from each close cluster.
- Pick representatives from a top performance band, such as within a tuned percentage or robust z-score range of the top reliable candidate.
- Reject builds that score highly but lack a consistent rotation unless they are clearly labeled as experimental.

Exit criteria:

- Switching recommended builds updates tree selection, leveling order, rotation, stats, gear, and warnings for that build.
- Duplicate poison-DoT loop variants collapse into one recommendation unless a variant has a meaningfully different loop.
- A stealth/burst build and a DoT loop build can both appear if both are competitive and reliable.

### M1.11G: Calibration and Live-Meta Sanity Layer

Status: planned; partly P2-gated.

Scope:

- Add a curated live-meta sanity layer for known severe theory/live mismatches.
- Track known examples: Runemaster DPS, Primalist DPS, Knight of Xoroth DPS, Felsworn, Cultist, Barbarian, and Venomancer relative ranking concerns.
- Prepare AscensionLogs/addon compatibility for Phase 2 calibration.

Exit criteria:

- Reports can label when a result is "uncalibrated theorycraft" versus "calibrated by logs".
- Confidence becomes sensitive to source completeness, role-map quality, mechanics coverage, simulation coverage, and empirical sample size.
- The system does not overfit anecdotal live rankings as hard truth without provenance.

## Non-Goals

- Do not copy GPL/AGPL code from SimulationCraft, WoWAnalyzer, or other projects without a license decision.
- Do not call AscensionDB from generated GitHub Pages pages.
- Do not claim observed DPS/HPS/tank value before log or simulation calibration exists.
- Do not build account/user workflows in M1.11.
- Do not move Vercel personal upload simulation earlier than Phase 2 unless the local simulator and input schemas are stable.

## P2/P3 Boundaries

P1/M1.11 should finish static guide correctness, source scraping, and role-aware theory output.

P2 should add:

- AscensionLogs or addon data ingestion.
- Vercel free-tier serverless upload endpoint for SimC-style CoA text.
- Personal character/build simulation requests with strict timeouts.
- Empirical calibration and confidence tuning.

P3 should add:

- Full encounter simulation depth.
- More expensive rotation optimization.
- Log-driven spec guide prose and generated sections from strict templates.
