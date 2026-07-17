# WoW Constants Schema

Records use schema version `coa-wow-constants-v1`, produced by `coa_client_extract` (M1.14D) from the
client GameTable DBCs plus tracked, verification-labelled authored inputs. It is the modeling-inputs
layer for the M1.16 analytical player-power engine. Loaded by `coa_meta.wow_constants.WowConstantsRepository`,
which verifies the sibling manifest and computes **no** formulas.

Design: [M1.14D WoW Conversion Primitives](../superpowers/specs/2026-07-17-m1-14-d-wow-constants-design.md).

## Artifact: `coa_wow_constants.json`

Top-level:

- `schema_version`: always `coa-wow-constants-v1`.
- `client_build`: the WoW generation + top content patch (e.g. `3.3.5a+patch-M`).
- `provenance`: `backend`, `backend_version`, and `source_dbcs` (per DBC `sha256`; the reader exposes
  this via `table_provenance(key)`).
- `class_axis`: the stock `ChrClasses` class axis (see below).
- `enum_maps`: `rating_enum` (`CombatRating` id→name, supported `0–24`, storage stride `32`) and
  `power_type` (int→name, shared with M1.14C — see [client-spell-schema.md](client-spell-schema.md)).
- `game_tables`: one entry per extracted GameTable (see below).
- `rules`: documented, verification-labelled non-DBC rules (see below).

### `game_tables[key]`

- `source_dbc`: the GameTable DBC name (e.g. `gtCombatRatings`).
- `physical_form`: `implicit_row` (single float, indexed by ordinal) or `explicit_id`.
- `axes`: the semantic coordinate axes (e.g. `["rating_id", "level"]`, `["wow_class_id", "rating_id"]`).
- `class_indexed`: whether lookups need a resolved `wow_class_id` (context is M1.16's, not the reader's).
- `domains`: supported per-axis `{min, max}` (distinct from storage strides).
- `drift`: header field-count / record-size deviation from the expected layout.
- `counts`: `source_records` (from the header), `emitted_entries` (supported coordinates emitted), and
  `padding_records` (unused storage slots not emitted).
- `reference_comparison`: anchor-scoped comparison against `wotlk_reference_anchors_v1.json`
  (`scope: "anchors"`, `anchor_set_version`, `anchor_set_sha256`, `checked`/`equal`/`different`,
  `status ∈ {matches_on_checked_anchors, differs_on_checked_anchors, no_anchors_checked}`). A differing
  valid value is a recorded Ascension deviation, **not** a failure; whole-table equality
  (`exact_match`) is a separate, stronger claim reserved for a full hashed-dataset comparison.
- `entries`: explicit-coordinate rows `{<axis>: int, ..., "value": float}` — never opaque flattened arrays.

### `class_axis`

- `namespace`: always `chr_classes` — the stock WoW class id domain (sparse `1–9`, `11`; hole at `10`),
  **not** the CoA class-type namespace (14–34).
- `reference_expected_ids` / `reference_holes`: the pinned stock expectation.
- `observed_client_ids`: the roster actually read from `ChrClasses.dbc`.
- `comparison`: `exact | extended | changed | ambiguous`. A non-`exact` axis requires a tracked,
  manifest-bound adjudication (`reports/client_extract/wow_class_axis_adjudication.json`) before
  canonical extraction.
- `default_power_type_by_wow_class_id`: the class's **default** power type (from `ChrClasses.power_type`)
  — not a CoA-class mapping and not a complete description of every resource a build uses.

### `rules`

Each rule carries `value`/`unit`, `authority` (`wotlk_reference` | `ascension_observed`),
`ascension_verification` (`unverified` | `verified` | `contradicted`), `applies_to` (applicability
scope), `source_ref`, and `notes`. Every rule ships `ascension_verification: unverified` until
M1.14G/logs confirm — a stock assumption is never presented as verified Ascension truth. Initial rules:
`base_energy`, `energy_regen_per_sec`, `rage_bounds`, `runic_power_bounds`, `gcd_floor_ms`, and
`standard_spell_gcd_base_ms` (the standard default, **not** a ceiling — the real base GCD is a per-spell
`StartRecoveryTime` operand delivered by M1.14E).

## Reference indexing contract

Axis meaning is proven against the pinned reference indexing contract, never inferred from record count:

- `level_stride = 100`; combat-rating index `rating_id * 100 + (level - 1)`.
- class scalar index `(wow_class_id - 1) * 32 + rating_id + 1` (rating storage stride `32`, `+1` offset).
- supported rating ids `0–24`.
- rating→% is the **identified** reference formula `class_scalar / combat_rating` — the reader returns
  both operands; M1.16 divides. The repository never evaluates it.

## Manifest: `coa_wow_constants.manifest.json`

Schema `coa-wow-constants-manifest-v1`, written **last** as the validity marker. Binds:

- `artifact`: `path`, `sha256`, `byte_length` of the snapshot.
- `source_dbc_sha256`: hash of every source DBC read.
- `authored_inputs`: `version` + `sha256` for each tracked authored input — `rules`, `rating_enum`,
  `power_type_enum`, `axis_layout_policy`, `reference_anchors`, and (when the class axis is not `exact`)
  `class_axis_adjudication`.
- `class_context_resolution`: `unproven | actor_wow_class_id | versioned_bridge` (default `unproven`).
- `table_summary`: per-table `source_records`/`emitted_entries`/`padding_records`, `drift`, and
  `reference_comparison_status`.
- `extractor_commit`, `client_build`, `extraction_date`.

## Redistribution boundary

The snapshot, manifest, and recon report are client-derived and git-ignored (regenerate from your own
client). Committed fixtures are synthetic. The authored inputs and the class-axis adjudication are
tracked. `coa_wow_constants.json` joins the M1.14C mandatory forward policy gate (see
[DECISIONS.md](../DECISIONS.md) Decision 18).
