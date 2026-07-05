# M1.10E/F Role Taxonomy and Gear/Stats Presentation Design

Date: 2026-07-05

Status: ready for implementation

## Goal

M1.10E/F finishes the Phase 1 guide-site content cleanup after M1.10A-D. The generated guide should use player-facing roles, explain role provenance, and present stat/gear recommendations in a way that is useful to WoW players without overstating data confidence.

M1.10E covers role taxonomy refinement.

M1.10F covers stat and gear presentation.

These should be implemented together because role classification drives scoring profiles, APL profiles, stat priority, gear targets, guide filters, and section wording.

## Research Summary

### Local Code State

The current repo has two role systems in practice:

- Report generation still uses broad engine roles: `dps`, `tank`, and `healer_support`.
- Newer guide and rotation modules already know about player-facing roles such as `melee_dps`, `caster_dps`, `tank`, `healer`, and `support`.

Current broad role inference lives in `coa_meta.reporting`:

- Curated tank keys: `black_knight`, `defiance`, `dreadnought`, `fortitude`, `moon_guard`, `mountain_king`, `oathkeeper`, `seraphim`, and `vanguard`.
- Curated healer/support keys: `artificer`, `blessings`, `brewing`, `fleshweaver`, `flameweaving`, `heretic`, `inspiration`, `invention`, `life`, `moon_priest`, `piety`, `support`, `time`, `vizier`, and `voodoo`.
- Fallback inference scores tank, heal, and aura tags/descriptions, otherwise returns `dps`.

The profile layer only has broad role profiles today:

- `generic_dps`
- `generic_tank`
- `generic_healer_support`
- `venomancer_stalker`

The current stat and gear modules are intentionally generic:

- `coa_meta.stats.ROLE_STAT_WEIGHTS` supports `dps`, `tank`, and `healer_support`.
- `coa_meta.gear.recommend_weapon_and_armor()` returns broad `weapon_types`, `armor_types`, and warnings.
- Guide rendering currently displays stat and gear sections but does not yet distinguish best targets from available options.

### Local Data Findings

The current normalized artifacts do not expose authoritative role metadata:

- `coa_scraper/dist/coa_classes.json` contains class tabs and essence caps, but no role fields.
- `coa_scraper/dist/coa_entries.jsonl` has no top-level role key.
- Raw entry text contains role-like words, but they are tooltip content rather than a canonical role field: roughly 323 raw hits for "healing", 13 for "tank", and 4 for "healer" in the current artifact.

Tag and tooltip inference is strong enough for many specs but not authoritative:

- Obvious tanks: `Dreadnought`, `Vanguard`, `Defiance`, `Moon Guard`, `Seraphim`, `Oathkeeper`, `Mountain King`, `Black Knight`.
- Obvious healers: `Blessings`, `Brewing`, `Fleshweaver`, `Flameweaving`, `Invention`, `Life`, `Moon Priest`, `Time`, `Vizier`.
- Obvious DPS split candidates: ranged/caster-heavy specs such as `Archery`, `Boltslinger`, `Sentinel`, `Stalking`; melee-heavy specs such as `Brutality`, `Godblade`, `Crusader`, `Riftblade`.
- Support is the weakest category because support and healer often share `heal`, `aura`, `resource_management`, and ally-text cues. It needs curated overrides and provenance rather than pure inference.

### External Guide Patterns

The reference guide sites reinforce the desired scope:

- Icy Veins separates class/spec guide navigation into Overview, Talents, Rotation, Gear, Stats, and related guide pages, and exposes DPS/tank/healer categories in navigation.
- Wowhead guide pages include sections like BiS Gear, Rotation, Talent Builds, Consumables, Stats, and Basics, and explicitly recommend simming your own character because stat value differs by character.
- Archon exposes data context for builds, including content filters, update recency, parse counts, stat priority, talent build, and gear overview. It clearly labels data-backed popularity and gear interpretation.
- Method separates introduction, talents, gearing, stats, playstyle/rotation, and utility-style guide sections.
- AscensionDB exposes spells, items, tools, and the official Ascension Builder, but the public static HTML does not expose an obvious CoA role taxonomy. It should remain a spell/item/link source, not be treated as authoritative for role unless a richer source payload is discovered.

## Product Requirements

### M1.10E Player Outcome

Every guide card and spec guide should expose one player-facing role:

- `melee_dps`
- `caster_dps`
- `tank`
- `healer`
- `support`

The player-facing role should include provenance:

- source: `authoritative`, `curated`, or `inferred`
- confidence: `high`, `medium`, or `low`
- evidence: concise data points, such as curated mapping name, top role tags, or tooltip terms
- engine role: the broad profile role used for scoring/APL until specialized profiles exist

