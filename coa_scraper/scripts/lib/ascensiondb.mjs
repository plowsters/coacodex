import fs from "node:fs";
import path from "node:path";

// readJsonl/writeJsonl/normalizeName now live in the AscensionDB-independent jsonl.mjs; imported (for
// this module's own internal use) and re-exported so callers keep a stable import surface.
import { readJsonl, writeJsonl, normalizeName } from "./jsonl.mjs";
export { readJsonl, writeJsonl, normalizeName };

const DB_HOST = "https://db.ascension.gg";

export function powerUrl(kind, id) {
  if (kind !== "spell" && kind !== "item") {
    throw new Error(`Unsupported AscensionDB kind: ${kind}`);
  }
  return `${DB_HOST}/?${kind}=${id}&power`;
}

export function stripTooltipHtml(html) {
  return String(html || "")
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&#x27;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

export function htmlToText(html) {
  return stripTooltipHtml(html);
}

export function extractLinkedIds(html, kind) {
  const rx = new RegExp(`href=["']\\?${kind}=(\\d+)["']`, "g");
  const ids = [];
  for (const match of String(html || "").matchAll(rx)) {
    const id = Number(match[1]);
    if (Number.isFinite(id) && !ids.includes(id)) {
      ids.push(id);
    }
  }
  return ids;
}

export function extractTooltipLevel(text) {
  const match = String(text || "").match(/\bLevel\s+(\d+)\b/i);
  return match ? Number(match[1]) : null;
}

export function parseRequiredLevel(text) {
  const value = String(text || "");
  const required = value.match(/\bRequires Level\s+(\d+)\b/i);
  if (required) {
    return Number(required[1]);
  }
  return extractTooltipLevel(value);
}

export function parseCooldownMs(text) {
  const match = String(text || "").match(/\b(\d+(?:\.\d+)?)\s*(sec|secs|second|seconds|min|mins|minute|minutes)\s+cooldown\b/i);
  return match ? durationToMs(match[1], match[2]) : null;
}

export function parseGcdMs(text) {
  const match = String(text || "").match(/\b(\d+(?:\.\d+)?)\s*(sec|secs|second|seconds)\s+global cooldown\b/i);
  return match ? durationToMs(match[1], match[2]) : null;
}

export function parseCastTimeMs(text) {
  const value = String(text || "");
  if (/\bInstant\b/i.test(value)) {
    return 0;
  }
  const match = value.match(/\b(\d+(?:\.\d+)?)\s*(sec|secs|second|seconds)\s+cast\b/i);
  return match ? durationToMs(match[1], match[2]) : null;
}

export function parseRangeYards(text) {
  const match = String(text || "").match(/\b(\d+(?:\.\d+)?)\s*yd\s+range\b/i);
  return match ? Number(match[1]) : null;
}

export function parseDurationMs(text) {
  const value = String(text || "");
  const match = value.match(/\b(?:lasts|over|for)\s+(\d+(?:\.\d+)?)\s*(sec|secs|second|seconds|min|mins|minute|minutes)\b/i);
  return match ? durationToMs(match[1], match[2]) : null;
}

export function parsePeriodMs(text) {
  const match = String(text || "").match(/\bevery\s+(\d+(?:\.\d+)?)\s*(sec|secs|second|seconds)\b/i);
  return match ? durationToMs(match[1], match[2]) : null;
}

export function parsePowerCosts(text) {
  const costs = [];
  const rx = /\bCosts?\s+(\d+(?:\.\d+)?)\s+([A-Za-z][A-Za-z ]*?)(?=\s+(?:and|to|for|when|if|Deals|Heals|Restores|Lasts|over|every|Requires|$)|[.,;]|$)/gi;
  for (const match of String(text || "").matchAll(rx)) {
    const amount = Number(match[1]);
    const resource = normalizeResourceName(match[2]);
    if (Number.isFinite(amount) && resource) {
      costs.push({ amount, resource });
    }
  }
  return costs;
}

export function parseItemClass(text) {
  const value = String(text || "");
  const lower = value.toLowerCase();
  const weaponMatch = lower.match(/\b(one-hand|two-hand|main hand|off hand|ranged)\s+(sword|axe|mace|dagger|staff|polearm|bow|crossbow|gun|wand|fist weapon)\b/i);
  if (weaponMatch) {
    const weaponType = weaponMatch[2].toLowerCase().replace(/\s+/g, "_");
    return {
      inventory_type: inventoryTypeFromWeaponPrefix(weaponMatch[1]),
      item_class: "weapon",
      item_subclass: weaponType,
      weapon_type: weaponType,
      armor_type: null
    };
  }

  const armorMatch = lower.match(/\b(cloth|leather|mail|plate)\s+(head|neck|shoulder|chest|wrist|hands|waist|legs|feet|finger|trinket|back|shield)\b/i);
  if (armorMatch) {
    return {
      inventory_type: armorMatch[2].toLowerCase(),
      item_class: "armor",
      item_subclass: armorMatch[1].toLowerCase(),
      weapon_type: null,
      armor_type: armorMatch[1].toLowerCase()
    };
  }

  return {
    inventory_type: null,
    item_class: null,
    item_subclass: null,
    weapon_type: null,
    armor_type: null
  };
}

export function parseStats(text) {
  const stats = [];
  const rx = /\+(\d+)\s+(Critical Strike|Attack Power|Spell Power|Strength|Agility|Stamina|Intellect|Spirit|Haste|Mastery|Versatility|Armor)\b/gi;
  for (const match of String(text || "").matchAll(rx)) {
    stats.push({
      stat: match[2].toLowerCase().replace(/\s+/g, "_"),
      value: Number(match[1])
    });
  }
  return stats;
}

function parseRegisterCall(payload, expectedKind, expectedId) {
  const kindName = expectedKind === "spell" ? "registerSpell" : "registerItem";
  const rx = new RegExp(`\\$WowheadPower\\.${kindName}\\((\\d+),\\s*(\\d+),\\s*([\\s\\S]*)\\);\\s*$`);
  const match = String(payload || "").trim().match(rx);
  if (!match) {
    return null;
  }

  const id = Number(match[1]);
  if (id !== Number(expectedId)) {
    throw new Error(`AscensionDB payload id ${id} did not match requested id ${expectedId}`);
  }

  return JSON.parse(match[3]);
}

export function parsePowerPayload(payload, { kind, id, url, fetchedAt = new Date().toISOString() }) {
  let data;
  try {
    data = parseRegisterCall(payload, kind, id);
  } catch (error) {
    return emptyPowerRow({
      kind,
      id,
      status: "parse_failed",
      url,
      fetchedAt,
      raw: String(payload || ""),
      warnings: [`parse_failed:${String(error.message || error)}`]
    });
  }

  if (data === null) {
    const kindName = kind === "spell" ? "registerSpell" : "registerItem";
    const status = String(payload || "").includes(`$WowheadPower.${kindName}`)
      ? "parse_failed"
      : "not_found";
    return emptyPowerRow({
      kind,
      id,
      status,
      url,
      fetchedAt,
      raw: String(payload || ""),
      warnings: status === "parse_failed" ? ["parse_failed:registration_call_malformed"] : []
    });
  }

  if (Object.keys(data).length === 0) {
    return emptyPowerRow({
      kind,
      id,
      status: "empty_registration",
      url,
      fetchedAt,
      raw: data,
      warnings: []
    });
  }

  const tooltipHtml = data.tooltip_enus || "";
  const tooltipText = stripTooltipHtml(tooltipHtml);
  const tooltipLevel = extractTooltipLevel(tooltipText);
  const requiredLevel = parseRequiredLevel(tooltipText);
  const linkedSpellIds = extractLinkedIds(tooltipHtml, "spell");
  const linkedItemIds = extractLinkedIds(tooltipHtml, "item");
  const itemClass = kind === "item" ? parseItemClass(tooltipText) : {};

  return {
    kind,
    id,
    status: "matched",
    name: data.name_enus || null,
    icon: data.icon || null,
    quality: data.quality ?? null,
    tooltip_html: tooltipHtml,
    tooltip_text: tooltipText,
    tooltip_level: tooltipLevel,
    required_level: requiredLevel,
    cooldown_ms: parseCooldownMs(tooltipText),
    gcd_ms: parseGcdMs(tooltipText),
    cast_time_ms: parseCastTimeMs(tooltipText),
    range_yards: parseRangeYards(tooltipText),
    duration_ms: parseDurationMs(tooltipText),
    period_ms: parsePeriodMs(tooltipText),
    power_costs: parsePowerCosts(tooltipText),
    mechanic_tags: inferMechanicTags(tooltipText),
    inventory_type: itemClass.inventory_type ?? null,
    item_class: itemClass.item_class ?? null,
    item_subclass: itemClass.item_subclass ?? null,
    weapon_type: itemClass.weapon_type ?? null,
    armor_type: itemClass.armor_type ?? null,
    stats: kind === "item" ? parseStats(tooltipText) : [],
    effects: kind === "item" ? linkedSpellIds.map(spellId => ({ effect_type: "use", spell_id: spellId })) : [],
    linked_spell_ids: linkedSpellIds,
    linked_item_ids: linkedItemIds,
    buff_tooltip_html: data.buff_enus || "",
    warnings: [],
    raw: data,
    provenance: { url, fetched_at: fetchedAt }
  };
}

export const parseAscensionDbPayload = parsePowerPayload;

function emptyPowerRow({
  kind,
  id,
  status,
  url,
  fetchedAt,
  raw,
  warnings = []
}) {
  return {
    kind,
    id,
    status,
    name: null,
    icon: null,
    quality: null,
    tooltip_html: "",
    tooltip_text: "",
    tooltip_level: null,
    required_level: null,
    cooldown_ms: null,
    gcd_ms: null,
    cast_time_ms: null,
    range_yards: null,
    duration_ms: null,
    period_ms: null,
    power_costs: [],
    mechanic_tags: [],
    inventory_type: null,
    item_class: null,
    item_subclass: null,
    weapon_type: null,
    armor_type: null,
    stats: [],
    effects: [],
    linked_spell_ids: [],
    linked_item_ids: [],
    buff_tooltip_html: "",
    warnings,
    raw,
    provenance: { url, fetched_at: fetchedAt }
  };
}

function durationToMs(amount, unit) {
  const value = Number(amount);
  if (!Number.isFinite(value)) {
    return null;
  }
  return Math.round(value * (String(unit || "").toLowerCase().startsWith("min") ? 60000 : 1000));
}

function normalizeResourceName(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b[a-z]/g, char => char.toUpperCase());
}

