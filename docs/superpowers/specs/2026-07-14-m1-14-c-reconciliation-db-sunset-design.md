# M1.14C Reconciliation and DB Sunset Design

> Third sub-milestone of [M1.14 Client DBC Data Foundation](2026-07-06-m1-14-client-dbc-data-foundation-design.md).
> Depends on M1.14A (`coa-client-spell-v1` extraction, WDBC per-table drift) and M1.14B (the
> `coa_attribution` participation block that scopes the projection). Realizes
> [Decision 18](../../DECISIONS.md) — the client becomes the top **per-field** mechanical source —
> inside the existing Node mechanics builder, without rewiring any consumer.
>
> Revised 2026-07-15 after design review: output domain and coverage accounting made explicit; one
> consistent malformed-input rule; per-DBC-table confidence; the full mechanics-record construction
> contract (name/kind/effects/confidence/provenance); candidate source identity; evidence-based
> conflict handling; a single canonical DB input; complete manifest hashing; required-input and item
> split; exact ignore filenames; concrete client acceptance assertions.

## Purpose

M1.14C makes the CoA client the authoritative per-field mechanical source in the mechanics artifact
and demotes db.ascension.gg to fallback-only. It does this by (1) having the Python extractor emit a
compact, attribution-scoped **client-spell projection** (with per-DBC-table confidence) that crosses
cleanly into the Node pipeline, and (2) replacing the mechanics builder's "one source per row" join
with a **per-field candidate selection** that records every competing value, with source identity, and
the reason each field's winner was chosen. The mechanics schema stays `coa-mechanics-v1`; the audit
data and the `schools` list are added as backward-compatible optional fields that the loader
round-trips, and `MechanicsRepository` keeps loading the artifact.

M1.14C is a data-plumbing and provenance milestone. It changes which source supplies each mechanical
field — including the spell **name** — and makes that decision auditable. It does not extract any new
client field, does not rewire any consumer, and does not change user-facing output.

## Non-Goals (deferred within M1.14, or later)

- **No extraction widening.** M1.14C consumes only the mechanical fields M1.14A/B already produce in
  `coa-client-spell-v1` (`cast_time_ms`, `duration_ms`, `range_min_yd`/`range_max_yd`, `school_mask`,
  `power_type`, `category`, `spell_icon_id`) plus the spell `name`. Cooldown, GCD, charges, costs,
  effects, coefficients, proc data, and server-side scaling are **not** in the client extract and are
  out of scope; they stay on the db/inferred tiers exactly as today. Adding DBC tables
  (`SpellRuneCost`, `SpellCooldowns`, `SpellEffect`, …) is a later extraction task. **Adding
  per-table confidence to the projection is provenance correction, not extraction widening** — it
  surfaces the per-table drift the WDBC reader already computes.
- **No rank-family consolidation.** Mechanics rows are keyed by distinct Builder `entry.spell_id`. If a
  higher rank of an ability is exposed as its own `spell_id`, it remains its own row; folding a rank
  family into one record is deferred. In the current Builder capture no rank spell_id appears as a
  separate entry (3,612 entries / 3,611 unique `spell_id`; only `503748` sits on two nodes), so the
  grouping rule operates on exact `spell_id` equality.
- **No consumer rewire and no user-facing change.** `coa_meta`'s report path
  (`reporting.py::_mechanics_repository_from_nodes`) still synthesizes mechanics from the selected
  Builder nodes; it does **not** load `coa_mechanics.jsonl`. Actual consumption of the reconciled
  artifact by scoring/rotation/reports is **M1.16**'s job. M1.14C's deliverable is the reconciled,
  provenanced artifact and its manifest — not a changed page. Stated so the milestone cannot "succeed"
  while leaving every user-facing result identical without saying so.
- **No Builder-graph or legality change.** The Builder remains authoritative for the talent graph, node
  descriptions, and legality until M1.15 (Decision 21). C only touches mechanical fields and the name.