The guide index should filter by the five player-facing roles. Broad roles such as `dps` and `healer_support` should not be the primary UI labels.

### M1.10E Engine Outcome

Do not break existing scoring/APL profiles. Add a compatibility bridge:

```text
melee_dps  -> dps
caster_dps -> dps
tank       -> tank
healer     -> healer_support
support    -> healer_support
```

The report should keep enough role metadata for both machines and players:

```text
SpecResult.role: player-facing role
SpecResult.engine_role: broad scoring/APL role
SpecResult.role_provenance: role source, confidence, evidence, scores
BuildReport.provenance.engine_role: broad profile role
BuildReport.provenance.role: player-facing role
```

If backwards compatibility requires preserving `role` as the broad role for one release, the guide model must still expose `guide_role`. The preferred implementation is to migrate JSON to the five-role taxonomy and provide `engine_role` explicitly.

### M1.10F Player Outcome

The Stats section should show one disclaimer per spec, not one warning per stat:

> Stat priorities are early theorycraft until simulations or combat logs are available.

Then show a ranked stat list with player wording:

- Primary target stats
- Useful secondary stats
- Low-priority or role-limited stats
- Why this priority exists
- Confidence and source label

The Weapons and Armor section should separate:

- Best targets for this spec
- Available to this class/spec
- Source warnings

The section should include icons when available. For M1.10F, typed chips are acceptable for weapon and armor types until item icon data exists.

### M1.10F Engine Outcome

Stat and gear output should become structured section payloads, not renderer-only prose:

```text
stat_priority:
  schema_version: "coa-stat-priority-v2"
  role: player-facing role
  engine_role: broad role
  disclaimer: one string
  source: "heuristic"
  confidence: "low" | "medium"
  groups:
    - group_id: "primary"
      label: "Best stats to target"
      entries: [...]
    - group_id: "secondary"
      label: "Good supporting stats"
      entries: [...]
    - group_id: "situational"
      label: "Situational stats"
      entries: [...]

gear_recommendation:
  schema_version: "coa-gear-recommendation-v2"
  role: player-facing role
  engine_role: broad role
  best_weapon_types: [...]
  best_armor_types: [...]
  available_weapon_types: [...]
  available_armor_types: [...]
  item_scores: [...]
  source: "defaults" | "item_data" | "mixed"
  confidence: "low" | "medium"
  warnings: [...]
```

For JSON compatibility, keep existing list-style `stat_priority` and v1 gear fields for one release, but make guide rendering prefer v2 payloads.

## Role Resolution Design

Create a dedicated role module instead of keeping inference in `reporting.py`.

Proposed file: `coa_meta/roles.py`

Primary objects:

```text
GuideRole = Literal["melee_dps", "caster_dps", "tank", "healer", "support"]
EngineRole = Literal["dps", "tank", "healer_support"]

RoleResolution
  role: GuideRole
  engine_role: EngineRole
  source: "authoritative" | "curated" | "inferred"
  confidence: "high" | "medium" | "low"
  evidence: tuple[str, ...]
  scores: dict[str, float]
```

Source priority:

1. Authoritative metadata, if a future builder payload or Ascension source exposes role fields.
2. Curated local spec mapping with explicit provenance.
3. Metadata inference from tags, descriptions, resources, damage schools, active/passive selected nodes, and APL action categories.

Curated mapping should live in data, not code:

```text
coa_meta/data/role_overrides.json
```

Each row should include class, spec, role, confidence, and evidence. Class-agnostic spec keys are acceptable only when the spec name is globally unique enough.

Inference should compute all five roles:

- `tank`: tank tags, threat/block/parry/dodge/armor/damage-taken text, shield/bulwark wording.
- `healer`: heal/hot/absorb/ally/allies/party/raid wording, healing tags, mana-like resource cues.
- `support`: aura/buff/debuff/resource-management/crowd-control/group-utility wording, without enough healing density to be healer.
- `melee_dps`: melee tags, physical/weapon/strike/fang/blade wording, builder/spender loops, low tank/heal density.
- `caster_dps`: ranged tags, spell/cast/damage-school density, mana/spell-power cues, DoT/proc loops, low heal density.

Tie-breaking:

1. Curated mapping wins over inference.
2. Tank wins if tank score clears threshold and is close to or above healer/support score.
3. Healer wins when healing score is clearly above support.
4. Support wins when aura/utility score is high but healing score is not dominant.
5. DPS then splits into melee/caster by higher signal. If tied, use `caster_dps` when spell/cast/school density is high, otherwise `melee_dps`.

