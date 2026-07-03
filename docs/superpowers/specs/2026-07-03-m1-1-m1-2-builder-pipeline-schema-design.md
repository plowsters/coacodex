# M1.1/M1.2 Builder Pipeline and Schema Design

## Scope

This spec covers Phase 1 Milestone 1.1 and Milestone 1.2 from [ROADMAP.md](../../ROADMAP.md):

- M1.1: Reproducible Builder Data Pipeline
- M1.2: Versioned Normalized Domain Schema

It does not implement build legality, scoring, APL generation, simulation, combat log ingestion, or web UI work. Those modules depend on the artifacts defined here.

## Goals

The builder data pipeline should be reproducible, auditable, and safe to consume by later optimizer modules. A future agent should be able to run one documented command sequence and understand:

- which official Ascension builder page was captured
- which scripts generated each artifact
- which builder version and payload metadata were used
- which files were produced
- which checksums identify those artifacts
- whether normalized records match the schema expected by the optimizer
- which fields came from the builder payload and which fields were inferred locally

## Non-Goals

- No attempt to infer optimal builds.
- No browser automation beyond the existing capture script.
- No new web frontend.
- No dependency on network package installation.
- No direct optimizer package split in this milestone.
- No raw DPS, projected DPS, or meta ranking output.

## Current State

The repository currently has a useful prototype pipeline:

- `coa_scraper/scrape-coa-network.mjs` captures HAR, raw responses, and snapshots.
- `coa_scraper/scripts/extract-coa-builder-payload.mjs` extracts Next Flight chunks and writes payload artifacts.
- `coa_scraper/scripts/inspect-coa-payload-shape.mjs` inventories payload shape.
- `coa_scraper/scripts/summarize-coa-payload.mjs` writes a payload report.
- `coa_scraper/scripts/export-coa-normalized.mjs` writes normalized dist artifacts.
- `coa_scraper/scripts/build-class-profile-input.mjs` writes profile summary inputs.
- `coa_scraper/reports/coa_normalization_report.txt` currently shows 21 classes, 3,612 records, no missing class records, no missing tab records, and no unknown essence-kind records for the included Vol'Jin Alpha capture.

The gaps are:

- no versioned normalized schema
- no artifact manifest
- no checksums
- no explicit provenance object in normalized artifacts
- inferred fields are mixed with source-derived fields
- no validation command that later optimizer code can depend on
- package scripts do not expose the full workflow

## Architecture

The target milestone architecture keeps five pipeline stages separate:

```text
capture
  -> extract payload
  -> inspect payload shape
  -> normalize records
  -> validate artifacts and write manifest
```

### Capture Stage

Current owner: `coa_scraper/scrape-coa-network.mjs`

Responsibilities:

- open the official builder URL
- capture HAR, raw network responses, snapshots, runtime dumps
- record enough context for later extraction

This milestone does not require fully automated clicking across classes/tabs. Manual interaction remains acceptable, but the capture docs must say so explicitly.

### Extraction Stage

Current owner: `coa_scraper/scripts/extract-coa-builder-payload.mjs`

Responsibilities:

- parse captured HTML
- extract `self.__next_f.push` chunks
- locate the builder payload whose runtime process is `api/v3 builder CoA parser`
- write raw builder payload and summary files
- write the reconstructed Next Flight stream for drift diagnosis

### Shape Analysis Stage

Current owner: `coa_scraper/scripts/inspect-coa-payload-shape.mjs`

Responsibilities:

- summarize top-level `talents` keys
- summarize class/tab ownership
- summarize `entriesByTab` buckets
- summarize entry key histograms and samples
- write machine-readable and human-readable shape reports

### Normalization Stage

Current owner: `coa_scraper/scripts/export-coa-normalized.mjs`

Responsibilities:

- map raw builder entries into normalized records
- preserve raw entries
- keep compatibility fields at top level for current optimizer prototypes
- add explicit schema version and provenance
- separate source-derived fields from locally inferred fields

### Validation and Manifest Stage

New owner: `coa_scraper/scripts/validate-normalized.mjs` and `coa_scraper/scripts/write-artifact-manifest.mjs`

Responsibilities:

- validate normalized artifacts against required schema constraints
- check counts and relationship invariants
- produce a manifest with checksums for source and generated artifacts
- fail with a non-zero exit code when required artifacts are missing or invalid

## Data Contracts

### Schema Version

All normalized artifacts should use:

```json
"schema_version": "coa-normalized-v1"
```

For JSONL records, every line must include `schema_version`. For JSON arrays or objects, the top-level object should include `schema_version` when the file format allows it. Backward-compatible top-level fields should remain until the optimizer has been migrated.

### Node Record Contract

Each normalized node record must include:

