#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const entriesPath = process.argv[2] || "dist/coa_entries.jsonl";
const classesPath = process.argv[3] || "dist/coa_classes.json";
const outPath = process.argv[4] || "dist/coa_class_profile_input.json";

const entries = fs.readFileSync(entriesPath, "utf8")
  .trim()
  .split("\n")
  .filter(Boolean)
  .map(line => JSON.parse(line));

const classes = JSON.parse(fs.readFileSync(classesPath, "utf8"));

const byClass = new Map();

for (const cls of classes) {
  byClass.set(cls.class_name, {
    class_id: cls.class_id,
    class_name: cls.class_name,
    essence_caps: cls.essence_caps,
    tabs: cls.tabs,
    counts: {
      ability: 0,
      talent: 0
    },
    resources: {},
    damage_schools: {},
    tags: {},
    entries_by_tab: {}
  });
}

const inc = (obj, key) => {
  if (!key) return;
  obj[key] = (obj[key] || 0) + 1;
};

for (const e of entries) {
  const cls = byClass.get(e.class_name);
  if (!cls) continue;

  if (e.essence_kind === "ability") cls.counts.ability++;
  if (e.essence_kind === "talent") cls.counts.talent++;

  for (const r of e.resources || []) inc(cls.resources, r);
  for (const s of e.damage_schools || []) inc(cls.damage_schools, s);
  for (const t of e.tags || []) inc(cls.tags, t);

  const tabKey = `${e.tab_id}:${e.tab_name}`;
  cls.entries_by_tab[tabKey] ??= {
    tab_id: e.tab_id,
    tab_name: e.tab_name,
    ability_count: 0,
    talent_count: 0,
    entries: []
  };

  const tab = cls.entries_by_tab[tabKey];

  if (e.essence_kind === "ability") tab.ability_count++;
  if (e.essence_kind === "talent") tab.talent_count++;

  tab.entries.push({
    entry_id: e.entry_id,
    spell_id: e.spell_id,
    name: e.name,
    entry_type: e.entry_type,
    essence_kind: e.essence_kind,
    ae_cost: e.ae_cost,
    te_cost: e.te_cost,
    required_tab_ae: e.required_tab_ae,
    required_tab_te: e.required_tab_te,
    required_level: e.required_level,
    max_rank: e.max_rank,
    row: e.row,
    col: e.col,
    node_type: e.node_type,
    is_passive: e.is_passive,
    tags: e.tags,
    damage_schools: e.damage_schools,
    resources: e.resources,
    description_text: e.description_text
  });
}

const output = [...byClass.values()]
  .sort((a, b) => a.class_id - b.class_id)
  .map(cls => ({
    ...cls,
    resources: Object.fromEntries(Object.entries(cls.resources).sort((a, b) => b[1] - a[1])),
    damage_schools: Object.fromEntries(Object.entries(cls.damage_schools).sort((a, b) => b[1] - a[1])),
    tags: Object.fromEntries(Object.entries(cls.tags).sort((a, b) => b[1] - a[1])),
    entries_by_tab: Object.fromEntries(
      Object.entries(cls.entries_by_tab)
        .sort((a, b) => Number(a[1].tab_id) - Number(b[1].tab_id))
    )
  }));

fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, JSON.stringify(output, null, 2));

console.log(`Wrote ${outPath}`);
console.log(`Classes: ${output.length}`);
for (const cls of output) {
  console.log(
    `${cls.class_name}: ${cls.counts.ability} ability, ${cls.counts.talent} talent, tags=${Object.keys(cls.tags).slice(0, 8).join(", ")}`
  );
}
