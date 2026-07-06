#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  mapWithConcurrency,
  parsePowerPayload,
  powerUrl,
  readJsonl,
  writeJsonl
} from "./lib/ascensiondb.mjs";
import {
  fetchCachedResource,
  loadCacheManifest,
  writeCacheManifest
} from "./lib/ascensiondb-cache.mjs";
import { resolveIconAsset } from "./lib/icon-assets.mjs";
import { writeJson } from "./lib/artifacts.mjs";

export function buildSeedResources(entries) {
  const ids = [
    ...new Set(entries.map(entry => Number(entry.spell_id)).filter(isPositiveId))
  ].sort((a, b) => a - b);

  return ids.map(id => resource("spell", id, "builder_spell"));
}

export function discoverLinkedResources(spellRows = [], itemRows = [], {
  linkedSpellDepth = 1,
  linkedItemDepth = 1,
  seen = new Set()
} = {}) {
  const discovered = [];
  const localSeen = new Set(seen);

  function add(kind, id, sourceKind) {
    const numericId = Number(id);
    if (!isPositiveId(numericId)) {
      return;
    }
    const key = `${kind}:${numericId}`;
    if (localSeen.has(key)) {
      return;
    }
    localSeen.add(key);
    discovered.push(resource(kind, numericId, sourceKind));
  }

  if (linkedSpellDepth > 0) {
    for (const id of uniqueLinkedIds(spellRows, "linked_spell_ids")) {
      add("spell", id, "linked_spell");
    }
  }
  if (linkedItemDepth > 0) {
    for (const id of uniqueLinkedIds(spellRows, "linked_item_ids")) {
      add("item", id, "linked_item");
    }
  }
  if (linkedSpellDepth > 0) {
    for (const id of uniqueLinkedIds(itemRows, "linked_spell_ids")) {
      add("spell", id, "linked_spell");
    }
  }
  if (linkedItemDepth > 0) {
    for (const id of uniqueLinkedIds(itemRows, "linked_item_ids")) {
      add("item", id, "linked_item");
    }
  }

  return discovered;
}

export function summarizeCacheRun(results, extra = {}) {
  const statusCounts = {};
  for (const result of results) {
    const status = result?.row?.status || result?.status || "unknown";
    statusCounts[status] = (statusCounts[status] || 0) + 1;
  }
  return {
    schema_version: "coa-ascensiondb-cache-summary-v1",
    resource_count: results.length,
    status_counts: statusCounts,
    ...extra
  };
}

export function normalizeCliOptions(argv) {
  const options = {
    entries: "dist/coa_entries.enriched.jsonl",
    out: "dist",
    reports: "reports",
    assetRoot: "dist/assets",
    manifest: "reports/coa_ascensiondb_cache_manifest.json",
    staleDays: 7,
    concurrency: 4,
    timeoutMs: 10000,
    limit: 0,
    linkedSpellDepth: 1,
    linkedItemDepth: 1,
    skipAssets: false,
    assetOnly: false,
    compatSpellsOnly: false,
    compatItemsOnly: false
  };

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const next = () => argv[++i];
    if (arg === "--entries") options.entries = next();
    else if (arg === "--out") options.out = next();
    else if (arg === "--reports") options.reports = next();
    else if (arg === "--asset-root") options.assetRoot = next();
    else if (arg === "--manifest") options.manifest = next();
    else if (arg === "--stale-days") options.staleDays = Number(next());
    else if (arg === "--concurrency") options.concurrency = Number(next());
    else if (arg === "--timeout-ms") options.timeoutMs = Number(next());
    else if (arg === "--limit") options.limit = Number(next());
    else if (arg === "--linked-spell-depth") options.linkedSpellDepth = Number(next());
    else if (arg === "--linked-item-depth") options.linkedItemDepth = Number(next());
    else if (arg === "--skip-assets") options.skipAssets = true;
    else if (arg === "--asset-only") options.assetOnly = true;
    else if (arg === "--compat-spells-only") options.compatSpellsOnly = true;
    else if (arg === "--compat-items-only") options.compatItemsOnly = true;
    else {
      throw new Error(`Unknown option: ${arg}`);
    }
  }

  return options;
}

