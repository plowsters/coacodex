#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const input = process.argv[2] || "reports/coa_builder_payload.json";
const outDir = process.argv[3] || "dist";

fs.mkdirSync(outDir, { recursive: true });
fs.mkdirSync("reports", { recursive: true });

const payload = JSON.parse(fs.readFileSync(input, "utf8"));
const talents = payload.talents || {};
const classes = talents.classes || [];
const entriesByTab = talents.entriesByTab || {};
const essenceByClass = talents.essenceByClass || {};

const stripHtml = s =>
  typeof s === "string"
    ? s
        .replace(/<br\s*\/?>/gi, "\n")
        .replace(/<[^>]+>/g, " ")
        .replace(/&nbsp;/g, " ")
        .replace(/&amp;/g, "&")
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .replace(/&#x27;/g, "'")
        .replace(/\s+/g, " ")
        .trim()
    : null;

const first = (...vals) => {
  for (const v of vals) {
    if (v !== undefined && v !== null && v !== "") return v;
  }
  return null;
};

const getDeep = (obj, paths) => {
  for (const p of paths) {
    let cur = obj;
    let ok = true;

    for (const part of p.split(".")) {
      if (!cur || typeof cur !== "object" || !(part in cur)) {
        ok = false;
        break;
      }
      cur = cur[part];
    }

    if (ok && cur !== undefined && cur !== null && cur !== "") return cur;
  }

  return null;
};

const toNumberOrNull = v => {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v.trim())) {
    return Number(v);
  }
  return null;
};

const discoverNumeric = (entry, names) => {
  for (const name of names) {
    const v = getDeep(entry, [name]);
    const n = toNumberOrNull(v);
    if (n !== null) return n;
  }
  return null;
};

const discoverId = entry =>
  first(
    entry.id,
    entry.entryId,
    entry.entry_id,
    entry.nodeId,
    entry.node_id,
    entry.talentId,
    entry.talent_id,
    entry.spellId,
    entry.spell_id,
    getDeep(entry, ["spell.id", "spell.spellId", "talent.id", "node.id", "entry.id"])
  );

const discoverSpellId = entry =>
  first(
    entry.spellId,
    entry.spell_id,
    getDeep(entry, ["spell.id", "spell.spellId", "talent.spellId", "node.spellId"])
  );

const discoverName = entry =>
  first(
    entry.name,
    entry.title,
    entry.label,
    entry.nodeName,
    entry.talentName,
    entry.spellName,
    getDeep(entry, ["spell.name", "talent.name", "node.name", "entry.name"])
  );

const discoverDescription = entry =>
  first(
    entry.description,
    entry.desc,
    entry.tooltip,
    entry.tooltipHtml,
    entry.html,
    getDeep(entry, ["spell.description", "talent.description", "node.description", "entry.description"])
  );

const discoverIcon = entry =>
  first(
    entry.icon,
    entry.iconPath,
    entry.icon_path,
    entry.texture,
    entry.image,
    getDeep(entry, ["spell.icon", "talent.icon", "node.icon", "entry.icon"])
  );

const flattenEntries = value => {
  if (Array.isArray(value)) return value;
  if (!value || typeof value !== "object") return [];

  for (const key of ["entries", "nodes", "talents", "items", "data", "value"]) {
    if (Array.isArray(value[key])) return value[key];
  }

  return [];
};

const classById = new Map(classes.map(c => [Number(c.classId), c]));

const tabByClassAndTab = new Map();
const tabsById = new Map();

for (const cls of classes) {
  for (const tab of cls.tabs || []) {
    const classId = Number(cls.classId);
    const tabId = Number(tab.tabId);

    const tabRecord = {
      classId,
      className: cls.className,
      tabId,
      tabName: tab.tabName,
      sortOrder: tab.sortOrder
    };

    tabByClassAndTab.set(`${classId}:${tabId}`, tabRecord);

    if (!tabsById.has(tabId)) tabsById.set(tabId, []);
    tabsById.get(tabId).push(tabRecord);
  }
}

const getEntryClassId = entry => {
  const n = Number(first(entry.classId, entry.class_id, entry.ownerClassId, entry.owner_class_id));
  return Number.isFinite(n) ? n : null;
};

const getEntryTabId = entry => {
  const n = Number(first(entry.tabId, entry.tab_id));
  return Number.isFinite(n) ? n : null;
};

