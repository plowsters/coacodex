import assert from "node:assert/strict";
import crypto from "node:crypto";
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
  fetchTextWithTimeout,
  mapWithConcurrency,
  parsePowerPayload,
  stripTooltipHtml
} from "../scripts/lib/ascensiondb.mjs";
import {
  classifySourceCategory,
  deriveAvailability,
  summarizeMetadataTabs
} from "../scripts/lib/source-level.mjs";
import {
  layoutFromNormalizedEntries,
  treeKindForNormalizedEntry
} from "../scripts/lib/builder-tree-layout.mjs";
import { parseCaptureOptions } from "../scripts/lib/capture-options.mjs";
import { validateNormalizedArtifacts } from "../scripts/validate-normalized.mjs";
import { writeArtifactManifest } from "../scripts/write-artifact-manifest.mjs";
import {
  buildMechanicsArtifact,
  buildCanonicalMechanics,
  summarizeMechanicsArtifacts
} from "../scripts/build-mechanics-artifacts.mjs";
import { buildItemRows } from "../scripts/build-item-artifacts.mjs";
import { normalizeSchoolMask, normalizePowerType } from "../scripts/lib/mechanics-normalize.mjs";
import { reconcileField, REASON } from "../scripts/lib/mechanics-reconcile.mjs";
import { fieldCandidates } from "../scripts/lib/mechanics-candidates.mjs";
import { loadAndValidateProjection, MechanicsBuildError } from "../scripts/lib/mechanics-projection.mjs";
import { resolveGeneration, GenerationResolveError } from "../scripts/lib/generation.mjs";

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

test("builder tree layout capture command is exposed", () => {
  const packageJson = loadJson(path.join(import.meta.dirname, "..", "package.json"));
  assert.equal(packageJson.scripts["capture:tree-layout"], "node scripts/capture-builder-tree-layout.mjs");

  const script = fs.readFileSync(path.join(import.meta.dirname, "..", "scripts", "capture-builder-tree-layout.mjs"), "utf8");
  assert.match(script, /--class/);
  assert.match(script, /--spec/);
  assert.match(script, /--out/);
  assert.match(script, /--screenshots/);
  assert.match(script, /--headless/);
  assert.match(script, /--viewport/);
  assert.match(script, /--entries/);
  assert.match(script, /--from-entries/);
  assert.match(script, /--pause-for-manual-selection/);
});

