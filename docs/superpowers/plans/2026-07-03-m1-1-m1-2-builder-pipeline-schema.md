# M1.1/M1.2 Builder Pipeline and Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the CoA builder data pipeline reproducible and add versioned normalized schema validation for the existing scraper/normalizer artifacts.

**Architecture:** Keep browser capture, payload extraction, normalization, validation, and manifest writing as separate Node scripts under `coa_scraper/`. Preserve current optimizer compatibility by keeping existing top-level normalized fields while adding schema/provenance/source metadata.

**Tech Stack:** Node.js ESM, Node standard library, existing Playwright dependency, JSON/JSONL, Markdown.

---

## File Structure

Create:

- `coa_scraper/scripts/lib/artifacts.mjs`: shared file hashing, JSON loading, JSONL loading, path existence, and artifact record helpers.
- `coa_scraper/scripts/write-artifact-manifest.mjs`: writes `reports/coa_artifact_manifest.json`.
- `coa_scraper/scripts/validate-normalized.mjs`: validates normalized artifacts and prints machine-readable summary.
- `coa_scraper/scripts/run-normalization-pipeline.mjs`: runs extraction, shape inspection, payload summary, normalization, class profile input generation, validation, and manifest writing.
- `coa_scraper/schemas/coa-normalized-node-v1.schema.json`: JSON Schema document for each JSONL node record.
- `coa_scraper/schemas/coa-normalized-class-v1.schema.json`: JSON Schema document for class records.
- `coa_scraper/schemas/coa-artifact-manifest-v1.schema.json`: JSON Schema document for manifest records.
- `docs/data/normalized-schema.md`: human-readable schema documentation.
- `coa_scraper/README.md`: operational pipeline docs.

Modify:

- `coa_scraper/scripts/export-coa-normalized.mjs`: add `schema_version`, `field_sources`, `inferred`, and top-level provenance while preserving existing fields.
- `coa_scraper/package.json`: add `capture`, `extract`, `normalize`, `validate`, and `pipeline` scripts.
- `docs/README.md`: link to `docs/data/normalized-schema.md`.

Test with:

- `cd coa_scraper && npm run pipeline`
- `cd coa_scraper && npm run validate`
- `python -m json.tool coa_scraper/reports/coa_artifact_manifest.json >/tmp/coa_manifest_check.json`
- `rg -n "schema_version" coa_scraper/dist/coa_entries.jsonl`

---

### Task 1: Add Artifact Utility Module

**Files:**

- Create: `coa_scraper/scripts/lib/artifacts.mjs`

- [ ] **Step 1: Create the utility module**

Create `coa_scraper/scripts/lib/artifacts.mjs` with this content:

```javascript
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export function repoRelative(filePath, rootDir = process.cwd()) {
  return path.relative(rootDir, filePath).replaceAll(path.sep, "/");
}

export function assertFile(filePath) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`Required file does not exist: ${filePath}`);
  }
}

export function sha256File(filePath) {
  assertFile(filePath);
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(filePath));
  return hash.digest("hex");
}

export function artifactRecord(filePath, rootDir = process.cwd()) {
  assertFile(filePath);
  const stat = fs.statSync(filePath);
  return {
    path: repoRelative(filePath, rootDir),
    bytes: stat.size,
    sha256: sha256File(filePath)
  };
}

export function loadJson(filePath) {
  assertFile(filePath);
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (err) {
    throw new Error(`Invalid JSON in ${filePath}: ${err.message}`);
  }
}

export function loadJsonl(filePath) {
  assertFile(filePath);
  const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/);
  const records = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    try {
      records.push(JSON.parse(line));
    } catch (err) {
      throw new Error(`Invalid JSONL in ${filePath}:${i + 1}: ${err.message}`);
    }
  }
  return records;
}

export function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`);
}
```

- [ ] **Step 2: Run a syntax check**

Run:

```bash
cd coa_scraper
node --check scripts/lib/artifacts.mjs
```

Expected: exit 0 with no output.

---

### Task 2: Add JSON Schema Documents

**Files:**

- Create: `coa_scraper/schemas/coa-normalized-node-v1.schema.json`
- Create: `coa_scraper/schemas/coa-normalized-class-v1.schema.json`
- Create: `coa_scraper/schemas/coa-artifact-manifest-v1.schema.json`

- [ ] **Step 1: Create node schema**

Create `coa_scraper/schemas/coa-normalized-node-v1.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://local.coa-meta/schemas/coa-normalized-node-v1.schema.json",
  "title": "CoA Normalized Node v1",
  "type": "object",
  "required": [
    "schema_version",
    "build_id",
    "build_slug",
    "build_name",
    "class_id",
    "class_name",
    "tab_id",
    "tab_name",
    "entry_type",
    "essence_kind",
    "entry_id",
    "name",
    "ae_cost",
    "te_cost",
    "required_tab_ae",
    "required_tab_te",
    "required_ids",
    "connected_node_ids",
    "tags",
    "damage_schools",
    "resources",
    "field_sources",
    "inferred",
    "raw"
  ],
  "properties": {
    "schema_version": { "const": "coa-normalized-v1" },
    "build_id": { "type": ["number", "null"] },
    "build_slug": { "type": ["string", "null"] },
    "build_name": { "type": ["string", "null"] },
    "class_id": { "type": "number" },
    "class_name": { "type": "string", "minLength": 1 },
    "tab_id": { "type": "number" },
    "tab_name": { "type": "string", "minLength": 1 },
    "tab_sort_order": { "type": ["number", "null"] },
    "entry_type": { "type": ["string", "null"] },
    "essence_kind": { "enum": ["ability", "talent", "unknown"] },
    "essence_type": { "enum": ["abilityEssence", "talentEssence", "unknown"] },
    "entry_id": { "type": ["number", "string", "null"] },
    "spell_id": { "type": ["number", "string", "null"] },
    "spell_ids": { "type": "array" },
    "name": { "type": "string", "minLength": 1 },
    "icon": { "type": ["string", "null"] },
    "ae_cost": { "type": "number", "minimum": 0 },
    "te_cost": { "type": "number", "minimum": 0 },
    "required_tab_ae": { "type": "number", "minimum": 0 },
    "required_tab_te": { "type": "number", "minimum": 0 },
    "description_html": { "type": ["string", "null"] },
    "description_text": { "type": ["string", "null"] },
    "required_level": { "type": ["number", "null"] },
    "max_rank": { "type": ["number", "null"] },
    "row": { "type": ["number", "null"] },
    "col": { "type": ["number", "null"] },
    "node_type": { "type": ["string", "null"] },
    "flags": { "type": ["number", "null"] },
    "group": { "type": ["number", "null"] },
    "is_passive": { "type": "boolean" },
    "is_starting_node": { "type": "boolean" },
    "required_ids": { "type": "array", "items": { "type": "number" } },
    "connected_node_ids": { "type": "array", "items": { "type": "number" } },
    "tags": { "type": "array", "items": { "type": "string" } },
    "damage_schools": { "type": "array", "items": { "type": "string" } },
    "resources": { "type": "array", "items": { "type": "string" } },
    "field_sources": { "type": "object" },
    "inferred": { "type": "object" },
    "raw": { "type": "object" }
  },
  "additionalProperties": true
}
```

- [ ] **Step 2: Create class schema**

Create `coa_scraper/schemas/coa-normalized-class-v1.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://local.coa-meta/schemas/coa-normalized-class-v1.schema.json",
  "title": "CoA Normalized Class v1",
  "type": "object",
  "required": ["schema_version", "class_id", "class_name", "tabs", "essence_caps"],
  "properties": {
    "schema_version": { "const": "coa-normalized-v1" },
    "class_id": { "type": "number" },
    "class_name": { "type": "string", "minLength": 1 },
    "tabs": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["tab_id", "tab_name", "sort_order", "nominal_essence_kind"],
        "properties": {
          "tab_id": { "type": "number" },
          "tab_name": { "type": "string", "minLength": 1 },
          "sort_order": { "type": ["number", "null"] },
          "nominal_essence_kind": { "enum": ["ability", "talent"] }
        },
        "additionalProperties": true
      }
    },
    "essence_caps": {
      "type": ["object", "null"],
      "properties": {
        "maxTalentEssence": { "type": "number" },
        "maxAbilityEssence": { "type": "number" }
      },
      "additionalProperties": true
    }
  },
  "additionalProperties": true
}
```

- [ ] **Step 3: Create manifest schema**

Create `coa_scraper/schemas/coa-artifact-manifest-v1.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://local.coa-meta/schemas/coa-artifact-manifest-v1.schema.json",
  "title": "CoA Artifact Manifest v1",
  "type": "object",
  "required": ["schema_version", "generated_at", "builder", "source", "scripts", "artifacts", "validation"],
  "properties": {
    "schema_version": { "const": "coa-artifact-manifest-v1" },
    "generated_at": { "type": "string" },
    "builder": {
      "type": "object",
      "required": ["id", "slug", "name", "max_level"],
      "properties": {
        "id": { "type": ["number", "null"] },
        "slug": { "type": ["string", "null"] },
        "name": { "type": ["string", "null"] },
        "max_level": { "type": ["number", "null"] }
      },
      "additionalProperties": true
    },
    "source": { "type": "object" },
    "scripts": { "type": "array" },
    "artifacts": { "type": "array" },
    "validation": { "type": "object" }
  },
  "additionalProperties": true
}
```

- [ ] **Step 4: Validate schema JSON syntax**

Run:

```bash
python -m json.tool coa_scraper/schemas/coa-normalized-node-v1.schema.json >/tmp/node_schema.json
python -m json.tool coa_scraper/schemas/coa-normalized-class-v1.schema.json >/tmp/class_schema.json
python -m json.tool coa_scraper/schemas/coa-artifact-manifest-v1.schema.json >/tmp/manifest_schema.json
```

Expected: all commands exit 0.

---

### Task 3: Add Schema Metadata to Normalized Exports

**Files:**

- Modify: `coa_scraper/scripts/export-coa-normalized.mjs`

- [ ] **Step 1: Add constants near the top**

After this line:

```javascript
const essenceByClass = talents.essenceByClass || {};
```

Add:

```javascript
const SCHEMA_VERSION = "coa-normalized-v1";

