import assert from "node:assert/strict";
import test from "node:test";

import { loadJson } from "../scripts/lib/artifacts.mjs";
import {
  buildSeedResources,
  discoverLinkedResources,
  normalizeCliOptions,
  summarizeCacheRun
} from "../scripts/enrich-ascensiondb-assets.mjs";

test("asset enrichment seeds unique builder spell resources", () => {
  const resources = buildSeedResources([
    { spell_id: 300, entry_id: 1 },
    { spell_id: 100, entry_id: 2 },
    { spell_id: 300, entry_id: 3 },
    { spell_id: null, entry_id: 4 }
  ]);

  assert.deepEqual(resources, [
    {
      kind: "spell",
      id: 100,
      source_kind: "builder_spell",
      source_id: 100,
      url: "https://db.ascension.gg/?spell=100&power"
    },
    {
      kind: "spell",
      id: 300,
      source_kind: "builder_spell",
      source_id: 300,
      url: "https://db.ascension.gg/?spell=300&power"
    }
  ]);
});

test("asset enrichment discovers bounded linked spell and item resources", () => {
  const resources = discoverLinkedResources(
    [
      { kind: "spell", id: 100, linked_spell_ids: [200, 201], linked_item_ids: [900] },
      { kind: "spell", id: 101, linked_spell_ids: [200], linked_item_ids: [] }
    ],
    [
      { kind: "item", id: 900, linked_spell_ids: [300], linked_item_ids: [901] }
    ],
    {
      linkedSpellDepth: 1,
      linkedItemDepth: 1,
      seen: new Set(["spell:100"])
    }
  );

  assert.deepEqual(resources, [
    {
      kind: "spell",
      id: 200,
      source_kind: "linked_spell",
      source_id: 200,
      url: "https://db.ascension.gg/?spell=200&power"
    },
    {
      kind: "spell",
      id: 201,
      source_kind: "linked_spell",
      source_id: 201,
      url: "https://db.ascension.gg/?spell=201&power"
    },
    {
      kind: "item",
      id: 900,
      source_kind: "linked_item",
      source_id: 900,
      url: "https://db.ascension.gg/?item=900&power"
    },
    {
      kind: "spell",
      id: 300,
      source_kind: "linked_spell",
      source_id: 300,
      url: "https://db.ascension.gg/?spell=300&power"
    },
    {
      kind: "item",
      id: 901,
      source_kind: "linked_item",
      source_id: 901,
      url: "https://db.ascension.gg/?item=901&power"
    }
  ]);

  assert.deepEqual(
    discoverLinkedResources([{ linked_spell_ids: [200], linked_item_ids: [900] }], [], {
      linkedSpellDepth: 0,
      linkedItemDepth: 0
    }),
    []
  );
});

test("asset enrichment summary counts cache statuses", () => {
  const summary = summarizeCacheRun([
    { row: { status: "fetched" } },
    { row: { status: "fetched" } },
    { row: { status: "fresh_cache" } },
    { row: { status: "not_modified" } },
    { row: { status: "fetch_failed" } },
    { row: { status: "parse_failed" } },
    { row: { status: "asset_missing" } }
  ]);

  assert.equal(summary.schema_version, "coa-ascensiondb-cache-summary-v1");
  assert.deepEqual(summary.status_counts, {
    fetched: 2,
    fresh_cache: 1,
    not_modified: 1,
    fetch_failed: 1,
    parse_failed: 1,
    asset_missing: 1
  });
});

test("asset enrichment CLI defaults are conservative", () => {
  const options = normalizeCliOptions([]);

  assert.equal(options.entries, "dist/coa_entries.enriched.jsonl");
  assert.equal(options.out, "dist");
  assert.equal(options.reports, "reports");
  assert.equal(options.assetRoot, "dist/assets");
  assert.equal(options.manifest, "reports/coa_ascensiondb_cache_manifest.json");
  assert.equal(options.staleDays, 7);
  assert.equal(options.concurrency, 4);
  assert.equal(options.timeoutMs, 10000);
  assert.equal(options.linkedSpellDepth, 1);
  assert.equal(options.linkedItemDepth, 1);
});

test("asset enrichment package script is exposed", () => {
  const packageJson = loadJson(new URL("../package.json", import.meta.url));

  assert.match(packageJson.scripts["enrich-assets"], /enrich-ascensiondb-assets\.mjs/);
});