test("builder tree layout uses normalized builder grid as canonical structure", () => {
  const rows = [
    validNode({
      class_name: "Venomancer",
      tab_name: "Class",
      entry_id: 101,
      name: "Class Starter",
      essence_kind: "ability",
      ae_cost: 1,
      te_cost: 0,
      row: 0,
      col: 0,
      connected_node_ids: [102]
    }),
    validNode({
      class_name: "Venomancer",
      tab_name: "Class",
      entry_id: 102,
      name: "Class Follow-up",
      essence_kind: "ability",
      ae_cost: 1,
      te_cost: 0,
      row: 1,
      col: 0,
      connected_node_ids: []
    }),
    validNode({
      class_name: "Venomancer",
      tab_name: "Stalking",
      entry_id: 201,
      name: "Spec Starter",
      essence_kind: "talent",
      ae_cost: 0,
      te_cost: 0,
      required_level: 0,
      row: 0,
      col: 4,
      connected_node_ids: [202]
    }),
    validNode({
      class_name: "Venomancer",
      tab_name: "Stalking",
      entry_id: 202,
      name: "Paid Spec Talent",
      essence_kind: "talent",
      ae_cost: 0,
      te_cost: 1,
      required_level: 0,
      row: 1,
      col: 4,
      required_ids: [201],
      connected_node_ids: []
    }),
    validNode({
      class_name: "Venomancer",
      tab_name: "Stalking",
      entry_id: 203,
      name: "Spec Core Ability",
      essence_kind: "ability",
      ae_cost: 0,
      te_cost: 0,
      required_level: 0,
      row: 1,
      col: 5,
      connected_node_ids: []
    }),
    validNode({
      class_name: "Venomancer",
      tab_name: "Stalking",
      entry_id: 301,
      name: "Level 10 Passive",
      essence_kind: "talent",
      ae_cost: 0,
      te_cost: 0,
      required_level: 10,
      row: 0,
      col: 10,
      connected_node_ids: [302]
    }),
    validNode({
      class_name: "Venomancer",
      tab_name: "Stalking",
      entry_id: 302,
      name: "Level 20 Passive",
      essence_kind: "talent",
      ae_cost: 0,
      te_cost: 0,
      required_level: 20,
      row: 2,
      col: 10,
      connected_node_ids: []
    })
  ];

  const layout = layoutFromNormalizedEntries(rows, {
    className: "Venomancer",
    specName: "Stalking",
    viewport: { width: 1920, height: 1080 },
    sourceUrl: "https://ascension.gg/en/v2/coa-builder/voljin-alpha"
  });

  const abilityTree = layout.trees.find(tree => tree.tree_kind === "ability_essence");
  const talentTree = layout.trees.find(tree => tree.tree_kind === "talent_essence");
  const passiveLane = layout.trees.find(tree => tree.tree_kind === "level_passives");

  assert.equal(layout.layout_source, "builder_grid");
  assert.deepEqual(abilityTree.nodes.map(node => node.entry_id), [101, 102]);
  assert.deepEqual(talentTree.nodes.map(node => node.entry_id), [201, 202, 203]);
  assert.deepEqual(passiveLane.nodes.map(node => node.entry_id), [301, 302]);
  assert.equal(treeKindForNormalizedEntry(rows[2]), "talent_essence");
  assert.equal(treeKindForNormalizedEntry(rows[4]), "talent_essence");
  assert.equal(treeKindForNormalizedEntry(rows[5]), "level_passives");
  assert(passiveLane.nodes.every(node => node.x === passiveLane.nodes[0].x));
  assert(passiveLane.nodes[1].y > passiveLane.nodes[0].y);
  assert(abilityTree.edges.some(edge => edge.source_entry_id === 101 && edge.target_entry_id === 102 && edge.kind === "connection"));
  assert(talentTree.edges.some(edge => edge.source_entry_id === 201 && edge.target_entry_id === 202 && edge.kind === "requirement"));
  assert(abilityTree.bounds.width > 64);
  assert(talentTree.bounds.height > 64);
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
  assert(manifest.scripts.some(artifact => artifact.path === "scripts/build-mechanics-artifacts.mjs" && artifact.missing === true));
  assert(manifest.artifacts.some(artifact => artifact.path === "dist/coa_mechanics.jsonl" && artifact.missing === true));
  assert(manifest.artifacts.some(artifact => artifact.path === "dist/coa_items.jsonl" && artifact.missing === true));
  assert(manifest.scripts.some(artifact => artifact.path === "scripts/lib/icon-assets.mjs" && artifact.missing === true));
  assert(manifest.artifacts.some(artifact => artifact.path === "dist/coa_db_spell_records.jsonl" && artifact.missing === true));
  assert(manifest.artifacts.some(artifact => artifact.path === "dist/coa_db_asset_records.jsonl" && artifact.missing === true));
  assert(manifest.artifacts.some(artifact => artifact.path === "reports/coa_ascensiondb_cache_summary.json" && artifact.missing === true));
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

test("DB enrichment utilities bound concurrency and preserve order", async () => {
  let active = 0;
  let maxActive = 0;
  const results = await mapWithConcurrency([1, 2, 3, 4], 2, async value => {
    active++;
    maxActive = Math.max(maxActive, active);
    await new Promise(resolve => setTimeout(resolve, 5));
    active--;
    return value * 10;
  });

  assert.deepEqual(results, [10, 20, 30, 40]);
  assert.equal(maxActive, 2);
});

test("DB enrichment fetches time out slow requests", async () => {
  const fetchImpl = async (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => {
      const error = new Error("aborted");
      error.name = "AbortError";
      reject(error);
    });
  });

  await assert.rejects(
    () => fetchTextWithTimeout("https://example.test/slow", { fetchImpl, timeoutMs: 1 }),
    /Timed out after 1ms/
  );
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

test("mechanics artifact builder emits client-derived spell mechanics (no AscensionDB source)", () => {
  const entry = validNode({
    entry_id: 501,
    spell_id: 92117,
    name: "Dream Flowers",
    tags: ["dot"],
    damage_schools: ["nature"],
    resources: ["Energy"],
    description_text: "Deals Nature damage over 12 sec."
  });
  // Client projection supplies the mechanical fields; the Builder supplies tags/effects. cooldown/gcd/
  // costs have NO source after AscensionDB removal and are null (E0R: missing != default).
  const projection = [{
    spell_id: 92117, name: "Dream Flowers",
    mechanics: { school_mask: 8, power_type: 3, cast_time_ms: 0, duration_ms: 12000, range_min_yd: 0, range_max_yd: 30 },
    coa_attribution: { is_coa: true, confidence: "high" },
  }];
  const itemPayload = parsePowerPayload(ITEM_POWER_FIXTURE, {
    kind: "item",
    id: 23887,
    url: "https://db.ascension.gg/?item=23887&power",
    fetchedAt: "2026-07-05T00:00:00.000Z"
  });

  const mechanicsRows = buildCanonicalMechanics({ entries: [entry], spellRows: [], projection });
  const itemRows = buildItemRows({ itemPayloadRows: [itemPayload] });
  const summary = summarizeMechanicsArtifacts({ mechanicsRows, itemRows });

  assert.equal(mechanicsRows[0].schema_version, "coa-mechanics-v1");
  assert.equal(mechanicsRows[0].spell_id, 92117);
  assert.deepEqual(mechanicsRows[0].source_node_ids, [501]);
  assert.equal(mechanicsRows[0].effects[0].effect_type, "damage");
  assert.equal(mechanicsRows[0].effects[0].school, "nature");
  assert.equal(mechanicsRows[0].cast_time_ms, 0);
  assert.equal(mechanicsRows[0].range_yards, 30);
  assert.equal(mechanicsRows[0].cooldown_ms, null);   // no AscensionDB source
  assert.equal(mechanicsRows[0].gcd_ms, null);
  assert.equal(mechanicsRows[0].costs, null);
  assert(!mechanicsRows[0].provenance.some((p) => p.source === "ascension_db"));
  // the item pipeline (parser + buildItemRows) is untouched by the mechanics DB removal
  assert.equal(itemRows[0].schema_version, "coa-item-v1");
  assert.equal(itemRows[0].item_id, 23887);
  assert.equal(itemRows[0].required_level, 58);
  assert.equal(itemRows[0].icon, "inv_boots_09");
  assert.deepEqual(itemRows[0].linked_spell_ids, [30556]);
  assert.equal(summary.mechanics_count, 1);
  assert.equal(summary.item_count, 1);
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

test("normalizeSchoolMask flags unknown bits; normalizePowerType flags unknown enum", () => {
  assert.deepEqual(normalizeSchoolMask(8), { schools: ["nature"], unknownBits: [] });
  assert.deepEqual(normalizeSchoolMask(12), { schools: ["fire", "nature"], unknownBits: [] }); // 4|8
  assert.deepEqual(normalizeSchoolMask(128), { schools: [], unknownBits: [128] });            // undocumented bit
  assert.equal(normalizePowerType(3).value, "energy");
  assert.equal(normalizePowerType(999).unknown, true);                                          // undocumented enum
});

test("build-mechanics is pointer-only + network-free in package.json (no AscensionDB)", () => {
  const packageJson = JSON.parse(
    fs.readFileSync(new URL("../package.json", import.meta.url), "utf8")
  );
  assert.match(packageJson.scripts["build-mechanics"], /build-mechanics-artifacts/);
  assert.match(packageJson.scripts["build-mechanics"], /--client-extract-pointer/);
  assert.doesNotMatch(packageJson.scripts["build-mechanics"], /--db-spells/);
  assert.equal(packageJson.scripts["pipeline:m1.9"], undefined);
});

test("reconcileField picks first eligible by tier and records all candidates", () => {
  const cand = (over) => ({
    source: "x", precedence_tier: "inferred", source_id: "s", source_field: "f",
    raw_value: null, normalized_value: null, confidence: "low", eligible: true, eligibility_reasons: [],
    ...over,
  });
  // client wins over a lower-tier inferred candidate even though both are eligible
  const out = reconcileField({
    field: "cast_time_ms",
    candidates: [
      cand({ source: "client_dbc", precedence_tier: "client_dbc", normalized_value: 1500, confidence: "high" }),
      cand({ source: "builder", precedence_tier: "inferred", normalized_value: 2000, confidence: "medium" }),
    ],
  });
  assert.equal(out.selected, 1500);
  assert.equal(out.provenance.selected_source, "client_dbc");
  assert.equal(out.provenance.selected_tier, "client_dbc");
  assert.equal(out.provenance.selection_reason, REASON.HIGHEST_PRECEDENCE_ELIGIBLE);
  assert.equal(out.provenance.candidates.length, 2);
  assert.equal(out.hadConflict, false);
});

test("reconcileField marks ALL same-tier conflicters ineligible and falls through", () => {
  const b = (id, v) => ({
    source: "builder", precedence_tier: "inferred", source_id: `builder_node:${id}`, source_field: "damage_schools",
    raw_value: v, normalized_value: v, confidence: "medium", eligible: true, eligibility_reasons: [],
  });
  const out = reconcileField({
    field: "schools",
    candidates: [
      { source: "client_dbc", precedence_tier: "client_dbc", source_id: "client_spell:1", source_field: "school_mask",
        raw_value: 8, normalized_value: ["nature"], confidence: "high", eligible: true, eligibility_reasons: [] },
      b(7131, ["nature"]), b(12264, ["shadow"]),
    ],
  });
  assert.deepEqual(out.selected, ["nature"]); // client wins
  assert.equal(out.hadConflict, true);
  const builders = out.provenance.candidates.filter((c) => c.source === "builder");
  assert(builders.every((c) => c.eligible === false));
  assert(builders.every((c) => c.eligibility_reasons.includes(REASON.SAME_TIER_CONFLICT)));
});

test("reconcileField omits field when only tier conflicts", () => {
  const b = (id, v) => ({
    source: "builder", precedence_tier: "inferred", source_id: `builder_node:${id}`, source_field: "damage_schools",
    raw_value: v, normalized_value: v, confidence: "medium", eligible: true, eligibility_reasons: [],
  });
  const out = reconcileField({ field: "schools", candidates: [b(1, ["nature"]), b(2, ["shadow"])] });
  assert.equal(out.selected, undefined);
  assert.equal(out.provenance.selection_reason, REASON.OMITTED_UNRESOLVED_CONFLICT);
});

test("fieldCandidates: client cast_time 0 is present (missing != zero) and eligible", () => {
  const clientRec = {
    mechanics: { cast_time_ms: 0, school_mask: 8, power_type: 3, duration_ms: null, range_max_yd: 30 },
    coa_attribution: { confidence: "high" },
    spell_id: 42,
  };
  const cands = fieldCandidates({ field: "cast_time_ms", clientRec, builderNodes: [] });
  const client = cands.find((c) => c.source === "client_dbc");
  assert.equal(client.normalized_value, 0);
  assert.equal(client.eligible, true);
  assert(!cands.some((c) => c.source === "ascension_db"));   // no DB tier exists anymore
});

test("fieldCandidates: v2 withheld (null) client field yields no eligible client candidate", () => {
  // v2 withholds an unproven/out-of-domain value to null at extraction; a null client value is simply
  // not eligible (no table-drift eligibility reason exists anymore — drift fails the extract closed).
  const clientRec = {
    mechanics: { cast_time_ms: null },
    coa_attribution: { confidence: "high" }, spell_id: 7,
  };
  const cands = fieldCandidates({ field: "cast_time_ms", clientRec, builderNodes: [] });
  const client = cands.find((c) => c.source === "client_dbc");
  assert.equal(client.eligible, false);
  // a populated client value, by contrast, is eligible by construction (already proof-gated)
  const ok = fieldCandidates({ field: "cast_time_ms", clientRec: { mechanics: { cast_time_ms: 1500 }, coa_attribution: { confidence: "high" }, spell_id: 7 }, builderNodes: [] });
  assert.equal(ok.find((c) => c.source === "client_dbc").eligible, true);
});

test("buildCanonicalMechanics: one row per spell_id, client field wins, schools + field_provenance present", () => {
  const projection = [{
    spell_id: 92117, name: "Adrenal Venom",
    mechanics: { school_mask: 8, power_type: 3, cast_time_ms: 0, duration_ms: 12000, range_min_yd: 0, range_max_yd: 30 },
    coa_attribution: { is_coa: true, confidence: "high" },
  }];
  const entryA = { spell_id: 92117, entry_id: 501, entry_type: "Ability", name: "Adrenal Venom", damage_schools: ["nature"], resources: ["energy"], tags: ["damage"] };
  const entryB = { spell_id: 92117, entry_id: 777, entry_type: "Talent", name: "Adrenal Venom", damage_schools: ["nature"], resources: ["energy"], tags: ["damage"] };
  const rows = buildCanonicalMechanics({ entries: [entryA, entryB], spellRows: [], projection });
  assert.equal(rows.length, 1);
  const r = rows[0];
  assert.equal(r.spell_id, 92117);
  assert.deepEqual(r.source_node_ids, [501, 777]);
  assert.equal(r.cast_time_ms, 0); // client 0 (missing != zero)
  assert.deepEqual(r.schools, ["nature"]);
  assert.equal(r.cooldown_ms, null);   // no AscensionDB source
  assert.equal(r.field_provenance.cast_time_ms.selected_source, "client_dbc");
  assert.equal(r.field_provenance.effects.selected_source, "inferred"); // effects field has provenance
  assert.deepEqual(r.raw.tags, ["damage"]); // builder tags carried under raw, not a top-level v1 field
  assert.equal(r.tags, undefined); // NOT a top-level field (would be dropped by the v1 loader)
  // kind is Builder-only now — no AscensionDB tooltip candidate ever appears
  assert(!r.field_provenance.kind.candidates.some((c) => c.source === "ascension_db"));
});

test("buildCanonicalMechanics: output is input-node-order-independent (canonicalized by entry_id)", () => {
  const projection = [{
    spell_id: 92117, name: "Adrenal Venom",
    mechanics: { school_mask: 8, power_type: 3, cast_time_ms: 0, duration_ms: 12000, range_min_yd: 0, range_max_yd: 30 },
    coa_attribution: { is_coa: true, confidence: "high" },
  }];
  const a = { spell_id: 92117, entry_id: 501, entry_type: "Ability", name: "Adrenal Venom", damage_schools: ["nature"], resources: ["energy"], tags: ["damage"] };
  const b = { spell_id: 92117, entry_id: 777, entry_type: "Talent", name: "Adrenal Venom", damage_schools: ["nature"], resources: ["energy"], tags: ["dot"] };
  const forward = buildCanonicalMechanics({ entries: [a, b], spellRows: [], projection });
  const reversed = buildCanonicalMechanics({ entries: [b, a], spellRows: [], projection });
  assert.equal(JSON.stringify(forward), JSON.stringify(reversed));
  assert.deepEqual(forward[0].raw.tags, ["damage", "dot"]); // set-like union, sorted, under raw
});

function writeProjectionFixture(dir, records) {
  const proj = path.join(dir, "p.jsonl");
  const man = path.join(dir, "p.manifest.json");
  const body = records.map((r) => JSON.stringify(r)).join("\n") + (records.length ? "\n" : "");
  fs.writeFileSync(proj, body);
  const sha = crypto.createHash("sha256").update(body).digest("hex");
  const uniq = new Set(records.map((r) => r.spell_id)).size;
  fs.writeFileSync(man, JSON.stringify({
    schema_version: "coa-client-spell-projection-v2",
    projection: { path: "p.jsonl", sha256: sha, byte_length: Buffer.byteLength(body) },
    counts: { projected_records: records.length, unique_spell_ids: uniq, source_records: records.length },
    client_build: "test-client-build",
  }));
  return { proj, man };
}

const _proof = { integrity: "verified", layout: "verified", interpretation: "verified" };
const _env = (v, kind = "int32") => ({ state: "present", raw_u32: v, decoded: { kind, value: v }, decoded_reason: "decoded", proof: _proof, evidence_ref: "fx" });
const _join = (v) => ({ state: "resolved", components: {}, composed_proof: _proof, decoded: v, decoded_reason: "decoded" });

function validProjRec(spell_id) {
  return {
    schema_version: "coa-client-spell-v2", spell_id, name: `S${spell_id}`,
    mechanics: { school_mask: 8, power_type: 3, cast_time_ms: 0, duration_ms: 12000, range_min_yd: 0, range_max_yd: 30, spell_icon_id: 1 },
    field_observations: {
      school_mask: _env(8, "uint32"), power_type: _env(3, "int32"),
      cast_time_ms: _join(0), duration_ms: _join(12000),
      range_min_yd: _join(0), range_max_yd: _join(30), spell_icon_id: _join(1),
    },
    coa_attribution: { is_coa: true, confidence: "high" },
  };
}

test("loadAndValidateProjection: coverage gap fails", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "proj-"));
  const { proj, man } = writeProjectionFixture(dir, [validProjRec(1)]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1, 2]) }),
    /builder_missing_from_projection/,
  );
});

