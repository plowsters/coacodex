# Client Advancement Schema

Records use schema version `coa-client-advancement-v1`, produced by `coa_client_extract` (M1.14B)
from `DBFilesClient/CharacterAdvancement.dbc` (plus its companion class-type/tab-type/spell tables).
One record is emitted **per advancement node** — the row in `CharacterAdvancement.dbc` — not per
spell. `coa-client-advancement-v1` is the candidate canonical talent graph; it is validated against
the CoA Builder oracle (`coa-builder-parity-v2`, see [client-content-schema.md](client-content-schema.md)
sibling docs and [DECISIONS.md](../DECISIONS.md) Decisions 21/22) but not yet consumed by the legality
or tree pipeline — that staged supersession is M1.15's job.

## Node identity is not spell identity

`node_id` (col 0 of `CharacterAdvancement.dbc`, unique across all 12,037 rows) is the canonical
identity of a record — the advancement-row id. `spell_id` (col 5) is **many-to-one** with nodes:
the same spell can be realized as more than one node. The canonical example is Builder spell
`503748`, which is one spell realized as two distinct Witch Doctor advancement nodes — a
Brewing-tab `Talent` node and a Class-tab `Ability` node — which is exactly why the Builder oracle
holds 3,612 records over only 3,611 unique spell IDs. Consumers that key on `spell_id` alone will
silently collapse these into one entry; key on `node_id` for ownership/graph identity, and use the
spell's aggregated `memberships[]` (on `coa-client-spell-v1`, filled by M1.14B) when the question is
"which advancement contexts does this spell participate in."

## Required Fields

- `schema_version`: always `coa-client-advancement-v1`
- `node_id`: the advancement-row id (`CharacterAdvancement` col 0) — canonical node identity
- `spell_id`: the spell realized by this node (`CharacterAdvancement` col 5); `0` when the node has
  no spell
- `name`: the spell's *current* name, joined from the already-extracted `coa-client-spell-v1` record
  by `spell_id` (not read from the advancement table's own string block)
- `class`: `{ class_type_id, internal, display, kind }` — the node's owning class, resolved via the
  `class_type` FK (col 32) against `CharacterAdvancementClassTypes` (see
  [client-class-types-schema.md](client-class-types-schema.md) for `kind`/`display` semantics; the
  curated alpha→display rename and its provenance live there, joined by `class_type_id`, not
  duplicated per node)
- `tab`: `{ tab_type_id, name }` — resolved via the tab-type FK against `CharacterAdvancementTabTypes`
- `entry_type`: the node's kind (e.g. `Ability`, `Talent`, `TalentAbility`), decoded from a proven
  numeric→string map — withheld (empty string) if that column has not decoded to `high` confidence
- `essence_kind`: `"ability"` | `"talent"` | `""`, derived from `entry_type` (`Ability`/
  `TalentAbility` → `ability`, `Talent` → `talent`, otherwise empty)
- `legality`: a dict carrying **only** the legality fields that decoded to `field_confidence: high`
  for this node. Possible keys: `ae_cost`, `te_cost`, `required_level`, `required_tab_ae`,
  `required_tab_te`, `max_rank`, `row`, `col`, `connected_node_ids`, `required_ids`. A field absent
  from `legality` is honestly unresolved for that node (not zero, not padding) — the parity report's
  `readiness.legality[field]` and `readiness.layout` reflect this per field, per artifact-wide
  confidence.
  - `required_level` follows the `{0} ∪ [1, 60]` rule: `0` normalizes to "no level requirement"
    (available immediately), never to "unknown" or padding; any other value must fall in `[1, 60]`
    or the node is rejected before canonical emission (`DbcSemanticError`).
  - `connected_node_ids` / `required_ids` are nonempty only once adjacency has been proven to resolve
    in the `node_id` domain (no dangling references, no self-reference); values are de-duplicated and
    sorted, with zero/padding slots normalized away.
- `field_confidence`: index-keyed-by-field-name map (e.g. `{"ae_cost": "high", "row": "high"}`)
  recording which `legality` entries reached `high` confidence. Only `high` fields are eligible to
  feed the M1.15 Builder-supersession adapter; every other field keeps the Builder as its fallback,
  explicitly marked.
- `raw`: `{ "cols": { "<cell_index>": <value>, ... } }` — the full index-keyed audit map of every raw
  column value for this row, retained regardless of decode confidence, so a later mis-mapping is
  recoverable without re-extraction. Because JSON object keys are always strings, the integer cell
  indices are stringified on serialization.
- `provenance`: per-table provenance for this record's contributing tables — `client_build`,
  `source_dbcs` (map of contributing table name → effective archive that supplied it, e.g.
  `CharacterAdvancement`, `CharacterAdvancementClassTypes`, `CharacterAdvancementTabTypes`, `Spell`),
  `supersedes` (`{"source_file": "CharacterAdvancementData.json"}` — see
  [client-content-schema.md](client-content-schema.md)), and `extraction_date`
- `coa_attribution`: the participation block for this node's spell — `{ is_coa, modes, exclusive_mode,
  confidence }` — identical in shape to the block filled on `coa-client-spell-v1` (see
  [client-spell-schema.md](client-spell-schema.md)) and joined here for per-node convenience; the
  spell-level record is where the aggregated `memberships[]` lives, not here (a node has exactly one
  precise `(class, tab)` context by construction)
  - `archive_family` / `id_range`: **not present** on the advancement record — those M1.14A raw
    signals live only on the spell record's `coa_attribution` block

## Consumer Rules

- Treat `node_id` as identity; never assume `spell_id` is unique.
- Only read a `legality` field a caller cares about if `field_confidence[field] == "high"`; an
  absent-from-`legality` field is not zero.
- `raw.cols` is an audit trail, not a stable contract — column indices are the current decode's
  resolution and may be re-mapped if a future decode pass corrects them (with `raw` used to verify the
  correction against the same source bytes).
- This artifact does not itself retire the Builder graph or legality pipeline. The node-level parity
  report (`coa-builder-parity-v2`) and the per-field Builder-supersession adapter are what M1.15
  consumes to do that, one field at a time (Decision 21).