function inventoryTypeFromWeaponPrefix(prefix) {
  const normalized = String(prefix || "").toLowerCase();
  if (normalized === "one-hand") {
    return "one_hand";
  }
  if (normalized === "two-hand") {
    return "two_hand";
  }
  if (normalized === "main hand") {
    return "main_hand";
  }
  if (normalized === "off hand") {
    return "off_hand";
  }
  return normalized.replace(/\s+/g, "_");
}

function inferMechanicTags(text) {
  const value = String(text || "");
  const tags = new Set();
  if (/\bdamage\b/i.test(value)) {
    tags.add("damage");
  }
  if (/\bheal|healing|restore[s]?\s+health\b/i.test(value)) {
    tags.add("heal");
  }
  if (/\bover\s+\d|every\s+\d/i.test(value) && /\bdamage|poison|bleed|burn|disease\b/i.test(value)) {
    tags.add("dot");
  }
  if (/\bover\s+\d|every\s+\d/i.test(value) && /\bheal|restore[s]?\s+health\b/i.test(value)) {
    tags.add("hot");
  }
  if (/\bcooldown\b/i.test(value)) {
    tags.add("cooldown");
  }
  if (/\bsummon|pet|minion\b/i.test(value)) {
    tags.add("summon");
  }
  if (/\bstun|silence|root|snare|slow\b/i.test(value)) {
    tags.add("crowd_control");
  }
  return [...tags].sort();
}

