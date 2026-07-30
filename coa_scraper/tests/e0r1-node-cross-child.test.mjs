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

// --- E0R.2 T6.3: the RELATIONAL icon rules, mirrored from Python and derived independently ---
// The v1 id/path cases these replace described a dialect that no longer exists: `asset_status` became an
// ASSET row's availability, and `converted`/`converted_ref` have no key to appear in.
test("a null reference claiming `available` FAILS", () => {
  const icons = corpus.validIconsV2();
  icons[1] = corpus.pick(corpus.iconsV2, "null_ref_claims_available")[0];   // spell 2
  assert.throws(run({ icons }), /readiness/);
});

test("a dangling asset_ref FAILS", () => {
  const icons = corpus.validIconsV2();
  icons[0] = corpus.pick(corpus.iconsV2, "dangling_asset_ref")[0];
  assert.throws(run({ icons }), /dangling asset_ref/);
});

test("a reference whose decoded_reason is not `decoded` FAILS", () => {
  const icons = corpus.validIconsV2();
  icons[0] = corpus.pick(corpus.iconsV2, "ref_with_undecoded_reason")[0];
  assert.throws(run({ icons }), /only a decoded join yields a path/);
});

// --- E0R.2 T8.1: the FIFTH null cause, found by the first real-client regenerate under e0r-v3 ---
// The client's SpellIcon row 1 exists, is proven, and its path string is EMPTY. Not `index_zero` (the
// FK is nonzero), not `side_row_missing` (the row is there), not `proof_withheld` (the join decoded):
// the path is provably nothing, which is what `verified_empty` says. Derived here independently of
// Python — the whole point of two boundaries.
test("a decoded reference whose proven path is EMPTY passes as `verified_empty`", () => {
  const icons = corpus.validIconsV2();
  icons[0] = corpus.pick(corpus.iconsV2, "verified_empty_path")[0];         // spell 1
  // The asset it no longer references must go too, or the orphan rule (correctly) fires instead.
  const iconAssets = corpus.validIconAssets()
    .filter((a) => a.asset_id !== corpus.validIconsV2()[0].asset_ref);
  assert.doesNotThrow(run({ icons, iconAssets }));
});

test("a decoded null reference that does NOT claim emptiness still FAILS", () => {
  // The exact contradiction the producer used to emit — the original invariant survives intact.
  const icons = corpus.validIconsV2();
  icons[0] = corpus.pick(corpus.iconsV2, "decoded_null_without_emptiness_claim")[0];
  assert.throws(run({ icons }), /verified_empty/);
});

test("an UNRESOLVED row may not claim emptiness", () => {
  // `verified_empty` means "I read it and it was empty"; side_row_missing never read it at all.
  const icons = corpus.validIconsV2();
  icons[0] = corpus.pick(corpus.iconsV2, "unresolved_claims_emptiness")[0];
  assert.throws(run({ icons }), /verified_empty/);
});

test("a row may not both reference an asset and claim its path is empty", () => {
  const icons = corpus.validIconsV2();
  icons[0] = corpus.pick(corpus.iconsV2, "reference_claims_emptiness")[0];
  assert.throws(run({ icons }), /verified_empty/);
});

test("an orphan asset row FAILS", () => {
  // The other direction from `no dangling`, and what makes the two children mutually determined.
  const iconAssets = [...corpus.validIconAssets(), corpus.pick(corpus.iconAssets, "orphan_asset")[0]]
    .sort((a, b) => (a.asset_id < b.asset_id ? -1 : 1));
  assert.throws(run({ iconAssets }), /referenced by no spell/);
});

// --- exact icon domain (trailing / extra / missing) ---
test("a trailing icon row beyond the full domain FAILS", () => {
  const icons = [...corpus.validIconsV2(), corpus.pick(corpus.iconsV2, "trailing_icon_beyond_domain")[0]];
  assert.throws(run({ icons }), /icons_agree/);
});

test("a missing icon row (catalog shorter than the full table) FAILS", () => {
  const icons = corpus.validIconsV2().slice(0, 2);       // drop spell 3's icon
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
