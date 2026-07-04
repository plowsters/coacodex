# Scoring Profile Schema

Scoring profiles use schema version `coa-scoring-profile-v1`.

## Purpose

Profiles convert legal build states into theorycraft projected DPS indexes. They do not produce observed DPS and do not prove live meta rankings.

## Required Fields

- `schema_version`
- `profile_id`
- `class_name`
- `spec_key`
- `role`
- `supported_encounters`
- `baseline_index`
- `weights`
- `named_boosts`
- `regex_boosts`
- `synergies`
- `anti_synergies`
- `confidence`
- `assumptions`

## Output

The theory scorer emits:

- `source: theorycraft`
- `projected_dps_index`
- `raw_score`
- `confidence`
- `uncertainty`
- `components`
- `assumptions`
- `warnings`

Projected indexes are relative theorycraft values. They are not raw DPS.
