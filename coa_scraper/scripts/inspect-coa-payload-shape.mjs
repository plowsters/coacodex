#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const input = process.argv[2] || "reports/coa_builder_payload.json";
const outTxt = process.argv[3] || "reports/coa_payload_shape_report.txt";
const outJson = process.argv[4] || "reports/coa_payload_shape.json";

const payload = JSON.parse(fs.readFileSync(input, "utf8"));
const talents = payload.talents || {};
const classes = talents.classes || [];
const entriesByTab = talents.entriesByTab || {};
const essenceByClass = talents.essenceByClass || {};

fs.mkdirSync(path.dirname(outTxt), { recursive: true });

const tabOwners = new Map();

for (const cls of classes) {
  for (const tab of cls.tabs || []) {
    const id = String(tab.tabId);
    if (!tabOwners.has(id)) tabOwners.set(id, []);
    tabOwners.get(id).push({
      classId: cls.classId,
      className: cls.className,
      tabId: tab.tabId,
      tabName: tab.tabName,
      sortOrder: tab.sortOrder
    });
  }
}

const typeOf = v => {
  if (Array.isArray(v)) return `array(${v.length})`;
  if (v === null) return "null";
  return typeof v;
};

const compactValue = v => {
  if (typeof v === "string") {
    return v.replace(/\s+/g, " ").slice(0, 160);
  }
  if (typeof v === "number" || typeof v === "boolean" || v === null) return v;
  if (Array.isArray(v)) return `array(${v.length})`;
  if (typeof v === "object") return `object(${Object.keys(v).length})`;
  return typeof v;
};

const summarizeObject = obj => {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return obj;

  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    out[k] = {
      type: typeOf(v),
      sample: compactValue(v)
    };
  }
  return out;
};

const keyHistogram = arr => {
  const counts = new Map();

  for (const item of arr) {
    if (!item || typeof item !== "object" || Array.isArray(item)) continue;
    for (const k of Object.keys(item)) {
      counts.set(k, (counts.get(k) || 0) + 1);
    }
  }

  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([key, count]) => ({ key, count }));
};

const objectSamples = arr => {
  const samples = [];
  for (const item of arr) {
    if (item && typeof item === "object" && !Array.isArray(item)) {
      samples.push({
        keys: Object.keys(item),
        summary: summarizeObject(item)
      });
    }
    if (samples.length >= 3) break;
  }
  return samples;
};

const report = {
  builder: {
    id: payload.id,
    slug: payload.slug,
    name: payload.name,
    max_level: payload.max_level
  },
  talentKeys: Object.fromEntries(
    Object.entries(talents).map(([k, v]) => [k, typeOf(v)])
  ),
  classCount: classes.length,
  entriesByTabCount: Object.keys(entriesByTab).length,
  essenceByClass,
  tabs: Object.entries(entriesByTab)
    .map(([tabId, entries]) => ({
      tabId: Number(tabId),
      owners: tabOwners.get(String(tabId)) || [],
      entryType: typeOf(entries),
      entryCount: Array.isArray(entries) ? entries.length : null,
      keyHistogram: Array.isArray(entries) ? keyHistogram(entries).slice(0, 40) : [],
      samples: Array.isArray(entries) ? objectSamples(entries) : summarizeObject(entries)
    }))
    .sort((a, b) => a.tabId - b.tabId)
};

const lines = [];

lines.push("===== CoA payload shape report =====");
lines.push(`Builder: ${report.builder.name} (${report.builder.slug})`);
lines.push(`Max level: ${report.builder.max_level}`);
lines.push("");

lines.push("===== talents keys =====");
for (const [k, v] of Object.entries(report.talentKeys)) {
  lines.push(`${k}: ${v}`);
}
lines.push("");

lines.push("===== essence caps =====");
for (const [classId, caps] of Object.entries(essenceByClass)) {
  const cls = classes.find(c => String(c.classId) === String(classId));
  lines.push(`${classId}\t${cls?.className ?? "UNKNOWN"}\t${JSON.stringify(caps)}`);
}
lines.push("");

lines.push("===== entriesByTab summary =====");
for (const tab of report.tabs) {
  const ownerText = tab.owners
    .map(o => `${o.className}/${o.tabName}#${o.tabId}`)
    .join(" | ");

  lines.push("");
  lines.push(`--- tab ${tab.tabId}: ${ownerText || "NO OWNER"} ---`);
  lines.push(`entries: ${tab.entryType}`);

  if (tab.keyHistogram?.length) {
    lines.push("keys:");
    for (const k of tab.keyHistogram.slice(0, 30)) {
      lines.push(`  ${k.key}: ${k.count}`);
    }
  }

  if (Array.isArray(tab.samples)) {
    lines.push("samples:");
    for (const sample of tab.samples) {
      lines.push(JSON.stringify(sample.summary).slice(0, 3000));
    }
  } else {
    lines.push(`sample object: ${JSON.stringify(tab.samples).slice(0, 3000)}`);
  }
}

fs.writeFileSync(outJson, JSON.stringify(report, null, 2));
fs.writeFileSync(outTxt, lines.join("\n"));

console.log(`Wrote ${outTxt}`);
console.log(`Wrote ${outJson}`);
console.log(`Tabs in entriesByTab: ${report.entriesByTabCount}`);
