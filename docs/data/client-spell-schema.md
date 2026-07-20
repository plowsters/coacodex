# Client Spell Schema

Records use schema version `coa-client-spell-v2` (M1.14E0), produced by `coa_client_extract` from the
CoA client's MPQ→DBC spell family. v2 builds records straight from raw `RecordView` cells under a
human-reviewed, hash-bound spell-layout **policy** (`coa_client_extract/data/spell_layout_v1.json`);
every emitted DBC-derived value carries a raw+proof `field_observations` entry, and the normalized
`mechanics`/`name` values are copied from those observations. Attribution is filled by M1.14B from
`CharacterAdvancement.dbc` (see [client-advancement-schema.md](client-advancement-schema.md)).

**Migration.** v1 (`coa-client-spell-v1`) and its table-level `schema_match_confidence_by_dbc` field
certification are **retired**. The Node reader rejects v1 rows/manifests with "regenerate with
M1.14E". Per-field/per-value observation proof is now authoritative.

## Required Fields
- `schema_version`: always `coa-client-spell-v2`
- `spell_id`: DBC spell id
- `name`: localized spell name from `Spell.dbc` (`null` if withheld)
- `mechanics`: normalized scalars (each `null` when withheld/unresolved): `power_type`, `school_mask`,
  `cast_time_ms`, `duration_ms`, `range_min_yd`, `range_max_yd`, `spell_icon_id`. **`category` is
  omitted from v2** (no proven cell). A normalized value is present ONLY when its observation is
  promotion-eligible (proof verified) AND, for `power_type`/`school_mask`, the value is in-domain.
- `field_observations`: per DBC-derived value, a raw+proof observation:
  - **Envelope** (numeric scalars): `{state, raw_u32, decoded, decoded_reason, proof, evidence_ref}`.
    `power_type`/`school_mask` are per-value **domain-gated**: an unseen enum/bit sets
    `decoded_reason: "value_out_of_domain"`, keeps `raw_u32`, and withholds the normalized value.
  - **StringObservation** (`name`, `description`): `{state, raw_offset, resolved, decoded_reason, proof,
    evidence_ref}`. `description` is `reference`-grade (tooltip macros unresolved) → `resolved` withheld.
  - **JoinObservation** (`cast_time_ms`, `duration_ms`, `range_min/max_yd`, `spell_icon_id`):
    `{state, components, composed_proof, decoded, decoded_reason}` with honest states `resolved` /
    `not_applicable` (index 0) / `unresolved` (side row missing, or an un-adjudicated null-cell join).
  - `proof` facets are `{integrity, layout, interpretation}` ∈ `{verified, reference, unproven,
    contradicted}`. See [DECISIONS.md](../DECISIONS.md) Decision 23.
- `provenance`: `base_archive`, `patch_chain`, `effective_archive`, `source_dbcs`, `policy_sha256`,
  `extraction_date`
  - `patch_chain` / `effective_archive` are StormLib's own reported chain (winner last), not attach order.
  - `source_dbcs` maps each contributing table (`Spell`, `SpellCastTimes`, `SpellDuration`,
    `SpellRange`, `SpellIcon`) to the archive that supplied it.
  - `policy_sha256` pins the exact spell-layout policy the record was extracted under.
  - Structural drift no longer produces a per-field low flag: a drifted spell-family table makes
    `open_view`/`require_dense` raise and the whole extract **fails closed** (nothing is emitted).
