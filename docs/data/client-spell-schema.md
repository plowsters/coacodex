# Client Spell Schema

Records use schema version `coa-client-spell-v1`, produced by `coa_client_extract` (M1.14A) from the
CoA client's MPQ→DBC spell family. Attribution is now filled by M1.14B from `CharacterAdvancement.dbc`
(see [client-advancement-schema.md](client-advancement-schema.md)); reconciliation into
`coa-mechanics-v1` is M1.14C.

## Required Fields
- `schema_version`: always `coa-client-spell-v1`
- `spell_id`: DBC spell id
- `name`: localized spell name from `Spell.dbc`
- `mechanics`: object with `school_mask`, `power_type`, `cast_time_ms`, `duration_ms`,
  `range_min_yd`, `range_max_yd`, `category`, `spell_icon_id` (any may be null when the source row is
  absent)
- `provenance`: `base_archive`, `patch_chain`, `effective_archive`, `source_dbcs`,
  `schema_match_confidence` (`high`|`low`), `schema_match_confidence_by_dbc`, `extraction_date`
  - `patch_chain` / `effective_archive` are StormLib's own reported chain of archives that
    supplied the winning bytes (winner last), not the attach order.
  - `source_dbcs` maps each contributing table (`Spell`, `SpellCastTimes`, `SpellDuration`,
    `SpellRange`) to the archive that supplied it.
  - `schema_match_confidence_by_dbc` (**M1.14C**, `coa_client_extract/artifacts.py`): a per-table
    breakdown, `{"Spell": "high"|"low", "SpellCastTimes": "high"|"low", "SpellDuration": "high"|"low",
    "SpellRange": "high"|"low"}`. `schema_match_confidence` (singular, M1.14A) is a coarse whole-record
    summary driven only by `Spell` table drift; `schema_match_confidence_by_dbc` is the finer-grained
    signal M1.14C's mechanics reconciler actually consumes — each mechanics field only accepts a
    client-sourced value when **every** DBC table that field depends on is `"high"` for that record (see
    [Canonical Build Failure Conditions](#canonical-build-failure-conditions) below). A table entry is
    `"low"` when that side table is absent, or present but drifted; `Spell` itself is `"low"` when
    `Spell.dbc` parsed with drift. Since `name` and every `mechanics.*` field ultimately depend on
    `Spell`, a `Spell: "low"` record is unusable as a client-tier source for **any** field, not just the
    ones with their own side table.
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

## The CoA Spell Projection (`coa-client-spell-projection-v1`)

`coa_client_extract/artifacts.py::write_client_spell_projection` filters the full `coa-client-spell-v1`
extract down to the CoA-attributed subset and writes it, plus a binding manifest, as a separate
artifact. This projection — not the full spell extract — is the client-tier input
`coa_scraper/scripts/build-mechanics-artifacts.mjs` reads when building `coa-mechanics-v1` records
(see [mechanics-schema.md](mechanics-schema.md)).

**Scope.** The projection includes exactly the records where `coa_attribution.is_coa == true`
(the `inclusion_rule.predicate` recorded in the manifest below) — i.e. it is scoped by the client's
**own** attribution, never by the Builder's `spell_id` domain. A record can be `projection_only`
(present in the projection, absent from the Builder) and the projection does not filter that out.

**Files.** `coa_client_spell_coa.jsonl` (the filtered records, one `coa-client-spell-v1` record per
line) and `coa_client_spell_projection.manifest.json` (the binding manifest), both written under
`reports/client_extract/`. Duplicate `spell_id`s in the filtered set are a hard error (raised before
either file is written). Written with the same manifest-as-validity-marker protocol as the mechanics
artifact: old manifest removed first, JSONL written atomically, manifest written atomically last.

**Projected fields.** Each row is a full `coa-client-spell-v1` record (`schema_version`, `spell_id`,
`name`, `mechanics`, `provenance` including `schema_match_confidence_by_dbc`, `coa_attribution`,
`memberships[]`) — the projection does not strip or reshape fields, it only filters rows.

**Manifest shape:**

```jsonc
{
  "schema_version": "coa-client-spell-projection-v1",
  "inclusion_rule": { "predicate": "coa_attribution.is_coa == true", "version": "m1.14c-1" },
  "source_artifact": { "path": "coa_client_spell.jsonl", "sha256": "...", "byte_length": 12345 },
  "projection": { "path": "coa_client_spell_coa.jsonl", "sha256": "...", "byte_length": 6789 },
  "client_build": "3.3.5a+<top-patch>",
  "extractor_commit": "<git sha of coa_client_extract at extraction time>",
  "extraction_date": "YYYY-MM-DD",
  "counts": {
    "source_records": 40000,
    "projected_records": 1234,
    "unique_spell_ids": 1234,
    "by_confidence": { "high": 1000, "medium": 200, "low": 34 }
  },
  "schema_confidence_summary": {
    "records_with_any_low_table": 12,
    "records_all_high": 1222
  }
}
```

`by_confidence` buckets projected rows by `coa_attribution.confidence` (`high`/`medium`/`low`, see
above). `schema_confidence_summary` buckets by whether **any** table in that row's
`schema_match_confidence_by_dbc` is `"low"` — a quick health check independent of `by_confidence`.

`coa_scraper/scripts/lib/mechanics-projection.mjs` (`loadAndValidateProjection`) is the sole reader:
it re-hashes both files and rejects the pair on any sha256/byte_length mismatch, missing/mismatched
`schema_version`, a non-`is_coa` row, a duplicate `spell_id`, or a count mismatch against the
manifest — before a single record is used for reconciliation.

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

- An `m.school_mask` bit not present in `SCHOOL_MASK_BITS` (an **unknown mask bit**).
- An `m.power_type` value not present in `POWER_TYPE_MAP` (an **unknown power enum**).
- `schema_match_confidence_by_dbc.Spell !== "high"` — `Spell` table drift makes the whole record
  (name + every mechanics field) unusable as a client-tier source.
- Per-table drift on a **populated** field the field depends on: e.g. `mechanics.cast_time_ms` is
  present but `schema_match_confidence_by_dbc.SpellCastTimes !== "high"`. The dependency matrix is
  `cast_time_ms` → `Spell`+`SpellCastTimes`; `duration_ms` → `Spell`+`SpellDuration`; `range_max_yd` →
  `Spell`+`SpellRange`; `school_mask`/`power_type` → `Spell` only. An **absent** field with a drifted
  side table does *not* fail the build (there's nothing populated to trust).
- A **torn projection pair**: exactly one of the projection JSONL and its manifest exists (JSONL
  present without its manifest, or manifest without its JSONL). Both must be present together, or
  both absent (only the fully-absent case is eligible to degrade). A half-written pair throws.
- Malformed types (non-string `name`, non-number/null numeric fields, non-integer/null int fields,
  a negative `school_mask`), a missing/malformed `schema_match_confidence_by_dbc` block, sha256 or
  byte-length mismatch against the projection manifest, a duplicate or non-`is_coa` row, or a
  `builder_missing_from_projection` coverage gap.

This is the *single malformed-input rule*: only a **fully-absent** projection (no file at all) is
eligible to degrade to a fallback build via `--allow-fallback-mechanics`; a **present-but-invalid**
projection fails the build even with that flag. See
[mechanics-schema.md § Mechanics Manifest](mechanics-schema.md#mechanics-manifest-coa-mechanics-manifest-v1)
for how canonical vs. fallback builds are recorded.

## Consumer Rules
- `schema_match_confidence: "low"` means DBC drift was detected for a contributing table; downstream
  consumers must not treat those mechanical fields as high-confidence.
- `schema_match_confidence_by_dbc` is the field-precise version of the same signal — prefer it over
  the coarse `schema_match_confidence` when deciding whether one specific mechanical field is trustworthy.
- Fields may be null; consumers tolerate partial records.
