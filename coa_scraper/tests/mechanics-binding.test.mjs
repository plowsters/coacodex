// coa_scraper/tests/mechanics-binding.test.mjs
// E0R.2 T4.3 — a canonical mechanics build must record WHAT IT READ.
//
// The artifact already carried its inputs' paths and hashes, but nothing tied it to a published
// generation: the same manifest would have been emitted whether the projection came from the generation
// under acceptance or from another one that replaced it. The producer's acceptance run re-derives all
// five identities independently and refuses the record if any of them names something else, so this side
// only has to state them — and state them from the RESOLVED generation, never from the flags passed in.
import { test } from "node:test";
import assert from "node:assert";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { MECHANICS_BINDING_KEYS, buildMechanicsArtifact, mechanicsInputBinding }
  from "../scripts/build-mechanics-artifacts.mjs";
import { resolveGeneration } from "../scripts/lib/generation.mjs";
import { buildCandidate } from "./helpers/candidate.mjs";

const ENTRIES_SHA = "a".repeat(64);

function resolved() {
  const { root } = buildCandidate({ publish: true });
  return { root, resolved: resolveGeneration(root) };
}

test("the binding names every input identity, from the resolved generation", () => {
  const { root, resolved: gen } = resolved();
  const pointer = JSON.parse(fs.readFileSync(path.join(root, "coa_client_extract.pointer.json"), "utf8"));
  const binding = mechanicsInputBinding(gen, ENTRIES_SHA);

  assert.deepEqual(Object.keys(binding).sort(), [...MECHANICS_BINDING_KEYS].sort());
  assert.equal(binding.input_generation_id, gen.generationId);
  assert.equal(binding.pointer_manifest_sha256, pointer.manifest_sha256);
  assert.equal(binding.policy_sha256, gen.manifest.binding.policy_sha256);
  assert.equal(binding.projection_child_sha256,
               gen.manifest.children["coa_client_spell_coa.jsonl"].sha256);
  assert.equal(binding.builder_entries_sha256, ENTRIES_SHA);
});

test("the pointer's manifest hash reaches the binding through the resolver", () => {
  // Not re-read from the pointer here: the resolver has already checked those bytes against it, and a
  // second independent read is a second chance to bind to something the resolver never validated.
  const { root, resolved: gen } = resolved();
  const manifestBytes = fs.readFileSync(path.join(gen.genDir, "manifest.json"));
  assert.equal(gen.pointerManifestSha256,
               crypto.createHash("sha256").update(manifestBytes).digest("hex"));
  assert.equal(mechanicsInputBinding(gen, ENTRIES_SHA).pointer_manifest_sha256,
               gen.pointerManifestSha256);
  assert.ok(root);
});

// A one-row projection pair, so the build under test is a real canonical build rather than a shape.
function projectionFixture(dir) {
  const proof = { integrity: "verified", layout: "verified", interpretation: "verified" };
  const env = (v, kind = "int32") => ({ state: "present", raw_u32: v, decoded: { kind, value: v },
                                        decoded_reason: "decoded", proof, evidence_ref: "fx" });
  const join = (v) => ({ state: "resolved", components: {}, composed_proof: proof, decoded: v,
                         decoded_reason: "decoded" });
  const rec = {
    schema_version: "coa-client-spell-v2", spell_id: 101, name: "S101",
    mechanics: { school_mask: 8, power_type: 3, cast_time_ms: 0, duration_ms: 12000,
                 range_min_yd: 0, range_max_yd: 30, spell_icon_id: 1 },
    field_observations: {
      school_mask: env(8, "uint32"), power_type: env(3, "int32"),
      cast_time_ms: join(0), duration_ms: join(12000),
      range_min_yd: join(0), range_max_yd: join(30), spell_icon_id: join(1),
    },
    coa_attribution: { is_coa: true, confidence: "high" },
  };
  const body = JSON.stringify(rec) + "\n";
  const proj = path.join(dir, "p.jsonl");
  const man = path.join(dir, "p.manifest.json");
  fs.writeFileSync(proj, body);
  fs.writeFileSync(man, JSON.stringify({
    schema_version: "coa-client-spell-projection-v2",
    projection: { path: "p.jsonl", sha256: crypto.createHash("sha256").update(body).digest("hex"),
                  byte_length: Buffer.byteLength(body) },
    counts: { projected_records: 1, unique_spell_ids: 1, source_records: 1 },
    client_build: "test-client-build",
  }));
  return { proj, man };
}

test("a canonical build writes the binding into its manifest", () => {
  const { resolved: gen } = resolved();
  const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "e0r2mech-"));
  const { proj, man } = projectionFixture(outDir);
  const binding = mechanicsInputBinding(gen, ENTRIES_SHA);

  const { canonical, manifest } = buildMechanicsArtifact({
    entries: [{ entry_id: 1, spell_id: 101, entry_type: "Ability", name: "Alpha",
                damage_schools: [], resources: [] }],
    projectionPath: proj, manifestPath: man, outDir, inputs: { binding },
  });

  assert.equal(canonical, true);
  assert.deepEqual(manifest.binding, binding);
  const written = JSON.parse(fs.readFileSync(path.join(outDir, "coa_mechanics.manifest.json"), "utf8"));
  assert.deepEqual(written.binding, binding);
});

test("a degraded build binds to nothing rather than claiming a generation", () => {
  const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "e0r2mech-"));
  const { manifest } = buildMechanicsArtifact({
    entries: [{ entry_id: 1, spell_id: 101, name: "Alpha" }],
    projectionPath: path.join(outDir, "does-not-exist.jsonl"),
    manifestPath: path.join(outDir, "does-not-exist.manifest.json"),
    outDir, allowFallback: true, inputs: { binding: { input_generation_id: "whatever" } },
  });
  assert.equal(manifest.canonical, false);
  assert.equal(manifest.binding, null);
});
