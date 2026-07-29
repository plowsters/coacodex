# e0r2_corpus_v4 — the v4 (hoisted + interned) full-child baseline

`full_rows.jsonl` holds the same five cases as `../e0r1_corpus/full_rows.jsonl`, re-encoded as
`coa-client-spell-v4` (E0R.2 T6.2): each cell keeps only its substrate plus the interned vocabulary
codes `s`/`d`, and `policy_ref`/`join_name` come from the field descriptors both languages derive from
the policy.

It sits **beside** the v3 corpus rather than replacing it. `e0r-v1` remains a supported contract
revision, so a generation published under it must still validate and still expand — which is impossible
if the v3 baseline is overwritten. Every cross-language test that reads the v3 corpus keeps reading it.

The policy, projection and icon baselines are **shared with `../e0r1_corpus/`**: the projection dialect
does not change in v4 (expansion absorbs the encoding), so duplicating those files here would create two
copies that can drift apart while claiming to describe one contract.

Both languages assert the same two properties over these bytes:

* every v4 cell expands to *exactly* what its v3 twin expands to, for all three cell shapes (scalar,
  absent join, resolved join);
* the payload is materially smaller — 3,678 bytes here against 7,884 for the same rows in v3.

The second number is small because corpus strings are short. The real generation's attribution is what
this is for: `policy_ref` 88.6 MB, `decoded_reason` 55.4 MB, `state` 36.3 MB, `join_name` 22.3 MB.