export async function runAscensionDbAssetEnrichment(options) {
  const startedAt = new Date().toISOString();
  logStage("Stage 1: load entries and cache manifest");
  const entries = fs.existsSync(options.entries) ? readJsonl(options.entries) : [];
  const existingManifestRows = loadCacheManifest(options.manifest);

  logStage("Stage 2: fetch/reuse spell payloads");
  const seedResources = applyLimit(buildSeedResources(entries), options.limit);
  const seedResults = await fetchAndParseResources(seedResources, {
    options,
    existingManifestRows,
    fetchedAt: startedAt
  });
  const seedSpellRows = seedResults.map(result => result.parsed);

  logStage("Stage 3: discover linked spell/item records");
  const seen = new Set(seedResources.map(item => `${item.kind}:${item.id}`));
  const linkedResources = applyLimit(
    discoverLinkedResources(seedSpellRows, [], {
      linkedSpellDepth: options.linkedSpellDepth,
      linkedItemDepth: options.linkedItemDepth,
      seen
    }),
    options.limit ? Math.max(0, options.limit - seedResources.length) : 0
  );

  logStage("Stage 4: fetch/reuse linked records");
  const linkedResults = await fetchAndParseResources(linkedResources, {
    options,
    existingManifestRows,
    fetchedAt: startedAt
  });

  const allResults = [...seedResults, ...linkedResults];
  const allRows = allResults.map(result => result.parsed);

  logStage("Stage 5: resolve icon assets");
  const iconResult = await resolveIconAssetsForRows(allRows, {
    skipAssets: options.skipAssets,
    assetRoot: options.assetRoot,
    manifestRows: existingManifestRows,
    staleDays: options.staleDays
  });

  logStage("Stage 6: write artifacts and summaries");
  const allRowsWithAssets = iconResult.rows;
  const allSpellRows = allRowsWithAssets.filter(row => row.kind === "spell");
  const linkedSpellRows = linkedResults.map(result => result.parsed).filter(row => row.kind === "spell");
  const itemRows = allRowsWithAssets.filter(row => row.kind === "item");

  fs.mkdirSync(options.out, { recursive: true });
  fs.mkdirSync(options.reports, { recursive: true });

  writeJsonl(path.join(options.out, "coa_db_spell_records.jsonl"), allSpellRows);
  writeJsonl(path.join(options.out, "coa_db_item_records.jsonl"), itemRows);
  writeJsonl(path.join(options.out, "coa_db_effect_records.jsonl"), linkedSpellRows);
  writeJsonl(path.join(options.out, "coa_db_asset_records.jsonl"), iconResult.assetRows);
  writeJsonl(path.join(options.out, "coa_db_spell_tooltips.jsonl"), seedSpellRows);
  writeJsonl(path.join(options.out, "coa_db_item_tooltips.jsonl"), itemRows);

  const manifestRows = mergeManifestRows(
    existingManifestRows,
    [...allResults.map(result => result.cache.row), ...iconResult.assetRows]
  );
  writeCacheManifest(options.manifest, manifestRows);

  const summary = summarizeCacheRun(allResults.map(result => result.cache), {
    fetched_at: startedAt,
    entries_path: options.entries,
    output_dir: options.out,
    reports_dir: options.reports,
    manifest: options.manifest,
    spell_count: allSpellRows.length,
    item_count: itemRows.length,
    effect_spell_count: linkedSpellRows.length,
    asset_count: iconResult.assetRows.length,
    concurrency: options.concurrency,
    timeout_ms: options.timeoutMs
  });
  writeJson(path.join(options.reports, "coa_ascensiondb_cache_summary.json"), summary);
  console.log(JSON.stringify(summary, null, 2));
  return summary;
}

export async function resolveIconAssetsForRows(rows, {
  skipAssets = false,
  assetRoot = "dist/assets",
  manifestRows = [],
  staleDays = 7,
  now = new Date(),
  fetchBinary,
  templates,
  writeAsset
} = {}) {
  if (skipAssets) {
    return {
      rows: rows.map(row => ({ ...row })),
      assetRows: []
    };
  }

  const iconTokens = [
    ...new Set(rows.map(row => row.icon).filter(Boolean))
  ].sort();
  const resolved = new Map();
  const assetRows = [];

  for (const iconToken of iconTokens) {
    const result = await resolveIconAsset({
      iconToken,
      manifestRows,
      assetRoot,
      staleDays,
      now,
      fetchBinary,
      templates,
      writeAsset
    });
    resolved.set(iconToken, result.asset_path);
    assetRows.push(result.row);
  }

  return {
    rows: rows.map(row => ({
      ...row,
      icon_asset_path: row.icon ? resolved.get(row.icon) || null : row.icon_asset_path || null
    })),
    assetRows
  };
}

