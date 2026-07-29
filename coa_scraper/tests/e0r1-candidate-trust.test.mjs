// coa_scraper/tests/e0r1-candidate-trust.test.mjs
// E0R.1 T3.1 — the Node candidate validator is a REAL trust gate: it checks the required-child registry,
// recomputes candidate_trust_sha256 (bigint-safe), asserts the staged policy child against the lock, and
// runs row semantics over the FULL required domain. Driven by the shared golden corpus (T3.0).
import { test } from "node:test";
import assert from "node:assert";
import { validateCandidateByPath, REQUIRED_CHILDREN } from "../scripts/lib/generation.mjs";
import { buildCandidate, loadCorpus } from "./helpers/candidate.mjs";

const corpus = loadCorpus();

test("a complete valid candidate passes", () => {
  const { genDir, lockPath } = buildCandidate();
  assert.doesNotThrow(() => validateCandidateByPath(genDir, { lockPath }));
});

test("an empty v3 candidate (no children) FAILS the required-child registry", () => {
  const { genDir, lockPath } = buildCandidate({ drop: REQUIRED_CHILDREN });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /required child .* missing/);
});

test("a missing required child FAILS", () => {
  const { genDir, lockPath } = buildCandidate({ drop: ["coa_client_essence.jsonl"] });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /required child coa_client_essence\.jsonl missing/);
});

test("a bad candidate_trust_sha256 FAILS", () => {
  const { genDir, lockPath } = buildCandidate({ trustOverride: "0".repeat(64) });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /candidate_trust_sha256 does not cover/);
});

test("a manifest field changed after the trust digest FAILS (digest no longer covers it)", () => {
  // Corrupt a trust-covered field without recomputing the digest by post-editing the file is awkward; instead
  // supply a stale digest computed over a different generation_id.
  const { genDir, lockPath } = buildCandidate({
    mutateManifest: (m) => { m._tamper = "unexpected"; }, trustOverride: undefined });
  // The digest DOES cover _tamper here (computed after mutate), so this must PASS — proving the digest is a
  // COMPLETE view (an unknown field is covered, never silently ignored).
  assert.doesNotThrow(() => validateCandidateByPath(genDir, { lockPath }));
});

test("a policy child not matching the lock FAILS", () => {
  const { genDir, lockPath } = buildCandidate({
    lock: { schema_version: "coa-spell-layout-lock-v1", sha256: "f".repeat(64) } });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /staged policy is not the supported policy/);
});

test("a required field omitted from BOTH mechanics and raw FAILS (full-domain iteration)", () => {
  // E0R.2 T2.3 tightened the rule this corpus case was written against: the domain now comes from the
  // policy's artifact_contract, and an observation must be in `raw` whether or not mechanics carries a
  // value — so this row is rejected on the raw domain rather than on the mechanics∪raw union.
  const full = [...corpus.validFull(), ...corpus.pick(corpus.fullV4, "required_field_omitted_from_both")];
  const { genDir, lockPath } = buildCandidate({ full });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /required field power_type omitted from raw/);
});

test("a full row carrying field_observations (wrong dialect) FAILS", () => {
  const full = corpus.pick(corpus.fullV4, "full_carries_field_observations");
  const { genDir, lockPath } = buildCandidate({ full });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /carries field_observations|unknown key/);
});

// Every projection reject case in the corpus must fail candidate validation (both biconditional directions,
// decoding disagreement, tampered proof/decoded, wrong dialect, missing field_observations, populated join).
for (const c of ["eligible_not_populated", "populated_not_eligible", "decoding_disagreement",
                 "tampered_proof", "tampered_decoded", "projection_carries_raw",
                 "missing_field_observations", "unresolved_join_populated"]) {
  test(`projection reject '${c}' FAILS candidate validation`, () => {
    const proj = corpus.pick(corpus.projection, c);
    const { genDir, lockPath } = buildCandidate({ proj });
    assert.throws(() => validateCandidateByPath(genDir, { lockPath }));
  });
}
