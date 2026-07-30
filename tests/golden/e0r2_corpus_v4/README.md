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

## `icons.jsonl` / `icon_assets.jsonl` — the normalized icon pair (T6.3), corrected by T8.1

The association/asset cases live here because T6.3 introduced the dialect. Four of them were added by
**T8.1**, when the first real-client regenerate under `e0r-v3` failed on spell 1: the client's
`SpellIcon` row 1 exists, is proven, and its path string is **empty**.

That is a *fifth* null cause T6.3 did not enumerate. It is not `index_zero` (the FK is 1), not
`side_row_missing` (the row is present), and not `proof_withheld` (the join decoded) — the path is
provably nothing, which is what `verified_empty` means. The cases pin both halves: `verified_empty_path`
is the accepted encoding, while `decoded_null_without_emptiness_claim` (the exact contradiction the
producer used to emit), `unresolved_claims_emptiness` and `reference_claims_emptiness` must all be
rejected, so the new value cannot be used to launder an unread field into a read one.
