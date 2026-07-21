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
`required_scalar_fields` names the normalized Spell scalars a full row must carry (`id`, `name`, `power_type`).

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
| `converted_without_ref` | ❌ | a converted row must carry a `converted_ref` |
| `source_only_with_converted_ref` | ❌ | a non-converted row must not carry a `converted_ref` |
| `trailing_icon_beyond_domain` | ❌ | icon row `spell_id` beyond the full-table domain (trailing/extra) |

The valid full/projection/icon baselines share spell ids `{1,2,3}`, so `expand_compact(full.raw) ==
projection.field_observations` and the streaming cross-child merge-join hold over them (guarded in
`tests/test_e0r1_corpus.py`).

Regenerate with `scratchpad/gen_e0r1_corpus.py` (kept out of the repo); the committed JSON is the authority.