test("loadAndValidateProjection: torn pair (only one file) throws even though it looks 'absent'", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "torn-"));
  const { proj } = writeProjectionFixture(dir, [validProjRec(1)]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: path.join(dir, "missing.json"), builderSpellIds: new Set([1]) }),
    /torn projection pair/,
  );
});

test("loadAndValidateProjection: v2 normalized value disagreeing with its observation throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "consist-"));
  const rec = validProjRec(1);
  rec.mechanics.cast_time_ms = 1500;            // observation still says decoded 0 -> inconsistent
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /cast_time_ms normalized 1500 disagrees with observation 0/,
  );
});

test("loadAndValidateProjection: a populated numeric field with no observation throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "noobs-"));
  const rec = validProjRec(1);
  delete rec.field_observations.power_type;     // power_type still populated (3)
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /power_type populated but has no field_observation/,
  );
});

test("loadAndValidateProjection: a v1 projection row is rejected with a regenerate message", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "v1row-"));
  const rec = validProjRec(1);
  rec.schema_version = "coa-client-spell-v1";
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /v1 schema; regenerate with M1\.14E/,
  );
});

test("loadAndValidateProjection: both files absent returns { absent: true }", () => {
  const out = loadAndValidateProjection({ projectionPath: "/no/such.jsonl", manifestPath: "/no/such.json", builderSpellIds: new Set() });
  assert.equal(out.absent, true);
});