export function uniqueSpellIds(entries) {
  return [
    ...new Set(entries.map(entry => Number(entry.spell_id)).filter(Number.isFinite))
  ].sort((a, b) => a - b);
}

function uniqueItemIds(entries) {
  return [
    ...new Set(entries.map(entry => Number(entry.item_id)).filter(Number.isFinite))
  ].sort((a, b) => a - b);
}

export async function buildEnrichmentRows({
  entries,
  kind,
  fetchPower,
  concurrency = 8,
  fetchedAt = new Date().toISOString()
}) {
  const idField = kind === "spell" ? "spell_id" : "item_id";
  const ids = kind === "spell" ? uniqueSpellIds(entries) : uniqueItemIds(entries);
  const byId = new Map(entries.map(entry => [Number(entry[idField]), entry]));

  return mapWithConcurrency(ids, concurrency, async id => {
    const url = powerUrl(kind, id);
    let parsed;

    try {
      const payload = await fetchPower({ kind, id, url });
      parsed = parsePowerPayload(payload, { kind, id, url, fetchedAt });
    } catch (error) {
      parsed = {
        kind,
        id,
        status: "fetch_failed",
        name: null,
        icon: null,
        tooltip_html: "",
        tooltip_text: "",
        tooltip_level: null,
        required_level: null,
        linked_spell_ids: [],
        linked_item_ids: [],
        raw: String(error.message || error),
        provenance: { url, fetched_at: fetchedAt }
      };
    }

    const entry = byId.get(id);
    const nameMatch = Boolean(
      parsed.name && entry && normalizeName(parsed.name) === normalizeName(entry.name)
    );

    return {
      ...parsed,
      entry_id: entry?.entry_id ?? null,
      builder_name: entry?.name ?? null,
      name_match: nameMatch
    };
  });
}

export async function mapWithConcurrency(items, concurrency, mapper) {
  const limit = Math.max(1, Math.floor(Number(concurrency) || 1));
  const results = new Array(items.length);
  let nextIndex = 0;

  async function worker() {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex++;
      results[index] = await mapper(items[index], index);
    }
  }

  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, () => worker()));
  return results;
}

export async function fetchTextWithTimeout(url, {
  fetchImpl = fetch,
  timeoutMs = 15000
} = {}) {
  const controller = new AbortController();
  const timer = timeoutMs > 0
    ? setTimeout(() => controller.abort(), timeoutMs)
    : null;

  try {
    const response = await fetchImpl(url, { signal: controller.signal });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status} for ${url}`);
    }
    return response.text();
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

export async function fetchText(url, options = {}) {
  return fetchTextWithTimeout(url, options);
}
