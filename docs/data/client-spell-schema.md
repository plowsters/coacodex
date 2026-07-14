# Client Spell Schema

Records use schema version `coa-client-spell-v1`, produced by `coa_client_extract` (M1.14A) from the
CoA client's MPQ→DBC spell family. Attribution is now filled by M1.14B from `CharacterAdvancement.dbc`
(see [client-advancement-schema.md](client-advancement-schema.md)); reconciliation into
`coa-mechanics-v1` is M1.14C.

## Required Fields
- `schema_version`: always `coa-client-spell-v1`
- `spell_id`: DBC spell id
- `name`: localized spell name from `Spell.dbc`
- `mechanics`: object with `school_mask`, `power_type`, `cast_time_ms`, `duration_ms`,
  `range_min_yd`, `range_max_yd`, `category`, `spell_icon_id` (any may be null when the source row is
  absent)
- `provenance`: `base_archive`, `patch_chain`, `effective_archive`, `source_dbcs`,
  `schema_match_confidence` (`high`|`low`), `extraction_date`
  - `patch_chain` / `effective_archive` are StormLib's own reported chain of archives that
    supplied the winning bytes (winner last), not the attach order.
  - `source_dbcs` maps each contributing table (`Spell`, `SpellCastTimes`, `SpellDuration`,
    `SpellRange`) to the archive that supplied it.
- `coa_attribution`: **filled by M1.14B** from the `CharacterAdvancement.dbc` participation model
  (see [client-advancement-schema.md](client-advancement-schema.md) and
  [DECISIONS.md](../DECISIONS.md) Decision 18-amended). The M1.14A placeholder
  `coa_attribution.status: "unknown"` is gone, replaced by:
  - `is_coa`: `true` iff any evidence contributes the `coa` mode
  - `modes`: sorted list of every mode this spell participates in — `coa`, `reborn`, `stock`, and/or
    `coa_system` (the `ConquestOfAzeroth` sentinel, marked non-playable). A spell can legitimately
    carry more than one mode (e.g. reused across CoA and Reborn); that is multi-mode reuse, not an
    unresolved conflict.
  - `exclusive_mode`: the single mode when `len(modes) == 1`, else `null`
  - `confidence`: `high` (advancement-registry membership, or the sentinel), `medium` (no advancement
    row, but on a proven CoA skill line), or `low` (no advancement row, high-custom-ID only —
    `is_coa: false`)
  - `archive_family` and `id_range`: the M1.14A raw signals are **retained**, unchanged in meaning,
    as provenance-only fields alongside the new participation block (`archive_family` is known
    uninformative for CoA-vs-other partitioning; kept for audit, not decision-making)
  - `memberships[]` (sibling field, not nested under `coa_attribution`): the spell's aggregated,
    stable list of `(class, tab)` contexts across every advancement node that realizes it — see
    [client-advancement-schema.md](client-advancement-schema.md) for the shared-spell `503748`
    example. Never a scalar `class`/`spec` field that flips to an array; a stock/classless membership
    never overwrites a CoA one.
  - **The alpha→display class rename (`Bloodmage`/`Felsworn`/`Templar`, see
    [client-class-types-schema.md](client-class-types-schema.md)) does not affect this record.** It is
    curated presentation metadata applied only to `class_display` inside `memberships[]`; the client's
    own `class_type_id` and `is_coa`/`modes` results are computed from the raw client identity and are
    unaffected by the rename either way.

## Mechanics scope (M1.14A)
M1.14A extracts the reduced spell family: `Spell` plus the three index tables it references
(`SpellCastTimes`, `SpellDuration`, `SpellRange`). The umbrella spec's fuller mechanical set
— spell cooldowns/category cooldowns, rune cost, and the `SpellEffect` `effects[]` join — is
**deferred to a later M1.14 sub-milestone**. Those tables are load-bearing for the M1.16
power model, not for M1.14A extraction, and are tracked as follow-up rather than dropped.

## Consumer Rules
- `schema_match_confidence: "low"` means DBC drift was detected for a contributing table; downstream
  consumers must not treat those mechanical fields as high-confidence.
- Fields may be null; consumers tolerate partial records.
