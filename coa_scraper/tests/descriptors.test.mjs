// coa_scraper/tests/descriptors.test.mjs
// E0R.2 T6.1 — kind-aware field descriptors, derived HERE and cross-checked against the policy.
//
// The consumer must derive the expected descriptor itself. A descriptor defines what every hoisted cell
// MEANS, so a staged one taken on its own word could redefine a field's substrate while compact->rich
// expansion stayed perfectly self-consistent — the producer and the consumer would agree on a lie.
//
// This is the EXPAND half: both encodings (with and without the inline policy_ref/join_name) expand to
// the same rich observation, so T6.2 can migrate the producer without a flag day.
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { DescriptorError, FIELD_DESCRIPTORS_SCHEMA, buildFieldDescriptors, expandCompact,
         requireFieldDescriptors } from "../scripts/lib/mechanics-projection.mjs";
import { validateCandidateByPath } from "../scripts/lib/generation.mjs";
import { buildCandidate } from "./helpers/candidate.mjs";

const CORPUS = path.join(fileURLToPath(new URL("../../tests/golden/e0r1_corpus/", import.meta.url)));

function policyDoc() {
  return JSON.parse(fs.readFileSync(path.join(CORPUS, "policy.json"), "utf8"));
}

function fullRows() {
  return fs.readFileSync(path.join(CORPUS, "full_rows.jsonl"), "utf8").split("\n")
    .filter((l) => l.trim()).map((l) => JSON.parse(l)).filter((r) => r.case === "valid_full");
}

// The same cell with everything a descriptor supplies removed — the T6.2 encoding, read here.
function strip(cell) {
  const out = {};
  for (const [k, v] of Object.entries(cell)) {
    if (k === "policy_ref" || k === "join_name") continue;
    if (k === "components") {
      out.components = {};
      for (const [ck, cv] of Object.entries(v)) {
        out.components[ck] = Object.fromEntries(
          Object.entries(cv).filter(([kk]) => kk !== "policy_ref"));
      }
      continue;
    }
    out[k] = v;
  }
  return out;
}

test("the descriptor covers every scalar field and every join, bound to the policy digest", () => {
  const doc = policyDoc();
  const d = buildFieldDescriptors(doc);
  assert.equal(d.schema_version, FIELD_DESCRIPTORS_SCHEMA);
  assert.equal(d.policy_sha256, doc.sha256);
  assert.deepEqual(Object.keys(d.fields).sort(),
                   [...new Set([...Object.keys(doc.tables.Spell.fields), ...Object.keys(doc.joins)])].sort());
});

test("a join descriptor carries the index pointer AND all three component pointers", () => {
  // One policy_ref cannot reconstruct a resolved join: its components point at three different
  // table-fields through the join mapping, and there is no synthetic /joins/... policy node.
  assert.deepEqual(buildFieldDescriptors(policyDoc()).fields.cast_time_ms, {
    kind: "join", join_name: "cast_time_ms",
    index_policy_ref: "/tables/Spell/fields/casting_time_index",
    components: {
      index: { policy_ref: "/tables/Spell/fields/casting_time_index" },
      side_id: { policy_ref: "/tables/SpellCastTimes/fields/id" },
      side_value: { policy_ref: "/tables/SpellCastTimes/fields/base_ms" },
    },
  });
});

test("a scalar descriptor is just its field pointer", () => {
  assert.deepEqual(buildFieldDescriptors(policyDoc()).fields.power_type,
                   { kind: "scalar", policy_ref: "/tables/Spell/fields/power_type" });
});

test("a hoisted cell expands to exactly what the fat cell expands to, for all three shapes", () => {
  const doc = policyDoc();
  const descriptors = buildFieldDescriptors(doc);
  const shapes = new Set();
  for (const row of fullRows()) {
    for (const [field, cell] of Object.entries(row.raw)) {
      shapes.add(!("join_name" in cell) ? "scalar"
                 : !("components" in cell) ? "join_absent" : "join_resolved");
      const fat = expandCompact(cell, doc, { field, descriptors });
      const thin = expandCompact(strip(cell), doc, { field, descriptors });
      assert.deepEqual(thin, fat, field);
    }
  }
  assert.deepEqual([...shapes].sort(), ["join_absent", "join_resolved", "scalar"],
                   "the corpus must exercise the resolved-join path E1 will reach");
});

test("a fat cell still expands with no descriptors at all", () => {
  // T6.1 EXPANDS. If the old encoding stopped working here the tree could not stay green until T6.2.
  const doc = policyDoc();
  for (const row of fullRows()) {
    for (const [field, cell] of Object.entries(row.raw)) {
      assert.deepEqual(expandCompact(cell, doc),
                       expandCompact(cell, doc, { field, descriptors: buildFieldDescriptors(doc) }));
    }
  }
});

test("a hoisted cell without a descriptor is refused rather than guessed", () => {
  const doc = policyDoc();
  const cell = strip(fullRows()[0].raw.power_type);
  assert.throws(() => expandCompact(cell, doc, { field: "power_type" }), DescriptorError);
});

test("the honest descriptor is accepted", () => {
  const doc = policyDoc();
  assert.doesNotThrow(() => requireFieldDescriptors(buildFieldDescriptors(doc), doc));
});

for (const [name, mutate, match] of [
  ["a redefined scalar pointer", (d) => { d.fields.power_type.policy_ref = "/tables/Spell/fields/school_mask"; }, /power_type/],
  ["a missing field", (d) => { delete d.fields.school_mask; }, /school_mask/],
  ["an invented field", (d) => { d.fields.invented = { kind: "scalar", policy_ref: "/x" }; }, /invented/],
  ["a redefined component pointer", (d) => { d.fields.cast_time_ms.components.side_value.policy_ref = "/tables/SpellDuration/fields/base_ms"; }, /cast_time_ms/],
  ["a join demoted to a scalar", (d) => { d.fields.cast_time_ms = { kind: "scalar", policy_ref: "/x" }; }, /cast_time_ms/],
  ["another policy's digest", (d) => { d.policy_sha256 = "0".repeat(64); }, /policy_sha256/],
  ["another schema", (d) => { d.schema_version = "coa-client-spell-fields-v0"; }, /schema_version/],
]) {
  test(`a staged descriptor with ${name} is rejected`, () => {
    const doc = policyDoc();
    const staged = buildFieldDescriptors(doc);
    mutate(staged);
    assert.throws(() => requireFieldDescriptors(staged, doc), match);
  });
}

// === E0R.2 T6.2 — the generation-level gate ======================================================
// A staged decoder is checked against what this validator derives, not read. Independently of Python:
// two boundaries agreeing only because one told the other is not agreement.

test("a generation whose staged descriptor disagrees with its policy is rejected", () => {
  const { genDir, lockPath } = buildCandidate({
    forgeDescriptors: (d) => { d.fields.power_type.policy_ref = "/tables/Spell/fields/school_mask"; } });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /power_type/);
});

test("a generation whose staged wire schema renumbers a code is rejected", () => {
  // The sharpest case: renumbering `present` changes what EVERY cell in the artifact says, at once,
  // with every hash still valid.
  const { genDir, lockPath } = buildCandidate({ forgeWire: (w) => { w.states.present = 7; } });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /states/);
});

test("the honest generation validates", () => {
  const { genDir, lockPath } = buildCandidate();
  assert.doesNotThrow(() => validateCandidateByPath(genDir, { lockPath }));
});