const getEssenceKind = entry => {
  const entryType = String(entry.entryType ?? "").toLowerCase();

  if (entryType === "ability") return "ability";
  if (entryType === "talent") return "talent";

  const ae = Number(entry.aeCost ?? 0);
  const te = Number(entry.teCost ?? 0);

  if (ae > 0 && te <= 0) return "ability";
  if (te > 0 && ae <= 0) return "talent";

  return "unknown";
};

const normalizeClass = cls => ({
  class_id: Number(cls.classId),
  class_name: cls.className,
  tabs: (cls.tabs || [])
    .slice()
    .sort((a, b) => (a.sortOrder ?? 0) - (b.sortOrder ?? 0) || a.tabName.localeCompare(b.tabName))
    .map(t => ({
      tab_id: Number(t.tabId),
      tab_name: t.tabName,
      sort_order: t.sortOrder,
      nominal_essence_kind: t.tabName === "Class" ? "ability" : "talent"
    })),
  essence_caps: essenceByClass[String(cls.classId)] || null
});

const detectTags = text => {
  const s = text || "";
  const tags = [];

  const rules = {
    heal: /\bheal|healing|restores? health|mending|regenerat(?:e|es|ing|ion)|absorb\b/i,
    tank: /\btaunt|threat|armor|parry|dodge|block|damage taken|shield|barrier|mitigation|brace\b/i,
    melee: /\bmelee|weapon damage|main-hand|off-hand|strike|slash|cleave|swing|combo\b/i,
    ranged: /\branged weapon|ranged damage|shot|shoot|arrow|bolt|blast|projectile|throw|spear\b/i,
    dot: /\bperiodic damage|damage over|bleed|burn|poison|venom|disease|every \d+ sec/i,
    hot: /\bperiodic healing|healing over|regenerat(?:e|es|ing) .* health/i,
    summon: /\bsummon|animate|minion|pet|construct|wraith|elemental|falcon|hound|ward\b/i,
    crowd_control: /\bstun|root|silence|disorient|incapacitate|fear|slow|freeze|frozen|knock/i,
    mobility: /\bcharge|dash|leap|blink|teleport|movement speed|sprint|rush\b/i,
    stealth: /\bstealth|stealthed|invisible|ambush\b/i,
    execute: /\bbelow 20% health|below 35% health|above 80% health|execute\b/i,
    proc: /\bchance to|whenever|after casting|critical strikes?|resets? the cooldown|your next\b/i,
    cooldown: /\bcooldown|recharge|charges?\b/i,
    builder: /\bgenerates?|restores? .* (Energy|Rage|Insanity|Felfury|Static|Heat|mana)|refunds?|grants?/i,
    spender: /\bcost|spend|spends|consumes?|depletes?|free of cost\b/i,
    aura: /\baura|allies within|party and raid|nearby allies|members\b/i,
    resource_management: /\bEnergy|Rage|Insanity|Felfury|Static|Heat|mana|Fill Level|Advantage\b/i
  };

  for (const [tag, rx] of Object.entries(rules)) {
    if (rx.test(s)) tags.push(tag);
  }

  return tags;
};

const detectSchools = text => {
  const s = text || "";
  const schools = [];

  const rules = {
    physical: /\bPhysical|weapon damage|bleed\b/i,
    fire: /\bFire|flame|burn|ember|pyro|ignite|hellfire|infernal\b/i,
    frost: /\bFrost|ice|rime|freeze|frozen|chill|hodir\b/i,
    shadow: /\bShadow|void|curse|horror|insanity|dark|soul\b/i,
    holy: /\bHoly|light|radiance|bless|vow|seraph|piety\b/i,
    nature: /\bNature|poison|venom|serpent|storm|lightning|earth|primal\b/i,
    arcane: /\bArcane|aether|chrono|time|distortion|rune|rift\b/i,
    fel: /\bFel|felfury|demon|infernal\b/i
  };

  for (const [school, rx] of Object.entries(rules)) {
    if (rx.test(s)) schools.push(school);
  }

  return schools;
};

const detectResources = text => {
  const s = text || "";
  const resources = [];

  const rules = {
    Energy: /\bEnergy\b/i,
    Rage: /\bRage\b/i,
    Insanity: /\bInsanity\b/i,
    Felfury: /\bFelfury\b/i,
    Static: /\bStatic\b/i,
    Heat: /\bHeat\b/i,
    Mana: /\bmana\b/i,
    Advantage: /\bAdvantage\b/i,
    "Fill Level": /\bFill Level\b/i
  };

  for (const [resource, rx] of Object.entries(rules)) {
    if (rx.test(s)) resources.push(resource);
  }

  return resources;
};

