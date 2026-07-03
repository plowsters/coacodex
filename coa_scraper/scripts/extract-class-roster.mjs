#!/usr/bin/env node
import fs from "node:fs";

const input = process.argv[2] || "data/snapshots/runtime-dump.json";
const output = process.argv[3] || "reports/class_roster_candidates.json";

const raw = fs.readFileSync(input, "utf8");

const classRegex =
  /\{\\"tabs\\":\[(?<tabs>.*?)\],\\"classId\\":(?<classId>\d+),\\"className\\":\\"(?<className>[^"]+)\\"\}/gs;

const tabRegex =
  /\{\\"tabId\\":(?<tabId>\d+),\\"tabName\\":\\"(?<tabName>[^"]+)\\",\\"sortOrder\\":(?<sortOrder>-?\d+)\}/g;

const classes = [];

for (const match of raw.matchAll(classRegex)) {
  const tabs = [];

  for (const tab of match.groups.tabs.matchAll(tabRegex)) {
    tabs.push({
      tabId: Number(tab.groups.tabId),
      tabName: tab.groups.tabName,
      sortOrder: Number(tab.groups.sortOrder)
    });
  }

  classes.push({
    classId: Number(match.groups.classId),
    className: match.groups.className,
    tabs
  });
}

const deduped = [...new Map(classes.map(c => [c.classId, c])).values()]
  .sort((a, b) => a.classId - b.classId);

fs.mkdirSync("reports", { recursive: true });
fs.writeFileSync(output, JSON.stringify(deduped, null, 2));

console.log(`Extracted ${deduped.length} class records to ${output}`);
for (const c of deduped) {
  console.log(`${c.classId}\t${c.className}\t${c.tabs.map(t => t.tabName).join(", ")}`);
}
