#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { readJsonl, writeJsonl } from "./lib/ascensiondb.mjs";
import { writeJson } from "./lib/artifacts.mjs";

const MECHANICS_SCHEMA_VERSION = "coa-mechanics-v1";
const ITEM_SCHEMA_VERSION = "coa-item-v1";

export function buildMechanicsRows({ entries, spellRows }) {
  const spellById = new Map(spellRows.map(row => [Number(row.spell_id ?? row.id), row]));
  return entries
    .filter(entry => Number.isFinite(Number(entry.spell_id)))
    .map(entry => {
      const spellRow = spellById.get(Number(entry.spell_id)) || entry.db_enrichment || null;
      const tooltipText = spellRow?.tooltip_text || entry.description_text || "";
      const effects = inferEffects({ entry, tooltipText, spellRow });
      const dbMatched = spellRow?.status === "matched";
      return {
        schema_version: MECHANICS_SCHEMA_VERSION,
        spell_id: Number(entry.spell_id),
        name: spellRow?.name || entry.name || "",
        kind: classifyMechanicKind(entry, tooltipText),
        source_node_ids: [Number(entry.entry_id)].filter(Number.isFinite),
        source_urls: sourceUrls(spellRow),
        school: firstValue(entry.damage_schools),
        power_type: firstValue(entry.resources),
        costs: costsObject(spellRow?.power_costs),
        generates: {},
        spends: {},
        cooldown_ms: numberOrNull(spellRow?.cooldown_ms),
        gcd_ms: numberOrNull(spellRow?.gcd_ms),
        cast_time_ms: numberOrNull(spellRow?.cast_time_ms),
        range_yards: numberOrNull(spellRow?.range_yards),
        effects,
        provenance: [
          {
            source: dbMatched ? "ascension_db" : "builder",
            source_id: `spell:${Number(entry.spell_id)}`,
            source_url: sourceUrls(spellRow)[0] || "",
            parser: "build-mechanics-artifacts",
            confidence: dbMatched ? "medium" : "low",
            notes: [
              ...(dbMatched ? ["derived_from_ascensiondb_tooltip"] : ["derived_from_builder_node"]),
              ...((spellRow?.warnings || []).map(warning => `db_warning:${warning}`))
            ]
          }
        ],
        confidence: dbMatched ? "medium" : "low",
        raw: {
          entry_id: entry.entry_id,
          db_status: spellRow?.status || null,
          linked_spell_ids: spellRow?.linked_spell_ids || [],
          linked_item_ids: spellRow?.linked_item_ids || []
        }
      };
    });
}

export function buildItemRows({ itemPayloadRows }) {
  return itemPayloadRows
    .filter(row => row.status === "matched")
    .map(row => ({
      schema_version: ITEM_SCHEMA_VERSION,
      item_id: Number(row.item_id ?? row.id),
      name: row.name || "",
      icon: row.icon || "",
      icon_asset_path: row.icon_asset_path || null,
      quality: row.quality ?? null,
      slot: row.inventory_type || inferItemSlot(row.tooltip_text),
      item_class: row.item_class || inferItemClass(row.tooltip_text),
      subclass: row.item_subclass || "",
      weapon_type: row.weapon_type || inferWeaponType(row.tooltip_text),
      armor_type: row.armor_type || inferArmorType(row.tooltip_text),
      stats: statsObject(row.stats),
      ratings: {},
      speed: null,
      min_damage: null,
      max_damage: null,
      spell_power: null,
      attack_power: null,
      required_level: row.required_level,
      linked_spell_ids: row.linked_spell_ids || [],
      linked_item_ids: row.linked_item_ids || [],
      tooltip_text: row.tooltip_text || "",
      source_urls: sourceUrls(row),
      provenance: [
        {
          source: "ascension_db",
          source_id: `item:${Number(row.item_id ?? row.id)}`,
          source_url: sourceUrls(row)[0] || "",
          parser: "build-mechanics-artifacts",
          confidence: "medium",
          notes: (row.warnings || []).map(warning => `db_warning:${warning}`)
        }
      ],
      confidence: "medium",
      raw: {
        status: row.status,
        fetched_at: row?.provenance?.fetched_at || null
      }
    }));
}

export function summarizeMechanicsArtifacts({ mechanicsRows, itemRows }) {
  const kinds = countBy(mechanicsRows, row => row.kind);
  const confidence = countBy(mechanicsRows, row => row.confidence);
  return {
    schema_version: "coa-mechanics-artifact-summary-v1",
    generated_at: new Date().toISOString(),
    mechanics_count: mechanicsRows.length,
    item_count: itemRows.length,
    mechanic_kind_counts: kinds,
    mechanic_confidence_counts: confidence
  };
}

