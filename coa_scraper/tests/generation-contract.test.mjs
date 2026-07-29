// coa_scraper/tests/generation-contract.test.mjs
// E0R.2 T1.3 — Node re-derives and compares the BOUND contract instead of restating a Python constant.
//
// The required-child list used to be a hand-mirrored array in generation.mjs. A mirrored constant is what
// drifts: the two boundaries could disagree about what a complete generation is, and nothing would say so.
// Node now reads the SAME immutable registry files Python ships, validates the selected revision with an
// INDEPENDENT implementation, and performs the same three-way comparison — staged bytes, bound hash, and
// membership in its own supported set. Two properties are asserted against Python directly: the canonical
// contract hash, and the supported-revision set.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import {
  GENERATION_CONTRACT_CHILD, GenerationResolveError, REQUIRED_CHILDREN, generationContractSha256,
  loadContractRegistry, loadCurrentContract, requiredChildrenFor, validateCandidateByPath,
  validateContractRegistry, validateGenerationContract,
} from "../scripts/lib/generation.mjs";
import { bindPolicyDoc, buildCandidate, loadCorpus, topologyReportFor, unbindPolicyDoc,
         writeTwoRevisionRegistry } from "./helpers/candidate.mjs";

const REPO = new URL("../../", import.meta.url).pathname;

function python(code) {
  return execFileSync("python3", ["-c", code],
    { cwd: REPO, encoding: "utf8", env: { ...process.env, PYTHONPATH: REPO } }).trim();
}

