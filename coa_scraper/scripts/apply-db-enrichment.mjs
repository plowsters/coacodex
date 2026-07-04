#!/usr/bin/env node
import path from "node:path";
import { fileURLToPath } from "node:url";

import { readJsonl, writeJsonl } from "./lib/ascensiondb.mjs";
import { deriveAvailability } from "./lib/source-level.mjs";

export function applyDbEnrichmentToEntries(entries, spellRows) {
  const bySpellId = new Map(spellRows.map(row => [Number(row.id), row]));

  return entries.map(entry => {
    const db = bySpellId.get(Number(entry.spell_id)) || null;
    if (!db) {
      return entry;
    }

    const availability = deriveAvailability({
      builderRequiredLevel: entry.required_level,
      builderTooltipText: entry.description_text,
      dbTooltipLevel: db.tooltip_level
    });

    return {
      ...entry,
      availability,
      db_enrichment: {
        spell_id: db.id,
        status: db.status,
        name: db.name,
        name_match: db.name_match,
        icon: db.icon,
        tooltip_html: db.tooltip_html,
        tooltip_text: db.tooltip_text,
        buff_tooltip_html: db.buff_tooltip_html || "",
        linked_spell_ids: db.linked_spell_ids || [],
        linked_item_ids: db.linked_item_ids || [],
        detail_status: "not_fetched",
        provenance: db.provenance
      }
    };
  });
}

function isCliEntryPoint() {
  return process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);
}

if (isCliEntryPoint()) {
  const entriesPath = process.argv[2] || "dist/coa_entries.jsonl";
  const spellRowsPath = process.argv[3] || "dist/coa_db_spell_tooltips.jsonl";
  const outPath = process.argv[4] || "dist/coa_entries.enriched.jsonl";
  const entries = readJsonl(entriesPath);
  const spellRows = readJsonl(spellRowsPath);

  writeJsonl(outPath, applyDbEnrichmentToEntries(entries, spellRows));
  console.log(`Wrote ${outPath}`);
}