function inferEffects({ entry, tooltipText, spellRow }) {
  const tags = entry.tags || [];
  const school = firstValue(entry.damage_schools) || inferSchool(tooltipText);
  const durationMs = numberOrNull(spellRow?.duration_ms) ?? inferDurationMs(tooltipText);
  const periodMs = numberOrNull(spellRow?.period_ms);
  const amount = inferAmount(tooltipText);
  if (tags.includes("heal") || /\bheal/i.test(tooltipText)) {
    return [
      {
        effect_type: "heal",
        school,
        target: "ally",
        amount,
        duration_ms: durationMs,
        period_ms: periodMs,
        tags: tags.filter(Boolean)
      }
    ];
  }
  if (tags.includes("summon") || /\bsummon|companion|pet\b/i.test(tooltipText)) {
    return [
      {
        effect_type: "summon",
        target: "self",
        duration_ms: durationMs,
        period_ms: periodMs,
        tags: tags.filter(Boolean)
      }
    ];
  }
  if (tags.includes("aura") || tags.includes("cooldown") || /\bbuff|aura|increases?\b/i.test(tooltipText)) {
    return [
      {
        effect_type: "aura_apply",
        target: "self",
        duration_ms: durationMs,
        period_ms: periodMs,
        tags: tags.filter(Boolean)
      }
    ];
  }
  if (tags.includes("dot") || entry.damage_schools?.length || /\bdamage\b/i.test(tooltipText)) {
    return [
      {
        effect_type: "damage",
        school,
        target: "enemy",
        amount,
        duration_ms: durationMs,
        period_ms: periodMs,
        tags: tags.filter(Boolean)
      }
    ];
  }
  return [];
}

function classifyMechanicKind(entry, tooltipText) {
  const tags = entry.tags || [];
  if (entry.is_passive || entry.entry_type === "Talent" && !/\bcast|deals?|heals?\b/i.test(tooltipText)) {
    return "passive";
  }
  if (tags.includes("summon")) {
    return "pet_action";
  }
  if (tags.includes("dot")) {
    return "debuff";
  }
  if (tags.includes("cooldown")) {
    return "cooldown";
  }
  return "ability";
}

function inferDurationMs(text) {
  const match = String(text || "").match(/\b(?:over|for|lasts?)\s+(\d+(?:\.\d+)?)\s*(sec|second|seconds|s)\b/i);
  return match ? Math.round(Number(match[1]) * 1000) : null;
}

function inferAmount(text) {
  const match = String(text || "").match(/\b(\d+(?:\.\d+)?)\s+(?:[A-Za-z]+\s+)?(?:damage|healing|health|heal)\b/i);
  return match ? Number(match[1]) : null;
}

function inferSchool(text) {
  const match = String(text || "").match(/\b(arcane|fire|frost|holy|nature|physical|shadow|fel)\b/i);
  return match ? match[1].toLowerCase() : "";
}

function inferItemSlot(text) {
  const lower = String(text || "").toLowerCase();
  if (lower.includes("boots")) return "feet";
  if (lower.includes("gloves")) return "hands";
  if (lower.includes("helm")) return "head";
  if (lower.includes("chest")) return "chest";
  return "";
}

function inferItemClass(text) {
  const lower = String(text || "").toLowerCase();
  if (/\baxe|sword|mace|dagger|staff|bow|gun|wand\b/.test(lower)) return "weapon";
  if (/\bcloth|leather|mail|plate|boots|gloves|helm|chest\b/.test(lower)) return "armor";
  return "";
}

function inferWeaponType(text) {
  const match = String(text || "").match(/\b(axe|sword|mace|dagger|staff|bow|gun|wand)\b/i);
  return match ? match[1].toLowerCase() : "";
}

function inferArmorType(text) {
  const match = String(text || "").match(/\b(cloth|leather|mail|plate)\b/i);
  return match ? match[1].toLowerCase() : "";
}

function firstValue(values) {
  return Array.isArray(values) && values.length ? String(values[0]) : "";
}

function costsObject(costs) {
  const output = {};
  for (const item of costs || []) {
    const resource = item?.resource ? String(item.resource) : "";
    const amount = Number(item?.amount);
    if (resource && Number.isFinite(amount)) {
      output[resource] = amount;
    }
  }
  return output;
}

function statsObject(stats) {
  const output = {};
  for (const item of stats || []) {
    const stat = item?.stat ? String(item.stat) : "";
    const value = Number(item?.value);
    if (stat && Number.isFinite(value)) {
      output[stat] = value;
    }
  }
  return output;
}

function sourceUrls(row) {
  const urls = [
    row?.source_url,
    row?.provenance?.url,
    ...(Array.isArray(row?.source_urls) ? row.source_urls : [])
  ].filter(Boolean);
  return [...new Set(urls)];
}

function numberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function countBy(rows, keyFn) {
  return rows.reduce((acc, row) => {
    const key = keyFn(row) || "unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function isCliEntryPoint() {
  return process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);
}

if (isCliEntryPoint()) {
  const entriesPath = process.argv[2] || "dist/coa_entries.enriched.jsonl";
  const spellRowsPath = process.argv[3] || "dist/coa_db_spell_tooltips.jsonl";
  const distDir = process.argv[4] || "dist";
  const reportsDir = process.argv[5] || "reports";
  const itemRowsPath = process.argv[6] || path.join(distDir, "coa_db_item_tooltips.jsonl");
  const entries = readJsonl(entriesPath);
  const spellRows = readJsonl(spellRowsPath);
  const itemPayloadRows = readJsonl(itemRowsPath);
  const mechanicsRows = buildMechanicsRows({ entries, spellRows });
  const itemRows = buildItemRows({ itemPayloadRows });
  const summary = summarizeMechanicsArtifacts({ mechanicsRows, itemRows });

  fs.mkdirSync(distDir, { recursive: true });
  fs.mkdirSync(reportsDir, { recursive: true });
  writeJsonl(path.join(distDir, "coa_mechanics.jsonl"), mechanicsRows);
  writeJsonl(path.join(distDir, "coa_items.jsonl"), itemRows);
  writeJson(path.join(reportsDir, "coa_mechanics_enrichment_summary.json"), summary);
  console.log(JSON.stringify(summary, null, 2));
}
