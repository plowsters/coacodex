#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

import {
  buildEnrichmentRows,
  fetchText,
  readJsonl,
  writeJsonl
} from "./lib/ascensiondb.mjs";
import { writeJson } from "./lib/artifacts.mjs";

const entriesPath = process.argv[2] || "dist/coa_entries.jsonl";
const distDir = process.argv[3] || "dist";
const reportsDir = process.argv[4] || "reports";
const concurrency = Number(process.env.ASCENSIONDB_CONCURRENCY || "32");
const timeoutMs = Number(process.env.ASCENSIONDB_TIMEOUT_MS || "10000");

const entries = readJsonl(entriesPath);
const fetchedAt = new Date().toISOString();
let completed = 0;
const rows = await buildEnrichmentRows({
  entries,
  kind: "spell",
  fetchedAt,
  concurrency,
  fetchPower: async ({ url }) => {
    try {
      return await fetchText(url, { timeoutMs });
    } finally {
      completed++;
      if (completed % 250 === 0) {
        console.error(`Fetched ${completed} AscensionDB spell payloads`);
      }
    }
  }
});

const outPath = path.join(distDir, "coa_db_spell_tooltips.jsonl");
writeJsonl(outPath, rows);

const statusCounts = rows.reduce((acc, row) => {
  acc[row.status] = (acc[row.status] || 0) + 1;
  return acc;
}, {});

const summary = {
  schema_version: "coa-db-enrichment-summary-v1",
  fetched_at: fetchedAt,
  entries_path: entriesPath,
  concurrency,
  timeout_ms: timeoutMs,
  spell_count: rows.length,
  status_counts: statusCounts,
  name_mismatch_count: rows.filter(row => row.status === "matched" && !row.name_match).length,
  tooltip_level_count: rows.filter(row => row.tooltip_level !== null).length,
  output: outPath
};

fs.mkdirSync(reportsDir, { recursive: true });
writeJson(path.join(reportsDir, "coa_db_enrichment_summary.json"), summary);

console.log(JSON.stringify(summary, null, 2));
