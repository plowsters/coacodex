#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { readJsonl, writeJsonl } from "./lib/ascensiondb.mjs";
import { sourceUrls } from "./build-mechanics-artifacts.mjs";

const ITEM_SCHEMA_VERSION = "coa-item-v1";

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
          parser: "build-item-artifacts",
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

function isCliEntryPoint() {
  return process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);
}

if (isCliEntryPoint()) {
  const itemRowsPath = process.argv[2] || "dist/coa_db_item_tooltips.jsonl";
  const distDir = process.argv[3] || "dist";
  const itemPayloadRows = readJsonl(itemRowsPath);
  const itemRows = buildItemRows({ itemPayloadRows });
  fs.mkdirSync(distDir, { recursive: true });
  writeJsonl(path.join(distDir, "coa_items.jsonl"), itemRows);
  console.log(`Wrote ${itemRows.length} items`);
}
