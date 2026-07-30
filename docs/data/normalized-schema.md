# Normalized CoA Schema

The normalized schema version for Phase 1 is `coa-normalized-v1`.

## Artifacts

- `coa_scraper/dist/coa_entries.jsonl`: one normalized talent or ability node per line.
- `coa_scraper/dist/coa_classes.json`: normalized class and tab metadata.
- `coa_scraper/dist/coa_essence_caps.json`: raw essence caps keyed by class id.
- `coa_scraper/reports/coa_artifact_manifest.json`: source, script, artifact, checksum, and validation metadata.

## Node Records

Each JSONL node record keeps current optimizer-compatible top-level fields and adds schema metadata.

Required groups:

- provenance: `schema_version`, `build_id`, `build_slug`, `build_name`
- ownership: `class_id`, `class_name`, `tab_id`, `tab_name`, `tab_sort_order`
- identity: `entry_id`, `spell_id`, `spell_ids`, `name`, `icon`
- type: `entry_type`, `essence_kind`, `essence_type`
- costs and gates: `ae_cost`, `te_cost`, `required_tab_ae`, `required_tab_te`, `required_level`, `max_rank`
- graph: `required_ids`, `connected_node_ids`, `row`, `col`, `node_type`, `is_passive`, `is_starting_node`
- tooltip: `description_html`, `description_text`
- inferred features: `tags`, `damage_schools`, `resources`, `inferred`
- audit: `field_sources`, `raw`

## Source and Inferred Fields

`field_sources` explains where key fields came from. `inferred` duplicates locally inferred features in a dedicated object while top-level arrays remain for backward compatibility.

The optimizer should treat `raw` as audit data and should prefer normalized fields unless debugging extraction drift.

## M1.8 Source and Level Fields

M1.8 keeps `coa-normalized-v1` and adds optional source-aware fields:

- `source_category`: `spec_tree`, `class_pool`, `trainer`, `misc_system`, `metadata_only`, or `unknown`.
- `source_confidence`: `high`, `medium`, or `low`.
- `availability`: builder, tooltip, DB tooltip, effective level, confidence, source, and notes. The
  `db_tooltip_required_level` key survives for shape compatibility but is now always `null` — the source
  that populated it was **removed** by M1.14E0R, so it can never contribute to
  `effective_required_level`.

M1.8 also added a `db_enrichment` join block. It was **removed** outright by M1.14E0R together with the
rest of the AscensionDB enrichment runtime; no script writes or reads it, and consumers must not expect
it.

Consumers must continue to support records without these fields. When present, `availability.effective_required_level` may be used for lower-level eligibility only if `availability.level_confidence` is `high` or `medium`.

## Validation

Run:

```bash
cd coa_scraper
npm run validate
```

Expected healthy Vol'Jin Alpha validation has zero missing class records, zero missing tab records, and zero unknown essence-kind records.
