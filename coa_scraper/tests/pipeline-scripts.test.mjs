import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  artifactRecord,
  loadJson,
  loadJsonl,
  sha256File,
  writeJson
} from "../scripts/lib/artifacts.mjs";
import {
  buildEnrichmentRows,
  extractLinkedIds,
  parsePowerPayload,
  stripTooltipHtml
} from "../scripts/lib/ascensiondb.mjs";
import {
  classifySourceCategory,
  deriveAvailability,
  summarizeMetadataTabs
} from "../scripts/lib/source-level.mjs";
import { parseCaptureOptions } from "../scripts/lib/capture-options.mjs";
import { validateNormalizedArtifacts } from "../scripts/validate-normalized.mjs";
import { writeArtifactManifest } from "../scripts/write-artifact-manifest.mjs";

function tempProject() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "coa-pipeline-test-"));
}

function writeJsonl(filePath, rows) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, rows.map(row => JSON.stringify(row)).join("\n") + "\n");
}

function validNode(overrides = {}) {
  return {
    schema_version: "coa-normalized-v1",
    build_id: 39,
    build_slug: "voljin-alpha",
    build_name: "Vol'Jin Alpha",
    class_id: 29,
    class_name: "Venomancer",
    tab_id: 77,
    tab_name: "Stalking",
    tab_sort_order: 2,
    entry_type: "Talent",
    essence_kind: "talent",
    essence_type: "talentEssence",
    entry_id: 123,
    spell_id: 456,
    spell_ids: [456],
    name: "Test Node",
    icon: "Interface\\Icons\\test",
    ae_cost: 0,
    te_cost: 1,
    required_tab_ae: 0,
    required_tab_te: 0,
    description_html: "Deals Nature damage.",
    description_text: "Deals Nature damage.",
    required_level: 0,
    max_rank: 1,
    row: 1,
    col: 2,
    node_type: "SpendCircle",
    flags: 0,
    group: 0,
    is_passive: false,
    is_starting_node: false,
    required_ids: [],
    connected_node_ids: [123],
    tags: ["dot"],
    damage_schools: ["nature"],
    resources: ["Energy"],
    field_sources: { name: "entry.name" },
    inferred: { tags: ["dot"], damage_schools: ["nature"], resources: ["Energy"] },
    raw: { id: 123 },
    ...overrides
  };
}

function validClass(overrides = {}) {
  return {
    schema_version: "coa-normalized-v1",
    class_id: 29,
    class_name: "Venomancer",
    tabs: [
      {
        tab_id: 77,
        tab_name: "Stalking",
        sort_order: 2,
        nominal_essence_kind: "talent"
      }
    ],
    essence_caps: {
      maxTalentEssence: 25,
      maxAbilityEssence: 26
    },
    ...overrides
  };
}

function writeValidationFixture(dir, nodeOverrides = {}) {
  const dist = path.join(dir, "dist");
  const reports = path.join(dir, "reports");
  fs.mkdirSync(dist, { recursive: true });
  fs.mkdirSync(reports, { recursive: true });
  writeJsonl(path.join(dist, "coa_entries.jsonl"), [validNode(nodeOverrides)]);
  writeJson(path.join(dist, "coa_classes.json"), [validClass()]);
  writeJson(path.join(dist, "coa_essence_caps.json"), {
    "29": { maxTalentEssence: 25, maxAbilityEssence: 26 }
  });
  writeJson(path.join(reports, "coa_payload_shape.json"), { builder: { id: 39 } });
  fs.writeFileSync(path.join(reports, "coa_normalization_report.txt"), "ok\n");
  fs.writeFileSync(path.join(reports, "coa_payload_shape_report.txt"), "ok\n");
  return { dist, reports };
}

function enrichedSpellRow(overrides = {}) {
  return {
    kind: "spell",
    id: 92117,
    entry_id: 123,
    builder_name: "Test Node",
    status: "matched",
    name: "Test Node",
    name_match: true,
    icon: "inv_test",
    tooltip_html: "<span>Level 10 Passive</span>",
    tooltip_text: "Level 10 Passive",
    tooltip_level: 10,
    required_level: 10,
    linked_spell_ids: [],
    linked_item_ids: [],
    provenance: {
      url: "https://db.ascension.gg/?spell=92117&power",
      fetched_at: "2026-07-04T00:00:00Z"
    },
    ...overrides
  };
}