test("loadAndValidateProjection: non-numeric cast_time_ms throws (no string leaks to canonical)", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "badnum-"));
  const rec = validProjRec(1);
  rec.mechanics.cast_time_ms = "2000"; // string, not number
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /cast_time_ms must be number\|null/,
  );
});

test("loadAndValidateProjection: negative school_mask throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "negmask-"));
  const rec = validProjRec(1);
  rec.mechanics.school_mask = -8;
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /school_mask must be a non-negative integer/,
  );
});

test("loadAndValidateProjection: fractional school_mask throws (bitmask must be integer)", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fracmask-"));
  const rec = validProjRec(1);
  rec.mechanics.school_mask = 8.5;
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /school_mask must be integer\|null/,
  );
});

test("loadAndValidateProjection: unknown school-mask bit throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "badbit-"));
  const rec = validProjRec(1);
  rec.mechanics.school_mask = 1 << 20; // no such school
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /unknown school-mask bits/,
  );
});

test("loadAndValidateProjection: unknown power_type enum throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "badpwr-"));
  const rec = validProjRec(1);
  rec.mechanics.power_type = 99;
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /unknown power_type/,
  );
});

test("loadAndValidateProjection: a v1 projection manifest is rejected with a regenerate message", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "v1man-"));
  const { proj, man } = writeProjectionFixture(dir, [validProjRec(1)]);
  const parsed = JSON.parse(fs.readFileSync(man, "utf8"));
  parsed.schema_version = "coa-client-spell-projection-v1";
  fs.writeFileSync(man, JSON.stringify(parsed));
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /manifest is v1; regenerate with M1\.14E/,
  );
});

