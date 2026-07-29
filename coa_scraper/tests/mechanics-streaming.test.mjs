// coa_scraper/tests/mechanics-streaming.test.mjs
// E0R.2 T5.1 — the canonical build streams the projection instead of reading it whole.
//
// `loadAndValidateProjectionV3` did readFileSync -> toString("utf8") -> split("\n") and then
// accumulated EVERY row into a `projection` array, which the caller turned into a Map. On the real
// client that is a 400 MB file held three ways at once, and Node peaked at 866 MB.
//
// The key observation is that `buildCanonicalMechanics` emits one row per BUILDER spell (~3,600), not
// per projection row (10,410) — the projection is only a lookup. So the stream needs to retain only the
// rows the Builder domain actually asks for, while still VALIDATING every row it passes: a corrupt row
// outside the domain is still a corrupt generation.
import { test } from "node:test";
import assert from "node:assert";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { loadAndValidateProjection, streamAndValidateProjectionV3 }
  from "../scripts/lib/mechanics-projection.mjs";

const POLICY = {
  sha256: "policy-sha-for-streaming",
  tables: { Spell: { fields: { power_type: {
    kind: "int32", layout: "verified", interpretation: "verified", promotion: "normalized" } } } },
};

function projRow(spell_id, { powerType = 3, decodedValue = powerType } = {}) {
  return {
    schema_version: "coa-client-spell-projection-v3", spell_id, name: `S${spell_id}`,
    mechanics: { power_type: powerType },
    field_observations: { power_type: {
      state: "present", raw_u32: decodedValue, decoded_reason: "decoded",
      policy_ref: "/tables/Spell/fields/power_type",
      proof: { integrity: "verified", layout: "verified", interpretation: "verified" },
      promotion: "normalized", decoded: { kind: "int32", value: decodedValue } } },
    coa_attribution: { is_coa: true, confidence: "high" },
  };
}

// A v3 projection of `rows` rows, its manifest, and the reviewed policy child — the three inputs a
// canonical build resolves out of a published generation.
function fixture(rows, { corruptLine = null } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mechstream-"));
  const projectionPath = path.join(dir, "coa_client_spell_coa.jsonl");
  const manifestPath = path.join(dir, "coa_client_spell_projection.manifest.json");
  const policyPath = path.join(dir, "spell_layout_v2.json");

  let body = "";
  for (let i = 1; i <= rows; i++) {
    // A row whose normalized value disagrees with its own observation: rejected by the per-row
    // re-derivation, wherever in the file it sits.
    body += JSON.stringify(i === corruptLine ? projRow(i, { powerType: 5, decodedValue: 3 })
                                             : projRow(i)) + "\n";
  }
  fs.writeFileSync(projectionPath, body);
  fs.writeFileSync(policyPath, JSON.stringify(POLICY));
  const manifest = {
    schema_version: "coa-client-spell-projection-manifest-v3",
    counts: { projected_records: rows, unique_spell_ids: rows },
    client_build: "test-client-build",
  };
  fs.writeFileSync(manifestPath, JSON.stringify(manifest));
  return { dir, projectionPath, manifestPath, policyPath, manifest, body };
}

function load(fx, builderSpellIds) {
  return loadAndValidateProjection({
    projectionPath: fx.projectionPath, manifestPath: fx.manifestPath, policyPath: fx.policyPath,
    builderSpellIds: new Set(builderSpellIds),
  });
}

test("the v3 loader reads no whole file and splits no whole string", () => {
  const src = streamAndValidateProjectionV3.toString();
  assert.doesNotMatch(src, /readFileSync\(\s*projectionPath/,
                      "the projection must not be slurped");
  assert.doesNotMatch(src, /\.split\(/, "a whole-file split defeats the point of streaming");
  assert.doesNotMatch(src, /toString\(\s*"utf8"\s*\)/,
                      "a whole-file utf8 decode is the same retention by another name");
});

test("only builder-domain rows are retained", () => {
  const fx = fixture(5000);
  const loaded = load(fx, [1, 2, 3]);
  assert.equal(loaded.absent, false);
  assert.equal(loaded.clientById.size, 3,
               "the projection is a LOOKUP; retaining rows nothing will ask for is the leak");
  assert.deepEqual([...loaded.clientById.keys()].sort((a, b) => a - b), [1, 2, 3]);
  assert.equal(loaded.clientById.get(2).name, "S2");
  assert.equal(loaded.projection, undefined, "the retained array is gone, not merely unused");
});

test("every row is still validated, including rows nothing will ask for", () => {
  const fx = fixture(200, { corruptLine: 73 });
  assert.throws(() => load(fx, [1]), /power_type.*re-decode/,
                "retention is an optimisation; validation coverage is the contract");
});

test("a duplicate spell_id anywhere in the stream is rejected", () => {
  const fx = fixture(50);
  fs.appendFileSync(fx.projectionPath, JSON.stringify(projRow(7)) + "\n");
  const parsed = JSON.parse(fs.readFileSync(fx.manifestPath, "utf8"));
  parsed.counts.projected_records = 51;
  fs.writeFileSync(fx.manifestPath, JSON.stringify(parsed));
  assert.throws(() => load(fx, [1]), /duplicate spell_id: 7/);
});

test("the incremental projection hash equals a whole-file hash", () => {
  const fx = fixture(5000);
  const loaded = load(fx, [1, 2, 3]);
  assert.equal(loaded.projection_sha256,
               crypto.createHash("sha256").update(fs.readFileSync(fx.projectionPath)).digest("hex"));
});

test("the manifest's counts are checked against what actually streamed", () => {
  const fx = fixture(100);
  const parsed = JSON.parse(fs.readFileSync(fx.manifestPath, "utf8"));
  parsed.counts.projected_records = 99;
  fs.writeFileSync(fx.manifestPath, JSON.stringify(parsed));
  assert.throws(() => load(fx, [1]), /projection count mismatch: manifest 99 != actual 100/);
});

test("a builder spell absent from the projection still fails closed", () => {
  const fx = fixture(10);
  assert.throws(() => load(fx, [1, 99999]), /builder_missing_from_projection/);
});

test("coverage counts the whole projection, not the retained slice", () => {
  const fx = fixture(1000);
  const loaded = load(fx, [1, 2, 3]);
  assert.deepEqual(loaded.coverage, {
    builder_joined_to_projection: 3, builder_missing_from_projection: 0, projection_only: 997,
  });
});