const records = [];

for (const [_bucketKey, value] of Object.entries(entriesByTab)) {
  const entries = flattenEntries(value);

  for (const entry of entries) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;

    const entryClassId = getEntryClassId(entry);
    const entryTabId = getEntryTabId(entry);

    const cls = classById.get(entryClassId) || null;
    const ownerTab = tabByClassAndTab.get(`${entryClassId}:${entryTabId}`) || null;

    const kind = getEssenceKind(entry);

    const name = discoverName(entry);
    const rawDescription = discoverDescription(entry);
    const description = stripHtml(rawDescription);
    const combinedText = `${name || ""} ${description || ""}`;

    const aeCost = Number(entry.aeCost ?? 0);
    const teCost = Number(entry.teCost ?? 0);
    const reqTabAE = Number(entry.reqTabAE ?? 0);
    const reqTabTE = Number(entry.reqTabTE ?? 0);

    const rec = {
      build_id: payload.id,
      build_slug: payload.slug,
      build_name: payload.name,

      class_id: entryClassId,
      class_name: cls?.className ?? null,

      tab_id: entryTabId,
      tab_name: ownerTab?.tabName ?? null,
      tab_sort_order: ownerTab?.sortOrder ?? null,

      entry_type: entry.entryType ?? null,
      essence_kind: kind,
      essence_type:
        kind === "ability" ? "abilityEssence" :
        kind === "talent" ? "talentEssence" :
        "unknown",

      entry_id: discoverId(entry),
      spell_id: discoverSpellId(entry),
      spell_ids: Array.isArray(entry.spellIds)
        ? entry.spellIds.filter(Boolean)
        : [],

      name,
      icon: discoverIcon(entry),

      ae_cost: Number.isFinite(aeCost) ? aeCost : 0,
      te_cost: Number.isFinite(teCost) ? teCost : 0,
      required_tab_ae: Number.isFinite(reqTabAE) ? reqTabAE : 0,
      required_tab_te: Number.isFinite(reqTabTE) ? reqTabTE : 0,

      description_html: rawDescription ?? null,
      description_text: description,

      required_level: discoverNumeric(entry, ["requiredLevel", "required_level", "level"]),
      max_rank: discoverNumeric(entry, ["maxPoints", "max_points", "maxRank", "max_rank", "ranks"]),

      row: discoverNumeric(entry, ["y", "row", "position.y", "gridY"]),
      col: discoverNumeric(entry, ["x", "col", "position.x", "gridX"]),

      node_type: entry.nodeType ?? null,
      flags: entry.flags ?? null,
      group: entry.group ?? null,
      is_passive: Boolean(entry.isPassive),
      is_starting_node: Boolean(entry.isStartingNode),

      required_ids: Array.isArray(entry.requiredIds)
        ? entry.requiredIds.filter(Boolean)
        : [],

      connected_node_ids: Array.isArray(entry.connectedNodeIds)
        ? entry.connectedNodeIds.filter(Boolean)
        : [],

      tags: detectTags(combinedText),
      damage_schools: detectSchools(combinedText),
      resources: detectResources(combinedText),

      raw: entry
    };

    records.push(rec);
  }
}

// Deduplicate conservative exact duplicates.
const seen = new Set();
const deduped = [];

for (const r of records) {
  const key = [
    r.class_id ?? "unknown-class",
    r.tab_id ?? "unknown-tab",
    r.essence_kind ?? "unknown-kind",
    r.entry_id ?? "",
    r.spell_id ?? "",
    r.name ?? ""
  ].join("::");

  if (seen.has(key)) continue;
  seen.add(key);
  deduped.push(r);
}

const classesOut = classes.map(normalizeClass);

fs.writeFileSync(
  path.join(outDir, "coa_classes.json"),
  JSON.stringify(classesOut, null, 2)
);

fs.writeFileSync(
  path.join(outDir, "coa_essence_caps.json"),
  JSON.stringify(essenceByClass, null, 2)
);

fs.writeFileSync(
  path.join(outDir, "coa_entries.jsonl"),
  deduped.map(r => JSON.stringify(r)).join("\n") + "\n"
);

fs.writeFileSync(
  path.join(outDir, "coa_entries.pretty.json"),
  JSON.stringify(deduped, null, 2)
);

const byClass = new Map();