## Stat Priority Design

Create grouped stat priorities from role-aware weights. M1.10F should not introduce real stat weights; it should make the current heuristic honest and easier to read.

Proposed changes:

- Keep `StatPriority` for compatibility.
- Add `StatPrioritySection` and `StatPriorityReport`.
- Add role-specific weights for all five player-facing roles.
- Map guide role to engine role where profile-specific stat data is missing.
- Emit one disclaimer string and one `warnings` list per spec.

Initial heuristic groups:

- `melee_dps`: attack power, strength/agility, hit/expertise, crit/haste.
- `caster_dps`: spell power, intellect, hit, haste/crit, spirit if mana-relevant.
- `tank`: stamina, armor, avoidance/block-related stats, hit/expertise, threat stats.
- `healer`: spell power, intellect, spirit, haste, crit, stamina.
- `support`: spell power or attack power depending evidence, intellect/spirit for caster support, haste/crit, stamina.

Because CoA classes are custom, the implementation should record evidence rather than pretending retail stat rules map perfectly.

## Gear Recommendation Design

Separate "best targets" from "available options".

Best targets should come from:

1. Item data if provided through `--gear-profile` or later item catalogs.
2. Curated class/spec defaults when available.
3. Role defaults when no better data exists.

Available options should come from:

1. Class/spec equipment source if discovered later.
2. Item records for the current profile.
3. Broad fallback list with a low-confidence warning.

Proposed file: `coa_meta/gear_catalog.py` or extensions to `coa_meta/gear.py`.

Recommended structured helpers:

```text
gear_targets_for_role(role, engine_role, items, class_name, spec_name)
available_gear_for_class(class_name, spec_name, items)
gear_recommendation_report(...)
```

Item links should use AscensionDB item URLs when item IDs exist:

```text
https://db.ascension.gg/?item=<item_id>
```

M1.10F should not rank full BiS lists unless item data exists. When item data is missing, show type targets and a clear warning:

```text
item_data_missing
class_equipment_source_missing
gear_targets_from_role_defaults
```

## Guide Rendering Design

Update the guide renderer so:

- Role chips use the five player-facing labels.
- Hover tooltip for role provenance explains source and evidence.
- Stats render one warning panel and grouped stat chips.
- Gear renders best targets first, then available options.
- Warnings only appear when warning lists are non-empty.
- Analyzer-only terms remain behind metric tooltips.

The legacy `render_spec_guide_html()` path in `reporting.py` should delegate HTML spec-page generation to the guide renderer. If that cannot be done cleanly in the implementation pass, update the legacy renderer to render the same v2 stat/gear payloads and add tests for both paths. Otherwise tests can pass while compatibility HTML remains stale.

## Data and CLI Compatibility

CLI role options should support:

- `auto`
- `melee_dps`
- `caster_dps`
- `tank`
- `healer`
- `support`
- Backwards aliases for `dps` and `healer_support`

Configured aliases should resolve as:

- `dps`: infer melee/caster when possible, otherwise `melee_dps`
- `healer_support`: infer healer/support when possible, otherwise `healer`

Report JSON compatibility:

- Prefer adding `engine_role` and `role_provenance` rather than changing profile IDs.
- Add schema docs for v2 stat and gear payloads.
- Keep old fields readable until a later schema version bump.

## Risks and Mitigations

- **Risk: role inference is wrong for hybrid specs.** Mitigation: curated overrides and visible provenance.
- **Risk: player-facing role conflicts with broad scoring profile.** Mitigation: explicit `engine_role` bridge and provenance in build reports.
- **Risk: stat priority looks authoritative.** Mitigation: one clear disclaimer per spec, low/medium confidence labels, no raw DPS/stat claims.
- **Risk: gear recommendations overpromise without item catalogs.** Mitigation: separate type targets from item rankings and surface missing-source warnings.
- **Risk: support and healer blur together.** Mitigation: support requires aura/utility dominance without healer dominance; curated overrides are allowed.

## References

- Icy Veins Outlaw Rogue guide: `https://www.icy-veins.com/wow/outlaw-rogue-pve-dps-guide`
- Wowhead Demonology Warlock guide: `https://www.wowhead.com/guide/classes/warlock/demonology/overview-pve-dps`
- Archon Brewmaster Monk Mythic+ build: `https://www.archon.gg/wow/builds/brewmaster/monk/mythic-plus/overview/10/all-dungeons/this-week`
- Method Discipline Priest guide: `https://www.method.gg/guides/discipline-priest`
- AscensionDB: `https://db.ascension.gg/`