test("loadAndValidateProjection: an unknown projection manifest schema throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "badschema-"));
  const { proj, man } = writeProjectionFixture(dir, [validProjRec(1)]);
  const parsed = JSON.parse(fs.readFileSync(man, "utf8"));
  parsed.schema_version = "coa-client-spell-projection-v9";
  fs.writeFileSync(man, JSON.stringify(parsed));
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /bad schema_version/,
  );
});

test("loadAndValidateProjection: missing manifest.counts member throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "nocounts-"));
  const { proj, man } = writeProjectionFixture(dir, [validProjRec(1)]);
  const parsed = JSON.parse(fs.readFileSync(man, "utf8"));
  delete parsed.counts.unique_spell_ids;
  fs.writeFileSync(man, JSON.stringify(parsed));
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /manifest.counts must have integer/,
  );
});

test("loadAndValidateProjection: manifest byte_length disagreeing with the file throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "badlen-"));
  const { proj, man } = writeProjectionFixture(dir, [validProjRec(1)]);
  const parsed = JSON.parse(fs.readFileSync(man, "utf8"));
  parsed.projection.byte_length += 1; // still an integer, but wrong
  fs.writeFileSync(man, JSON.stringify(parsed));
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /byte_length mismatch/,
  );
});

test("buildMechanicsArtifact: absent projection without flag fails closed (writes nothing)", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mech-"));
  assert.throws(() => buildMechanicsArtifact({
    entries: [{ spell_id: 1, entry_id: 1, entry_type: "Ability", name: "X" }],
    spellRows: [], projectionPath: "/no.jsonl", manifestPath: "/no.json", outDir: dir, allowFallback: false,
  }), /projection/i);
  assert.equal(fs.existsSync(path.join(dir, "coa_mechanics.jsonl")), false);
});

