#!/usr/bin/env node
import fs from "node:fs";

const input = process.argv[2] || "reports/coa_builder_payload.json";
const output = process.argv[3] || "reports/coa_payload_report.txt";

const payload = JSON.parse(fs.readFileSync(input, "utf8"));
const talents = payload.talents || {};

const lines = [];

lines.push("===== CoA builder payload report =====");
lines.push(`Builder: ${payload.name}`);
lines.push(`Slug: ${payload.slug}`);
lines.push(`ID: ${payload.id}`);
lines.push(`Max level: ${payload.max_level}`);
lines.push("");

lines.push("===== talents keys =====");
for (const [k, v] of Object.entries(talents)) {
  const type = Array.isArray(v) ? `array(${v.length})` : typeof v;
  lines.push(`${k}: ${type}`);
}
lines.push("");

if (Array.isArray(talents.classes)) {
  lines.push("===== classes =====");
  for (const c of talents.classes) {
    const tabs = Array.isArray(c.tabs)
      ? c.tabs.map(t => `${t.tabName}#${t.tabId}`).join(", ")
      : "";
    lines.push(`${c.classId}\t${c.className}\t${tabs}`);
  }
  lines.push("");
}

function sampleArray(key, limit = 5) {
  const arr = talents[key];
  if (!Array.isArray(arr)) return;

  lines.push(`===== sample talents.${key} =====`);
  for (const item of arr.slice(0, limit)) {
    lines.push(JSON.stringify(item).slice(0, 1000));
  }
  lines.push("");
}

for (const key of Object.keys(talents)) {
  if (Array.isArray(talents[key])) {
    sampleArray(key, 3);
  }
}

fs.writeFileSync(output, lines.join("\n"), "utf8");
console.log(`Wrote ${output}`);
