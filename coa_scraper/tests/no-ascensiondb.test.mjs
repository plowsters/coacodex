// The negative gate for the E0R AscensionDB sunset: the canonical mechanics reconciliation has no
// `ascension_db` tier, no db.ascension.gg command survives in either package.json, and a canonical build
// makes NO network request and emits NO ascension_db provenance. E0R.1 T5.1 completes the sunset: the
// DB parser/cache/item-builder runtime is DELETED, no runtime script imports ascensiondb or carries the
// hostname, and the sole surviving hostname-bearing file — the opt-in icon downloader — refuses to run
// without an explicit --authorize and only ever writes under a diagnostic/ directory.
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import https from "node:https";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { TIERS } from "../scripts/lib/mechanics-reconcile.mjs";
import { buildCanonicalMechanics } from "../scripts/build-mechanics-artifacts.mjs";

const SCRIPTS_DIR = fileURLToPath(new URL("../scripts/", import.meta.url));
const DOWNLOADER = path.join(SCRIPTS_DIR, "download-spell-icons.mjs");

function* runtimeScripts(dir = SCRIPTS_DIR) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "dist" || entry.name === "reports" || entry.name === "node_modules") continue;
      yield* runtimeScripts(full);
    } else if (entry.name.endsWith(".mjs") && full !== DOWNLOADER) {
      yield full;
    }
  }
}

function runDownloader(args, cwd) {
  return spawnSync(process.execPath, [DOWNLOADER, ...args], { cwd, encoding: "utf8" });
}

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
      projection: [{ spell_id: 1, name: "X", mechanics: {}, raw: {}, coa_attribution: { is_coa: true } }],
    });
    const blob = JSON.stringify(rows);
    assert.ok(!/ascension_db|db\.ascension\.gg/.test(blob));
    assert.ok(!rows.some((r) => (r.provenance || []).some((p) => p.source === "ascension_db")));
    assert.ok(!rows.some((r) => Object.values(r.field_provenance || {}).some(
      (p) => p.selected_tier === "ascension_db")));
  } finally { http.request = origHttp; https.request = origHttps; }
});

test("the AscensionDB runtime modules are deleted", () => {
  for (const rel of ["lib/ascensiondb.mjs", "lib/ascensiondb-cache.mjs", "build-item-artifacts.mjs"]) {
    assert.ok(!fs.existsSync(path.join(SCRIPTS_DIR, rel)), `${rel} must be git rm'd by the sunset`);
  }
});

test("no runtime script imports ascensiondb or contains the db host", () => {
  const offenders = [];
  for (const file of runtimeScripts()) {
    const text = fs.readFileSync(file, "utf8");
    if (text.includes("db.ascension.gg")) offenders.push(`${file}: contains db.ascension.gg`);
    if (/(?:from|import)\s*\(?\s*["'][^"']*ascensiondb/.test(text)) offenders.push(`${file}: imports ascensiondb`);
    if (text.includes("download-spell-icons")) offenders.push(`${file}: imports the opt-in downloader`);
  }
  assert.deepEqual(offenders, []);
});

test("the icon downloader refuses to run without --authorize", () => {
  const res = runDownloader(["--icon", "inv_misc_test"], os.tmpdir());
  assert.equal(res.status, 2);
  assert.match(res.stderr, /--authorize/);
});

test("the icon downloader refuses an --out outside a diagnostic/ dir", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "coa-dl-"));
  const res = runDownloader(["--authorize", "--icon", "inv_misc_test", "--out", path.join(tmp, "icons")], tmp);
  assert.equal(res.status, 2);
  assert.match(res.stderr, /diagnostic/);
  assert.ok(!fs.existsSync(path.join(tmp, "icons")), "nothing may be written outside diagnostic/");
});

test("authorized downloader writes only under diagnostic/ (offline: empty slug list)", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "coa-dl-"));
  const slugs = path.join(tmp, "slugs.txt");
  fs.writeFileSync(slugs, "# no slugs -> zero network requests\n");
  const outDir = path.join(tmp, "diagnostic", "icons");
  const res = runDownloader(["--authorize", "--icons", slugs, "--out", outDir], tmp);
  assert.equal(res.status, 0, res.stderr);
  const summary = JSON.parse(res.stdout);
  assert.equal(summary.requested, 0);
  assert.ok(fs.existsSync(outDir));
});