- `schema_version`
- `build_id`
- `build_slug`
- `build_name`
- `class_id`
- `class_name`
- `tab_id`
- `tab_name`
- `tab_sort_order`
- `entry_type`
- `essence_kind`
- `essence_type`
- `entry_id`
- `spell_id`
- `spell_ids`
- `name`
- `icon`
- `ae_cost`
- `te_cost`
- `required_tab_ae`
- `required_tab_te`
- `description_html`
- `description_text`
- `required_level`
- `max_rank`
- `row`
- `col`
- `node_type`
- `flags`
- `group`
- `is_passive`
- `is_starting_node`
- `required_ids`
- `connected_node_ids`
- `tags`
- `damage_schools`
- `resources`
- `field_sources`
- `inferred`
- `raw`

### Field Source Contract

`field_sources` records whether a value is source-provided, normalized from source, or inferred locally.

Example:

```json
"field_sources": {
  "class_id": "payload.talents.classes + entry.classId",
  "tab_name": "payload.talents.classes.tabs",
  "description_text": "description_html stripped locally",
  "tags": "local regex inference",
  "damage_schools": "local regex inference",
  "resources": "local regex inference"
}
```

### Inferred Contract

`inferred` stores locally inferred fields in a dedicated object while preserving top-level compatibility fields.

Example:

```json
"inferred": {
  "tags": ["dot", "proc"],
  "damage_schools": ["nature"],
  "resources": ["Energy"],
  "confidence": {
    "tags": "medium",
    "damage_schools": "medium",
    "resources": "medium"
  }
}
```

### Manifest Contract

The artifact manifest should be written to:

```text
coa_scraper/reports/coa_artifact_manifest.json
```

Required manifest fields:

- `schema_version`
- `generated_at`
- `builder`
- `source`
- `scripts`
- `artifacts`
- `validation`

Example shape:

```json
{
  "schema_version": "coa-artifact-manifest-v1",
  "generated_at": "2026-07-03T17:00:00.000Z",
  "builder": {
    "id": 39,
    "slug": "voljin-alpha",
    "name": "Vol'Jin Alpha",
    "max_level": 60
  },
  "source": {
    "url": "https://ascension.gg/en/v2/coa-builder/voljin-alpha",
    "snapshot": "data/snapshots/final-page-content.html",
    "har": "data/coa.har"
  },
  "scripts": [
    {"path": "scripts/extract-coa-builder-payload.mjs", "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}
  ],
  "artifacts": [
    {"path": "dist/coa_entries.jsonl", "bytes": 8558835, "sha256": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"}
  ],
  "validation": {
    "status": "pass",
    "class_count": 21,
    "record_count": 3612,
    "missing_class_records": 0,
    "missing_tab_records": 0,
    "unknown_essence_kind_records": 0
  }
}
```

## Validation Rules

The validation script should enforce these checks:

- all required files exist
- `coa_entries.jsonl` is valid JSONL
- each node has `schema_version: "coa-normalized-v1"`
- every node has non-empty `class_name`, `tab_name`, `name`, `entry_type`, and `essence_kind`
- `entry_id`, `class_id`, `tab_id`, costs, required level, row, and column are numeric or null only where explicitly allowed
- `essence_kind` is one of `ability`, `talent`, or `unknown`
- `unknown` essence kind count is reported and fails validation unless explicitly allowed
- each class listed in `coa_classes.json` has at least one normalized entry
- each node's `required_ids` and `connected_node_ids` arrays contain numbers
- missing class and missing tab counts are reported and fail validation
- shape report and normalization report exist after pipeline run

## Command Design

The package scripts should expose the workflow:

```bash
npm run capture
npm run extract
npm run normalize
npm run validate
npm run pipeline
```

`npm run pipeline` should run extraction, shape analysis, normalization, class-profile input generation, validation, and manifest writing using the already captured snapshot. It should not run the browser capture step.

## Error Handling

Pipeline scripts should fail loudly:

- missing input file: print exact missing path and exit 1
- invalid JSON or JSONL: print path and line number where possible and exit 1
- missing builder payload marker: print marker name and extraction input path and exit 1
- validation failure: print a compact failure list and exit 1
- checksum failure is not a separate mode in this milestone because checksums are written, not compared to a lockfile

## Documentation Updates

Add:

- `coa_scraper/README.md` with the full pipeline command sequence
- `docs/data/normalized-schema.md` explaining v1 schema and field sources
- references from `docs/README.md` to the schema docs

## Testing and Verification

This milestone should be verified without launching Chromium:

```bash
cd coa_scraper
npm run pipeline
npm run validate
```

Expected output includes:

- `dist/coa_entries.jsonl`
- `dist/coa_classes.json`
- `dist/coa_essence_caps.json`
- `reports/coa_artifact_manifest.json`
- validation status pass
- zero missing class records
- zero missing tab records
- zero unknown essence-kind records

Browser capture remains manually verified when data is refreshed:

```bash
cd coa_scraper
npm run capture
```

## Intentional Deferrals

- Legal build validation against official builder examples is M1.3.
- Optimizer refusal of invalid schema is partly M1.2 but final enforcement in the optimizer package happens when the optimizer split begins.
- Full JSON Schema validation through AJV or another library is deferred until dependency policy is decided. This milestone includes checked-in schema documents and a local validator using Node standard library.
- Automated class/tab clicking in the builder UI is useful but not required for M1.1 because the current capture flow already supports manual exploration.
