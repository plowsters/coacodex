// The negative gate for the E0R AscensionDB sunset: the canonical mechanics reconciliation has no
// `ascension_db` tier, no db.ascension.gg command survives in either package.json, and a canonical build
// makes NO network request and emits NO ascension_db provenance.
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import http from "node:http";
import https from "node:https";
import { TIERS } from "../scripts/lib/mechanics-reconcile.mjs";
import { buildCanonicalMechanics } from "../scripts/build-mechanics-artifacts.mjs";

test("ascension_db is not a canonical reconciliation tier", () => {
  assert.ok(!TIERS.includes("ascension_db"));
  assert.deepEqual(TIERS, ["client_dbc", "verified_builder", "inferred"]);
});

test("no canonical AscensionDB command survives in either package.json", () => {
  for (const url of ["../package.json", "../../package.json"]) {
    const pkg = JSON.parse(fs.readFileSync(new URL(url, import.meta.url)));
    const joined = JSON.stringify(pkg.scripts || {});
    assert.ok(!/--db-spells|enrich-db|apply-db-enrichment|pipeline:m1\.9/.test(joined),
      `retired AscensionDB command leaked into ${url}: ${joined}`);
  }
  const scraper = JSON.parse(fs.readFileSync(new URL("../package.json", import.meta.url)));
  assert.ok(scraper.scripts["build-mechanics"].includes("--client-extract-pointer"));
  assert.ok(!scraper.scripts["build-mechanics"].includes("--db-spells"));
});

test("canonical build makes NO network request and emits no ascension_db provenance", () => {
  const trap = () => { throw new Error("network access is forbidden in a canonical build"); };
  const origHttp = http.request, origHttps = https.request;
  http.request = trap; https.request = trap;                       // network trap
  try {
    const rows = buildCanonicalMechanics({
      entries: [{ spell_id: 1, entry_id: 1, entry_type: "Ability", name: "X", damage_schools: [], resources: [] }],
      spellRows: [],
      projection: [{ spell_id: 1, name: "X", mechanics: {}, raw: {}, coa_attribution: { is_coa: true } }],
    });
    const blob = JSON.stringify(rows);
    assert.ok(!/ascension_db|db\.ascension\.gg/.test(blob));
    assert.ok(!rows.some((r) => (r.provenance || []).some((p) => p.source === "ascension_db")));
    assert.ok(!rows.some((r) => Object.values(r.field_provenance || {}).some(
      (p) => p.selected_tier === "ascension_db")));
  } finally { http.request = origHttp; https.request = origHttps; }
});
