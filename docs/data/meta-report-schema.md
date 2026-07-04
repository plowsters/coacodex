# Meta Report Schema

Schema version: `coa-meta-report-v1`

The meta report is the canonical Phase 1 theorycraft output. JSON is the source of truth. Markdown and HTML are renderings of the same model.

## Top-Level Object

- `schema_version`: always `coa-meta-report-v1`
- `generated_at`: UTC ISO timestamp
- `input_artifacts`: paths used for normalized entries and class metadata
- `run_config`: class/spec/level/encounter/search settings
- `assumptions`: report-level assumptions
- `warnings`: report-level warnings
- `class_summaries`: summaries derived from spec results
- `spec_results`: one row per class/spec/encounter profile

## Spec Result

- `class_name`
- `spec_id`
- `spec_name`
- `level`
- `encounter_profile_id`
- `search_profile_id`
- `scoring_profile_id`
- `apl_profile_id`
- `top_builds`
- `warnings`

## Build Result

- `rank`
- `projected_dps_index`
- `confidence_label`
- `selected_nodes`
- `score_breakdown`
- `generated_apl`
- `explanation`
- `provenance`
- `warnings`

`projected_dps_index` is a theorycraft index. It is not raw DPS, simulated DPS, observed DPS, or empirical DPS.