for (const r of deduped) {
  const key = r.class_name || "UNKNOWN_CLASS";

  if (!byClass.has(key)) {
    byClass.set(key, {
      class_name: key,
      ability_count: 0,
      talent_count: 0,
      unknown_count: 0,
      tabs: new Map()
    });
  }

  const c = byClass.get(key);

  if (r.essence_kind === "ability") c.ability_count++;
  else if (r.essence_kind === "talent") c.talent_count++;
  else c.unknown_count++;

  const tabKey = `${r.tab_id}:${r.tab_name}`;
  c.tabs.set(tabKey, (c.tabs.get(tabKey) || 0) + 1);
}

const missingClass = deduped.filter(r => !r.class_name);
const missingTab = deduped.filter(r => !r.tab_name);
const unknownKind = deduped.filter(r => r.essence_kind === "unknown");

const reportLines = [];

reportLines.push("===== CoA normalized export report =====");
reportLines.push(`Builder: ${payload.name} (${payload.slug})`);
reportLines.push(`Classes: ${classes.length}`);
reportLines.push(`Raw records: ${records.length}`);
reportLines.push(`Deduped records: ${deduped.length}`);
reportLines.push(`Missing class records: ${missingClass.length}`);
reportLines.push(`Missing tab records: ${missingTab.length}`);
reportLines.push(`Unknown essence-kind records: ${unknownKind.length}`);
reportLines.push("");

for (const c of [...byClass.values()].sort((a, b) => a.class_name.localeCompare(b.class_name))) {
  reportLines.push(`${c.class_name}`);
  reportLines.push(`  ability: ${c.ability_count}`);
  reportLines.push(`  talent: ${c.talent_count}`);
  reportLines.push(`  unknown: ${c.unknown_count}`);

  for (const [tab, count] of [...c.tabs.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    reportLines.push(`  ${tab}: ${count}`);
  }

  reportLines.push("");
}

if (missingClass.length) {
  reportLines.push("===== missing class samples =====");
  for (const r of missingClass.slice(0, 50)) {
    reportLines.push(JSON.stringify({
      class_id: r.class_id,
      tab_id: r.tab_id,
      tab_name: r.tab_name,
      entry_type: r.entry_type,
      essence_kind: r.essence_kind,
      entry_id: r.entry_id,
      spell_id: r.spell_id,
      name: r.name
    }));
  }
  reportLines.push("");
}

if (missingTab.length) {
  reportLines.push("===== missing tab samples =====");
  for (const r of missingTab.slice(0, 50)) {
    reportLines.push(JSON.stringify({
      class_id: r.class_id,
      class_name: r.class_name,
      tab_id: r.tab_id,
      entry_type: r.entry_type,
      essence_kind: r.essence_kind,
      entry_id: r.entry_id,
      spell_id: r.spell_id,
      name: r.name
    }));
  }
  reportLines.push("");
}

if (unknownKind.length) {
  reportLines.push("===== unknown kind samples =====");
  for (const r of unknownKind.slice(0, 50)) {
    reportLines.push(JSON.stringify({
      class_id: r.class_id,
      class_name: r.class_name,
      tab_id: r.tab_id,
      tab_name: r.tab_name,
      entry_type: r.entry_type,
      ae_cost: r.ae_cost,
      te_cost: r.te_cost,
      entry_id: r.entry_id,
      spell_id: r.spell_id,
      name: r.name
    }));
  }
  reportLines.push("");
}

fs.writeFileSync(
  "reports/coa_normalization_report.txt",
  reportLines.join("\n")
);

const countsRows = [];

for (const r of deduped) {
  countsRows.push([
    r.class_name || "UNKNOWN_CLASS",
    r.tab_name || "UNKNOWN_TAB",
    r.essence_kind || "unknown"
  ].join("\t"));
}

fs.writeFileSync(
  "reports/coa_counts_by_class_tab_kind.txt",
  countsRows.sort().join("\n") + "\n"
);

console.log(`Wrote ${path.join(outDir, "coa_classes.json")}`);
console.log(`Wrote ${path.join(outDir, "coa_essence_caps.json")}`);
console.log(`Wrote ${path.join(outDir, "coa_entries.jsonl")}`);
console.log(`Wrote ${path.join(outDir, "coa_entries.pretty.json")}`);
console.log("Wrote reports/coa_normalization_report.txt");
console.log("Wrote reports/coa_counts_by_class_tab_kind.txt");
console.log(`Deduped records: ${deduped.length}`);
console.log(`Missing class records: ${missingClass.length}`);
console.log(`Missing tab records: ${missingTab.length}`);
console.log(`Unknown essence-kind records: ${unknownKind.length}`);