test("buildMechanicsArtifact: absent projection + fallback writes degraded, canonical:false", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mech-"));
  const out = buildMechanicsArtifact({
    entries: [{ spell_id: 1, entry_id: 1, entry_type: "Ability", name: "X", damage_schools: [], resources: [] }],
    spellRows: [], projectionPath: "/no.jsonl", manifestPath: "/no.json", outDir: dir, allowFallback: true,
  });
  assert.equal(out.canonical, false);
  assert.equal(fs.existsSync(path.join(dir, "coa_mechanics.fallback.jsonl")), true);
  const man = JSON.parse(fs.readFileSync(path.join(dir, "coa_mechanics.fallback.manifest.json"), "utf8"));
  assert.equal(man.canonical, false);
  assert.equal(man.client_source, "absent");
  assert.equal(man.reconciler_commit, null);
  assert.equal(man.client_build, null);
  assert.equal(typeof man.counts.omitted_fields, "number");
});

test("acceptance: manifest binds the EXACT generated projection sha; canonical true", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "acc-"));
  const { proj, man } = writeProjectionFixture(dir, [validProjRec(42)]);
  const projSha = crypto.createHash("sha256").update(fs.readFileSync(proj)).digest("hex");
  const out = buildMechanicsArtifact({
    entries: [{ spell_id: 42, entry_id: 1, entry_type: "Ability", name: "S42", damage_schools: [], resources: [] }],
    spellRows: [], projectionPath: proj, manifestPath: man, outDir: dir, allowFallback: false,
    inputs: { projection_path: proj, projection_manifest_path: man, reconciler_commit: "deadbeef" },
  });
  assert.equal(out.canonical, true);
  assert.equal(out.manifest.inputs.projection.sha256, projSha);
  assert.equal(out.manifest.coverage.builder_missing_from_projection, 0);
  assert.equal(out.manifest.reconciler_commit, "deadbeef");
  assert.equal(out.manifest.client_build, "test-client-build");
  const c = out.manifest.counts;
  for (const k of ["unresolved_conflicts", "ineligible_candidates", "omitted_fields", "kind_disagreements"]) {
    assert.equal(typeof c[k], "number", `counts.${k} must be an integer`);
  }
});