function tmpdir(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "e0r2-contract-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

// --- cross-language agreement (the whole point of deleting the mirror) ---

test("Node and Python compute the same canonical contract hash", () => {
  const fromPython = python(
    "from coa_client_extract.contracts import generation_contract_sha256, load_current_contract;" +
    "print(generation_contract_sha256(load_current_contract()[1]))");
  assert.equal(generationContractSha256(loadCurrentContract()[1]), fromPython);
});

test("Node and Python support exactly the same revision set, and agree on current", () => {
  const fromPython = JSON.parse(python(
    "import json;from coa_client_extract.contracts import load_contract_registry;" +
    "r=load_contract_registry();print(json.dumps({'supported': sorted(r['supported']), 'current': r['current']}))"));
  const registry = loadContractRegistry();
  assert.deepEqual(Object.keys(registry.supported).sort(), fromPython.supported);
  assert.equal(registry.current, fromPython.current);
});

test("Node and Python require exactly the same children", () => {
  const fromPython = JSON.parse(python(
    "import json;from coa_client_extract.publish import CURRENT_REQUIRED_CHILDREN;" +
    "print(json.dumps(list(CURRENT_REQUIRED_CHILDREN)))"));
  assert.deepEqual(REQUIRED_CHILDREN, fromPython);
  assert.ok(REQUIRED_CHILDREN.includes(GENERATION_CONTRACT_CHILD));
});

test("the hand-mirrored name list is gone", () => {
  const src = fs.readFileSync(new URL("../scripts/lib/generation.mjs", import.meta.url), "utf8");
  assert.ok(!/REQUIRED_CHILDREN = \[/.test(src), "a mirrored constant is what drifts");
});

// --- Node's own contract self-validation (independent implementation, not a port) ---

test("the shipped contract is accepted unmodified", () => {
  const [revision, doc] = loadCurrentContract();
  assert.equal(validateGenerationContract(structuredClone(doc)).revision, revision);
});

const MALFORMED = [
  ["schema_version", (d) => { d.schema_version = "nope"; }, /schema_version/],
  ["extra top-level key", (d) => { d.smuggled = 1; }, /smuggled/],
  ["empty revision", (d) => { d.revision = ""; }, /revision/],
  ["unpinned wire schema", (d) => { d.observation_wire_schema = {}; }, /observation wire schema/],
  ["no children", (d) => { d.children = {}; }, /no children/],
  ["bad kind", (d) => { d.children["spell_layout_v2.json"].kind = "parquet"; }, /kind/],
  ["empty shape", (d) => { d.children["spell_layout_v2.json"].shape = ""; }, /shape/],
  ["extra child key", (d) => { d.children["spell_layout_v2.json"].unexpected = 1; }, /keys/],
  ["missing child key", (d) => { delete d.children["spell_layout_v2.json"].optional; }, /keys/],
  ["non-boolean optional", (d) => { d.children["spell_layout_v2.json"].optional = "yes"; }, /optional/],
  ["jsonl without row schema", (d) => { d.children["coa_client_spell.jsonl"].row_schema_version = null; }, /row_schema_version/],
  ["json with a row schema", (d) => { d.children["spell_layout_v2.json"].row_schema_version = "x"; }, /row_schema_version/],
  ["reused shape", (d) => { d.children.dupe = structuredClone(d.children["spell_layout_v2.json"]); }, /reused/],
  ["traversal child name", (d) => { d.children["../escape.json"] = d.children["spell_layout_v2.json"]; }, /unsafe child name/],
  ["separator in child name", (d) => { d.children["sub/dir.json"] = d.children["spell_layout_v2.json"]; }, /unsafe child name/],
  ["boolean floor", (d) => { d.children["coa_client_content.jsonl"].cardinality = { rule: "min", min: true }; }, /min/],
  ["zero floor", (d) => { d.children["coa_client_content.jsonl"].cardinality = { rule: "min", min: 0 }; }, /min/],
  ["float floor", (d) => { d.children["coa_client_content.jsonl"].cardinality = { rule: "min", min: 1.5 }; }, /min/],
  ["invented rule", (d) => { d.children["coa_client_content.jsonl"].cardinality.rule = "invented"; }, /rule/],
  ["contradictory cardinality", (d) => { d.children["spell_layout_v2.json"].cardinality = { rule: "single_document", source_table: "Spell" }; }, /cardinality/],
  ["empty source_table", (d) => { d.children["coa_client_advancement.jsonl"].cardinality.source_table = ""; }, /source_table/],
];

for (const [label, mutate, match] of MALFORMED) {
  test(`Node rejects a malformed contract: ${label}`, () => {
    const doc = structuredClone(loadCurrentContract()[1]);
    mutate(doc);
    assert.throws(() => validateGenerationContract(doc), match);
  });
}

test("an explicit positive floor is accepted", () => {
  const doc = structuredClone(loadCurrentContract()[1]);
  doc.children["coa_client_content.jsonl"].cardinality = { rule: "min", min: 5 };
  assert.ok(validateGenerationContract(doc));
});

const MALFORMED_REGISTRY = [
  ["schema_version", (d) => { d.schema_version = "nope"; }, /schema_version/],
  ["current not supported", (d) => { d.current = "e0r-v99"; }, /current/],
  ["no revisions", (d) => { d.supported = {}; }, /supported/],
  ["extra key", (d) => { d.smuggled = 1; }, /smuggled/],
  ["extra entry key", (d) => { d.supported["e0r-v1"].extra = 1; }, /path, sha256/],
  ["traversal path", (d) => { d.supported["e0r-v1"].path = "../escape.json"; }, /unsafe/],
  ["short digest", (d) => { d.supported["e0r-v1"].sha256 = "short"; }, /sha256/],
];

for (const [label, mutate, match] of MALFORMED_REGISTRY) {
  test(`Node rejects a malformed registry: ${label}`, () => {
    const doc = structuredClone(loadContractRegistry());
    mutate(doc);
    assert.throws(() => validateContractRegistry(doc), match);
  });
}

test("every supported revision file still hashes to its pinned digest", () => {
  const registry = loadContractRegistry();
  const dir = new URL("../../coa_client_extract/data/generation_contracts/", import.meta.url);
  for (const [revision, entry] of Object.entries(registry.supported)) {
    const doc = JSON.parse(fs.readFileSync(new URL(entry.path, dir), "utf8"));
    assert.equal(generationContractSha256(doc), entry.sha256,
      `${revision} was edited in place; add a new revision instead`);
    assert.equal(doc.revision, revision);
  }
});

// --- the three-way comparison in the candidate validator ---

test("a complete candidate with a staged, bound, supported contract passes", () => {
  const { genDir, lockPath } = buildCandidate();
  assert.doesNotThrow(() => validateCandidateByPath(genDir, { lockPath }));
});

test("a candidate without the staged contract child is rejected", () => {
  const { genDir, lockPath } = buildCandidate({ drop: [GENERATION_CONTRACT_CHILD] });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /generation_contract\.json missing/);
});

test("a staged contract that differs from the bound hash is rejected", () => {
  const { genDir, lockPath } = buildCandidate({
    bindOverride: { schema_version: "coa-generation-contract-v1", revision: "e0r-v1", sha256: "0".repeat(64) },
  });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /generation_contract/);
});

