# M1.11B Role Map and Role-Specific Objective Indexes Design

Date: 2026-07-05

Status: ready for implementation

## Goal

M1.11B replaces heuristic role labels and DPS-only score presentation with a source-backed role map and role-specific theorycraft indexes.

The launch-video role list supplied by the project owner is treated as the authoritative seed for M1.11B until a machine-readable CoA Builder or Ascension source exposes equivalent role metadata. Complexity labels from the launch video are preserved as metadata but ignored by scoring for now.

## Design Decision: Hybrid Specs

Hybrid specs use a primary role plus optional secondary roles.

Example:

```text
Inspiration Guardian
  primary_role: melee_dps
  secondary_roles: ["support"]
```

Rationale:

- It preserves the six-role UI taxonomy: `tank`, `healer`, `support`, `caster_dps`, `ranged_dps`, `melee_dps`.
- It lets hybrid specs appear when users filter by either primary or secondary role.
- It avoids creating combined role strings like `melee_dps_support`.
- It does not force separate guide variants before the build/rotation engine can prove distinct role builds.

Guide behavior:

- A spec card can appear in every role section it belongs to.
- The card should clearly show primary role and secondary roles.
- Scoring defaults to `primary_role`.
- Future role-specific build variants can create separate guide variants when logs/sims justify them.

## Source Role Map

Schema target: `coa-spec-role-map-v1`

Fields:

- `class_name`: source class name.
- `source_spec_name`: name used by normalized builder/API records.
- `display_spec_name`: player-facing name after legacy renames.
- `primary_role`: one of `melee_dps`, `ranged_dps`, `caster_dps`, `tank`, `healer`, `support`.
- `secondary_roles`: zero or more additional guide roles.
- `engine_role`: broad compatibility role: `dps`, `tank`, or `healer_support`.
- `complexity`: launch-video complexity label, retained for future guide metadata.
- `source`: `authoritative_video`, `authoritative_builder`, `curated`, or `inferred`.
- `confidence`: `high`, `medium`, or `low`.
- `evidence`: short strings naming launch-video transcript, builder tab, or inference evidence.
- `source_urls`: empty until the official launch video URL is recorded.
- `notes`: explicit ambiguity or migration notes.

The first data file should live at:

```text
coa_meta/data/spec_roles.json
```

The current `role_overrides.json` can remain as a compatibility input for one release, but M1.11B should make `spec_roles.json` the preferred role source.

## Official Role Seed

The role seed contains 21 classes and 70 reportable specs.

### Necromancer

| Spec | Primary | Secondary |
| --- | --- | --- |
| Death | caster_dps |  |
| Animation | caster_dps |  |
| Rime | caster_dps |  |

### Guardian

| Spec | Primary | Secondary |
| --- | --- | --- |
| Gladiator | melee_dps |  |
| Inspiration | melee_dps | support |
| Vanguard | tank |  |

### Runemaster

| Source Spec | Display Spec | Primary | Secondary |
| --- | --- | --- | --- |
| Riftblade | Riftblade | melee_dps |  |
| Arcane | Glyphic | caster_dps |  |
| Runic | Engravement | melee_dps |  |

### Reaper

| Spec | Primary | Secondary |
| --- | --- | --- |
| Harvest | melee_dps |  |
| Soul | melee_dps |  |
| Domination | tank |  |

### Starcaller

| Spec | Primary | Secondary |
| --- | --- | --- |
| Moon Priest | healer |  |
| Sentinel | ranged_dps |  |
| Warden | melee_dps |  |
| Moon Guard | tank |  |

### Bloodmage

| Spec | Primary | Secondary |
| --- | --- | --- |
| Fleshweaver | support |  |
| Sanguine | caster_dps |  |
| Accursed | melee_dps | caster_dps |
| Eternal | tank |  |

### Ranger

| Spec | Primary | Secondary |
| --- | --- | --- |
| Archery | ranged_dps |  |
| Brigand | melee_dps |  |
| Farstrider | ranged_dps | support |

### Knight of Xoroth

| Spec | Primary | Secondary |
| --- | --- | --- |
| War | melee_dps |  |
| Hellfire | melee_dps |  |
| Defiance | tank |  |

### Sun Cleric

| Spec | Primary | Secondary |
| --- | --- | --- |
| Piety | caster_dps |  |
| Valkyrie | melee_dps |  |
| Blessings | healer |  |
| Seraphim | tank |  |

### Cultist

| Spec | Primary | Secondary |
| --- | --- | --- |
| Heretic | healer |  |
| Corruption | caster_dps |  |
| Godblade | melee_dps |  |
| Dreadnought | tank |  |

### Tinker

| Spec | Primary | Secondary |
| --- | --- | --- |
| Mechanics | melee_dps |  |
| Invention | healer |  |
| Demolition | ranged_dps |  |

### Stormbringer

| Spec | Primary | Secondary |
| --- | --- | --- |
| Wind | caster_dps | support |
| Maelstrom | caster_dps |  |
| Lightning | caster_dps |  |

### Templar

| Spec | Primary | Secondary |
| --- | --- | --- |
| Oathkeeper | tank |  |
| Zealot | melee_dps |  |
| Crusader | melee_dps |  |

