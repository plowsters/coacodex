#!/usr/bin/env node
import fs from "node:fs";

const input = process.argv[2] || "data/snapshots/final-page-content.html";
const output = process.argv[3] || "reports/rendered_node_labels.json";

const raw = fs.readFileSync(input, "utf8");

const decode = s =>
  s
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");

const labels = [];
const rx = /aria-label="([^"]+)"/g;

for (const m of raw.matchAll(rx)) {
  const label = decode(m[1]).replace(/\s+/g, " ").trim();

  if (
    /Talent Essence|Ability Essence|requires one connected node|requires .* connected node/i.test(label)
  ) {
    labels.push(label);
  }
}

const deduped = [...new Set(labels)].sort();

fs.mkdirSync("reports", { recursive: true });
fs.writeFileSync(output, JSON.stringify(deduped, null, 2));

console.log(`Extracted ${deduped.length} rendered node labels to ${output}`);
console.log(deduped.slice(0, 30).join("\n"));