test("a binding naming a different revision than the staged child is rejected", () => {
  const [, doc] = loadCurrentContract();
  const { genDir, lockPath } = buildCandidate({
    bindOverride: { schema_version: "coa-generation-contract-v1", revision: "e0r-v99",
                    sha256: generationContractSha256(doc) },
  });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /bound revision/);
});

test("a generation with no contract binding at all is rejected", () => {
  const { genDir, lockPath } = buildCandidate({ dropBinding: true });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /does not bind it/);
});

test("a generation bound to an unsupported contract is rejected", () => {
  const { genDir, lockPath } = buildCandidate({ contractMutate: (d) => { d.revision = "made-up-v9"; } });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /not the supported contract/);
});

test("a staged contract edited under a supported revision is rejected", () => {
  const { genDir, lockPath } = buildCandidate({
    contractMutate: (d) => { delete d.children["coa_client_essence.jsonl"]; },
  });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /not the supported contract/);
});

test("a structurally broken staged contract is rejected as malformed", () => {
  const { genDir, lockPath } = buildCandidate({ contractMutate: (d) => { d.children.bad = "nope"; } });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /spec must be an object/);
});

test("rewriting the bound hash after the fact breaks the trust digest", () => {
  const { genDir, lockPath } = buildCandidate();
  const manifestPath = path.join(genDir, "manifest.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  manifest.binding.generation_contract.sha256 = "0".repeat(64);
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /candidate_trust_sha256/);
});

// --- membership, not equality with `current` ---

test("a generation under a non-current but supported revision still validates", (t) => {
  const { contractsDir, v1 } = writeTwoRevisionRegistry(path.join(tmpdir(t), "generation_contracts"));
  const { genDir, lockPath } = buildCandidate({ contract: ["e0r-v1", v1] });
  assert.equal(loadCurrentContract(contractsDir)[0], "e0r-v2");   // NOT the revision the generation uses
  assert.doesNotThrow(() => validateCandidateByPath(genDir, { lockPath, contractsDir }));
});

test("a revision dropped from the registry stops resolving", (t) => {
  const dir = path.join(tmpdir(t), "generation_contracts");
  const { contractsDir, v1 } = writeTwoRevisionRegistry(dir);
  const { genDir, lockPath } = buildCandidate({ contract: ["e0r-v1", v1] });

  const indexPath = path.join(dir, "index.json");
  const index = JSON.parse(fs.readFileSync(indexPath, "utf8"));
  delete index.supported["e0r-v1"];
  fs.writeFileSync(indexPath, JSON.stringify(index, null, 2));
  assert.throws(() => validateCandidateByPath(genDir, { lockPath, contractsDir }),
    (e) => e instanceof GenerationResolveError && /not the supported contract/.test(e.message));
});

// --- T2.1: policy-rooted cardinality, mirrored (independent implementation, same rules) ---

test("Node accepts the honest candidate the cardinality cases mutate", () => {
  const { genDir, lockPath } = buildCandidate();
  assert.doesNotThrow(() => validateCandidateByPath(genDir, { lockPath }));
});

test("Node rejects a truncated full child against the reviewed bound", () => {
  const corpus = loadCorpus();
  // Size the policy to THREE spells, then stage two: the correspondence is broken on purpose.
  const policy = bindPolicyDoc(corpus.policy, { spellRecords: 3 });
  const { genDir, lockPath } = buildCandidate({ policy, full: corpus.validFull().slice(0, 2),
                                                proj: corpus.validProj().slice(0, 2),
                                                icons: corpus.validIcons().slice(0, 2) });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /reviewed_bound_record_count/);
});

