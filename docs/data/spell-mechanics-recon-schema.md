# Spell-Mechanics Recon Schema

Report schema `coa-spell-mechanics-recon-v1`, produced by `coa_client_extract mechanics-recon`
(`coa_client_extract/spell_mechanics.py`). The recon is a **hard hold**: it discovers, by scanning,
every column the spell-layout policy will emit, then reports whether those discoveries agree with an
already-reviewed, client-bound policy. **Recon never writes the policy** — it only proposes a delta.

## Lifecycle (`status`)

- `blocked` — evidence collection failed (a required table missing/unreadable, an expected-absent
  table present, header drift, duplicate spell ids, an anchor not uniquely discoverable, or over
  budget). CLI exit **3**. `blocking_findings` lists each cause.
- `review_required` — discovery succeeded but the results are not yet reviewed/bound (the policy is
  not `reviewed`, or its `bound` does not match the opened client). CLI exit **4**.
- `verified` — every discovery agrees with an already-reviewed, hash-bound policy whose
  `bound.client_build` + per-DBC sha256 match the opened client. CLI exit **0**.

StormLib absent is a separate fail-closed (exit **2**).

## Fields

- `schema_version`: `coa-spell-mechanics-recon-v1`
- `status`: the lifecycle value above
- `blocking_findings`: `[{field, reason, ...}]` — empty unless `status == "blocked"`
- `source_pins`: `dbc` (per-table `{sha256}`), `policy_sha256`, `extractor_commit`, `client_build`,
  `effective_archive`, `patch_chain`
- `layout_proof`: per anchor field (`power_type`, `school_mask`, `name`) —
  `{discovered_cell, coverage, unique, matches_policy}`. Discovery scans **every** cell for the one
  that matches **all** present anchors; it never assumes the policy's cell.
- `index_fk`: per adjudicated join index field — the discovered FK cell + validity stats, or a
  `no_unique_index_cell` finding. Only joins whose policy index cell is non-null are re-checked.
- `enum_domains`: `power_type_observed`, `unknown_power_types`, `unknown_school_bits` — unseen symbols
  are recorded, never blocking (the extractor's per-value gate withholds them downstream).
- `topology`: per required / expected-absent table — `{present, required|expected_absent}`
- `proposed_policy_delta`: `{field: discovered_cell}` for every uniquely-discovered anchor + index
  cell. This is the recon's ONLY output about layout — a human applies it to the policy.
- `duplicates`, `budget`: duplicate spell ids (sample) and the real budget report (serialized bytes,
  elapsed, peak RSS ceilings).

## Discovery is genuine, not a policy echo

A plain FK-validity scan cannot uniquely resolve the spell→side-table join index columns: on the real
client, dozens of small-integer columns coincidentally fall inside a side table's id range (empirically
>25 candidates per side table). E0 therefore ships the joins **un-adjudicated** (`raw_only`, null index
cells) and leaves their promotion to M1.14E1's value-anchor joined-pair discovery (validate the index
cell by resolving through to KNOWN cast/duration/range values for anchor spells). The scalar substrate
(`id`, `name`, `power_type@41`, `school_mask@225`) is anchor-proven and verified.

## Manual adjudication procedure (the one-time human step)

1. Run `coa_client_extract mechanics-recon --client-root <Data> --out <dir>` → exit 4
   (`review_required`) against an un-adjudicated policy.
2. Review `proposed_policy_delta` and the `layout_proof` / `index_fk` evidence in the report.
3. Author the confirmed cells + `bound` (`client_build` + per-DBC sha256) into
   `coa_client_extract/data/spell_layout_v1.json`, set the field facets, and flip `reviewed: true`.
   Re-hash the policy (`compute_policy_sha256`).
4. Re-run recon → exit 0 (`verified`). Only a `verified`, bound policy lets `regenerate` emit canonical
   v2 artifacts. This procedure is deliberately human — recon never self-approves.

## M1.14E0R

Recon and regenerate share **one** source-topology verifier (`verify_source_topology`): sha256 + full
5-field header + member/effective-archive/patch-chain + density + key-uniqueness per required table, plus
the expected-absent set, matched facet-for-facet against the reviewed policy's structured `bound`. Recon
also reports joined-pair value-anchor discovery (all four side-table joins), a static `power_type`
negative anchor (a signed reading proven by an observed negative), and the three-part budget.
