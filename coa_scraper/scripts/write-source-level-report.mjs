#!/usr/bin/env node
import path from "node:path";
import { fileURLToPath } from "node:url";

import { loadJson, writeJson } from "./lib/artifacts.mjs";
import { readJsonl } from "./lib/jsonl.mjs";
import { summarizeMetadataTabs } from "./lib/source-level.mjs";

export function buildSourceLevelReport(entries, classes) {
  const metadata = summarizeMetadataTabs(classes, entries);
  const levelMismatches = entries.filter(entry =>
    Number(entry.required_level || 0) === 0 &&
    entry.availability?.tooltip_required_level !== null &&
    entry.availability?.tooltip_required_level !== undefined
  );
  const classPoolUnknown = entries.filter(entry =>
    entry.source_category === "class_pool" &&
    entry.availability?.level_confidence === "low"
  );

  const report = {
    schema_version: "coa-source-level-report-v1",
    record_count: entries.length,
    metadata_tab_count: metadata.tab_count,
    metadata_tabs_without_nodes: metadata.tabs_without_nodes,
    required_level_zero_with_tooltip_level_count: levelMismatches.length,
    required_level_zero_with_tooltip_level_samples: levelMismatches.slice(0, 25).map(entry => ({
      class_name: entry.class_name,
      tab_name: entry.tab_name,
      entry_id: entry.entry_id,
      spell_id: entry.spell_id,
      name: entry.name,
      tooltip_required_level: entry.availability.tooltip_required_level
    })),
    class_pool_unknown_level_count: classPoolUnknown.length,
    class_pool_unknown_level_samples: classPoolUnknown.slice(0, 25).map(entry => ({
      class_name: entry.class_name,
      entry_id: entry.entry_id,
      spell_id: entry.spell_id,
      name: entry.name
    }))
  };

  return { metadata, report };
}

function isCliEntryPoint() {
  return process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);
}

if (isCliEntryPoint()) {
  const entriesPath = process.argv[2] || "dist/coa_entries.jsonl";
  const classesPath = process.argv[3] || "dist/coa_classes.json";
  const reportsDir = process.argv[4] || "reports";

  const entries = readJsonl(entriesPath);
  const classes = loadJson(classesPath);
  const { metadata, report } = buildSourceLevelReport(entries, classes);

  writeJson(path.join(reportsDir, "coa_metadata_tab_report.json"), metadata);
  writeJson(path.join(reportsDir, "coa_source_level_report.json"), report);
  console.log(JSON.stringify(report, null, 2));
}
