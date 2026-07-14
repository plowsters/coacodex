# Client Class-Types, Tab-Types, and Essence Schema

Three companion metadata artifacts, all produced by `coa_client_extract` (M1.14B) alongside
`coa-client-advancement-v1` (see [client-advancement-schema.md](client-advancement-schema.md)). Node
records alone cannot retire the Builder pipeline, which also consumes class/tab metadata
(`coa_classes.json`) and essence caps (`coa_essence_caps.json`); these artifacts supply that data from
the client.

## `coa-client-class-types-v1`

One record per row of `CharacterAdvancementClassTypes.dbc` (46 rows).

### Fields

- `schema_version`: always `coa-client-class-types-v1`
- `class_type_id`: the row id (FK target of `CharacterAdvancement` col 32)
- `internal`: the raw client name — the independently-recoverable attribution identity, always
  present regardless of `display_source`
- `display`: the human-readable name; equal to `internal` unless a curated alias overrides it
- `kind`: `coa_class` | `coa_system` | `reborn` | `stock` | `meta` | `unknown`
- `display_source`: `client` (the default — `display` is just `internal`) or `curated_alias` (the
  three renamed classes below)
- `display_evidence`: list of evidence tags backing `display_source: curated_alias`; empty when
  `display_source` is `client`

### Class-type bands (verified against the real client, 2026-07-13)

| Range | `kind` | Notes |
|---|---|---|
| 2–11 | `stock` | Hunter..DeathKnight — stock WotLK classes |
| 12–13 | `meta` | `General`, `Hero` |
| **14–34** | **`coa_class`** | **The 21 playable CoA classes.** |
| **35** | **`coa_system`** | **`ConquestOfAzeroth` — an umbrella/sentinel row, NOT a playable class.** Excluded from the playable count. |
| 36–46 | `reborn` | `Reborn*` classes |
| anything else | `unknown` | outside every known band — flagged as a possible new class or drift, never silently bucketed as `stock` |

The playable band spans ids 14–35 (22 ids), but the playable *set* is exactly the 21 ids 14–34, with
35 excluded as the sentinel. `assert_playable_cardinality` raises if the resolved playable count is
ever not exactly 21.

### Curated display aliases

Three playable classes are stored in the client under scrapped-alpha internal names. The rename to
their current display name is **curated presentation metadata, not a client-native fact** — a
client-native derivation was attempted (joining the advancement internal name to a `SkillLine`
display name through shared spells) and does not work, because CoA advancement nodes share spells
with per-*spec* skill lines, not the class-band skill lines. The alias is applied only to `display`;
it never changes `class_type_id`, `internal`, or any attribution (`is_coa`/`modes`) result, so the raw
client identity stays independently recoverable.

| `class_type_id` | `internal` (client) | `display` (curated alias) |
|---|---|---|
| 22 | `SonOfArugal` | `Bloodmage` |
| 16 | `DemonHunter` | `Felsworn` |
| 21 | `Monk` | `Templar` |

`display_evidence` for all three is `["builder_class_name", "project_owner_confirmation"]` — the
Builder's own class naming plus explicit confirmation from the project owner that these were alpha
classes revamped into existing classes (corroborated by spell theme: `SonOfArugal` = blood,
`DemonHunter` = fel, `Monk` = holy).

Example record:

```json
{ "schema_version": "coa-client-class-types-v1", "class_type_id": 22, "internal": "SonOfArugal",
  "display": "Bloodmage", "kind": "coa_class", "display_source": "curated_alias",
  "display_evidence": ["builder_class_name", "project_owner_confirmation"] }
```

## `coa-client-tab-types-v1`

One record per row of `CharacterAdvancementTabTypes.dbc`.

### Fields

- `schema_version`: always `coa-client-tab-types-v1`
- `tab_type_id`: the row id (FK target of the advancement node's tab-type column)
- `name`: the tab's display name (e.g. `Class`, a spec tab name)

## `coa-client-essence-v1`

One record per row of `CharacterAdvancementEssence.dbc` (5,440 rows; columns `1..80 × 1..32`) —
extracted **raw**, with **undecoded semantics**. This table is per-level/per-tier essence
*progression* data (how much essence is available at each level/tier), a distinct quantity from the
per-class essence *caps* (below). M1.14B ships it raw with provenance for auditability; it does not
assert any column meaning.

### Fields

- `schema_version`: always `coa-client-essence-v1`
- `cols`: `{ "<cell_index>": <value>, ... }` — the full index-keyed raw row, same shape as
  `coa-client-advancement-v1`'s `raw.cols`; no column is claimed to mean anything yet
- `provenance`: `client_build`, `source_dbcs` (names **`CharacterAdvancementEssence` as its own
  source table** — this artifact's provenance does not point back at `CharacterAdvancement`),
  `semantics: "undecoded_per_level_progression"`, `extraction_date`

### Readiness: this artifact is deliberately gated, and deliberately non-blocking

Because `coa-client-essence-v1`'s per-level semantics are undecoded, the parity report
(`coa-builder-parity-v2`) sets its `readiness.leveling_progression_ready` to `false`. Decoding this
table — and validating a build's AE/TE spend against per-level essence availability rather than only
the max-level caps — is a **separate M1.15 sub-milestone** ("Level-by-level build validation"), its
own gate (Decision 21/22). `leveling_progression_ready` **never blocks** any max-level readiness
dimension (`attribution_ready`/`ownership_ready`/`adjacency_ready`/per-field `legality`) or
`full_builder_retirement_ready` — coupling a proven max-level graph to an unfinished leveling feature
would be a scope error.

### Essence caps are a different quantity, and not a decode of this table

Per-class essence **caps** — max Ability Essence **26** / Talent Essence **25** — are the pool sizes
that gate a *completed max-level build*. They are uniform across classes and are carried as a
**versioned `verified_constant`** (currently the values in `coa_essence_caps.json`), **not decoded
from `CharacterAdvancementEssence`**. Under Decision 21's per-field rule they are an explicitly-
retained fallback source with honest provenance (`source: verified_constant`,
`corroboration: pending_client_ui`) until corroborated against the live client UI/behavior. Because
CoA Codex validates max-level builds, the caps are the only essence quantity the max-level legality
flip needs, and they are already available — the raw per-level progression table is a separate,
not-yet-decoded capability.
