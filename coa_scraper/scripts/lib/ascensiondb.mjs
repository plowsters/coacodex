import fs from "node:fs";
import path from "node:path";

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
  const data = parseRegisterCall(payload, kind, id);
  if (data === null) {
    return {
      kind,
      id,
      status: "not_found",
      name: null,
      icon: null,
      tooltip_html: "",
      tooltip_text: "",
      tooltip_level: null,
      required_level: null,
      linked_spell_ids: [],
      linked_item_ids: [],
      raw: String(payload || ""),
      provenance: { url, fetched_at: fetchedAt }
    };
  }

  if (Object.keys(data).length === 0) {
    return {
      kind,
      id,
      status: "empty_registration",
      name: null,
      icon: null,
      tooltip_html: "",
      tooltip_text: "",
      tooltip_level: null,
      required_level: null,
      linked_spell_ids: [],
      linked_item_ids: [],
      raw: data,
      provenance: { url, fetched_at: fetchedAt }
    };
  }

  const tooltipHtml = data.tooltip_enus || "";
  const tooltipText = stripTooltipHtml(tooltipHtml);
  const tooltipLevel = extractTooltipLevel(tooltipText);
  const requiredLevelMatch = tooltipText.match(/\bRequires Level\s+(\d+)\b/i);

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
    required_level: requiredLevelMatch ? Number(requiredLevelMatch[1]) : tooltipLevel,
    linked_spell_ids: extractLinkedIds(tooltipHtml, "spell"),
    linked_item_ids: extractLinkedIds(tooltipHtml, "item"),
    buff_tooltip_html: data.buff_enus || "",
    raw: data,
    provenance: { url, fetched_at: fetchedAt }
  };
}

export function readJsonl(filePath) {
  if (!fs.existsSync(filePath)) {
    return [];
  }
  const text = fs.readFileSync(filePath, "utf8").trim();
  if (!text) {
    return [];
  }
  return text.split("\n").filter(Boolean).map(line => JSON.parse(line));
}

export function writeJsonl(filePath, rows) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${rows.map(row => JSON.stringify(row)).join("\n")}\n`);
}

export function normalizeName(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
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
