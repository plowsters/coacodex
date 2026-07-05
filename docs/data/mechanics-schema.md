# Mechanics Schema

Mechanics records use schema version `coa-mechanics-v1`.

## Purpose

Mechanics records describe how spells, passives, buffs, debuffs, pets, and item effects behave when the simulator or report explainers need more than builder legality data. The schema is intentionally tolerant of partial records because many fields are inferred from AscensionDB tooltips or later log calibration.

## Required Fields

- `schema_version`: always `coa-mechanics-v1`
- `spell_id`: canonical spell identifier when available
- `name`: display name
- `kind`: ability, passive, buff, debuff, cooldown, pet_action, item_effect, proc, or another explicit mechanic kind
- `effects`: zero or more mechanic effect records
- `provenance`: source and confidence records
- `confidence`: high, medium, or low

## Common Optional Fields

- `source_node_ids`: builder node IDs associated with the spell
- `source_urls`: AscensionDB or other source URLs
- `school`, `power_type`, `range_yards`
- `cast_time_ms`, `gcd_ms`, `cooldown_ms`, `charges`
- `duration_ms`, `tick_interval_ms`
- `costs`, `generates`, `spends`
- `max_targets`
- `proc`
- `raw`

## Effect Fields

Effects use `effect_type` values such as:

- `damage`
- `heal`
- `absorb`
- `aura_apply`
- `aura_refresh`
- `resource_delta`
- `summon`
- `cooldown_modify`
- `stat_modify`
- `trigger_spell`

Effects may include `school`, `target`, `amount`, `aura`, `stat`, `trigger_spell_id`, `duration_ms`, `tick_interval_ms`, `scaling`, `tags`, and raw source data.

## Provenance

Every inferred or source-derived record should include provenance:

- `source`: builder, ascension_db, tooltip_parser, override, log_calibration, or another explicit source
- `source_id`: source-local identifier such as `spell:2001`
- `source_url`: optional canonical URL
- `parser`: parser or rule name
- `confidence`: high, medium, or low
- `notes`: short audit notes

## Consumer Rules

- Consumers must tolerate missing optional fields.
- Low-confidence mechanics should not silently produce high-confidence simulation results.
- Raw source payloads are audit data and should not replace normalized fields unless debugging enrichment drift.