for (const child of ["coa_client_class_types.jsonl", "coa_client_tab_types.jsonl",
                     "coa_client_essence.jsonl"]) {
  test(`Node gates the one-to-one ancillary child ${child}`, () => {
    const { genDir, lockPath } = buildCandidate({ truncateChild: [child, 1] });
    assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /derived_from_source_topology/);
  });
}

test("Node rejects a declared derivation whose accounting does not close", () => {
  const { genDir, lockPath } = buildCandidate({
    derivations: { "coa_client_advancement.jsonl": { source: "CharacterAdvancement", kept: 2, rejected: 0 },
                   "coa_client_content.jsonl": { source: "content_json", source_entries: 2, kept: 2, rejected: 0 } },
  });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /declared_derivation/);
});

test("Node rejects a content derivation that disagrees with the reviewed source entries", () => {
  const { genDir, lockPath } = buildCandidate({
    derivations: { "coa_client_advancement.jsonl": { source: "CharacterAdvancement", kept: 2, rejected: 1 },
                   "coa_client_content.jsonl": { source: "content_json", source_entries: 99, kept: 2, rejected: 0 } },
  });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /declared_content_derivation/);
});

test("Node rejects a candidate that rewrites its own topology to match a truncation", () => {
  const corpus = loadCorpus();
  const policy = bindPolicyDoc(corpus.policy, { spellRecords: 3 });
  const topology = topologyReportFor(policy);
  topology.tables.Spell.header = { ...topology.tables.Spell.header, record_count: 1 };
  const { genDir, lockPath } = buildCandidate({ policy, topology,
                                                full: corpus.validFull().slice(0, 1),
                                                proj: corpus.validProj().slice(0, 1),
                                                icons: corpus.validIcons().slice(0, 1) });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }),
    /topology does not match the reviewed bound/);
});

test("Node rejects a manifest policy hash that disagrees with the staged policy", () => {
  const corpus = loadCorpus();
  const policy = bindPolicyDoc(corpus.policy, { spellRecords: 3 });
  const { genDir, lockPath } = buildCandidate({ policy,
                                                mutateManifest: (m) => { m.binding.policy_sha256 = "0".repeat(64); } });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /binding\.policy_sha256/);
});

test("Node rejects an unbound staged policy", () => {
  const corpus = loadCorpus();
  const bound = bindPolicyDoc(corpus.policy, { spellRecords: 3 });
  const topology = topologyReportFor(bound);      // captured before the bound is removed
  const unbound = unbindPolicyDoc(bound);         // rehashed, so the lock still matches it honestly
  const { genDir, lockPath } = buildCandidate({ policy: unbound, topology });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /unbound/);
});

test("Node rejects an unregistered child", () => {
  const { genDir, lockPath } = buildCandidate({ extraChild: ["smuggled.jsonl", '{"x":1}\n'] });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /unregistered child/);
});

test("Node rejects a JSON child carrying two concatenated documents", () => {
  const { genDir, lockPath } = buildCandidate({ duplicateJsonDocument: "coa_client_archive_plan.json" });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /single_document/);
});

test("requiredChildrenFor reads the generation's own contract, not current", () => {
  const [, contract] = loadCurrentContract();
  const older = structuredClone(contract);
  older.children = { [GENERATION_CONTRACT_CHILD]: contract.children[GENERATION_CONTRACT_CHILD],
                     "spell_layout_v2.json": contract.children["spell_layout_v2.json"] };
  assert.deepEqual(requiredChildrenFor(older), [GENERATION_CONTRACT_CHILD, "spell_layout_v2.json"]);

  const relaxed = structuredClone(contract);
  relaxed.children["coa_client_essence.jsonl"].optional = true;
  assert.ok(!requiredChildrenFor(relaxed).includes("coa_client_essence.jsonl"));
});
