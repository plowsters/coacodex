// coa_scraper/tests/generation-e0r.test.mjs
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { resolveGeneration, validateCandidateByPath } from "../scripts/lib/generation.mjs";
import { buildCandidate } from "./helpers/candidate.mjs";

const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");

function stage(publicationState, { manifestSchema = "coa-client-extract-manifest-v3" } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "gen-"));
  const genId = "abc123";
  const genDir = path.join(root, `gen-${genId}`);
  fs.mkdirSync(genDir);
  const child = Buffer.from('{"schema_version":"coa-client-spell-v3","spell_id":1}\n');
  fs.writeFileSync(path.join(genDir, "coa_client_spell.jsonl"), child);
  const manifest = {
    schema_version: manifestSchema, generation_id: genId, publication_state: publicationState,
    children: { "coa_client_spell.jsonl": { sha256: sha(child), byte_length: child.length, records: 1,
                                            schema_version: "coa-client-spell-v3" } },
  };
  const manBody = Buffer.from(JSON.stringify(manifest));
  fs.writeFileSync(path.join(genDir, "manifest.json"), manBody);
  const pointer = { schema_version: "coa-client-extract-pointer-v1", generation_id: genId,
                    manifest_sha256: sha(manBody) };
  fs.writeFileSync(path.join(root, "coa_client_extract.pointer.json"), Buffer.from(JSON.stringify(pointer)));
  return root;
}

test("Node rejects a pointer that resolves a candidate manifest", () => {
  assert.throws(() => resolveGeneration(stage("candidate")), /candidate/);
});

test("Node rejects a pre-E0R (unsupported) manifest schema_version", () => {
  assert.throws(() => resolveGeneration(stage("published", { manifestSchema: "coa-client-extract-manifest-v1" })),
    /unsupported manifest schema_version/);
});

test("Node resolves a published v3 generation", () => {
  const r = resolveGeneration(stage("published"));
  assert.equal(r.generationId, "abc123");
  assert.ok(r.children["coa_client_spell.jsonl"]);
});

test("Node validates a complete staged candidate generation by path (no pointer)", () => {
  const { genDir, lockPath } = buildCandidate();
  const r = validateCandidateByPath(genDir, { lockPath });
  assert.ok(r.children["coa_client_spell.jsonl"]);
  assert.equal(r.manifest.publication_state, "candidate");
});

test("Node candidate validation rejects a non-candidate (already published) manifest by path", () => {
  const { genDir, lockPath } = buildCandidate({ mutateManifest: (m) => { m.publication_state = "published"; } });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /not a candidate/);
});

test("Node candidate validation fails closed on a tampered child", () => {
  const { genDir, lockPath } = buildCandidate();
  fs.writeFileSync(path.join(genDir, "coa_client_essence.jsonl"), Buffer.from('{"tampered":true}\n'));
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /sha256 mismatch/);
});
