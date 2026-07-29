// coa_scraper/tests/e0r1-node-cross-child.test.mjs
// E0R.1 T3.1b — the Node candidate validator runs the streaming cross-child + bundle checks (mirroring
// Python publish._cross_child/_icon_bundle): per-child sorted uniqueness + exact icon domain, projection ⊆
// is_coa, disjoint v3 dialects, identity/attribution agreement, compact_raw_expands_to_envelope, and icon
// id/path agreement. Driven by the shared golden corpus (T3.0).
import { test } from "node:test";
import assert from "node:assert";
import { validateCandidateByPath } from "../scripts/lib/generation.mjs";
import { buildCandidate, loadCorpus } from "./helpers/candidate.mjs";

const corpus = loadCorpus();
const clone = (x) => structuredClone(x);
const run = (opts) => { const { genDir, lockPath } = buildCandidate(opts); return () => validateCandidateByPath(genDir, { lockPath }); };

test("the valid baseline passes cross-child", () => {
  assert.doesNotThrow(run({}));
});

// --- icon id/path agreement + bundle consistency (corpus reject rows, domain preserved) ---
test("placeholder icon carrying a client_path FAILS (id/path agreement)", () => {
  const icons = corpus.validIcons();
  icons[1] = corpus.pick(corpus.icons, "placeholder_with_path")[0];   // spell 2
  assert.throws(run({ icons }), /placeholder spell 2 carries a client_path/);
});

test("a converted icon row FAILS (E0R.2 T2.5: the status is prohibited outright)", () => {
  // The corpus case is named for the retired rule (a converted row needs a converted_ref); the stronger
  // rule that replaced it rejects the status itself, so the row still fails.
  const icons = corpus.validIcons();
  icons[0] = corpus.pick(corpus.icons, "converted_without_ref")[0];
  assert.throws(run({ icons }), /converted/);
});

test("a source_only icon row carrying a converted_ref FAILS", () => {
  // A bundle reference is unverifiable on ANY status: the shape has no such key, and verifyIconRow
  // restates the prohibition behind it.
  const icons = corpus.validIcons();
  icons[0] = corpus.pick(corpus.icons, "source_only_with_converted_ref")[0];
  assert.throws(run({ icons }), /converted_ref/);
});

// --- exact icon domain (trailing / extra / missing) ---
test("a trailing icon row beyond the full domain FAILS", () => {
  const icons = [...corpus.validIcons(), corpus.pick(corpus.icons, "trailing_icon_beyond_domain")[0]];
  assert.throws(run({ icons }), /icons_agree/);
});

test("a missing icon row (catalog shorter than the full table) FAILS", () => {
  const icons = corpus.validIcons().slice(0, 2);       // drop spell 3's icon
  assert.throws(run({ icons }), /icons_agree/);
});

// --- sorted uniqueness ---
test("a duplicate/out-of-order projection spell_id FAILS", () => {
  const proj = corpus.validProj();
  proj[2] = clone(proj[1]);                            // spell 2 repeated out of order after spell 2
  assert.throws(run({ proj }), /sorted_unique_ids/);
});

// --- identity / attribution agreement ---
test("a full/projection name disagreement FAILS", () => {
  const full = corpus.validFull();
  full[0] = clone(full[0]); full[0].name = "WRONG";    // full-level name only; raw + proj untouched
  assert.throws(run({ full }), /identity_agrees: spell 1 name differs/);
});

// --- compact_raw_expands_to_envelope ---
test("a full.raw that does not expand to the projection's field_observations FAILS", () => {
  const full = corpus.validFull();
  full[0] = clone(full[0]);
  // E0R.2 T2.3: the tamper must PRESERVE the observation domain (deleting the cell is now caught one
  // gate earlier, as loss), so this stays a test of expansion EQUALITY: same cells, different substrate.
  full[0].raw.power_type.raw_u32 = 99;
  assert.throws(run({ full }), /compact_raw_expands_to_envelope: spell 1/);
});

// --- projection ⊆ is_coa within domain ---
test("a projection row for a NON-is_coa full spell FAILS (outside domain)", () => {
  const full = corpus.validFull();
  full[1] = clone(full[1]); full[1].coa_attribution.is_coa = false;   // spell 2 no longer is_coa
  assert.throws(run({ full }), /projection_within_domain/);
});