test("acceptance: fallback does NOT modify a pre-existing canonical artifact", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "acc2-"));
  const canonical = path.join(dir, "coa_mechanics.jsonl");
  fs.writeFileSync(canonical, "SENTINEL-CANONICAL\n");
  buildMechanicsArtifact({
    entries: [{ spell_id: 1, entry_id: 1, entry_type: "Ability", name: "X", damage_schools: [], resources: [] }],
    spellRows: [], projectionPath: "/no.jsonl", manifestPath: "/no.json", outDir: dir, allowFallback: true,
  });
  assert.equal(fs.readFileSync(canonical, "utf8"), "SENTINEL-CANONICAL\n"); // untouched
  assert.equal(fs.existsSync(path.join(dir, "coa_mechanics.fallback.jsonl")), true);
});

test("acceptance: a canonical build emits no ascension_db provenance (DB removed)", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "acc3-"));
  const rec = validProjRec(7);
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  buildMechanicsArtifact({
    entries: [{ spell_id: 7, entry_id: 1, entry_type: "Ability", name: "S7", damage_schools: [], resources: [] }],
    spellRows: [], projectionPath: proj, manifestPath: man, outDir: dir, allowFallback: false,
  });
  const row = JSON.parse(fs.readFileSync(path.join(dir, "coa_mechanics.jsonl"), "utf8").trim());
  assert.equal(row.cooldown_ms ?? null, null);
  assert.equal(row.gcd_ms ?? null, null);
  assert.equal(row.costs ?? null, null);
  assert(!row.provenance.some((p) => p.source === "ascension_db"));
});

test("acceptance: kind_disagreements counts a real Builder kind disagreement (Ability vs Talent, no tooltip)", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "acc4-"));
  const { proj, man } = writeProjectionFixture(dir, [validProjRec(100)]);
  // No db row and no builder description_text → tooltipText is "". "Ability" classifies as "ability";
  // "Talent" with no cast/deals/heals tooltip match classifies as "passive" (classifyMechanicKind's
  // first branch) → the two nodes disagree on kind and resolveKind records
  // REASON.KIND_NODE_DISAGREEMENT_RESOLVED for the row's kind field.
  const entryA = { spell_id: 100, entry_id: 1, entry_type: "Ability", name: "S100", damage_schools: [], resources: [] };
  const entryB = { spell_id: 100, entry_id: 2, entry_type: "Talent", name: "S100", damage_schools: [], resources: [] };
  const out = buildMechanicsArtifact({
    entries: [entryA, entryB],
    spellRows: [], projectionPath: proj, manifestPath: man, outDir: dir, allowFallback: false,
  });
  assert.equal(out.manifest.counts.kind_disagreements, 1);
});