The supplied launch-video transcript has the third Templar line formatted as `Intermediate: Intermediate - melee DPS`. Current builder data has a `Crusader` tab, so M1.11B should map this row to `Crusader` with a note requiring video/source verification before marking it `high` confidence.

### Witch Doctor

| Spec | Primary | Secondary |
| --- | --- | --- |
| Voodoo | caster_dps |  |
| Brewing | healer |  |
| Shadowhunting | ranged_dps |  |

### Barbarian

| Spec | Primary | Secondary |
| --- | --- | --- |
| Headhunting | ranged_dps |  |
| Brutality | melee_dps |  |
| Ancestry | melee_dps | support |

### Pyromancer

| Spec | Primary | Secondary |
| --- | --- | --- |
| Flameweaving | healer |  |
| Incineration | caster_dps |  |
| Draconic | caster_dps |  |

### Chronomancer

| Spec | Primary | Secondary |
| --- | --- | --- |
| Time | healer |  |
| Infinite | caster_dps |  |
| Artificer | ranged_dps |  |

### Venomancer

| Source Spec | Display Spec | Primary | Secondary |
| --- | --- | --- | --- |
| Fortitude | Fortitude | tank |  |
| Stalking | Stalking | melee_dps |  |
| Venom | Rot | caster_dps |  |
| Vizier | Vizier | healer |  |

### Felsworn

| Spec | Primary | Secondary |
| --- | --- | --- |
| Infernal | caster_dps |  |
| Slayer | melee_dps |  |
| Tyrant | tank |  |

### Witch Hunter

| Source Spec | Display Spec | Primary | Secondary |
| --- | --- | --- | --- |
| Boltslinger | Boltslinger | ranged_dps |  |
| Inquisition | Inquisition | melee_dps |  |
| Black Knight | Black Knight | tank |  |
| Houndmaster | Darkness | ranged_dps |  |

### Primalist

| Source Spec | Display Spec | Primary | Secondary |
| --- | --- | --- | --- |
| Geomancy | Geomancy | caster_dps |  |
| Life | Grovekeeper | support |  |
| Primal | Wildwalker | melee_dps |  |
| Mountain King | Mountain King | tank |  |

## Role Resolution Priority

M1.11B should resolve roles in this order:

1. `spec_roles.json` authoritative/curated rows.
2. Existing `role_overrides.json` for backwards compatibility.
3. Metadata inference from tags, tooltip text, APL actions, resources, and damage schools.

If a source role row exists, inference should not override it. Inference can still emit diagnostic scores for warnings and future validation.

## Role-Specific Objective Indexes

M1.11B should add a role objective layer without deleting the existing score field.

New build fields:

```text
primary_index
primary_index_label
objective_id
objective_breakdown
alternate_objective_scores
```

Compatibility:

- Keep `projected_dps_index` for one schema generation.
- For DPS specs, `projected_dps_index` and `primary_index` can initially share the same value.
- For healer/tank/support specs, `primary_index` is the guide-facing score.

Labels:

- Damage specs: `Projected Damage Index`
- Healers: `Projected Healing Index`
- Tanks: `Projected Survival/Threat Index`
- Support: `Projected Support Index`

Objective components:

- Damage: damaging active abilities, DoT/proc density, cooldown efficiency, resource conversion, target scaling, uptime.
- Healing: healing throughput, HoT/shield coverage, recovery cooldowns, mana efficiency, ally targeting.
- Tank: mitigation uptime, effective health, self-healing, threat generation, control, defensive cooldown coverage.
- Support: buffs, debuffs, group amplification, resource support, crowd control, utility, uptime.

Hybrid behavior:

- Primary objective drives default sorting and build selection.
- Secondary objective scores are emitted for transparency.
- Future guide variants may run separate searches for secondary roles once M1.11E/F can produce role-specific builds and rotations.

## Report and UI Behavior

Index:

- A spec belongs to `primary_role` and every `secondary_role`.
- Filtering by a secondary role should show hybrid specs.
- Cards should display primary and secondary role badges.
- If a card is duplicated across role sections, it should link to the same canonical spec guide.

Spec guide:

- Header shows primary role and secondary role chips.
- Build cards use `primary_index_label`.
- Analyzer metric tooltips explain each index in player language.
- Role provenance stays in Data Notes or a tooltip, not as a primary player-facing badge.

## Testing Strategy

Tests should cover:

- The official seed has 70 specs and all current builder tabs are mapped or explicitly ignored.
- Legacy display names map to source names without breaking joins.
- Hybrid roles serialize and filter correctly.
- Role-specific index labels render for tank/healer/support specs.
- Existing `projected_dps_index` consumers still pass during transition.

## Risks

- Launch-video transcript ambiguity can produce one wrong row. Mitigation: record source notes and keep the Templar third spec at medium confidence until source URL verification.
- Secondary roles may cause duplicate cards on the index. Mitigation: use canonical guide URLs and clear primary/secondary badges.
- Role-specific indexes can look more precise than they are. Mitigation: keep theorycraft disclaimers and expose objective breakdown/provenance.
