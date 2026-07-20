# Mechanics Schema

Mechanics records use schema version `coa-mechanics-v1`.

## Purpose

Mechanics records describe how spells, passives, buffs, debuffs, pets, and item effects behave when the simulator or report explainers need more than builder legality data. The schema is intentionally tolerant of partial records because many fields are inferred from AscensionDB tooltips or later log calibration.

## Required Fields

- `schema_version`: always `coa-mechanics-v1`
- `spell_id`: canonical spell identifier when available
- `name`: display name
- `kind`: ability, passive, buff, debuff, cooldown, pet_action, item_effect, proc, or another explicit mechanic kind
- `effects`: zero or more mechanic effect records
- `provenance`: source and confidence records
- `confidence`: high, medium, or low

## Common Optional Fields

- `source_node_ids`: builder node IDs associated with the spell
- `source_urls`: AscensionDB or other source URLs
- `school`, `power_type`, `range_yards`
- `schools`: additive multi-school list — see [Schools](#schools) below
- `cast_time_ms`, `gcd_ms`, `cooldown_ms`, `charges`
- `duration_ms`, `tick_interval_ms`
- `costs`, `generates`, `spends`
- `max_targets`
- `proc`
- `field_provenance`: per-field candidate/selection audit trail — see
  [Field-Level Provenance](#field-level-provenance-field_provenance) below. As of M1.14C,
  `coa_scraper/scripts/build-mechanics-artifacts.mjs` always emits this object, but the loader
  (`coa_meta/mechanics.py`) treats it as optional (a hand-authored or legacy record may omit it).
- `raw`: audit-only payload, never a normalized-field replacement. As emitted by
  `build-mechanics-artifacts.mjs`, `raw.tags` carries the merged, set-like union of every
  contributing builder node's tags — **builder tags are not a top-level field**; they live under
  `raw.tags` only. `raw` also carries `category`, `spell_icon_id`, `school_mask` (client-sourced,
  when present) and the AscensionDB audit trio `db_status`, `db_excluded`, `db_exclusion_reason`,
  plus `linked_item_ids`. None of `raw.*` is part of the normalized contract.

## Effect Fields

Effects use `effect_type` values such as:

- `damage`
- `heal`
- `absorb`
- `aura_apply`
- `aura_refresh`
- `resource_delta`
- `summon`
- `cooldown_modify`
- `stat_modify`
- `trigger_spell`

Effects may include `school`, `target`, `amount`, `aura`, `stat`, `trigger_spell_id`, `duration_ms`, `tick_interval_ms`, `scaling`, `tags`, and raw source data. `tick_interval_ms` is the canonical field name emitted by the builder; the `coa_meta/mechanics.py` loader also accepts a legacy `period_ms` key on input for backward compatibility, but always **reserializes** it as `tick_interval_ms` — `period_ms` never survives a round-trip.

## Provenance

Every inferred or source-derived record should include provenance:

- `source`: builder, ascension_db, tooltip_parser, override, log_calibration, or another explicit source
- `source_id`: source-local identifier such as `spell:2001`
- `source_url`: optional canonical URL
- `parser`: parser or rule name
- `confidence`: high, medium, or low
- `notes`: short audit notes

## Schools

`schools` (a list of school-name strings) is the **authoritative** multi-school field, added in
M1.14C. `school` (singular) is a **single-school convenience** derived from it:

- `schools.length === 1` → `school` is set to that one value (e.g. `"fire"`).
- `schools.length === 0` or `schools.length > 1` → `school` is the empty string `""`. A multi-bit
  school mask (e.g. fire + shadow) is **not** collapsed into one arbitrary winner in `school`; only
  `schools` reflects the full set.

Consumers that need every school a spell belongs to **must** read `schools`, not `school`.
`school` exists only for callers that only ever care about the common single-school case.

The bit → school-name mapping (`SCHOOL_MASK_BITS`, from `coa_scraper/scripts/lib/mechanics-normalize.mjs`)
is the WotLK 3.3.5a `Spell.dbc` school mask, validated against observed CoA data:

| Bit | School |
| --- | --- |
| 1 | physical |
| 2 | holy |
| 4 | fire |
| 8 | nature |
| 16 | frost |
| 32 | shadow |
| 64 | arcane |

A school-mask bit outside this table is an **unknown mask bit** — see
[client-spell-schema.md](client-spell-schema.md) for the fail-closed rule this triggers on a
canonical build.

## Field-Level Provenance (`field_provenance`)

`field_provenance` is an object keyed by mechanics field name (e.g. `name`, `kind`, `cast_time_ms`,
`duration_ms`, `range_yards`, `schools`, `power_type`, `cooldown_ms`, `gcd_ms`, `costs`, `effects`).
Each value has the shape:

```jsonc
{
  "selected_source": "client_dbc" | "builder" | "ascension_db" | "inferred" | null,
  "selected_tier": "client_dbc" | "verified_builder" | "ascension_db" | "inferred" | null,
  "selected_value": <the value that won, or null if the field was omitted>,
  "selection_reason": "highest_precedence_eligible" | "only_candidate" | "db_fallback"
    | "inferred_last_resort" | "inferred_from_text" | "kind_node_disagreement_resolved"
    | "omitted_unresolved_conflict" | "omitted_no_eligible_candidate",
  "warnings": ["kind_node_disagreement", ...],
  "candidates": [ /* every candidate considered, see below */ ]
}
```

Each entry in `candidates[]` records one source's contribution attempt, whether or not it won:

```jsonc
{
  "source": "client_dbc" | "builder" | "ascension_db",
  "precedence_tier": "client_dbc" | "verified_builder" | "ascension_db" | "inferred",
  "source_id": "client_spell:805775" | "builder_node:1234" | "ascension_db:9001",
  "source_field": "cast_time_ms" | "school_mask" | "entry_type" | "tooltip_text" | ...,
  "raw_value": <value as read from the source, before normalization>,
  "normalized_value": <value after normalization, or null>,
  "confidence": "high" | "medium" | "low",
  "eligible": true | false,
  "eligibility_reasons": ["client_table_drift", "unknown_mask_bit", "unknown_enum",
    "same_tier_conflict", "db_identity_mismatch", "db_identity_unverifiable", ...],
  "contributed": true   // present ONLY on `kind` and `effects` candidates
}
```

A candidate's `source` is always one of `client_dbc`, `builder`, or `ascension_db` — **never**
`inferred`. `inferred` is a *tier* / *field-level source*, not a candidate source: it appears only as
a candidate's `precedence_tier` (see below) and as a field-level `selected_source` / `selected_tier`
(on the `effects` field, whose value is heuristically inferred rather than drawn from any single
candidate).

`precedence_tier` is one of four ranked tiers, highest first: `client_dbc` → `verified_builder` →
`ascension_db` → `inferred`. Within a tier, if two or more present candidates disagree, **all**
candidates in that tier are marked `eligible: false` with reason `same_tier_conflict` and the field
falls through to the next tier (never a node-order winner). The first eligible candidate in
precedence order wins.

`source` and `precedence_tier` are **not** independent, and a `builder` candidate does not sit at a
fixed tier: for the `name` and `kind` fields a builder candidate is `verified_builder`, but for the
five reconciled *mechanical* fields (`schools`, `power_type`, `cast_time_ms`, `duration_ms`,
`range_yards`) a builder candidate is `inferred` (builder-derived mechanics are inferred data, ranked
below `ascension_db`). This is why `per_field_winner_counts_by_tier` (in the manifest) will show
`verified_builder` wins for `name`/`kind` but **never** for `schools`/`power_type`/etc. — a builder
win on a mechanical field is counted under `inferred`, not `verified_builder`.

The `contributed` flag exists only on the `kind` and `effects` entries in `field_provenance`. Both
`kind` (ability/passive/debuff/cooldown/pet_action classification) and `effects` (heuristically
inferred from tag/tooltip text) are **not** reconciled through the tiered precedence engine above —
they are derived from every builder node plus the record's tooltip text. `contributed: true` marks
each candidate whose value was actually incorporated into the emitted result — so for `kind`, **every**
builder-node candidate is `contributed` (the classification is derived from all nodes), and the
tooltip candidate is `contributed` only when it is db-sourced; for `effects`, the db tooltip candidate
is `contributed` only when db-sourced. Marking the db tooltip this way is how the record-level
`provenance` array (below) can list `ascension_db` even when no top-level field's `selected_source`
is `ascension_db` — a DB-sourced tooltip that only informed `kind`/`effects` still counts as DB
participation.

## Record-Level `confidence`

The top-level `confidence` field is an aggregate computed by `build-mechanics-artifacts.mjs` from the
per-field `selected_source` values:

1. `"high"` — **both** `schools` and `power_type` were selected from `client_dbc`, **and** at least
   one of `cast_time_ms` / `duration_ms` was also selected from `client_dbc`.
2. `"medium"` — the `"high"` condition isn't met, but at least one field anywhere in the record was
   selected from `client_dbc`.
3. `"low"` — no field was selected from `client_dbc` (the record relies entirely on
   builder/AscensionDB/inferred data).

## Mechanics Manifest (`coa-mechanics-manifest-v1`)

Every mechanics build (canonical or fallback) writes a companion manifest alongside the JSONL
(`coa_mechanics.manifest.json` / `coa_mechanics.fallback.manifest.json`), written by
`coa_scraper/scripts/build-mechanics-artifacts.mjs`. The manifest — not the JSONL — is the validity
marker: it is written last, atomically, after the JSONL, and the previous manifest is removed first,
so a crash never leaves a stale manifest next to a new JSONL.

```jsonc
{
  "schema_version": "coa-mechanics-manifest-v1",
  "generated_at": "<ISO 8601 timestamp>",
  "canonical": true | false,          // true only for a real-projection build
  "client_source": "present" | "absent",
  "fallback_authorized": true | false, // true only on a degraded (--allow-fallback-mechanics) build
  "reconciliation_policy_version": "m1.14c-1",
  "reconciler_commit": "<git HEAD of the reconciler build; null on a fallback build>",
  "client_build": "<from the projection manifest; null on a fallback build>",
  "inputs": {
    "builder_entries": { "path": "...", "sha256": "..." } | null,
    "db_spell_tooltips": { "path": "...", "sha256": "..." } | null,
    "projection": { "path": "...", "sha256": "..." },        // {path:null, sha256:null} when absent
    "projection_manifest": { "path": "...", "sha256": "..." } // {path:null, sha256:null} when absent
  },
  "outputs": { "mechanics_jsonl": "coa_mechanics.jsonl", "sha256": "...", "record_count": 1234 },
  "coverage": {                        // null on a fallback (degraded) build
    "builder_joined_to_projection": 1200,
    "builder_missing_from_projection": 0,
    "projection_only": 34
  },
  "per_field_winner_counts_by_source": { "cast_time_ms": { "client_dbc": 900, "ascension_db": 50 }, ... },
  "per_field_winner_counts_by_tier": { "cast_time_ms": { "client_dbc": 900, "ascension_db": 50 }, ... },
  "counts": { "unresolved_conflicts": 0, "ineligible_candidates": 0, "omitted_fields": 0, "kind_disagreements": 0 }
}
```

**Canonical vs degraded/fallback.** `canonical: true` builds require a present, validated client
projection (see [client-spell-schema.md](client-spell-schema.md)) and are written to the plain
`coa_mechanics.jsonl` / `coa_mechanics.manifest.json` filenames. `canonical: false` builds happen only
when the projection is **entirely absent** and `--allow-fallback-mechanics` was passed; they are
written **only** to the separate `coa_mechanics.fallback.jsonl` / `coa_mechanics.fallback.manifest.json`
filenames — a degraded build never writes the canonical filenames, so a stale canonical artifact from
a previous run is never silently shadowed by a degraded one. A *present but invalid* projection
(bad schema, checksum mismatch, per-table drift on a used field, unknown mask/enum, an `is_coa:false`
row, or a coverage gap) fails the build **even with** `--allow-fallback-mechanics` — only a
fully-**absent** projection is eligible to degrade.

`inputs` binds every source file's content by sha256, so the manifest fully pins reproducibility.
`coverage` (present only on a canonical build) accounts for the join between the Builder's
`spell_id` domain and the projection: `builder_missing_from_projection` must be `0` for a canonical
build to succeed at all (`loadAndValidateProjection` fails the build closed otherwise); `projection_only` counts CoA-attributed
client spells with no Builder node. `per_field_winner_counts_by_source` / `_by_tier` are per-field
histograms of which `selected_source` / `selected_tier` won across all rows — a quick audit of how
much of the artifact is client-backed vs DB-fallback vs inferred.

`reconciler_commit` is the git HEAD of the reconciler build (the CLI populates it best-effort from
`git rev-parse HEAD`, `null` if that fails) and `client_build` is sourced from the validated
projection manifest's `client_build`. Both are `null` on a fallback (degraded) build — a fallback has
no real projection to bind to, and `canonical: false` disables `reconciler_commit` regardless of
whether a commit could be resolved.

`counts` is an aggregate audit block computed in a single pass over the emitted rows'
`field_provenance` (on BOTH canonical and fallback builds — fallback rows carry real
`field_provenance`, so the counts are honest there too). Zero-valued keys are always present (never
omitted). The four counts:
- **`ineligible_candidates`** — total number of candidate objects, across every row and every
  `field_provenance` entry, with `eligible === false`. Captures every candidate the reconciler barred:
  same-tier conflicts, db identity mismatch, client-table drift, etc.
- **`omitted_fields`** — number of (row, field) provenance entries where `selected_source` is falsy
  **AND** `candidates.length > 0`: a field for which candidate data existed but none survived
  eligibility (e.g. an identity-barred db-only field, or a same-tier-conflict omission). The
  `candidates.length > 0` guard deliberately excludes fields that simply never had a candidate (e.g.
  `effects` on a spell with nothing to infer) — those are not "omissions" in the audit sense.
- **`unresolved_conflicts`** — number of (row, field) provenance entries whose
  `selection_reason === REASON.OMITTED_UNRESOLVED_CONFLICT`. This is the subset of `omitted_fields`
  caused specifically by an unresolved same-tier conflict (`unresolved_conflicts` ⊆ `omitted_fields`);
  it may legitimately be `0` in the common case.
- **`kind_disagreements`** — number of rows whose `field_provenance.kind.selection_reason ===
  REASON.KIND_NODE_DISAGREEMENT_RESOLVED` (the `kind` field's Builder nodes disagreed and were
  resolved by behavior-order).

## Consumer Rules

- Consumers must tolerate missing optional fields.
- Low-confidence mechanics should not silently produce high-confidence simulation results.
- Raw source payloads are audit data and should not replace normalized fields unless debugging enrichment drift.

## M1.14E0R — `coa-mechanics-v2`

`costs` is now `dict | None` (`null` = unknown, `{}` = verified empty) and is **always serialized
explicitly** (missing ≠ default). Each record may carry `field_readiness` `{field: {status, reason_code}}`
validated against the readiness state machine — see
[field-readiness-schema.md](field-readiness-schema.md). The loader hard-rejects `coa-mechanics-v1`. With
AscensionDB removed, `cooldown_ms`/`gcd_ms`/`costs` are `null` + `{unavailable, pending_e1_operand}` until
M1.14E1 supplies the operands.