- `coa_attribution`: **filled by M1.14B** from the `CharacterAdvancement.dbc` participation model
  (see [client-advancement-schema.md](client-advancement-schema.md) and
  [DECISIONS.md](../DECISIONS.md) Decision 18-amended). The M1.14A placeholder
  `coa_attribution.status: "unknown"` is gone, replaced by:
  - `is_coa`: `true` iff any evidence contributes the `coa` mode
  - `modes`: sorted list of every mode this spell participates in — exactly one or more of `coa`,
    `reborn`, `stock` (three values, no others). A node whose class kind is the `ConquestOfAzeroth`
    sentinel (class-type 35, kind `coa_system` — see
    [client-class-types-schema.md](client-class-types-schema.md)) contributes mode `coa`; `coa_system`
    is a class **kind**, never a member of `modes[]`. A spell can legitimately carry more than one mode
    (e.g. reused across CoA and Reborn); that is multi-mode reuse, not an unresolved conflict.
  - `exclusive_mode`: the single mode when `len(modes) == 1`, else `null`
  - `confidence`: `high` (advancement-registry membership, including the sentinel), `medium` (no
    advancement row, but on a proven CoA skill line), or `low` (absent from both the advancement graph
    and the proven CoA skill-line index — `is_coa: false`, regardless of `id_range`; a stock-ID orphan
    gets the identical `low`/`is_coa: false` result, since `id_range` separates custom from stock, it
    does not gate this branch)
  - `archive_family` and `id_range`: the M1.14A raw signals are **retained**, unchanged in meaning,
    as provenance-only fields alongside the new participation block (`archive_family` is known
    uninformative for CoA-vs-other partitioning; kept for audit, not decision-making)
  - `memberships[]` (sibling field, not nested under `coa_attribution`): the spell's aggregated,
    stable list of `(class, tab)` contexts across every advancement node that realizes it — see
    [client-advancement-schema.md](client-advancement-schema.md) for the shared-spell `503748`
    example. Never a scalar `class`/`spec` field that flips to an array; a stock/classless membership
    never overwrites a CoA one. Each membership dict carries `mode`, `class_type_id`,
    `class_internal`, `class_display`, `class_kind`, `tab_type_id`, `tab_name`, `node_id`, and
    `entry_type`. `class_kind` is the owning class's raw kind (`coa_class` | `coa_system` | `reborn` |
    `stock` | `meta` | `unknown`, see [client-class-types-schema.md](client-class-types-schema.md)) —
    it gives consumers the system-vs-playable distinction (e.g. the `ConquestOfAzeroth` sentinel,
    `class_kind: "coa_system"`) without polluting `coa_attribution.modes[]`, which stays exactly
    `coa | reborn | stock`.
  - **The alpha→display class rename (`Bloodmage`/`Felsworn`/`Templar`, see
    [client-class-types-schema.md](client-class-types-schema.md)) does not affect this record.** It is
    curated presentation metadata applied only to `class_display` inside `memberships[]`; the client's
    own `class_type_id` and `is_coa`/`modes` results are computed from the raw client identity and are
    unaffected by the rename either way.

## Mechanics scope (M1.14A)
M1.14A extracts the reduced spell family: `Spell` plus the three index tables it references
(`SpellCastTimes`, `SpellDuration`, `SpellRange`). The umbrella spec's fuller mechanical set
— spell cooldowns/category cooldowns, rune cost, and the `SpellEffect` `effects[]` join — is
**deferred to a later M1.14 sub-milestone**. Those tables are load-bearing for the M1.16
power model, not for M1.14A extraction, and are tracked as follow-up rather than dropped.

## The CoA Spell Projection (`coa-client-spell-projection-v2`)

`coa_client_extract/artifacts.py::write_client_spell_projection` filters the full `coa-client-spell-v2`
extract down to the CoA-attributed subset (`coa_attribution.is_coa == true`) and writes it plus a
binding manifest. The projection — not the full spell extract — is the client-tier input the Node
mechanics build reads. **It is published transactionally inside a generation** and consumed via the
validated pointer (see [client-extract-generation-schema.md](client-extract-generation-schema.md)); the
fixed-path files remain only for the legacy `--allow-fallback-mechanics` degraded path.

**Projected fields.** Each row is a full `coa-client-spell-v2` record (including its
`field_observations` block) — the projection filters rows, it does not reshape them.

**Manifest shape:**

```jsonc
{
  "schema_version": "coa-client-spell-projection-v2",
  "inclusion_rule": { "predicate": "coa_attribution.is_coa == true", "version": "m1.14e-1" },
  "source_artifact": { "path": "coa_client_spell.jsonl", "sha256": "...", "byte_length": 12345 },
  "projection": { "path": "coa_client_spell_coa.jsonl", "sha256": "...", "byte_length": 6789 },
  "client_build": "3.3.5a+<top-patch>",
  "extractor_commit": "...", "extraction_date": "YYYY-MM-DD",
  "counts": { "source_records": 40000, "projected_records": 1234, "unique_spell_ids": 1234,
              "by_confidence": { "high": 1000, "medium": 200, "low": 34 } },
  "value_gate_summary": { "records_with_withheld_value": 12, "records_all_in_domain": 1222 }
}
```