// --- M1.14E0 Task 7: transactional generation resolver (Node parity with the Python resolver) ---
function writeGenerationFixture(root, projRecords) {
  const genId = "aabbccddeeff00112233445566778899";
  const genDir = path.join(root, `gen-${genId}`);
  fs.mkdirSync(genDir, { recursive: true });
  const projBody = projRecords.map((r) => JSON.stringify(r)).join("\n") + (projRecords.length ? "\n" : "");
  const projSha = crypto.createHash("sha256").update(projBody).digest("hex");
  fs.writeFileSync(path.join(genDir, "coa_client_spell_coa.jsonl"), projBody);
  const projManifest = {
    schema_version: "coa-client-spell-projection-v2",
    projection: { path: "coa_client_spell_coa.jsonl", sha256: projSha, byte_length: Buffer.byteLength(projBody) },
    counts: { projected_records: projRecords.length, unique_spell_ids: new Set(projRecords.map((r) => r.spell_id)).size, source_records: projRecords.length },
    client_build: "3.3.5a+patch-CZZ",
  };
  const pmBody = JSON.stringify(projManifest, null, 2) + "\n";
  const pmSha = crypto.createHash("sha256").update(pmBody).digest("hex");
  fs.writeFileSync(path.join(genDir, "coa_client_spell_projection.manifest.json"), pmBody);
  const children = {
    "coa_client_spell_coa.jsonl": { sha256: projSha, byte_length: Buffer.byteLength(projBody), records: projRecords.length, schema_version: "coa-client-spell-v2" },
    "coa_client_spell_projection.manifest.json": { sha256: pmSha, byte_length: Buffer.byteLength(pmBody), records: 1, schema_version: "coa-client-spell-projection-v2" },
  };
  const manifest = { schema_version: "coa-client-extract-manifest-v2", generation_id: genId, published_at: 1, predecessor_generation_id: null, children, outputs: {}, unknown_symbol_inventory: { power_type: [], school_bits: [] }, binding: {} };
  const mBody = JSON.stringify(manifest, null, 2) + "\n";
  const mSha = crypto.createHash("sha256").update(mBody).digest("hex");
  fs.writeFileSync(path.join(genDir, "manifest.json"), mBody);
  const pointer = { schema_version: "coa-client-extract-pointer-v1", generation_id: genId, manifest_path: `gen-${genId}/manifest.json`, manifest_sha256: mSha };
  fs.writeFileSync(path.join(root, "coa_client_extract.pointer.json"), JSON.stringify(pointer, null, 2) + "\n");
  return { genDir, genId };
}

test("resolveGeneration: validates and returns child paths", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "gen-"));
  writeGenerationFixture(dir, [validProjRec(1)]);
  const r = resolveGeneration(dir);
  assert.equal(r.generationId, "aabbccddeeff00112233445566778899");
  assert.ok(r.children["coa_client_spell_coa.jsonl"].endsWith("coa_client_spell_coa.jsonl"));
  assert.ok(fs.existsSync(r.children["coa_client_spell_projection.manifest.json"]));
});

test("resolveGeneration: manifest hash tamper fails closed", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "gentamper-"));
  const { genDir } = writeGenerationFixture(dir, [validProjRec(1)]);
  fs.appendFileSync(path.join(genDir, "manifest.json"), "  ");
  assert.throws(() => resolveGeneration(dir), /manifest sha256 does not match/);
});

test("resolveGeneration: a tampered child fails closed", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "genchild-"));
  const { genDir } = writeGenerationFixture(dir, [validProjRec(1)]);
  fs.writeFileSync(path.join(genDir, "coa_client_spell_coa.jsonl"), '{"schema_version":"coa-client-spell-v2","spell_id":999}\n');
  assert.throws(() => resolveGeneration(dir), /sha256 mismatch/);
});

test("build via resolved generation pointer produces a canonical mechanics row", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "genbuild-"));
  writeGenerationFixture(dir, [validProjRec(92117)]);
  const resolved = resolveGeneration(dir);
  const out = buildMechanicsArtifact({
    entries: [{ spell_id: 92117, entry_id: 1, entry_type: "Ability", name: "S92117", damage_schools: [], resources: [] }],
    spellRows: [], projectionPath: resolved.children["coa_client_spell_coa.jsonl"],
    manifestPath: resolved.children["coa_client_spell_projection.manifest.json"], outDir: dir, allowFallback: false,
  });
  assert.equal(out.canonical, true);
});