- **No redistribution-boundary change.** The real projection, the real mechanics artifact, and their
  manifests stay untracked (see [Redistribution boundary](#redistribution-boundary-and-ignore-rules)).
  C commits only schemas, synthetic fixtures, tests, ignore rules, and regeneration docs.
- **Item generation is split out**, not deleted (see [Inputs, CLI, atomicity](#inputs-cli-flags-and-atomic-output)).

## Architecture

Two stages joined by a versioned artifact, preserving the Python-extraction / Node-mechanics seam.
Python owns extraction and CoA scoping; Node owns reconciliation and the `coa-mechanics-v1` contract.

### Data flow

```
coa_client_extract (Python, M1.14A/B)
  ├─ coa_client_spell.jsonl                       167 MB full Spell.dbc extract (audit/archive; untracked)
  └─ coa_client_spell_coa.jsonl + coa_client_spell_projection.manifest.json   NEW (M1.14C)
        · scope: coa_attribution.is_coa == true  (includes client-only CoA spells)
        · NOT scoped by Builder spell IDs — the Builder never becomes a whitelist
        · each record gains schema_match_confidence_by_dbc  (Spell/CastTimes/Duration/Range)
        · manifest binds the projection to its source, the full extract, and a client build
                            │  (compact: ~thousands of rows, hashable)
                            ▼
build-mechanics-artifacts.mjs (Node, M1.14C)   per-field reconciliation over the BUILDER spell_id domain
        client_dbc  ▸  verified Builder  ▸  AscensionDB  ▸  inferred tooltip
        (single canonical DB input; entry.db_enrichment ignored)
                            │
                            ▼
  coa_mechanics.jsonl  (coa-mechanics-v1)  +  coa_mechanics.manifest.json (coa-mechanics-manifest-v1)
        · one row per distinct Builder spell_id
        · name/kind/effects/confidence/provenance/source_urls/raw + normalized fields + schools
        · field_provenance  (winner + reason + every candidate WITH source identity)
        · manifest binds canonical/degraded status + all input hashes to the JSONL sha256

build-item-artifacts.mjs (Node, split)  →  coa_items.jsonl   (independent of mechanics fail-closed)
                            │
                            ▼
  MechanicsRepository (coa_meta) — loads unchanged API; now round-trips field_provenance AND schools
        · real consumption by scoring/reports is M1.16
```

### Output domain and coverage accounting

`coa_mechanics.jsonl` is scoped to the **unique current Builder `entry.spell_id` values** — the domain
the artifact has always had. The attribution-scoped projection is a *candidate source*, deliberately
broader (it includes client-only CoA spells the Builder never exposed); those client-only records are
**carried in the projection for M1.15/M1.16** and do **not** produce mechanics rows in M1.14C. Scoping
the *output* to the Builder domain does **not** make the Builder an attribution whitelist — the
projection is independently client-scoped by `is_coa`; the Builder only decides which of those spells
already have a graph row to attach mechanics to today.

The build computes and reports coverage, three-way:

- `builder_joined_to_projection` — Builder spell IDs found in the projection.
- `builder_missing_from_projection` — Builder spell IDs absent from the projection.
- `projection_only` — projection spell IDs with no Builder entry (expected > 0; the client-only set).

A **canonical** build requires `builder_missing_from_projection == 0`, matching M1.14B's proven 100%
unique-spell recall: if the client extract has drifted enough to lose a Builder spell, that is a
regression to fix, not a silent db-fallback. (Under `--allow-fallback-mechanics` with an *absent*
projection this check is moot — there is no projection to cover the domain.)

## Components

### Python — projection emitter and per-table confidence (`coa_client_extract`)

A new writer (`artifacts.py::write_client_spell_projection`, invoked by the `regenerate` CLI) emits
`coa_client_spell_coa.jsonl` from the already-built `coa-client-spell-v1` records, keeping every record
whose `coa_attribution.is_coa` is `true`. Each projected record is the client-spell record **plus one
additive field nested under `provenance`** (sibling of the existing `provenance.schema_match_confidence`
and `provenance.source_dbcs`):

```json
"provenance": {
  "…": "… existing coa-client-spell-v1 provenance …",
  "schema_match_confidence": "high",
  "schema_match_confidence_by_dbc": { "Spell": "high", "SpellCastTimes": "high", "SpellDuration": "high", "SpellRange": "high" }
}
```

Today `artifacts.py` sets a single record-level `provenance.schema_match_confidence` from `spell.drift` only,
so a misparsed `SpellCastTimes`/`SpellDuration`/`SpellRange` could still masquerade as `high`. The
WDBC reader already computes `DbcTable.drift` per table; the emitter surfaces those per-table results
into `schema_match_confidence_by_dbc`. The legacy scalar `schema_match_confidence` is retained
(it stays the `Spell`-table value) for backward compatibility; the per-table map is what eligibility
consults.

The projection is a **filtered, provenance-corrected view** of `coa-client-spell-v1`, not a new spell
schema — it reuses the client-spell schema and its tests, plus the new per-table field.

Alongside it, a **projection manifest** (`coa-client-spell-projection-v1`) records:

- `source_artifact`: path + `sha256` + `byte_length` of the full `coa_client_spell.jsonl`.
- `projection`: path + `sha256` + `byte_length` of `coa_client_spell_coa.jsonl`.
- `client_build`, `extraction_date` (from the extraction manifest).
- `inclusion_rule`: literal predicate (`coa_attribution.is_coa == true`) + version.
- `counts`: `source_records`, `projected_records`, unique `spell_id` count, breakdown by
  `coa_attribution.confidence` (`high`/`medium`) and `modes`.
- `schema_confidence_summary`: per-table `high`/`low` counts across the projection.
- `extractor_commit`: the `coa_client_extract` git commit.

### Node — per-field reconciliation (`build-mechanics-artifacts.mjs`)

`buildMechanicsRows` is reworked into: **validate projection + manifest → group Builder entries by
`spell_id` → gather candidates (with source identity) per field from every source → select per field →
construct the full record → emit one row per `spell_id`**. A single `reconcileField(candidates, policy)`
helper implements precedence, eligibility, and conflict handling and returns both the selected value and
the `field_provenance` entry, so the policy lives in one testable function. Item building moves to
`build-item-artifacts.mjs`.

### Python — loader round-trip (`coa_meta/mechanics.py`)

`MechanicRecord` gains **optional** `schools: tuple[str, ...]` and `field_provenance` (a small mapping
of field name → selection record). `mechanic_from_raw` and `to_dict` learn to read and re-emit both, so
load-and-reserialize no longer discards them. This stays `coa-mechanics-v1` (added optional fields, no
type change). Without this, `schools` and `field_provenance` would be silently dropped on the first
round-trip. `MechanicsRepository` keeps its public API and keys by `spell_id`.

## Per-field reconciliation

### Precedence, eligibility, and conflict handling

For each field, the builder assembles candidates and selects the **first *eligible* candidate** in
precedence order — eligible = *present* **and** *successfully normalized* **and** *structurally valid*
**and** *permitted by the validity gates*. First-eligible, never first-non-null.

**Source, precedence tier, and eligibility are three separate properties**, never conflated:

- **`source`** — a candidate's actual origin: `client_dbc`, `builder`, `ascension_db`, or `inferred`.
- **`precedence_tier`** — where it competes: `client_dbc` ▸ `verified_builder` ▸ `ascension_db` ▸
  `inferred` (highest first). A Builder-native field lands in `verified_builder` **only when its M1.2
  source/inferred split marks it source-provided**; a regex-inferred Builder field (e.g.
  `damage_schools`/`resources` derived from tooltip text) lands in the `inferred` tier instead.
  Tier assignment is *not* a disqualification — a Builder-inferred candidate is fully **eligible** at
  the `inferred` tier; it just competes late.
- **`eligible`** — structural/policy validity (present, normalized, valid, passes the validity gates and
  the gates below). A candidate can be eligible in a low tier, or ineligible in a high tier.

Selection is the first candidate that is `eligible`, walking tiers highest-first (first-eligible, never
first-non-null). AscensionDB values are **regex-parsed from the tooltip HTML, not structured DB
mechanics**, and are fallback-only after M1.14C; they never override an eligible client value. The
selected `field_provenance` entry records **both `selected_source` and `selected_tier`**.

**Record-level DB identity gate.** A stale db row is stale for *all* its contributions, not only the
name. The gate computes identity itself rather than trusting the existing `name_match` — which is
Builder-based (`normalizeName(db.name) === normalizeName(builder.name)`) and therefore the wrong
authority once the client name is canonical, and is capture-dependent (the committed artifact carries
the stale `805775` → *Fang Venom: Lifeblood* with `name_match: false`; a fresh fetch may currently
agree). The rule:

1. **Identity reference** = the client name if present; else the consensus verified-Builder name; else
   the db name.
2. **Compare** the normalized db name **directly** to that reference.
3. The existing Builder-based `name_match` is retained as **audit evidence only** — never an independent
   veto.
4. **On mismatch,** the db row is excluded from **every semantic contribution** — mechanical fields,
   inferred effects, **`kind`, `tags`,** and selected `provenance` — and preserved **only** in
   `candidates`/`raw` audit data, marked `db_identity_mismatch`. So a spell named *Adrenal Venom* (client)
   can never draw cooldown/GCD/cost/behavior from a stale *Fang Venom: Lifeblood* db row.

Fields with no surviving eligible candidate after the gate are omitted (mechanical fields) or fall to
the next non-db tier. The behavior is proven with a **synthetic stale-db fixture** (default tier) that
pins *Fang Venom: Lifeblood*; the real-client test asserts the gate outcome for the *actually observed*
db name (or pins the db artifact + its hash), never a presumed value.

**Same-tier disagreement is not resolved by fiat.** If two or more candidates in the *same* tier
disagree (e.g. the two Builder nodes for `503748` carry different inferred `damage_schools`), the tier is
not internally verified: **every** conflicting candidate in that tier is marked ineligible with
`same_tier_conflict` (not just one of them), and selection falls through to the next tier. If no eligible
candidate remains anywhere, the mechanical field is **omitted** and the unresolved conflict is recorded.
No lowest-node-id or node-order tiebreak is ever used to manufacture a winner. (Record-level required
fields — `name`, `kind` — cannot be omitted; their conflict rules are in
[Record construction](#record-construction-contract).)

Every candidate — winners, agreeing corroborators, and ineligible ones — is retained with full source
identity in `field_provenance`.

### Exact validity gates and the single malformed-input rule

There is **one** rule for degraded builds, stated once:

> `--allow-fallback-mechanics` authorizes exactly one condition: a **completely absent** projection. It
> does **not** authorize any malformed, drifted, or semantically unsupported *present* projection.

Consequences, applied uniformly (a canonical build fails on any of these; the fallback flag does **not**
rescue them):

- **Per-table client confidence.** A field's `client_dbc` candidate is eligible only if **every DBC
  table contributing to that field** is `high` in `schema_match_confidence_by_dbc`:
  `name`/`school(s)`/`power_type` need `Spell`; `cast_time_ms` needs `Spell` **and** `SpellCastTimes`;
  `duration_ms` needs `Spell` **and** `SpellDuration`; `range_yards` needs `Spell` **and** `SpellRange`.
  A contributing table below `high` for a spell that carries that field is an **abnormal extraction
  defect** and **fails the canonical build** (naming the table + sample spells) — it is *not* treated as
  a legitimately-absent field that silently falls through to db. Known DBC drift must be fixed upstream,
  not down-ranked.
- **Unknown enum / mask.** An unrecognized `school_mask` bit or `power_type` enum value is a
  normalization defect and **fails** the build. Never silently dropped, never degraded.
- **Attribution confidence.** The projection is `is_coa == true`, i.e. attribution `high` (advancement
  membership) or `medium` (proven CoA skill line); both are permitted for canonical client selection and
  the level is recorded per candidate. A row with `is_coa: false` in the projection is malformed → fail.
- **Coverage.** `builder_missing_from_projection == 0` (above). A gap fails the canonical build.
- **Checksum / schema.** The projection's `schema_version` must match; the manifest's `projection.sha256`
  must equal the projection file's hash; the manifest's `schema_version` must match. Any mismatch is
  malformed → fail.

### Field-mapping matrix (client → `coa-mechanics-v1`)

| `coa-mechanics-v1` field | Client source | Contributing DBC tables (all must be `high`) | Normalization | Notes |
|---|---|---|---|---|
| `name` | `name` | `Spell` | passthrough | precedence client → Builder → db (db name was previously first, preserving stale names) |
| `cast_time_ms` | `mechanics.cast_time_ms` | `Spell`, `SpellCastTimes` | int; **`null`=absent, `0`=instant** | missing ≠ zero |
| `duration_ms` | `mechanics.duration_ms` | `Spell`, `SpellDuration` | int; `null`=absent; negative handled per [sentinels](#enum-maps-and-numeric-sentinels) | |
| `range_yards` | `mechanics.range_max_yd` | `Spell`, `SpellRange` | float; use **max** | both endpoints retained in `field_provenance` as a `{min,max}` object |
| `school` (scalar) | `mechanics.school_mask` | `Spell` | single-bit mask → school string | convenience only; **omitted** when multi-bit |
| `schools` (list, **new**) | `mechanics.school_mask` | `Spell` | bitmask → sorted school list | authoritative; loader round-trips it |
| `power_type` | `mechanics.power_type` (int) | `Spell` | enum int → string via documented map | unknown value fails |
| — | `mechanics.category` | — | — | no v1 field; kept in `raw`/`field_provenance` only, not invented into v1 |
| — | `mechanics.spell_icon_id` | — | — | icons come from M1.11D; kept in `raw`/`field_provenance` only |
| `cooldown_ms`, `gcd_ms`, `charges`, `costs` | *(not in client extract)* | — | — | remain db/inferred-sourced, unchanged |

### Missing versus zero

`numberOrNull` currently coerces JSON `null` to `0` (`Number(null) === 0`), so an absent
`duration_ms: null` becomes a real `0` and a legit `cast_time_ms: 0` (instant) is indistinguishable from
missing. Fixed **before** eligibility: a helper distinguishes *absent* (`null`/`undefined`/missing key ⇒
candidate not present) from a *real numeric value* (including `0`). **Presence, not truthiness,** drives
candidate eligibility.

### Multi-school masks: the `schools` list

A `school_mask` is a **set**; with no client field defining primacy, "first bit" would manufacture
semantics. So:

- Single known bit → `schools: ["nature"]` **and** legacy `school: "nature"`.
- Multiple known bits → `schools: ["fire","frost"]`; the legacy scalar `school` is **omitted** (never
  filled from a lower tier, which would falsely imply a single-school spell).
- The raw mask + normalization detail are retained in `field_provenance`.
- `schools` is serialized in a **documented bit order**, explicitly **not** described as priority.
- An **unknown** mask bit **fails** the build.

Contract: when present, `schools` is authoritative; `school` is a backward-compatible single-school
convenience. Additive optional sibling ⇒ `coa-mechanics-v1`-compatible. M1.16 consumes `schools`.
`MechanicsRepository` round-trips `schools`.

### Record construction contract

A mechanics row is more than the numeric fields; M1.14C defines every field of the emitted record so a
mixed-source row is internally consistent:

- **`name`** — precedence `client_dbc` → verified Builder → AscensionDB. (Previously db-first, which
  kept stale names after the "sunset"; the acid test `805775` proves the client name now wins.)
- **`kind`** — derived from **spell-behavior signals** (tags/tooltip/cast presence) that are shared
  across a spell's nodes, **independent of node order**. Tooltip signals from an identity-mismatched db
  row are **excluded** (per the DB identity gate); tooltip-derived `kind`/`tags` fall back to the Builder
  node description in that case. When nodes disagree (e.g. `503748` is a `Talent` on node 7131 and an
  `Ability` on node 12264, giving `passive` vs `ability`), resolve by a documented behavior precedence —
  an active, castable behavior outranks a passive classification — and record a `kind_node_disagreement`
  warning in `field_provenance`. Never resolved by which node was iterated first.
- **`effects`** — still inferred (client effects are out of scope). To avoid an internally contradictory
  record, effect `duration_ms` and the scalar effect `school` are drawn from the **reconciled** top-level
  `duration_ms`/`schools` when those were client-selected, rather than independently from the db tooltip.
  `MechanicEffect.school` is a **scalar**, so when the reconciled `schools` is **multi-bit**, effect
  `school` is **omitted** (left empty) and the authoritative multi-school value lives only in top-level
  `schools`; M1.14C does not add an `effect.schools` list (avoids widening `MechanicEffect`). Effect
  timing is emitted as **`tick_interval_ms`** (see fixes). Effects derived from a db row that failed the
  DB identity gate are dropped (that row supplies nothing).
- **`confidence`** (record-level, required, used downstream) — a **conservative documented aggregate**:
  `high` only if `name`, `school(s)`, `power_type`, and at least one of `cast_time_ms`/`duration_ms` are
  all client-selected at per-table `high`; `low` if no client mechanical field was selected (spell
  absent from the projection, or degraded build); `medium` otherwise. The rule is documented in the
  schema so consumers can rely on it.
- **`provenance[]`** — deduplicated, one entry per **selected** source actually used in the record
  (`client_dbc`/`builder`/`ascension_db`/`inferred`), each with its confidence and notes. This is the
  record-level roll-up; per-field detail lives in `field_provenance`.
- **`source_urls`** — union of the db/source URLs of every source that contributed a **selected** value,
  de-duplicated.
- **`source_node_ids`** — sorted, unique node IDs of every Builder entry sharing this `spell_id`.
- **`raw`** — retains `category`, `spell_icon_id`, the raw `school_mask`, db status, and linked IDs for
  audit.

### `field_provenance` with source identity

An optional object keyed by mechanics field name. Field-level and candidate-level reasons are kept
**separate**:

```json
"field_provenance": {
  "schools": {
    "selected_source": "client_dbc",
    "selected_tier": "client_dbc",
    "selected_value": ["nature"],
    "selection_reason": "highest_precedence_eligible",
    "warnings": [],
    "candidates": [
      { "source": "client_dbc", "precedence_tier": "client_dbc", "source_id": "client_spell:805775",
        "source_field": "school_mask", "raw_value": 8, "normalized_value": ["nature"],
        "confidence": "high", "eligible": true, "eligibility_reasons": [] },
      { "source": "builder", "precedence_tier": "inferred", "source_id": "builder_node:7131",
        "source_field": "damage_schools", "raw_value": ["nature"], "normalized_value": ["nature"],
        "confidence": "medium", "eligible": false, "eligibility_reasons": ["same_tier_conflict"] },
      { "source": "builder", "precedence_tier": "inferred", "source_id": "builder_node:12264",
        "source_field": "damage_schools", "raw_value": ["shadow"], "normalized_value": ["shadow"],
        "confidence": "medium", "eligible": false, "eligibility_reasons": ["same_tier_conflict"] }
    ]
  }
}
```

- **Three separate properties per candidate** — `source` (origin), `precedence_tier` (where it competes),
  and `eligible` (validity). A Builder-inferred candidate has `source: "builder"`,
  `precedence_tier: "inferred"`, and `eligible: true` unless a defect disqualifies it — its tier is not a
  disqualification. The field entry records both `selected_source` and `selected_tier`.
- **Candidate identity** — every candidate carries `source`, `source_id` (e.g. `builder_node:7131`,
  `client_spell:805775`, `ascension_db:805775`), and `source_field`, so two Builder candidates are
  distinguishable (they must not both collapse to `"builder"`).
- **`selection_reason`** — one field-level stable code: `highest_precedence_eligible`, `only_candidate`,
  `db_fallback`, `inferred_last_resort`, `omitted_unresolved_conflict`, `omitted_no_eligible_candidate`.
- **`eligibility_reasons`** — candidate-level stable codes explaining **in**eligibility only (an eligible
  candidate has an empty list): `client_table_drift`, `same_tier_conflict`, `db_identity_mismatch`,
  `unknown_enum`, `unknown_mask_bit`, `absent`. (`builder_inferred` is **not** here — it is a
  `precedence_tier`, not a disqualification. `client_table_drift`, `unknown_enum`, `unknown_mask_bit`
  appear only in **failure diagnostics** — the error/report emitted when a canonical build fails — never
  in an emitted mechanics artifact: a canonical build fails on them, and a degraded build has no
  projection and therefore no client candidates at all.)
- **`warnings`** — optional field-level notes such as `kind_node_disagreement`.
- **range** `raw_value` is an object `{ "min": …, "max": … }` retaining both endpoints.

A **`coa-mechanics-v2`** is reserved for a real model break (e.g. `school`→list as the *primary* type,
or `range_yards`→structured object). Provenance and the additive `schools` sibling do not justify a bump.

## Canonical vs degraded, and the mechanics manifest

| Situation | Behavior |
|---|---|
| Projection present + valid | **Canonical** build → `coa_mechanics.jsonl` (+ canonical manifest). |
| A single client field legitimately absent (`null`) for a spell | field-level fallback to the next eligible tier; build stays **canonical**. |
| Projection **absent**, no flag | **Fail before writing anything.** |
| Projection absent + `--allow-fallback-mechanics` | Write a **degraded** artifact to `coa_mechanics.fallback.jsonl` (+ `coa_mechanics.fallback.manifest.json`). A fallback build **never** writes the canonical `coa_mechanics.jsonl`/`.manifest.json` — only a validated projection may produce the canonical filename. (`MechanicsRepository` reads the JSONL directly and never consults the manifest, so degraded bytes must never occupy the canonical filename regardless of a `canonical:false` marker.) |
| Projection **present but** malformed / wrong schema / checksum-invalid / per-table drift / unknown mask-enum / `is_coa:false` row / coverage gap | **Fail even with** `--allow-fallback-mechanics`. |

The manifest (`coa-mechanics-manifest-v1`) binds status **and all reconciliation inputs** to the output
hash, so status can never detach from the data or be reproduced from a different input set:

```json
{
  "schema_version": "coa-mechanics-manifest-v1",
  "generated_at": "…",
  "canonical": true,
  "client_source": "present",
  "fallback_authorized": false,
  "reconciliation_policy_version": "m1.14c-1",
  "reconciler_commit": "…",
  "client_build": "…",
  "inputs": {
    "builder_entries":  { "path": "dist/coa_entries.jsonl",            "sha256": "…" },
    "db_spell_tooltips":{ "path": "dist/coa_db_spell_tooltips.jsonl",  "sha256": "…" | null },
    "projection":       { "path": "…/coa_client_spell_coa.jsonl",      "sha256": "…" },
    "projection_manifest": { "path": "…", "sha256": "…" }
  },
  "outputs": { "mechanics_jsonl": "coa_mechanics.jsonl", "sha256": "…", "record_count": 3611 },
  "coverage": { "builder_joined_to_projection": 3611, "builder_missing_from_projection": 0, "projection_only": … },
  "per_field_winner_counts_by_source": { "cast_time_ms": {"client_dbc": …, "ascension_db": …, "inferred": …}, "…": {} },
  "per_field_winner_counts_by_tier":   { "cast_time_ms": {"client_dbc": …, "ascension_db": …, "inferred": …}, "…": {} },
  "counts": { "unresolved_conflicts": 0, "ineligible_candidates": …, "omitted_fields": …, "kind_disagreements": … }
}
```

Winner counts are recorded **both** ways because `source` and `precedence_tier` are distinct: a `builder`
source can win at the `verified_builder` tier *or* (demoted) at the `inferred` tier, so
`per_field_winner_counts_by_source` (keyed by `selected_source`) and `per_field_winner_counts_by_tier`
(keyed by `selected_tier`) answer different questions and neither is derivable from the other.

The manifest binds **both** the projection **and** its manifest hash, so client-build/confidence metadata
cannot change without changing a recorded hash. `db_spell_tooltips.sha256` is `null` when the db input is
legitimately absent (recorded explicitly, not silently).

**Degraded manifest.** A fallback run (absent projection + `--allow-fallback-mechanics`) writes a manifest
with the **same schema** but degraded values: `canonical: false`, `client_source: "absent"`,
`fallback_authorized: true`, `inputs.projection` and `inputs.projection_manifest` set to
`{ "path": null, "sha256": null }`, `client_build: null`, and `coverage: null` (there is no projection to
cover the domain). `outputs.mechanics_jsonl` points to `coa_mechanics.fallback.jsonl`. The degraded build
writes **only** the `coa_mechanics.fallback.*` files and leaves the canonical `coa_mechanics.jsonl`/
`.manifest.json` untouched — there is deliberately **no** flag to place degraded bytes at the canonical
filename, because `MechanicsRepository` reads the JSONL directly and would ingest them as canonical
regardless of a `canonical:false` marker in a sidecar manifest.

## Projection validation (beyond the file hash)

Before trusting a present projection, the Node builder validates what it can see **without** the 167 MB
source extract (which it never reads):

- projection-manifest `schema_version`;
- every row `schema_version == "coa-client-spell-v1"` and `coa_attribution.is_coa == true`;
- unique numeric `spell_id`s;
- recomputed **projection-side** row count, byte length, and `sha256` match the manifest, and recomputed
  per-table/mode summaries match the manifest's `schema_confidence_summary`/`counts`;
- coverage: no Builder `spell_id` is unexpectedly absent (`builder_missing_from_projection == 0`).

The **full-source** values (`source_artifact.sha256`, `source_records`) are produced by Python, which held
the full extract, and are **trusted from the manifest, not recomputed by Node** — Node cannot recompute
them without the 167 MB artifact. Any recomputable-value mismatch is a malformed-present-projection ⇒ fail
(even with the fallback flag).

## Carried-in contract fixes (prerequisites, not cleanup)

These ship **in** M1.14C because client data cannot be reconciled correctly on top of them:

1. **Missing-versus-zero** — fixed before candidate eligibility.
2. **One deterministic row per `spell_id`** — group Builder entries by `spell_id`, emit exactly one row
   with **sorted, unique** `source_node_ids` (fixes the `503748` two-node last-row-wins in
   `MechanicsRepository._by_spell_id`). Multiple nodes for one `spell_id` contribute **distinct,
   source-identified candidates**; grouping never introduces an implicit winner (see same-tier conflict
   handling and the `kind` rule).
3. **`period_ms` → `tick_interval_ms`** — the effect timing field is renamed to match the schema and the
   Python `MechanicEffect` loader (today Node emits `period_ms`, the loader reads `tick_interval_ms`, so
   periodic timing is silently dropped). The ossifying assertion in
   `coa_scraper/tests/pipeline-scripts.test.mjs` (asserting `effects[0].period_ms`) is corrected to the
   canonical name. For transition, the Python loader **temporarily accepts** a legacy `period_ms` key on
   input but **always reserializes** `tick_interval_ms`. Same "test locked in wrong behavior" pattern
   M1.14E audits, resolved here because it is in the file M1.14C rewrites.

## Inputs, CLI flags, and atomic output

- **Required inputs:** `dist/coa_entries.jsonl` (the **raw** Builder entries — *not* the enriched file).
  The Builder entries file defines the output domain and is **required**: a missing or invalid file
  **fails**. Passing the raw entries (not `coa_entries.enriched.jsonl`) eliminates the embedded
  `entry.db_enrichment` copy, so there is exactly **one canonical DB input** and the db data cannot
  bypass manifest hashing or the candidate policy.
- **Optional inputs:** `dist/coa_db_spell_tooltips.jsonl` (the single canonical db source). A missing db
  file is allowed (db simply contributes no candidates); its absence is recorded as
  `inputs.db_spell_tooltips.sha256: null`. Missing individual db *rows/fields* are likewise fine.
- **Projection input:** `coa_client_spell_coa.jsonl` + its manifest. Absence → fail-closed unless
  `--allow-fallback-mechanics`.
- **CLI flags & defaults:** `--builder-entries` (default `dist/coa_entries.jsonl`), `--db-spells`
  (default `dist/coa_db_spell_tooltips.jsonl`), `--projection` (default the repo-root
  `reports/client_extract/coa_client_spell_coa.jsonl`, reached as `../reports/...` when run from
  `coa_scraper/`), `--projection-manifest`, `--out` (default `dist`), `--allow-fallback-mechanics`.
  There is deliberately no flag to write degraded bytes to the canonical filename.
- **Item generation is a separate command** (`build-item-artifacts.mjs`, producing `coa_items.jsonl`)
  so canonical-mechanics fail-closed behavior never entangles item output and vice-versa.
- **Separate canonical vs fallback package commands (maintainer workflow).** Because the projection is
  untracked, a maintainer *without* the client cannot produce canonical mechanics — so the pipeline must
  not silently hard-fail for them, nor silently degrade for someone who *does* have the client. Two
  explicit npm scripts:
  - `build-mechanics` — **canonical**, fail-closed; requires a valid projection. Used by the
    client-holding maintainer and by release regeneration.
  - `build-mechanics:fallback` — passes `--allow-fallback-mechanics`; writes only the separate degraded
    files. The explicit, opt-in path for a client-less contributor.
  - `build-items` — the split item command.
  The `pipeline:m1.9` script calls `build-items` + `build-mechanics` (canonical) after the client
  projection exists; a documented `pipeline:m1.9:fallback` variant substitutes `build-mechanics:fallback`
  for client-less runs. `scripts/write-artifact-manifest.mjs` is updated to include the split item output
  and the new mechanics manifests (canonical and fallback) in the artifact manifest it aggregates.
- **Atomic output, manifest as the validity marker.** The manifest — not the JSONL — certifies a build.
  To avoid a crash leaving a *new* JSONL beside a *stale* manifest, the writer (1) **removes the previous
  manifest first**, (2) atomically replaces the JSONL (temp path + rename), then (3) writes the new
  manifest **also via temp path + atomic rename**, carrying the finalized JSONL's hash. Because the
  manifest write is itself atomic, an interruption leaves *no* manifest — never a *partial* or *stale*
  one — so the JSONL is simply uncertified and must be regenerated. (Equivalent alternative: publish a
  versioned output directory swapped in via one atomic pointer.)

## Redistribution boundary and ignore rules

Per Decision 20 (committed fixtures are **synthetic**, never client asset-derived bytes), the real
client-derived outputs stay untracked. M1.14C commits: the projection-manifest and mechanics-manifest
**schemas** + schema docs; **synthetic** fixtures (projection, db rows, Builder entries); the **tests**;
**explicit, file-specific** `.gitignore` rules; and **regeneration docs**.

The ignore rules name exact files, and must **not** blanket-ignore `reports/client_extract/` (the
tracked `coa_ca_decode_report.json` and `client_only_adjudication.json` must stay visible):

```
# client-derived factual outputs — regenerate from your own client
reports/client_extract/coa_client_spell.jsonl
reports/client_extract/coa_client_spell_coa.jsonl
reports/client_extract/coa_client_spell_projection.manifest.json
coa_scraper/dist/coa_mechanics.jsonl
coa_scraper/dist/coa_mechanics.manifest.json
coa_scraper/dist/coa_mechanics.fallback.jsonl
coa_scraper/dist/coa_mechanics.fallback.manifest.json
```

Regeneration docs state accurately: a fresh clone can reproduce the **tests** and the **fallback**
mechanics, but **cannot** reproduce the **canonical** artifact without the user's own client.

**Forward policy gate (mandatory, before M1.16 or any canonical public release).** M1.14C does not
broaden the boundary, but records a hard entry condition: before M1.16 consumes these artifacts, or
before any canonical public release, one explicit policy decision must cover **all** client-derived
outputs *consistently* — `coa_client_spell_coa.jsonl`, `coa_mechanics.jsonl`, and any site output that
embeds those derived facts. This is the mechanics analogue of the M1.15 adjacency-domain entry
condition; it must not disappear during decomposition.

## Enum maps and numeric sentinels

The `power_type` int→string map and the `school_mask` bit→name map are recorded in the design's
companion schema doc (`docs/data/client-spell-schema.md` cross-reference) and validated by a pre-plan
reconnaissance task against the real extract: enumerate the **observed** `power_type` values and
`school_mask` bits across the CoA projection and confirm the documented maps cover them exactly (an
unobserved-but-defined entry is fine; an observed-but-undefined value is the `unknown_enum`/
`unknown_mask_bit` failure). Numeric **sentinels** are checked against DBC semantics before being called
invalid — in particular, do **not** assume every negative `duration_ms` is invalid; WotLK
`SpellDuration` uses `-1` for "infinite/until-cancelled", which is a legitimate value to preserve, not a
parse error. The recon task records the real sentinel set so normalization treats them correctly.

## Decision impacts

- **Decision 18** moves from *planned* to *realized for the mechanical fields the client carries* (plus
  the name), via per-field precedence rather than wholesale replacement. The `source` value `client_dbc`
  joins the mechanics provenance vocabulary; db.ascension.gg is demoted to fallback-only for mechanical
  fields and the name.
- No new decision is required; C implements Decision 18 within the existing artifact contract. The
  redistribution forward-policy gate is flagged for decision at M1.16 / public release, not settled here.

## Error handling

- **Missing projection** → fail closed unless `--allow-fallback-mechanics` (which writes only the
  separate degraded file).
- **Malformed / drifted / unsupported present projection** (bad schema, checksum mismatch, per-table
  drift on a used field, unknown mask/enum, `is_coa:false` row, coverage gap) → **fail even with** the
  fallback flag.
- **Missing/invalid Builder entries file** → fail (required; defines the domain).
- **Missing db file or rows** → allowed; those tiers contribute no candidates (recorded).
- **DB identity mismatch** (normalized db name ≠ the identity reference: client name → consensus
  verified-Builder name → db name) → the db row is excluded from every semantic contribution (fields,
  effects, `kind`, `tags`, selected provenance), retained only in `candidates`/`raw` as
  `db_identity_mismatch`; affected fields fall to the next non-db tier or are omitted. Not a build
  failure — a stale db row is expected and handled, not an error. The Builder-based `name_match` is audit
  evidence only, never the veto.
- **Unresolved same-tier conflict** on an optional mechanical field → omit the field + record; on a
  required record field (`name`/`kind`) → resolve by the documented record-construction precedence.
- Every failure names the offending file/spell and the specific gate that rejected it.

## Testing strategy

Default tier (no client, no StormLib, CI):

- **Precedence truth table** — client wins when eligible; a legitimately-absent client field falls to
  db; a Builder-*inferred* field is demoted below db; db never overrides an eligible client value;
  agreeing candidates recorded as corroboration.
- **Per-table confidence** — a client candidate whose `SpellCastTimes` is `low` **fails a canonical
  build** for `cast_time_ms` (not a silent db-fallthrough); `Spell` `low` fails name/school/power.
- **Single malformed-input rule** — unknown mask bit / unknown power enum / checksum mismatch / wrong
  schema / `is_coa:false` row / coverage gap all fail **even with** `--allow-fallback-mechanics`; only a
  fully-absent projection degrades (to the separate file).
- **Same-tier conflict** — two Builder nodes disagreeing → **both** ineligible (`same_tier_conflict`) →
  fall through; if nothing remains, field omitted with `omitted_unresolved_conflict`; no node-order
  winner. A Builder-inferred candidate that does **not** conflict stays `eligible` at the `inferred` tier.
- **DB identity gate** — a **synthetic** db row whose name mismatches the identity reference (client name
  → consensus Builder → db) supplies **zero** selected contributions: its cooldown/GCD/cost candidates
  are present but `db_identity_mismatch`/`eligible:false`, and its inferred **effects, `kind`, and
  `tags`** are dropped (a pinned *Fang Venom: Lifeblood* row must not name-or-behavior-taint an *Adrenal
  Venom* record). A synthetic db row whose name **matches** the reference remains eligible fallback
  (proving the gate is not over-eager), even if its Builder-based `name_match` is `false`.
- **Record construction** — `name` client→Builder→db; `kind` from behavior with `503748`
  Talent/Ability → active behavior wins + `kind_node_disagreement` warning; record `confidence`
  aggregate; deduped `provenance[]`/`source_urls`; effect timing draws from reconciled top-level fields;
  multi-school reconciled field → effect `school` omitted (scalar-only), top-level `schools` authoritative.
- **Missing vs zero** — `null`=absent, `0`=instant; never confused.
- **Normalization** — mask → `schools` (single-bit also sets `school`; multi-bit omits it); power enum;
  range uses max with both endpoints retained; `-1` duration preserved as infinite.
- **Deterministic dedup** — one row per `spell_id`, sorted-unique `source_node_ids`; candidates
  source-identified.
- **`tick_interval_ms`** — builder emits canonical name; corrected test asserts it; loader accepts
  legacy `period_ms` on input and reserializes the canonical name.
- **Manifest binding & validation** — mechanics manifest `outputs.sha256` matches the JSONL; all input
  hashes recorded; projection validation catches tampering/mismatch; `db … : null` on absent db.
- **Atomicity** — a forced failure leaves no new JSONL paired with a stale manifest.

Integration exit test (default tier): the produced JSONL **loads through `MechanicsRepository`** and
**round-trips `field_provenance` and `schools`** (load → reserialize → equal), proving the additive
fields survive the real loader and are consumable by M1.16.

Client tier (`@pytest.mark.client`, real client + StormLib): regenerate the projection from the full
extract, verify manifest checksums/counts, then assert the acid test on `805775` concretely:

- `name` selected == the client name (`"Adrenal Venom"`); the stale db name
  (`"Fang Venom: Lifeblood"`) is retained as a **visible competing candidate** in `field_provenance`;
- at least one overlapping **mechanical** field (e.g. `power_type` or `cast_time_ms`) has its exact
  reconciled value **and** `selected_source == "client_dbc"`;
- the DB identity gate is exercised on the live capture by comparing the *observed* normalized db name to
  the client name: if they match, db fields are eligible fallback (gate vacuous); if they differ, every
  db candidate is `db_identity_mismatch` — the assertion checks the gate outcome for the observed db name,
  not a presumed stale value. (Alternatively the db artifact + its hash are pinned so the outcome is
  fixed; the zero-selected-contributions behavior itself is proven by the synthetic default-tier fixture
  above.)
- every observed `school_mask` bit and `power_type` value across the CoA projection is covered by the
  documented maps (no `unknown_*`).

## Exit Criteria

- The extractor emits `coa_client_spell_coa.jsonl` scoped by `coa_attribution.is_coa == true` with an
  additive `schema_match_confidence_by_dbc`, plus a `coa-client-spell-projection-v1` manifest binding it
  to the full-extract and projection hashes, client build, inclusion rule, and counts.
- `build-mechanics-artifacts.mjs` selects each field by first-eligible precedence — tracking `source`,
  `precedence_tier`, and `eligible` as three distinct properties — resolves same-tier conflicts by
  marking **all** conflicting candidates ineligible and falling through (never node order), records every
  candidate with source identity in `field_provenance` (with `selected_source` + `selected_tier`),
  constructs the full record (name/kind/effects/confidence/provenance/source_urls/raw) per contract, and
  demotes db to fallback-only. Output stays `coa-mechanics-v1`, scoped to the Builder `spell_id` domain,
  one row per `spell_id`, with `builder_missing_from_projection == 0` required for canonical.
- The record-level DB identity gate computes identity against the client-first reference (client name →
  consensus Builder → db) — treating the Builder-based `name_match` as audit-only — and bars a
  name-mismatched db row from supplying **any** field, effect, `kind`, or `tag` (`db_identity_mismatch`,
  retained but never selected); proven by a synthetic stale-db fixture that pins *Fang Venom: Lifeblood*.
- The single malformed-input rule holds: only a fully-absent projection degrades (to a separate
  `coa_mechanics.fallback.jsonl`); any present-but-invalid projection fails even with the flag. Unknown
  mask/enum and per-table drift fail canonical builds.
- Field mapping is normalized per the matrix, including additive `schools`; missing ≠ zero; `-1`
  duration preserved; enum/mask maps validated against the real extract by the recon task.
- Carried-in fixes land (missing/zero, deterministic one-row-per-`spell_id` with source-identified
  candidates, `tick_interval_ms` + corrected test + loader legacy acceptance).
- A `coa-mechanics-manifest-v1` binds canonical/degraded status and **all input hashes** (builder, db
  or explicit null, projection, projection-manifest) to the JSONL `sha256`, with per-field winner and
  conflict/omission counts; artifacts are written atomically.
- Item generation is a separate command; the Builder entries file is required; the single canonical db
  input is used (`entry.db_enrichment` ignored).
- `MechanicsRepository` loads the artifact and round-trips `field_provenance` **and** `schools`
  (integration exit test). The report path is unchanged; consumption is documented as deferred to M1.16.
- Real projection, mechanics artifact, and manifests remain untracked via **file-specific** ignore
  rules (not a blanket `reports/client_extract/` ignore); C commits schemas, synthetic fixtures, tests,
  ignore rules, and regeneration docs. The redistribution forward-policy gate is recorded as a mandatory
  M1.16 / public-release entry condition.