`value_gate_summary` (replacing v1's `schema_confidence_summary`) buckets rows by whether any
`field_observations` entry withheld a normalized value for an out-of-domain symbol (`raw` retained).

`coa_scraper/scripts/lib/mechanics-projection.mjs` (`loadAndValidateProjection`) is the sole reader: it
re-hashes both files and rejects the pair on any sha256/byte_length mismatch, a **v1 schema** (with
"regenerate with M1.14E"), a non-`is_coa` row, a duplicate `spell_id`, a count mismatch, or a
populated numeric normalized value that disagrees with (or lacks) its `field_observations` entry.

## Enum & Sentinel Reference

These maps live in `coa_scraper/scripts/lib/mechanics-normalize.mjs` and are the ground truth for
normalizing `mechanics.school_mask` and `mechanics.power_type`.

**`SCHOOL_MASK_BITS`** (WotLK 3.3.5a `Spell.dbc` school mask; a mask is a sum of set bits — a spell
with fire **and** shadow damage carries mask `4 | 32 == 36`):

```js
{ 1: "physical", 2: "holy", 4: "fire", 8: "nature", 16: "frost", 32: "shadow", 64: "arcane" }
```

**`POWER_TYPE_MAP`** (`Spell.dbc` `PowerType` enum → resource name):

```js
{ "-2": "health", "0": "mana", "1": "rage", "2": "focus", "3": "energy",
  "4": "happiness", "5": "runes", "6": "runic_power" }
```

**`DURATION_SENTINELS`**: `{ INFINITE: -1 }`. A `mechanics.duration_ms` (or DBC `SpellDuration`
`base_ms`) value of `-1` is the legitimate WotLK "infinite / until cancelled" sentinel — it is
**preserved as `-1`**, never treated as a parse error or coerced to `null`/`0`. `null`/absent means
"no duration data"; `-1` means "infinite duration"; the two are never conflated.

## Canonical Build Failure Conditions

`coa_scraper/scripts/lib/mechanics-projection.mjs` validates every projection row **before**
reconciliation and **fails the whole build closed** (throws `MechanicsBuildError`, no partial output)
on any of:

- A **v1 schema** on the manifest or any row — rejected with "regenerate with M1.14E".
- An `m.school_mask` bit not in `SCHOOL_MASK_BITS`, or an `m.power_type` not in `POWER_TYPE_MAP`
  (defensive; the extractor's per-value gate already withholds these to `null`).
- A populated numeric normalized value that **disagrees with its `field_observations` entry**, or a
  populated numeric field with **no** observation — the proof/observation is authoritative.
- A **torn projection pair** (exactly one of the JSONL / manifest exists); only a fully-absent
  projection may degrade via `--allow-fallback-mechanics`.
- Malformed types (non-string/null `name`, non-number/null numeric fields, non-integer/null int
  fields, a negative `school_mask`), sha256/byte-length mismatch against the manifest, a duplicate or
  non-`is_coa` row, or a `builder_missing_from_projection` coverage gap.

Table-level drift is no longer a projection failure condition: structural drift fails the *extract*
closed (nothing is emitted), so any row that reaches the projection already parsed cleanly. See
[mechanics-schema.md § Mechanics Manifest](mechanics-schema.md#mechanics-manifest-coa-mechanics-manifest-v1)
for how canonical vs. fallback builds are recorded.

## Consumer Rules
- Per-field/per-value **observation proof** is authoritative. A `mechanics.*` value is trustworthy iff
  it is non-`null` (it was populated only because its observation was promotion-eligible and in-domain).
- The reconciler treats a populated client value as eligible by construction; a `null` value is simply
  absent (no separate table-drift eligibility signal exists anymore).
- Fields may be `null`; consumers tolerate partial records. `field_observations` retains the `raw` for
  every withheld value for audit.

## M1.14E0R — `coa-client-spell-v3`

The full-table child is now the **compact** `coa-client-spell-v3` row: identity + normalized `mechanics`
+ `coa_attribution` + a compact `raw` block (scalar `raw_u32`/string `raw_offset`+`resolved`, join
components, and `state`), with proof/promotion/evidence **inferred from the pinned policy via a
`policy_ref`** rather than repeated per row. The CoA projection (`coa-client-spell-projection-v3`) is the
`is_coa` subset; a consumer re-derives eligibility independently from the staged policy child. Graph
attribution (class memberships) lives in `coa_client_advancement.jsonl`, not on the spell row.
