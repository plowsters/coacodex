#!/usr/bin/env node
import path from "node:path";
import { fileURLToPath } from "node:url";

import { artifactRecord, loadJson, writeJson } from "./lib/artifacts.mjs";

const DEFAULT_SOURCE_URL = "https://ascension.gg/en/v2/coa-builder/voljin-alpha";

const scriptPaths = [
  "scrape-coa-network.mjs",
  "scripts/extract-coa-builder-payload.mjs",
  "scripts/inspect-coa-payload-shape.mjs",
  "scripts/summarize-coa-payload.mjs",
  "scripts/export-coa-normalized.mjs",
  "scripts/build-class-profile-input.mjs",
  "scripts/lib/ascensiondb.mjs",
  "scripts/lib/ascensiondb-cache.mjs",
  "scripts/lib/capture-options.mjs",
  "scripts/lib/icon-assets.mjs",
  "scripts/lib/source-level.mjs",
  "scripts/enrich-ascensiondb-assets.mjs",
  "scripts/enrich-ascensiondb.mjs",
  "scripts/apply-db-enrichment.mjs",
  "scripts/enrich-linked-items.mjs",
  "scripts/build-mechanics-artifacts.mjs",
  "scripts/write-source-level-report.mjs",
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
  "reports/coa_source_level_report.json",
  "reports/coa_metadata_tab_report.json",
  "reports/coa_db_enrichment_summary.json",
  "reports/coa_item_enrichment_summary.json",
  "reports/coa_ascensiondb_cache_manifest.json",
  "reports/coa_ascensiondb_cache_summary.json",
  "reports/coa_mechanics_enrichment_summary.json",
  "dist/coa_entries.jsonl",
  "dist/coa_entries.pretty.json",
  "dist/coa_classes.json",
  "dist/coa_essence_caps.json",
  "dist/coa_class_profile_input.json",
  "dist/coa_db_spell_records.jsonl",
  "dist/coa_db_spell_tooltips.jsonl",
  "dist/coa_db_item_records.jsonl",
  "dist/coa_db_item_tooltips.jsonl",
  "dist/coa_db_effect_records.jsonl",
  "dist/coa_db_asset_records.jsonl",
  "dist/coa_entries.enriched.jsonl",
  "dist/coa_mechanics.jsonl",
  "dist/coa_items.jsonl"
];

function optionalRecord(relativePath, rootDir) {
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

export function writeArtifactManifest({
  rootDir = process.cwd(),
  reportsDir = "reports",
  distDir = "dist",
  outPath = path.join(reportsDir, "coa_artifact_manifest.json"),
  sourceUrl = DEFAULT_SOURCE_URL
} = {}) {
  const payloadPath = path.join(reportsDir, "coa_builder_payload.json");
  const validationPath = path.join(reportsDir, "coa_validation_summary.json");
  const payload = loadJson(payloadPath);
  const validation = loadJson(validationPath);

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
      url: sourceUrl,
      snapshot: "data/snapshots/final-page-content.html",
      har: "data/coa.har"
    },
    scripts: scriptPaths.map(relativePath => optionalRecord(relativePath, rootDir)),
    artifacts: artifactPaths.map(relativePath => optionalRecord(relativePath, rootDir)),
    validation,
    dist_dir: path.relative(rootDir, distDir).replaceAll(path.sep, "/") || ".",
    reports_dir: path.relative(rootDir, reportsDir).replaceAll(path.sep, "/") || "."
  };

  writeJson(outPath, manifest);
  return manifest;
}

function isCliEntryPoint() {
  return process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);
}

if (isCliEntryPoint()) {
  const reportsDir = process.argv[2] || "reports";
  const distDir = process.argv[3] || "dist";
  const outPath = process.argv[4] || path.join(reportsDir, "coa_artifact_manifest.json");
  writeArtifactManifest({ reportsDir, distDir, outPath });
  console.log(`Wrote ${outPath}`);
}
