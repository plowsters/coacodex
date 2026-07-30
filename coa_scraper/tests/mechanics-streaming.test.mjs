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

import { buildCanonicalMechanics, buildMechanicsArtifact, statsAccumulator }
  from "../scripts/build-mechanics-artifacts.mjs";
import { loadAndValidateProjection, streamAndValidateProjectionV3 }
  from "../scripts/lib/mechanics-projection.mjs";
import { BUILDER_SPELLS, entries, projectionFixture, tempDir }
  from "./helpers/mechanics-fixture.mjs";

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

// === E0R.2 T5.2 — rows are generated and counted incrementally ===================================
//
// `buildCanonicalMechanics` returned an array, and `writeArtifact` then walked it FOUR more times:
// winnerCounts, aggregateCounts, fieldReadinessCoverage and rows.length. The whole output is ~3,600
// rows, so this is not the 400 MB problem — it is the reason the output could never BE a stream. A
// generator plus a fold is what makes the write loop the only pass.
//
// The golden hash below was recorded from the pre-refactor implementation over the fixed fixture in
// tests/helpers/mechanics-fixture.mjs. It is the whole point of the exercise: a performance change
// that alters the artifact is not a performance change.
const GOLDEN_JSONL_SHA256 = "b8431e54c5551daea8b71c609e2b0613c29caeb04a0c19157cfc3483e7ea2c9d";
const GOLDEN_RECORD_COUNT = BUILDER_SPELLS;

function goldenBuild() {
  const dir = tempDir();
  const { proj, man } = projectionFixture(dir);
  const out = buildMechanicsArtifact({ entries: entries(), projectionPath: proj, manifestPath: man,
                                       outDir: dir });
  return { dir, ...out };
}

test("the artifact is byte-identical to the pre-refactor implementation", () => {
  const { manifest, dir } = goldenBuild();
  assert.equal(manifest.outputs.sha256, GOLDEN_JSONL_SHA256);
  assert.equal(manifest.outputs.record_count, GOLDEN_RECORD_COUNT);
  assert.equal(crypto.createHash("sha256")
                     .update(fs.readFileSync(path.join(dir, "coa_mechanics.jsonl"))).digest("hex"),
               GOLDEN_JSONL_SHA256);
});

test("every statistic is byte-identical to the pre-refactor implementation", () => {
  const { manifest } = goldenBuild();
  assert.deepEqual(manifest.per_field_winner_counts_by_source, {
    name: { client_dbc: 40 }, cast_time_ms: { client_dbc: 40 }, duration_ms: { client_dbc: 40 },
    range_yards: { client_dbc: 40 }, schools: { client_dbc: 40 }, power_type: { client_dbc: 40 },
    kind: { builder: 40 }, effects: { inferred: 40 },
  });
  assert.deepEqual(manifest.per_field_winner_counts_by_tier, {
    name: { client_dbc: 40 }, cast_time_ms: { client_dbc: 40 }, duration_ms: { client_dbc: 40 },
    range_yards: { client_dbc: 40 }, schools: { client_dbc: 40 }, power_type: { client_dbc: 40 },
    kind: { verified_builder: 40 }, effects: { inferred: 40 },
  });
  assert.deepEqual(manifest.counts, {
    unresolved_conflicts: 0, ineligible_candidates: 92, omitted_fields: 0, kind_disagreements: 13,
  });
  assert.deepEqual(manifest.field_readiness_coverage, {
    schema_version: "coa-mechanics-readiness-coverage-v1", rows: 40, fields_considered: 160,
    statuses: { unavailable: 120, absent: 40 },
    reason_codes: { pending_e1_operand: 120, absent: 40 },
    fields: {
      cooldown_ms: { considered: 40, statuses: { unavailable: 40 }, reason_codes: { pending_e1_operand: 40 } },
      costs: { considered: 40, statuses: { unavailable: 40 }, reason_codes: { pending_e1_operand: 40 } },
      gcd_ms: { considered: 40, statuses: { unavailable: 40 }, reason_codes: { pending_e1_operand: 40 } },
      power_type: { considered: 40, statuses: { absent: 40 }, reason_codes: { absent: 40 } },
    },
  });
});

test("buildCanonicalMechanics returns an iterator, not an array", () => {
  const rows = buildCanonicalMechanics({ entries: entries(3), projection: [] });
  assert.equal(Array.isArray(rows), false);
  assert.equal(typeof rows[Symbol.iterator], "function");
  assert.equal(typeof rows.next, "function", "a one-shot generator, not a re-iterable collection");
  assert.equal(rows.length, undefined);
});

test("the generator yields rows ascending by spell_id", () => {
  const ids = [...buildCanonicalMechanics({ entries: entries(20), projection: [] })].map((r) => r.spell_id);
  assert.deepEqual(ids, [...ids].sort((a, b) => a - b));
  assert.equal(new Set(ids).size, ids.length);
});

test("the write loop is the only pass: a one-shot generator still yields complete statistics", () => {
  // The behavioural proof. If ANY statistic were still computed by re-walking `rows`, a generator
  // already consumed by the write loop would give that pass zero rows and the counts would come back
  // empty rather than wrong — which is exactly how this kind of refactor fails silently.
  const dir = tempDir();
  const { proj, man } = projectionFixture(dir);
  const { manifest } = buildMechanicsArtifact({
    entries: entries(), projectionPath: proj, manifestPath: man, outDir: dir });
  assert.equal(manifest.outputs.record_count, GOLDEN_RECORD_COUNT);
  assert.equal(manifest.field_readiness_coverage.rows, GOLDEN_RECORD_COUNT);
  assert.equal(manifest.per_field_winner_counts_by_source.name.client_dbc, GOLDEN_RECORD_COUNT);
  assert.ok(manifest.counts.ineligible_candidates > 0);
});

test("nothing materializes the rows", () => {
  const src = fs.readFileSync(new URL("../scripts/build-mechanics-artifacts.mjs", import.meta.url), "utf8");
  assert.doesNotMatch(src, /\[\.\.\.rows\]/, "spreading the rows re-creates the array the generator removed");
  assert.doesNotMatch(src, /rows\.length/, "a length is a second pass over a materialized array");
  assert.doesNotMatch(src, /winnerCounts\(rows\)/);
  assert.doesNotMatch(src, /aggregateCounts\(rows\)/);
  // The T4.1 entry point still exists and still takes an iterable; what must be gone is the manifest
  // being built by handing it the rows a second time.
  assert.doesNotMatch(src, /field_readiness_coverage:\s*fieldReadinessCoverage\(/);
});

test("the accumulator folds one row at a time and holds counters, not rows", () => {
  const acc = statsAccumulator();
  const rows = [...buildCanonicalMechanics({ entries: entries(5), projection: [] })];
  for (const row of rows) acc.observe(row);
  const result = acc.result();
  assert.equal(result.record_count, 5);
  assert.equal(result.field_readiness_coverage.rows, 5);
  for (const value of Object.values(acc)) {
    assert.notEqual(typeof value, "object", "the accumulator's surface is functions, never retained state");
  }
});
