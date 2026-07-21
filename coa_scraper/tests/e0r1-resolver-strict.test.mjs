// coa_scraper/tests/e0r1-resolver-strict.test.mjs
// E0R.1 T3.2 — the Node resolver (resolveGeneration) resolves ONLY a fully-published E0R generation, the
// identical gate to Python resolve_active_generation: a pre-v3 manifest, a non-published state, a trust
// digest that does not cover the manifest, a `validation` that is not both python+node true, a not-within-
// budget report, or a missing required child is REJECTED.
import { test } from "node:test";
import assert from "node:assert";
import { resolveGeneration } from "../scripts/lib/generation.mjs";
import { buildCandidate } from "./helpers/candidate.mjs";

test("a valid published generation resolves", () => {
  const { root } = buildCandidate({ publish: true });
  assert.doesNotThrow(() => resolveGeneration(root));
});

test("a pre-v3 manifest is rejected", () => {
  const { root } = buildCandidate({ publish: true, mutatePublished: (m) => { m.schema_version = "coa-client-extract-manifest-v2"; } });
  assert.throws(() => resolveGeneration(root), /requires v3/);
});

test("a non-published state is rejected", () => {
  const { root } = buildCandidate({ publish: true, mutatePublished: (m) => { m.publication_state = "draft"; } });
  assert.throws(() => resolveGeneration(root), /not published/);
});

test("a trust digest that does not cover the manifest is rejected", () => {
  const { root } = buildCandidate({ publish: true, mutatePublished: (m) => { m.candidate_trust_sha256 = "0".repeat(64); } });
  assert.throws(() => resolveGeneration(root), /candidate_trust_sha256 does not cover/);
});

test("validation not both python+node true is rejected", () => {
  const { root } = buildCandidate({ publish: true, validation: { python: true, node: false } });
  assert.throws(() => resolveGeneration(root), /not validated by both/);
});

test("an over-budget generation is rejected", () => {
  const { root } = buildCandidate({ publish: true, budget: { within_budget: false } });
  assert.throws(() => resolveGeneration(root), /exceeded its budget/);
});

test("a missing required child is rejected", () => {
  // `drop` builds the manifest (and its trust digest) WITHOUT the child, so the required-child gate — not a
  // child-integrity error or a trust mismatch — is what surfaces.
  const { root } = buildCandidate({ publish: true, drop: ["coa_client_essence.jsonl"] });
  assert.throws(() => resolveGeneration(root), /required child coa_client_essence\.jsonl missing/);
});