const SPELL_POWER_FIXTURE = `$WowheadPower.registerSpell(92117, 0, {
    "name_enus": "Dream Flowers",
    "icon": "inv_legion_faction_dreamweavers",
    "tooltip_enus": "<table><tr><td><span class=\\"q\\"><span style=\\"color: #66DDFF;\\">Level 10 Passive</span><br />Your damaging critical strikes spawn a <a href=\\"?spell=561005\\">Dream Flower</a>.</span></td></tr></table><!--?92117:1:1:80-->",
    "spells_enus": [],
    "buff_enus": "",
    "buffspells_enus": []
});`;

const EMPTY_SPELL_POWER_FIXTURE = `$WowheadPower.registerSpell(804137, 0, {});`;

const ITEM_POWER_FIXTURE = `$WowheadPower.registerItem(23887, 0, {
    "name_enus": "Schematic: Rocket Boots Xtreme",
    "quality": 3,
    "icon": "inv_boots_09",
    "tooltip_enus": "<table><tr><td><b class=\\"q3\\">Schematic: Rocket Boots Xtreme</b><br />Requires Level 58<br /><span class=\\"q2\\">Use: <a href=\\"?spell=30556\\">Teaches you how to make Rocket Boots Xtreme.</a></span><br /><span class=\\"q3\\"><a href=\\"?item=23824\\">Rocket Boots Xtreme</a></span></td></tr></table>"
});`;

test("artifact utilities hash, load, and describe files", () => {
  const dir = tempProject();
  const file = path.join(dir, "data.json");
  writeJson(file, { ok: true });
  fs.writeFileSync(path.join(dir, "rows.jsonl"), "");

  assert.equal(loadJson(file).ok, true);
  assert.match(sha256File(file), /^[a-f0-9]{64}$/);
  assert.deepEqual(loadJsonl(path.join(dir, "rows.jsonl")), []);

  fs.writeFileSync(path.join(dir, "rows.jsonl"), "{\"a\":1}\n");
  assert.deepEqual(loadJsonl(path.join(dir, "rows.jsonl")), [{ a: 1 }]);
  assert.equal(artifactRecord(file, dir).path, "data.json");
});

test("validator accepts complete normalized artifacts and writes summary", () => {
  const dir = tempProject();
  const { dist, reports } = writeValidationFixture(dir);

  const summary = validateNormalizedArtifacts({ distDir: dist, reportsDir: reports });

  assert.equal(summary.status, "pass");
  assert.equal(summary.record_count, 1);
  assert.equal(summary.missing_class_records, 0);
  assert.equal(summary.missing_tab_records, 0);
  assert.equal(summary.unknown_essence_kind_records, 0);
});

test("validator rejects records without schema metadata", () => {
  const dir = tempProject();
  const { dist, reports } = writeValidationFixture(dir, {
    schema_version: null,
    field_sources: null,
    inferred: null
  });

  assert.throws(
    () => validateNormalizedArtifacts({ distDir: dist, reportsDir: reports }),
    /Normalized artifact validation failed/
  );

  const summary = loadJson(path.join(reports, "coa_validation_summary.json"));
  assert.equal(summary.status, "fail");
  assert(summary.failures.some(failure => failure.includes("missing schema_version")));
});

test("validator accepts optional M1.8 source and availability fields", () => {
  const dir = tempProject();
  const { dist, reports } = writeValidationFixture(dir, {
    source_category: "spec_tree",
    source_confidence: "high",
    availability: {
      builder_required_level: 0,
      tooltip_required_level: 10,
      db_tooltip_required_level: null,
      effective_required_level: 10,
      level_source: "builder_tooltip",
      level_confidence: "medium",
      notes: ["builder_required_level_zero_but_tooltip_has_level"]
    }
  });

  const summary = validateNormalizedArtifacts({ distDir: dist, reportsDir: reports });

  assert.equal(summary.status, "pass");
  assert.equal(summary.m1_8_source_records, 1);
});

test("manifest writer records builder, validation, artifact hashes, and missing optional files", () => {
  const dir = tempProject();
  const reports = path.join(dir, "reports");
  const dist = path.join(dir, "dist");
  fs.mkdirSync(reports, { recursive: true });
  fs.mkdirSync(dist, { recursive: true });

  writeJson(path.join(reports, "coa_builder_payload.json"), {
    id: 39,
    slug: "voljin-alpha",
    name: "Vol'Jin Alpha",
    max_level: 60
  });
  writeJson(path.join(reports, "coa_validation_summary.json"), {
    status: "pass",
    record_count: 1
  });
  fs.writeFileSync(path.join(dist, "coa_entries.jsonl"), "{}\n");

  const outPath = path.join(reports, "manifest.json");
  writeArtifactManifest({ rootDir: dir, reportsDir: reports, distDir: dist, outPath });

  const manifest = loadJson(outPath);
  assert.equal(manifest.schema_version, "coa-artifact-manifest-v1");
  assert.equal(manifest.builder.slug, "voljin-alpha");
  assert.equal(manifest.validation.status, "pass");
  assert(manifest.artifacts.some(artifact => artifact.path === "dist/coa_entries.jsonl" && artifact.sha256));
  assert(manifest.scripts.some(artifact => artifact.path === "scripts/lib/capture-options.mjs" && artifact.missing === true));
  assert(manifest.artifacts.some(artifact => artifact.missing === true));
});

