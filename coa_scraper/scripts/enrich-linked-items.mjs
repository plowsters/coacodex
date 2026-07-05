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

export function itemEntriesFromSpellRows(spellRows) {
  const ids = [
    ...new Set(
      spellRows.flatMap(row => row.linked_item_ids || []).map(Number).filter(Number.isFinite)
    )
  ].sort((a, b) => a - b);
  return ids.map(id => ({
    item_id: id,
    entry_id: null,
    name: ""
  }));
}

const spellRowsPath = process.argv[2] || "dist/coa_db_spell_tooltips.jsonl";
const distDir = process.argv[3] || "dist";
const reportsDir = process.argv[4] || "reports";
const concurrency = Number(process.env.ASCENSIONDB_CONCURRENCY || "16");
const timeoutMs = Number(process.env.ASCENSIONDB_TIMEOUT_MS || "10000");

const spellRows = readJsonl(spellRowsPath);
const itemEntries = itemEntriesFromSpellRows(spellRows);
const fetchedAt = new Date().toISOString();
let completed = 0;

const rows = await buildEnrichmentRows({
  entries: itemEntries,
  kind: "item",
  fetchedAt,
  concurrency,
  fetchPower: async ({ url }) => {
    try {
      return await fetchText(url, { timeoutMs });
    } finally {
      completed++;
      if (completed % 100 === 0) {
        console.error(`Fetched ${completed} AscensionDB item payloads`);
      }
    }
  }
});

const outPath = path.join(distDir, "coa_db_item_tooltips.jsonl");
writeJsonl(outPath, rows);

const statusCounts = rows.reduce((acc, row) => {
  acc[row.status] = (acc[row.status] || 0) + 1;
  return acc;
}, {});

const summary = {
  schema_version: "coa-db-item-enrichment-summary-v1",
  fetched_at: fetchedAt,
  spell_rows_path: spellRowsPath,
  linked_item_count: itemEntries.length,
  item_count: rows.length,
  concurrency,
  timeout_ms: timeoutMs,
  status_counts: statusCounts,
  output: outPath
};

fs.mkdirSync(reportsDir, { recursive: true });
writeJson(path.join(reportsDir, "coa_item_enrichment_summary.json"), summary);

console.log(JSON.stringify(summary, null, 2));
