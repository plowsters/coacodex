# E0R.1 shared golden corpus

One frozen fixture corpus consumed by **both** the Python and Node trust-boundary suites so the two verifiers
can never silently diverge. The VALID baselines are produced by the real pipeline
(`iter_spell_records` / `project_v3_row` / `iter_icon_catalog`) against the synthetic `policy.json`; each
REJECT case is a labelled targeted mutation that violates exactly one named invariant.

Every row carries `case` (label) and `golden_accept` (expected verdict). Consumers strip those two keys before
handing the row to a validator.

## `policy.json`
Reviewed `coa-spell-layout-v2` doc. Fields exercise every proof/promotion combination:
`power_type` (verified/normalized numeric), `school_mask` (verified-layout / **reference** / **raw_only**),
`name` (string, normalized), `cast_time_ms` (**resolved** numeric join), `duration_ms` (**absent** null-cell
raw_only join — the reviewed_ambiguous state), `spell_icon_id` (string join, normalized).
`artifact_contract` (E0R.2 T2.3) names the FULL observation domain — `required_raw_observations` (every
scalar and non-icon join a full row's `raw` must carry, regardless of promotion), `required_mechanics_keys`
and `nullable_mechanics_keys` (the keys that must be PRESENT, with `null` a recorded observation), and
`icon_observation_domain` (the joins the icon child owns instead). It is derived from the tables/joins and
re-derived at load, so it cannot drift from the layout it describes. It replaced an optional
`required_scalar_fields` list that named only the normalized scalars — and that the real policy never
carried, so the consumer's domain check asked nothing of any real row.

## `projection_rows.jsonl` — rich `field_observations` dialect (row semantics: Node T3.1, Python T3.3, golden)
| case | accept | violates |
|------|--------|----------|
| `valid` (×3) | ✅ | — baseline projected rows |
| `unresolved_join_not_populated` | ✅ | absent join, not eligible, not populated (correct) |
| `eligible_not_populated` | ❌ | biconditional: `power_type` eligible but mechanics value dropped |
| `populated_not_eligible` | ❌ | biconditional: raw_only `school_mask` carries a value |
| `decoding_disagreement` | ❌ | mechanics value ≠ re-decode of `raw_u32` |
| `tampered_proof` | ❌ | observation proof claim ≠ policy |
| `tampered_decoded` | ❌ | observation decoded claim ≠ re-decode |
| `projection_carries_raw` | ❌ | wrong dialect (projection must be rich only) |
| `missing_field_observations` | ❌ | projection lacks `field_observations` |
| `unresolved_join_populated` | ❌ | absent join carries a mechanics value |
| `index_zero_join_not_populated` | ✅ | fk==0 join (components WITHOUT `side_value`), not eligible, not populated — the verifier must not touch `components.side_value` (pre-T3.3 Python KeyErrored here) |
| `side_row_missing_join_not_populated` | ✅ | nonzero fk with no side row, same no-`side_value` shape |
| `index_zero_join_populated` | ❌ | unresolved (fk==0) join carries a mechanics value — must fail the biconditional as a ValueError, never crash |

## `full_rows.jsonl` — compact `raw` dialect (full-domain row semantics: Node T3.1)
| case | accept | violates |
|------|--------|----------|
| `valid_full` (×3) | ✅ | — baseline compact rows |
| `required_field_omitted_from_both` | ❌ | `power_type` absent from **both** mechanics and raw (validator must iterate policy-required ∪ mechanics ∪ raw) |
| `full_carries_field_observations` | ❌ | wrong dialect (full must be compact only) |

## `icons.jsonl` — `coa-client-spell-icons-v1` (cross-child + bundle: Node T3.1b, Python T3.3)
| case | accept | violates |
|------|--------|----------|
| `valid_icon` (×3) | ✅ | — source_only + placeholder baselines |
| `placeholder_with_path` | ❌ | a placeholder must have a null `client_path` |
| `converted_without_ref` | ❌ | E0R.2 T2.5: `converted` is not an admissible `asset_status` at all (the case name is the retired rule it was written for) |
| `source_only_with_converted_ref` | ❌ | E0R.2 T2.5: `converted_ref` is not an admissible key on any status — the shape rejects it, and `_verify_icon_row`/`verifyIconRow` restate the prohibition behind that |
| `trailing_icon_beyond_domain` | ❌ | icon row `spell_id` beyond the full-table domain (trailing/extra) |

The valid full/projection/icon baselines share spell ids `{1,2,3}`, so `expand_compact(full.raw) ==
projection.field_observations` and the streaming cross-child merge-join hold over them (guarded in
`tests/test_e0r1_corpus.py`).

Regenerate with `scratchpad/gen_e0r1_corpus.py` (kept out of the repo); the committed JSON is the authority.