test("AscensionDB parser reads spell power payloads", () => {
  const parsed = parsePowerPayload(SPELL_POWER_FIXTURE, {
    kind: "spell",
    id: 92117,
    url: "https://db.ascension.gg/?spell=92117&power"
  });

  assert.equal(parsed.kind, "spell");
  assert.equal(parsed.id, 92117);
  assert.equal(parsed.status, "matched");
  assert.equal(parsed.name, "Dream Flowers");
  assert.equal(parsed.icon, "inv_legion_faction_dreamweavers");
  assert.equal(parsed.tooltip_level, 10);
  assert.deepEqual(parsed.linked_spell_ids, [561005]);
  assert.deepEqual(parsed.linked_item_ids, []);
  assert.match(parsed.tooltip_text, /Level 10 Passive/);
  assert.equal(parsed.provenance.url, "https://db.ascension.gg/?spell=92117&power");
});

test("AscensionDB parser classifies empty spell registrations", () => {
  const parsed = parsePowerPayload(EMPTY_SPELL_POWER_FIXTURE, {
    kind: "spell",
    id: 804137,
    url: "https://db.ascension.gg/?spell=804137&power"
  });

  assert.equal(parsed.kind, "spell");
  assert.equal(parsed.id, 804137);
  assert.equal(parsed.status, "empty_registration");
  assert.equal(parsed.name, null);
  assert.equal(parsed.tooltip_html, "");
  assert.deepEqual(parsed.linked_spell_ids, []);
});

test("AscensionDB parser reads item power payloads", () => {
  const parsed = parsePowerPayload(ITEM_POWER_FIXTURE, {
    kind: "item",
    id: 23887,
    url: "https://db.ascension.gg/?item=23887&power"
  });

  assert.equal(parsed.kind, "item");
  assert.equal(parsed.id, 23887);
  assert.equal(parsed.status, "matched");
  assert.equal(parsed.name, "Schematic: Rocket Boots Xtreme");
  assert.equal(parsed.required_level, 58);
  assert.deepEqual(parsed.linked_spell_ids, [30556]);
  assert.deepEqual(parsed.linked_item_ids, [23824]);
});

test("tooltip utilities strip HTML and extract linked ids", () => {
  const html = `<span>Requires Level 20</span><a href="?spell=100">Spell</a><a href="?item=200">Item</a>`;

  assert.equal(stripTooltipHtml(html), "Requires Level 20 Spell Item");
  assert.deepEqual(extractLinkedIds(html, "spell"), [100]);
  assert.deepEqual(extractLinkedIds(html, "item"), [200]);
});

test("DB enrichment rows use fetch results and classify name differences", async () => {
  const entries = [
    validNode({ entry_id: 1, spell_id: 92117, name: "Dream Flowers" }),
    validNode({ entry_id: 2, spell_id: 804137, name: "Headhunter's Spear" })
  ];
  const responses = new Map([
    [92117, SPELL_POWER_FIXTURE],
    [804137, EMPTY_SPELL_POWER_FIXTURE]
  ]);
  const fetchPower = async ({ id }) => responses.get(id);

  const rows = await buildEnrichmentRows({
    entries,
    kind: "spell",
    fetchPower,
    fetchedAt: "2026-07-04T00:00:00.000Z"
  });

  assert.equal(rows.length, 2);
  assert.equal(rows[0].status, "matched");
  assert.equal(rows[0].name_match, true);
  assert.equal(rows[1].status, "empty_registration");
  assert.equal(rows[1].name_match, false);
});

test("source category distinguishes spec tree, class pool, and unknown nodes", () => {
  assert.equal(classifySourceCategory(validNode({ tab_name: "Stalking" })), "spec_tree");
  assert.equal(classifySourceCategory(validNode({ tab_name: "Class" })), "class_pool");
  assert.equal(classifySourceCategory(validNode({ tab_name: "" })), "unknown");
});