async function fetchAndParseResources(resources, { options, existingManifestRows, fetchedAt }) {
  return mapWithConcurrency(resources, options.concurrency, async item => {
    const cache = await fetchCachedResource({
      url: item.url,
      resourceKind: item.kind,
      sourceKind: item.source_kind,
      sourceId: item.source_id,
      parserVersion: "ascensiondb-power-v2",
      manifestRows: existingManifestRows,
      staleDays: options.staleDays,
      bodyRoot: path.join(options.out, "cache", "ascensiondb", "bodies"),
      fetchText: (url, fetchOptions) => fetchTextWithHeaders(url, {
        ...fetchOptions,
        timeoutMs: options.timeoutMs
      })
    });

    const parsed = cache.status === "fetch_failed"
      ? fetchFailedRow(item, cache, fetchedAt)
      : parsePowerPayload(cache.body, {
        kind: item.kind,
        id: item.id,
        url: item.url,
        fetchedAt
      });

    return {
      cache,
      parsed: {
        ...parsed,
        cache_key: cache.row.cache_key,
        cache_status: cache.status,
        source_url: item.url,
        icon_asset_path: null,
        parser_version: "ascensiondb-power-v2"
      }
    };
  });
}

async function fetchTextWithHeaders(url, {
  headers = {},
  timeoutMs = 10000
} = {}) {
  const controller = new AbortController();
  const timer = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const response = await fetch(url, { headers, signal: controller.signal });
    return {
      status: response.status,
      headers: response.headers,
      text: await response.text()
    };
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(`Timed out after ${timeoutMs}ms for ${url}`);
    }
    throw error;
  } finally {
    if (timer) {
      clearTimeout(timer);
    }
  }
}

function resource(kind, id, sourceKind) {
  return {
    kind,
    id,
    source_kind: sourceKind,
    source_id: id,
    url: powerUrl(kind, id)
  };
}

function uniqueLinkedIds(rows, fieldName) {
  return [
    ...new Set(
      rows.flatMap(row => row?.[fieldName] || []).map(Number).filter(isPositiveId)
    )
  ].sort((a, b) => a - b);
}

function isPositiveId(value) {
  return Number.isFinite(value) && value > 0;
}

function applyLimit(items, limit) {
  const numericLimit = Number(limit || 0);
  return numericLimit > 0 ? items.slice(0, numericLimit) : items;
}

function mergeManifestRows(existingRows, newRows) {
  const byKey = new Map();
  for (const row of existingRows) {
    byKey.set(row.cache_key || row.url, row);
  }
  for (const row of newRows) {
    byKey.set(row.cache_key || row.url, row);
  }
  return [...byKey.values()].sort((a, b) => String(a.url).localeCompare(String(b.url)));
}

function fetchFailedRow(item, cache, fetchedAt) {
  return {
    kind: item.kind,
    id: item.id,
    status: "fetch_failed",
    name: null,
    icon: null,
    tooltip_html: "",
    tooltip_text: "",
    tooltip_level: null,
    required_level: null,
    linked_spell_ids: [],
    linked_item_ids: [],
    warnings: [],
    errors: cache.row.errors || [],
    raw: "",
    provenance: { url: item.url, fetched_at: fetchedAt }
  };
}

function logStage(message) {
  console.error(`[ascensiondb-assets] ${message}`);
}

function isMainModule() {
  return process.argv[1] && path.resolve(fileURLToPath(import.meta.url)) === path.resolve(process.argv[1]);
}

if (isMainModule()) {
  runAscensionDbAssetEnrichment(normalizeCliOptions(process.argv.slice(2))).catch(error => {
    console.error(`[ascensiondb-assets] failed: ${error.stack || error.message || error}`);
    process.exitCode = 1;
  });
}
