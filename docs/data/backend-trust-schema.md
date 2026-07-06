# Backend Trust Schema

Schema version: `coa-backend-trust-v1`

Backend trust reports are internal Phase 1 QA artifacts. They are not rendered in guide HTML and must not be presented as player-facing empirical confidence until Phase 2 logs exist.

## Trust Result

- `schema_version`
- `subject_id`
- `trust_label`
- `score`
- `components`
- `watchlist_matches`
- `warnings`

## Component

- `component_id`
- `score`
- `weight`
- `notes`

Trust scores are coarse internal diagnostics. They are not observed DPS, HPS, mitigation, or player performance.

## User-Facing Boundary

Phase 1 guide HTML must not render backend trust scores, watchlist concerns, or live sanity labels. The sidecar exists for maintainers and future Phase 2 calibration only.