test("availability uses builder level when explicit", () => {
  const availability = deriveAvailability({
    builderRequiredLevel: 40,
    builderTooltipText: "Level 40 Passive",
    dbTooltipLevel: null
  });

  assert.equal(availability.effective_required_level, 40);
  assert.equal(availability.level_source, "builder_required_level");
  assert.equal(availability.level_confidence, "high");
});

test("availability upgrades zero builder level when tooltip has level text", () => {
  const availability = deriveAvailability({
    builderRequiredLevel: 0,
    builderTooltipText: "Level 10 Passive",
    dbTooltipLevel: 10
  });

  assert.equal(availability.effective_required_level, 10);
  assert.equal(availability.level_source, "db_tooltip");
  assert.equal(availability.level_confidence, "medium");
  assert(availability.notes.includes("builder_required_level_zero_but_tooltip_has_level"));
});

test("metadata summary reports tabs without node rows", () => {
  const classes = [
    validClass({
      tabs: [
        { tab_id: 77, tab_name: "Stalking", sort_order: 2, nominal_essence_kind: "talent" },
        { tab_id: 1, tab_name: "None", sort_order: 0, nominal_essence_kind: "talent" }
      ]
    })
  ];
  const rows = summarizeMetadataTabs(classes, [validNode({ tab_id: 77, tab_name: "Stalking" })]);

  assert.deepEqual(rows.tabs_without_nodes.map(row => row.tab_name), ["None"]);
});

test("DB enrichment can be joined into normalized entries", async () => {
  const { applyDbEnrichmentToEntries } = await import("../scripts/apply-db-enrichment.mjs");
  const rows = applyDbEnrichmentToEntries(
    [validNode({ spell_id: 92117, required_level: 0, description_text: "Level 10 Passive" })],
    [enrichedSpellRow()]
  );

  assert.equal(rows[0].db_enrichment.status, "matched");
  assert.equal(rows[0].availability.effective_required_level, 10);
  assert.equal(rows[0].availability.level_source, "db_tooltip");
});

test("source level report summarizes metadata tabs and level quality", async () => {
  const { buildSourceLevelReport } = await import("../scripts/write-source-level-report.mjs");
  const classes = [
    validClass({
      tabs: [
        { tab_id: 77, tab_name: "Stalking", sort_order: 2, nominal_essence_kind: "talent" },
        { tab_id: 1, tab_name: "Class", sort_order: 0, nominal_essence_kind: "ability" },
        { tab_id: 2, tab_name: "None", sort_order: 1, nominal_essence_kind: "talent" }
      ]
    })
  ];
  const entries = [
    validNode({
      required_level: 0,
      availability: {
        tooltip_required_level: 10,
        effective_required_level: 10,
        level_confidence: "medium"
      }
    }),
    validNode({
      entry_id: 124,
      spell_id: 789,
      tab_id: 1,
      tab_name: "Class",
      source_category: "class_pool",
      availability: {
        tooltip_required_level: null,
        effective_required_level: 0,
        level_confidence: "low"
      }
    })
  ];

  const { metadata, report } = buildSourceLevelReport(entries, classes);

  assert.deepEqual(metadata.tabs_without_nodes.map(row => row.tab_name), ["None"]);
  assert.equal(report.required_level_zero_with_tooltip_level_count, 1);
  assert.equal(report.class_pool_unknown_level_count, 1);
});

test("capture options support unattended headless mode", () => {
  const options = parseCaptureOptions([
    "--headless",
    "--finalize-on-load",
    "--wait-ms",
    "250",
    "--url",
    "https://example.test/builder",
    "--out-dir",
    "tmp/raw",
    "--snapshot-dir",
    "tmp/snap",
    "--har",
    "tmp/capture.har"
  ]);

  assert.equal(options.url, "https://example.test/builder");
  assert.equal(options.outDir, "tmp/raw");
  assert.equal(options.snapshotDir, "tmp/snap");
  assert.equal(options.harPath, "tmp/capture.har");
  assert.equal(options.waitMs, 250);
  assert.equal(options.headless, true);
  assert.equal(options.interactive, false);
});

test("M1.8 pipeline refreshes manifest after DB enrichment artifacts", () => {
  const packageJson = JSON.parse(
    fs.readFileSync(new URL("../package.json", import.meta.url), "utf8")
  );

  assert.match(packageJson.scripts["pipeline:m1.8"], /enrich-db/);
  assert.match(packageJson.scripts["pipeline:m1.8"], /apply-db-enrichment/);
  assert.match(packageJson.scripts["pipeline:m1.8"], /write-artifact-manifest/);
});
