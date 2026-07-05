# M1.10 Guide Site and Report UX Design

Date: 2026-07-05

Implementation status: M1.10A/B and M1.10C/D are implemented in the current repo. M1.10E/F remains planned.

## Goal

M1.10 turns the generated meta report into a static, GitHub Pages-friendly CoA guide site. The report should feel like a player guide first and an analyzer artifact second. The canonical JSON can remain technical, but the HTML should explain choices in WoW player language and reserve analyzer terms for tooltips.

## Reference Patterns

Reviewed guide resources:

- Icy Veins class/spec guides: left-side guide navigation, clear section hierarchy, changelog, rotation/talents/stats pages.
- Wowhead class guides: overview-first pages, jump links, spell/item links, and dense tooltip-driven details.
- Archon builds: filterable context, top tabs for overview/talents/rotation/gear, and performance-oriented build cards.
- Method guides: concise class/spec introduction, talents, gearing, stats, playstyle/rotation, and interface/macro sections.

The CoA site should use these guide information patterns without copying their visual identity. The requested visual direction is fel/void: green and purple, dark fantasy surfaces, glowing accents, and restrained effects that make the report feel made for a WoW audience.

## Current Data That Can Drive M1.10

The current normalized artifacts already provide enough structure for a strong static guide:

- Class, spec tab, spell ID, entry ID, name, description, and icon path.
- Ability/talent distinction through `essence_kind`, `entry_type`, AE/TE costs, and tab ownership.
- Required level, source category, availability confidence, prerequisite IDs, connected node IDs, and row/column placement.
- Tags, damage schools, resources, and inferred role hints.
- Generated top builds, selected nodes, scoring breakdowns, APL JSON, rotation summaries, stat priority placeholders, gear recommendations, warnings, and provenance.
- AscensionDB-enriched tooltip data for most spell IDs, with fetch/mismatch warnings in the scraper reports.

## P1 Feature Plan

Detailed follow-up docs:

- [M1.10A/B Guide Information Architecture and Asset Integration Design](2026-07-05-m1-10-a-b-guide-ia-assets-design.md)
- [M1.10A/B Guide IA and Asset Integration Implementation Plan](../plans/2026-07-05-m1-10-a-b-guide-ia-assets.md)
- [M1.10C/D Talent Tree Renderer and Build Diversity Design](2026-07-05-m1-10-c-d-tree-diversity-design.md)
- [M1.10C/D Talent Tree Renderer and Build Diversity Implementation Plan](../plans/2026-07-05-m1-10-c-d-tree-diversity.md)

### Guide Information Architecture

Main page:

- Show a class/spec guide index rather than a dense ranking table.
- Provide role filters for `melee_dps`, `caster_dps`, `tank`, `healer`, and `support`.
- Provide encounter filters only where the report has generated data.
- Show each spec as a guide card with icon/media, role, confidence, best build label, warnings badge when present, and links to the spec guide.
- Keep CoA Meta Analyzer metrics behind tooltips.

Spec guide page:

- Overview: role, playstyle label, strengths, caveats, and current data confidence.
- Recommended Builds: two or three distinct builds chosen from the top performance band.
- Talent Tree: builder-like tree, level-aware recommended path, hover tooltips, and legality feedback.
- Rotation: core loop, opener, cooldown usage, defensive/healing/support priorities, and reliability notes.
- Stats: one disclaimer warning that stat priority is heuristic until sims/logs exist.
- Weapons and Armor: best targets for the spec first, then all available types.
- Abilities and Talents: searchable/listed section with icons, descriptions, source confidence, and DB hotlinks.
- Warnings: hidden unless warnings exist.
- Data Notes: capture version, source artifacts, and updated timestamp.

### Asset and Tooltip Integration

Implement now:

- Resolve normalized icon paths to local scraper assets where present.
- Fall back to generated icon URLs or styled placeholder frames when an icon file is unavailable.
- Link spells/talents to `https://db.ascension.gg/?spell=<spell_id>` or the discovered canonical spell URL pattern once confirmed by the scraper.
- Use local tooltip payloads generated from normalized description and DB enrichment so the static site does not need live API calls.

Needs additional source work:

- Class/spec photos or hero images require either CoA/Ascension asset capture, licensed/owned art, or generated bitmap assets with a consistent style.
- Exact item, weapon, and armor icons require item source scraping or a maintained item catalog.

### CoA-Style Talent Tree Renderer

Detailed design: [M1.10C/D Talent Tree Renderer and Build Diversity Design](2026-07-05-m1-10-c-d-tree-diversity-design.md).

Implement now:

- Use `row`, `col`, `connected_node_ids`, `required_ids`, `max_rank`, `ae_cost`, `te_cost`, `required_tab_ae`, `required_tab_te`, and effective required level.
- Render each spec as a grid matching the builder's node placement.
- Draw edges between connected nodes with CSS/SVG overlays.
- Mark selected, available, gated, and illegal states.
- Add level controls so users can see what is legal at level 10, 20, 30, 40, 50, and 60.
- Show AE/TE totals and prerequisite failures inline.

Avoid in P1:

- Reusing the live builder runtime or copying its full JavaScript. A lighter renderer is more maintainable and keeps the report static.
- Editable build sharing unless the builder import/export format is extracted and tested.

### Rotation and Build Diversity

Detailed design: [M1.10C/D Talent Tree Renderer and Build Diversity Design](2026-07-05-m1-10-c-d-tree-diversity-design.md).

Current report output should stop simply listing action categories. M1.10 should derive:

- Core loop: the shortest repeatable priority cycle from the generated APL and selected active abilities.
- Opener: first-use cooldowns, setup DoTs, summons, or buffs.
- Resource rule: builder/spender threshold or "use on cooldown" fallback.
- Maintenance rule: keep DoTs/buffs active only when the data supports duration or maintenance tags.
- Role rule: mitigation loop for tanks, healing cadence for healers, support upkeep for support specs.
- Reliability note: high when the loop uses explicit selected abilities and strong tags; lower when the APL is mostly inferred from generic categories.

Build diversity heuristic:

- Generate more candidates than the number shown.
- Compute a playstyle fingerprint from selected active abilities, tags, resources, damage schools, role tags, APL action categories, cooldown count, DoT count, summon/pet count, and melee/ranged/caster signals.
- Define a top performance band using a relative threshold and score spread, for example within 5-10% of the best projected index or within one robust standard deviation when enough candidates exist.
- Prefer builds with reliable core loops over builds that score highly only because of passive/tag density.
- Select two or three builds that maximize fingerprint distance while staying inside the performance band.
- Always explain why each build was selected, such as "poison DoT loop", "pet/summon setup", "burst cooldown window", "defensive sustain", or "support aura uptime".

### Role Taxonomy

P1 target roles:

- `melee_dps`
- `caster_dps`
- `tank`
- `healer`
- `support`

Source priority:

1. Authoritative CoA/Ascension role metadata if discovered in the builder payload, DB payloads, or official class/spec pages.
2. Curated local mapping with provenance when source roles are absent.
3. Metadata inference from tags, descriptions, resources, ability range/cast language, damage schools, healing/tank/support terms, and selected APL actions.

The report should expose role provenance because incorrect role selection can cause the searcher to miss valid builds.

### Gear and Stats

Implement now:

- Show one yellow warning disclaimer per spec: stat priorities are heuristic until simulations/logs exist.
- Split gear into "Best targets for this spec" and "Available to this class/spec".
- Preserve warnings when item/armor/weapon data is missing.
- Use icons when available; otherwise show clean typed chips rather than empty art boxes.

P2/P3 gated:

- Real stat weights, weapon speed preferences, armor optimization, and item ranking require item data plus logs or simulations.

## Feature Feasibility Matrix

### Implementable With Current Data

- Static class/spec guide index and individual spec pages.
- User-facing copy templates based on structured summary fields.
- Icons for spells/talents where icon paths resolve.
- DB hotlinks for spells/talents with spell IDs.
- Static hover tooltips from normalized descriptions and DB enrichment.
- Builder-like tree placement from row/column/edge data.
- Level, AE, TE, prerequisite, and rank legality display.
- Conditional warning sections.
- Single stat priority disclaimer per spec.
- Metric tooltips for analyzer-only concepts.
- Initial role split using curated mappings and metadata inference.
- Diverse-build selection based on candidate fingerprints.

### Addable With More CoA/Ascension Source Data

- Exact class/spec hero media and portraits.
- Exact AscensionDB tooltip formatting and richer buff/effect links.
- Weapon and armor availability by class/spec from authoritative item/class data.
- Item icons, item links, and target gear tables.
- Builder import/export links if the builder link format can be decoded.
- Authoritative spec roles if the source exists outside the current normalized artifacts.

### Better Deferred To P2/P3

- Sim/log-backed stat weights and per-stat DPS/HPS/mitigation values.
- Rotation consistency proven by simulated timelines or real combat logs.
- Gear rankings from actual character profiles.
- Personal upload simulation through Vercel serverless functions.
- LLM-written spec introductions and overviews. This should use strict templates, structured inputs, provenance, and review gates after the report schema is stable.

### Too Expensive Or High Maintenance

- Copying the live CoA builder's runtime and trying to keep it synchronized.
- Maintaining fully hand-written guide prose for every class/spec.
- Claiming exact DPS/HPS/mitigation outcomes before simulation or logs support them.
- Reproducing every retail guide feature without equivalent CoA systems or data.

### Irrelevant Unless CoA Adds Equivalent Data

- Retail race recommendations.
- Retail tier sets, embellishments, trinket rankings, enchants, gems, and consumables.
- Mythic+ dungeon-specific filters and route advice.
- Retail addon/interface/macro pages beyond generic future UI guidance.

## Documentation Impact

- `docs/ROADMAP.md`: M1.10 milestone and P2/P3 boundaries.
- `docs/ARCHITECTURE.md`: static guide-site flow and frontend boundary.
- `docs/MODULES.md`: web frontend/report asset responsibilities.
- `docs/data/meta-report-schema.md`: later updates for guide page payloads, role taxonomy, build fingerprints, and tooltip payloads.
- `docs/README.md`: current command behavior and report-generation logs.