const baseFieldSources = {
  build_id: "payload.id",
  build_slug: "payload.slug",
  build_name: "payload.name",
  class_id: "entry.classId",
  class_name: "payload.talents.classes[classId].className",
  tab_id: "entry.tabId",
  tab_name: "payload.talents.classes[classId].tabs[tabId].tabName",
  entry_type: "entry.entryType",
  essence_kind: "entry.entryType with aeCost/teCost fallback",
  entry_id: "entry id aliases",
  spell_id: "entry spellId aliases",
  name: "entry name aliases",
  icon: "entry icon aliases",
  costs: "entry.aeCost and entry.teCost",
  requirements: "entry.reqTabAE, entry.reqTabTE, entry.requiredIds, entry.requiredLevel",
  position: "entry.x and entry.y",
  graph: "entry.connectedNodeIds",
  description_html: "entry description aliases",
  description_text: "description_html stripped locally",
  tags: "local regex inference from name and description_text",
  damage_schools: "local regex inference from name and description_text",
  resources: "local regex inference from name and description_text",
  raw: "original entry object"
};
```

- [ ] **Step 2: Add schema fields to each normalized record**

Inside the `const rec = {` object, add this as the first property:

```javascript
      schema_version: SCHEMA_VERSION,
```

Inside the same object, replace the current inferred field section:

```javascript
      tags: detectTags(combinedText),
      damage_schools: detectSchools(combinedText),
      resources: detectResources(combinedText),

      raw: entry
```

with:

```javascript
      tags: detectTags(combinedText),
      damage_schools: detectSchools(combinedText),
      resources: detectResources(combinedText),

      field_sources: baseFieldSources,
      inferred: {
        tags: detectTags(combinedText),
        damage_schools: detectSchools(combinedText),
        resources: detectResources(combinedText),
        confidence: {
          tags: "medium",
          damage_schools: "medium",
          resources: "medium"
        }
      },

      raw: entry
```

- [ ] **Step 3: Add schema version to class records**

In `normalizeClass`, replace:

```javascript
const normalizeClass = cls => ({
  class_id: Number(cls.classId),
```

with:

```javascript
const normalizeClass = cls => ({
  schema_version: SCHEMA_VERSION,
  class_id: Number(cls.classId),
```

- [ ] **Step 4: Regenerate normalized artifacts**

Run:

```bash
cd coa_scraper
node scripts/export-coa-normalized.mjs reports/coa_builder_payload.json dist
```

Expected output includes:

```text
Wrote dist/coa_classes.json
Wrote dist/coa_essence_caps.json
Wrote dist/coa_entries.jsonl
Wrote dist/coa_entries.pretty.json
Deduped records: 3612
Missing class records: 0
Missing tab records: 0
Unknown essence-kind records: 0
```

- [ ] **Step 5: Confirm schema metadata exists**

Run:

```bash
cd coa_scraper
node -e 'const fs=require("fs"); const first=JSON.parse(fs.readFileSync("dist/coa_entries.jsonl","utf8").split(/\n/)[0]); console.log(first.schema_version, !!first.field_sources, !!first.inferred)'
```

Expected output:

```text
coa-normalized-v1 true true
```

---

### Task 4: Add Normalized Artifact Validator

**Files:**

- Create: `coa_scraper/scripts/validate-normalized.mjs`

- [ ] **Step 1: Create validator script**

Create `coa_scraper/scripts/validate-normalized.mjs`:

```javascript
#!/usr/bin/env node
import path from "node:path";
import { loadJson, loadJsonl, writeJson } from "./lib/artifacts.mjs";

const distDir = process.argv[2] || "dist";
const reportsDir = process.argv[3] || "reports";
const allowUnknown = process.argv.includes("--allow-unknown-essence-kind");

const entriesPath = path.join(distDir, "coa_entries.jsonl");
const classesPath = path.join(distDir, "coa_classes.json");
const essenceCapsPath = path.join(distDir, "coa_essence_caps.json");
const normalizationReportPath = path.join(reportsDir, "coa_normalization_report.txt");
const shapeReportPath = path.join(reportsDir, "coa_payload_shape_report.txt");

const entries = loadJsonl(entriesPath);
const classes = loadJson(classesPath);
loadJson(essenceCapsPath);

const failures = [];
const warnings = [];

function fail(message) {
  failures.push(message);
}

function isNumberArray(value) {
  return Array.isArray(value) && value.every(v => typeof v === "number" && Number.isFinite(v));
}

if (!entries.length) fail("coa_entries.jsonl contains no records");
if (!Array.isArray(classes) || !classes.length) fail("coa_classes.json contains no class records");

const classNames = new Set(classes.map(c => c.class_name).filter(Boolean));
const entryClassNames = new Set(entries.map(e => e.class_name).filter(Boolean));

for (const cls of classes) {
  if (cls.schema_version !== "coa-normalized-v1") fail(`class ${cls.class_name || cls.class_id} missing schema_version`);
  if (!cls.class_name) fail(`class ${cls.class_id} missing class_name`);
  if (typeof cls.class_id !== "number") fail(`class ${cls.class_name} has non-number class_id`);
  if (!Array.isArray(cls.tabs)) fail(`class ${cls.class_name} tabs is not an array`);
  if (!entryClassNames.has(cls.class_name)) fail(`class ${cls.class_name} has no normalized entries`);
}

let missingClassRecords = 0;
let missingTabRecords = 0;
let unknownEssenceKindRecords = 0;

for (let i = 0; i < entries.length; i++) {
  const e = entries[i];
  const label = `${e.class_name || "UNKNOWN_CLASS"}:${e.tab_name || "UNKNOWN_TAB"}:${e.name || "UNKNOWN_NAME"}:${e.entry_id || i}`;

  if (e.schema_version !== "coa-normalized-v1") fail(`${label} missing schema_version`);
  if (!e.class_name) missingClassRecords++;
  if (!e.tab_name) missingTabRecords++;
  if (!["ability", "talent", "unknown"].includes(e.essence_kind)) fail(`${label} invalid essence_kind ${e.essence_kind}`);
  if (e.essence_kind === "unknown") unknownEssenceKindRecords++;
  if (!e.name) fail(`${label} missing name`);
  if (typeof e.class_id !== "number") fail(`${label} class_id is not numeric`);
  if (typeof e.tab_id !== "number") fail(`${label} tab_id is not numeric`);
  if (typeof e.ae_cost !== "number") fail(`${label} ae_cost is not numeric`);
  if (typeof e.te_cost !== "number") fail(`${label} te_cost is not numeric`);
  if (typeof e.required_tab_ae !== "number") fail(`${label} required_tab_ae is not numeric`);
  if (typeof e.required_tab_te !== "number") fail(`${label} required_tab_te is not numeric`);
  if (!isNumberArray(e.required_ids)) fail(`${label} required_ids must be numeric array`);
  if (!isNumberArray(e.connected_node_ids)) fail(`${label} connected_node_ids must be numeric array`);
  if (!Array.isArray(e.tags)) fail(`${label} tags must be array`);
  if (!Array.isArray(e.damage_schools)) fail(`${label} damage_schools must be array`);
  if (!Array.isArray(e.resources)) fail(`${label} resources must be array`);
  if (!e.field_sources || typeof e.field_sources !== "object") fail(`${label} missing field_sources object`);
  if (!e.inferred || typeof e.inferred !== "object") fail(`${label} missing inferred object`);
  if (!e.raw || typeof e.raw !== "object") fail(`${label} missing raw object`);
}

if (missingClassRecords > 0) fail(`missing class records: ${missingClassRecords}`);
if (missingTabRecords > 0) fail(`missing tab records: ${missingTabRecords}`);
if (unknownEssenceKindRecords > 0 && !allowUnknown) fail(`unknown essence-kind records: ${unknownEssenceKindRecords}`);

try {
  loadJson(path.join(reportsDir, "coa_payload_shape.json"));
} catch (err) {
  warnings.push(err.message);
}

for (const requiredReport of [normalizationReportPath, shapeReportPath]) {
  try {
    loadJson(requiredReport);
  } catch (_err) {
    // Text reports are checked by existence through a lightweight path read below.
  }
}

const summary = {
  schema_version: "coa-validation-summary-v1",
  status: failures.length ? "fail" : "pass",
  class_count: classes.length,
  record_count: entries.length,
  class_names: [...classNames].sort(),
  missing_class_records: missingClassRecords,
  missing_tab_records: missingTabRecords,
  unknown_essence_kind_records: unknownEssenceKindRecords,
  failures,
  warnings
};

writeJson(path.join(reportsDir, "coa_validation_summary.json"), summary);
console.log(JSON.stringify(summary, null, 2));

if (failures.length) process.exit(1);
```

- [ ] **Step 2: Fix text-report existence check**

The script above intentionally avoids parsing text reports as JSON, but it still needs existence checks. Add this import at the top:

```javascript
import fs from "node:fs";
```

Then replace this block:

```javascript
for (const requiredReport of [normalizationReportPath, shapeReportPath]) {
  try {
    loadJson(requiredReport);
  } catch (_err) {
    // Text reports are checked by existence through a lightweight path read below.
  }
}
```

with:

```javascript
for (const requiredReport of [normalizationReportPath, shapeReportPath]) {
  if (!fs.existsSync(requiredReport)) {
    fail(`required report does not exist: ${requiredReport}`);
  }
}
```

- [ ] **Step 3: Run syntax check**

Run:

```bash
cd coa_scraper
node --check scripts/validate-normalized.mjs
```

Expected: exit 0 with no output.

- [ ] **Step 4: Run validator**

Run:

```bash
cd coa_scraper
node scripts/validate-normalized.mjs dist reports
```

Expected output includes:

```json
"status": "pass"
```

and:

```json
"missing_class_records": 0,
"missing_tab_records": 0,
"unknown_essence_kind_records": 0
```

---

### Task 5: Add Artifact Manifest Writer

**Files:**

- Create: `coa_scraper/scripts/write-artifact-manifest.mjs`

- [ ] **Step 1: Create manifest writer script**

Create `coa_scraper/scripts/write-artifact-manifest.mjs`:

```javascript
#!/usr/bin/env node
import path from "node:path";
import { artifactRecord, loadJson, writeJson } from "./lib/artifacts.mjs";

const rootDir = process.cwd();
const reportsDir = process.argv[2] || "reports";
const distDir = process.argv[3] || "dist";
const outPath = process.argv[4] || path.join(reportsDir, "coa_artifact_manifest.json");

const payloadPath = path.join(reportsDir, "coa_builder_payload.json");
const validationPath = path.join(reportsDir, "coa_validation_summary.json");
const payload = loadJson(payloadPath);
const validation = loadJson(validationPath);

const scriptPaths = [
  "scrape-coa-network.mjs",
  "scripts/extract-coa-builder-payload.mjs",
  "scripts/inspect-coa-payload-shape.mjs",
  "scripts/summarize-coa-payload.mjs",
  "scripts/export-coa-normalized.mjs",
  "scripts/build-class-profile-input.mjs",
  "scripts/validate-normalized.mjs",
  "scripts/write-artifact-manifest.mjs",
  "scripts/run-normalization-pipeline.mjs"
];

const artifactPaths = [
  "data/coa.har",
  "data/snapshots/final-page-content.html",
  "data/snapshots/final-runtime-dump.json",
  "reports/next_flight_stream.txt",
  "reports/coa_builder_payload.json",
  "reports/coa_builder_summary.json",
  "reports/coa_payload_shape.json",
  "reports/coa_payload_shape_report.txt",
  "reports/coa_payload_report.txt",
  "reports/coa_normalization_report.txt",
  "reports/coa_counts_by_class_tab_kind.txt",
  "reports/coa_validation_summary.json",
  "dist/coa_entries.jsonl",
  "dist/coa_entries.pretty.json",
  "dist/coa_classes.json",
  "dist/coa_essence_caps.json",
  "dist/coa_class_profile_input.json"
];

function optionalRecord(relativePath) {
  try {
    return artifactRecord(path.join(rootDir, relativePath), rootDir);
  } catch (err) {
    return {
      path: relativePath,
      missing: true,
      note: err.message
    };
  }
}

const manifest = {
  schema_version: "coa-artifact-manifest-v1",
  generated_at: new Date().toISOString(),
  builder: {
    id: payload.id ?? null,
    slug: payload.slug ?? null,
    name: payload.name ?? null,
    max_level: payload.max_level ?? null
  },
  source: {
    url: "https://ascension.gg/en/v2/coa-builder/voljin-alpha",
    snapshot: "data/snapshots/final-page-content.html",
    har: "data/coa.har"
  },
  scripts: scriptPaths.map(optionalRecord),
  artifacts: artifactPaths.map(optionalRecord),
  validation
};

writeJson(outPath, manifest);
console.log(`Wrote ${outPath}`);
```

- [ ] **Step 2: Run syntax check**

Run:

```bash
cd coa_scraper
node --check scripts/write-artifact-manifest.mjs
```

Expected: exit 0 with no output.

- [ ] **Step 3: Generate manifest**

Run:

```bash
cd coa_scraper
node scripts/write-artifact-manifest.mjs reports dist reports/coa_artifact_manifest.json
```

Expected output:

```text
Wrote reports/coa_artifact_manifest.json
```

- [ ] **Step 4: Validate manifest JSON syntax**

Run:

```bash
python -m json.tool coa_scraper/reports/coa_artifact_manifest.json >/tmp/coa_artifact_manifest.json
```

Expected: exit 0.

---

### Task 6: Add Pipeline Orchestrator

**Files:**

- Create: `coa_scraper/scripts/run-normalization-pipeline.mjs`

- [ ] **Step 1: Create pipeline script**

Create `coa_scraper/scripts/run-normalization-pipeline.mjs`:

```javascript
#!/usr/bin/env node
import { spawnSync } from "node:child_process";

const steps = [
  ["extract payload", ["node", "scripts/extract-coa-builder-payload.mjs", "data/snapshots/final-page-content.html", "reports"]],
  ["inspect payload shape", ["node", "scripts/inspect-coa-payload-shape.mjs", "reports/coa_builder_payload.json", "reports/coa_payload_shape_report.txt", "reports/coa_payload_shape.json"]],
  ["summarize payload", ["node", "scripts/summarize-coa-payload.mjs", "reports/coa_builder_payload.json", "reports/coa_payload_report.txt"]],
  ["normalize payload", ["node", "scripts/export-coa-normalized.mjs", "reports/coa_builder_payload.json", "dist"]],
  ["build class profile input", ["node", "scripts/build-class-profile-input.mjs", "dist/coa_entries.jsonl", "dist/coa_classes.json", "dist/coa_class_profile_input.json"]],
  ["validate normalized artifacts", ["node", "scripts/validate-normalized.mjs", "dist", "reports"]],
  ["write artifact manifest", ["node", "scripts/write-artifact-manifest.mjs", "reports", "dist", "reports/coa_artifact_manifest.json"]]
];

for (const [label, cmd] of steps) {
  console.log(`\n=== ${label} ===`);
  const result = spawnSync(cmd[0], cmd.slice(1), {
    stdio: "inherit",
    shell: false
  });
  if (result.status !== 0) {
    console.error(`Step failed: ${label}`);
    process.exit(result.status || 1);
  }
}

console.log("\nPipeline completed successfully.");
```

- [ ] **Step 2: Run syntax check**

Run:

```bash
cd coa_scraper
node --check scripts/run-normalization-pipeline.mjs
```

Expected: exit 0 with no output.

- [ ] **Step 3: Run pipeline**

Run:

```bash
cd coa_scraper
node scripts/run-normalization-pipeline.mjs
```

Expected final output:

```text
Pipeline completed successfully.
```

---

### Task 7: Update Package Scripts

**Files:**

- Modify: `coa_scraper/package.json`

- [ ] **Step 1: Replace scripts block**

Replace:

```json
  "scripts": {
    "test": "echo \"Error: no test specified\" && exit 1"
  },
```

with:

```json
  "scripts": {
    "capture": "node scrape-coa-network.mjs",
    "extract": "node scripts/extract-coa-builder-payload.mjs data/snapshots/final-page-content.html reports",
    "normalize": "node scripts/export-coa-normalized.mjs reports/coa_builder_payload.json dist",
    "validate": "node scripts/validate-normalized.mjs dist reports",
    "pipeline": "node scripts/run-normalization-pipeline.mjs",
    "test": "npm run validate"
  },
```

- [ ] **Step 2: Validate package JSON syntax**

Run:

```bash
python -m json.tool coa_scraper/package.json >/tmp/coa_package.json
```

Expected: exit 0.

- [ ] **Step 3: Run package scripts**

Run:

```bash
cd coa_scraper
npm run pipeline
npm run validate
```

Expected: both commands exit 0.

---

### Task 8: Add Pipeline and Schema Documentation

**Files:**

- Create: `coa_scraper/README.md`
- Create: `docs/data/normalized-schema.md`
- Modify: `docs/README.md`

- [ ] **Step 1: Create scraper README**

Create `coa_scraper/README.md`:

````markdown
# CoA Scraper Pipeline

This module captures the official Ascension Conquest of Azeroth builder, extracts the builder payload, normalizes talent and ability entries, validates the normalized artifacts, and writes an artifact manifest.

## Capture

Run:

```bash
npm run capture
```

The capture script opens Chromium and saves HAR/raw responses/snapshots under `data/`. Manual interaction is currently expected: after the page loads, click through classes and tabs that need to be present in the final snapshot, then press Enter in the terminal.

## Regenerate Artifacts From Existing Snapshot

Run:

```bash
npm run pipeline
```

This command reads `data/snapshots/final-page-content.html` and writes:

- `reports/coa_builder_payload.json`
- `reports/coa_builder_summary.json`
- `reports/coa_payload_shape.json`
- `reports/coa_payload_shape_report.txt`
- `reports/coa_payload_report.txt`
- `reports/coa_normalization_report.txt`
- `reports/coa_counts_by_class_tab_kind.txt`
- `reports/coa_validation_summary.json`
- `reports/coa_artifact_manifest.json`
- `dist/coa_entries.jsonl`
- `dist/coa_entries.pretty.json`
- `dist/coa_classes.json`
- `dist/coa_essence_caps.json`
- `dist/coa_class_profile_input.json`

## Validate

Run:

```bash
npm run validate
```

Validation fails when required normalized fields are missing, class/tab ownership is missing, unknown essence kinds are present, or normalized records do not include schema metadata.

## Source of Truth

The optimizer consumes `dist/coa_entries.jsonl`, `dist/coa_classes.json`, and `dist/coa_essence_caps.json`. It should not parse HAR files, HTML snapshots, or Next Flight payloads directly.
````

- [ ] **Step 2: Create schema docs**

Create `docs/data/normalized-schema.md`:

````markdown
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

## Validation

Run:

```bash
cd coa_scraper
npm run validate
```

Expected healthy Vol'Jin Alpha validation has zero missing class records, zero missing tab records, and zero unknown essence-kind records.
````

- [ ] **Step 3: Link schema docs from docs README**

In `docs/README.md`, after:

```markdown
- [ASSESSMENT.md](ASSESSMENT.md) assesses the prior conversation and identifies corrections or missing design work.
```

Add:

```markdown
- [data/normalized-schema.md](data/normalized-schema.md) documents the `coa-normalized-v1` artifact contract.
```

- [ ] **Step 4: Verify docs exist**

Run:

```bash
test -f coa_scraper/README.md
test -f docs/data/normalized-schema.md
```

Expected: both commands exit 0.

---

### Task 9: Final Verification

**Files:**

- Generated: `coa_scraper/reports/coa_validation_summary.json`
- Generated: `coa_scraper/reports/coa_artifact_manifest.json`
- Generated: `coa_scraper/dist/coa_entries.jsonl`
- Generated: `coa_scraper/dist/coa_classes.json`

- [ ] **Step 1: Run full pipeline**

Run:

```bash
cd coa_scraper
npm run pipeline
```

Expected final output:

```text
Pipeline completed successfully.
```

- [ ] **Step 2: Run validator directly**

Run:

```bash
cd coa_scraper
npm run validate
```

Expected output includes:

```json
"status": "pass"
```

- [ ] **Step 3: Confirm manifest syntax**

Run:

```bash
python -m json.tool coa_scraper/reports/coa_artifact_manifest.json >/tmp/coa_artifact_manifest.json
```

Expected: exit 0.

- [ ] **Step 4: Confirm normalized records carry schema metadata**

Run:

```bash
node -e 'const fs=require("fs"); const rows=fs.readFileSync("coa_scraper/dist/coa_entries.jsonl","utf8").trim().split(/\n/).map(JSON.parse); console.log(rows.length, rows.every(r=>r.schema_version==="coa-normalized-v1" && r.field_sources && r.inferred))'
```

Expected output:

```text
3612 true
```

- [ ] **Step 5: Check documentation red-flag markers**

Run:

```bash
python - <<'PY'
from pathlib import Path
terms = ["TB" + "D", "TO" + "DO", "FIX" + "ME", "implement " + "later"]
paths = [Path("docs"), Path("coa_scraper/README.md")]
matches = []
for root in paths:
    files = root.rglob("*") if root.is_dir() else [root]
    for path in files:
        if not path.is_file() or path.suffix not in {".md", ""}:
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if any(term in line for term in terms):
                matches.append(f"{path}:{line_no}:{line}")
if matches:
    print("\n".join(matches))
    raise SystemExit(1)
PY
```

Expected: exit 0 with no output.

- [ ] **Step 6: Commit if git is available**

Run:

```bash
git status --short
```

If this command succeeds, commit the milestone docs and implementation changes:

```bash
git add docs coa_scraper
git commit -m "feat: add reproducible CoA data pipeline schema"
```

If this command fails with `fatal: not a git repository`, record that the workspace has no usable git metadata and skip the commit.
