# Client-Extract Generation Schema

`coa_client_extract regenerate` publishes the CoA spell projection transactionally as an immutable
**generation** and emits a validated **pointer** (`coa_client_extract/publish.py`). The Node mechanics
build (consumer) REQUIRES this pointer for a canonical run and re-validates it
(`coa_scraper/scripts/lib/generation.mjs`).

## Layout

```
<root>/
  coa_client_extract.pointer.json          # the active pointer (published LAST, atomically)
  gen-<uuid4hex>/                           # immutable; created with exist_ok=False (collision-safe)
    manifest.json                           # generation-local binding manifest
    coa_client_spell_coa.jsonl             # the CoA projection (coa-client-spell-v2 rows)
    coa_client_spell_projection.manifest.json
```

## Pointer (`coa-client-extract-pointer-v1`)

`{schema_version, generation_id, manifest_path, manifest_sha256}`. Published last, so a reader never
sees a pointer to a half-written generation.

## Manifest (`coa-client-extract-manifest-v2`)

A **superset of all ten v1 manifest fields** plus:

- `generation_id`, `published_at` (monotonic ns), `predecessor_generation_id` (the pointer's prior
  target captured at publish — the load-bearing link for retention, since a random UUID + date-only
  field cannot identify the predecessor)
- `children`: `{name: {sha256, byte_length, records, schema_version}}` — the exact child inventory
- `outputs`: a deterministic `{name: sha256}` **index view** derived from `children`, for *migrated*
  resolvers only — NOT backward compatibility for unmigrated v1 consumers (who get a pointer + v2 rows
  they cannot read; hence the migration)
- `unknown_symbol_inventory`: `{power_type: [...], school_bits: [...]}` — the per-value gate's aggregate
- `binding`: `source_dbc` (`{sha256, header, archive}` per table), `policy_sha256`,
  `anchor_set_sha256`, `enum_policy_sha256`

## Resolver validation (Python `resolve_active_generation`, Node `resolveGeneration`)

Both fail closed on any mismatch: pointer schema, `gen-<id>/` containment, manifest hash vs pointer,
manifest `generation_id`, and for **each** child — safe name (no absolute/`..`/separators), path
containment, sha256, byte length, record count (`.jsonl` = non-empty lines; else 1), non-empty
`schema_version`, and uniqueness. A consumer never reads an unvalidated child.

## Producer publishes; consumer requires

`regenerate` publishes the pointer as an output and never takes one as input. The Node
`build-mechanics-artifacts.mjs` **requires `--client-extract-pointer`** for a canonical run and
validates it; the legacy fixed-path `--projection`/`--projection-manifest` mode runs only under the
existing `--allow-fallback-mechanics` degraded path. Passing both is an error.

## Retention (separate best-effort maintenance — publish never prunes)

`prune-generations` follows the `predecessor_generation_id` chain (ordered by `published_at`) to keep
the current pointer target + its immediate predecessor, and removes older `gen-*` only past a grace
period **and under an enforced quiescent window / advisory lock**. Absent quiescence it deletes nothing
and returns the plan — the semantics are documented best-effort.

## M1.14E0R — `coa-client-extract-manifest-v3` (transactional)

The manifest gains `publication_state` (`candidate` | `published`) and a `candidate_trust_sha256` over
every trust-critical field. A **candidate** manifest is never pointer-resolvable; publication validates the
candidate by path in Python **and** Node (per-child + a streaming cross-child merge-join over sorted
`spell_id`), then writes the **final** manifest (only `publication_state`/`validation`/`budget` may differ,
reproducing the trust digest) and the pointer **last** under a process lock. Required children now include
the full v3 spell child, the v3 projection + its manifest, the `coa-client-spell-icons-v1` catalog, and the
reviewed `spell_layout_v2.json` policy child. `binding` carries the full verified source **topology**.
