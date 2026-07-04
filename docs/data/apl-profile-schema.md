# APL Profile Schema

APL profiles use schema version `coa-apl-profile-v1`.

## Purpose

Profiles drive Phase 1 action-priority-list generation from normalized builder data and legal build states. They do not execute rotations, ingest logs, or produce DPS.

## Required Fields

- `schema_version`
- `profile_id`
- `class_name`
- `spec_key`
- `role`
- `supported_encounters`
- `resources`
- `thresholds`
- `condition_templates`
- `rules`
- `branches`
- `assumptions`

## Supported Match Operators

- `tags_any`
- `tags_all`
- `schools_any`
- `resources_any`
- `name_contains_any`
- `description_matches_any`
- `entry_type_in`
- `essence_kind_in`
- `active_only`
- `passive_only`
- `selected_rank_at_least`

## Future Inputs

Profiles may list `combat_log_metrics`, `saved_variables_snapshot`, or `sim_state` in `future_inputs` for compatibility planning. M1.5 profiles must not require those inputs.
