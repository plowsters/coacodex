# Item Schema

Item records use schema version `coa-item-v1`.

## Purpose

Item records describe equipment, weapons, armor, and item effects used by gear recommendations and later personal simulations.

M1.9 sourced item records primarily from AscensionDB power payloads. That pipeline was **removed** by M1.14E0R and no client-native item extraction replaced it yet, so this schema currently has **no producer**: it documents the target shape for a later milestone, not an artifact the repository builds today.

## Required Fields

- `schema_version`: always `coa-item-v1`
- `item_id`
- `name`
- `confidence`
- `provenance`

## Common Optional Fields

- `icon`
- `quality`
- `slot`
- `item_class`
- `subclass`
- `weapon_type`
- `armor_type`
- `stats`
- `ratings`
- `speed`
- `min_damage`
- `max_damage`
- `spell_power`
- `attack_power`
- `required_level`
- `linked_spell_ids`
- `linked_item_ids`
- `tooltip_text`
- `source_urls`
- `raw`

## Consumer Rules

- Consumers must tolerate missing stat and slot fields.
- Role and gear recommendations should report low confidence when item data is tooltip-only.
- Uploaded character profiles in later phases should map items by `item_id` and retain the raw source text for audit.
