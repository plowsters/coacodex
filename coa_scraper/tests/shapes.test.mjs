// coa_scraper/tests/shapes.test.mjs
// E0R.2 T2.2 — Node's shape validators, held to the SAME golden documents as Python's.
//
// The two implementations are independent; the documents are not. That is what makes their agreement
// mean something: a shared serialization would reproduce a shared bug, but a shared corpus catches a
// divergence in either direction. Writing this suite is what surfaced the join-`decoded` variance (a
// join's decoded value is a bare scalar, a scalar's is an envelope) that Python's structure hid.
import test from "node:test";
import assert from "node:assert/strict";
import { SHAPES, ShapeError } from "../scripts/lib/shapes.mjs";
import { loadContractRegistry, loadSupportedContract } from "../scripts/lib/generation.mjs";
import fs from "node:fs";
const WIRE_REASONS = JSON.parse(fs.readFileSync(
  new URL("../../coa_client_extract/data/observation_wire_schema.json", import.meta.url),
  "utf8")).decoded_reasons;
import { goldenDocuments, goldenRows, producerSpellRows } from "./helpers/golden.mjs";

const SHAPE_NAMES = Object.keys(SHAPES).sort();

test("every SUPPORTED revision's shapes are implemented, and nothing else is", () => {
  // E0R.2 T6.2: the union over SUPPORTED revisions, not just `current`. A revision stays in the
  // registry so generations published under it remain resolvable — which is only true if the shapes it
  // names are still implemented. `full_spell_row_v3` is exactly that case: retired from the current
  // contract, retained here.
  const registry = loadContractRegistry();
  const contracted = new Set();
  for (const [revision, entry] of Object.entries(registry.supported)) {
    const contract = loadSupportedContract(revision, entry.sha256);
    for (const spec of Object.values(contract.children)) contracted.add(spec.shape);
  }
  assert.deepEqual([...contracted].sort(), SHAPE_NAMES);
  assert.ok(contracted.has("full_spell_row_v3"), "a supported revision's shape may never be deleted");
});

test("Node implements exactly the shapes Python implements", () => {
  // The golden dump is keyed by Python's SHAPES; neither language may quietly stop checking a child
  // the other still checks.
  assert.deepEqual(Object.keys(goldenDocuments().shapes).sort(), SHAPE_NAMES);
});

for (const shape of SHAPE_NAMES) {
  test(`${shape} accepts its golden document`, () => {
    SHAPES[shape](goldenRows(shape));
  });

  test(`${shape} rejects an unknown key`, () => {
    const doc = goldenRows(shape);
    doc.smuggled = 1;
    assert.throws(() => SHAPES[shape](doc), /smuggled/);
  });

  test(`${shape} rejects a non-object`, () => {
    assert.throws(() => SHAPES[shape]([]), ShapeError);
  });
}

test("the producer rows satisfy the same shapes as the corpus", () => {
  const { full, projection, icon } = producerSpellRows();
  SHAPES.full_spell_row_v4(full);
  SHAPES.projection_row_v3(projection);
  SHAPES.icon_row_v1(icon);
});

// --- the `{}` hole ---

for (const shape of ["archive_plan_v1", "projection_manifest_v3", "spell_policy_v2",
                     "generation_contract_v1"]) {
  test(`an empty JSON document is not a valid ${shape}`, () => {
    assert.throws(() => SHAPES[shape]({}), ShapeError);
  });
}

test("an archive plan without an ordering rule is rejected", () => {
  const doc = goldenRows("archive_plan_v1");
  delete doc.ordering_rule;
  assert.throws(() => SHAPES.archive_plan_v1(doc), /ordering_rule/);
});

test("an unreviewed policy may not be staged", () => {
  const doc = goldenRows("spell_policy_v2");
  doc.reviewed = false;
  assert.throws(() => SHAPES.spell_policy_v2(doc), /reviewed/);
});

// --- observation envelopes ---

test("a full row with a malformed raw envelope is rejected", () => {
  const row = goldenRows("full_spell_row_v3");
  row.raw = { id: { state: "present" } };
  assert.throws(() => SHAPES.full_spell_row_v3(row), /raw\.id/);
});

test("a full row with no observations at all is rejected", () => {
  const row = goldenRows("full_spell_row_v3");
  row.raw = {};
  assert.throws(() => SHAPES.full_spell_row_v3(row), /not lossless/);
});

test("an observation outside the closed vocabulary is rejected", () => {
  const row = goldenRows("full_spell_row_v3");
  row.raw.id.state = "candidate";      // a publication_state, never an observation state
  assert.throws(() => SHAPES.full_spell_row_v3(row), /closed vocabulary/);
});

test("a compact full row may not carry rich proof", () => {
  const row = goldenRows("full_spell_row_v3");
  row.raw.id.proof = { integrity: "verified", layout: "verified", interpretation: "verified" };
  assert.throws(() => SHAPES.full_spell_row_v3(row), /proof/);
});

test("a projection row with a malformed proof is rejected", () => {
  const { projection } = producerSpellRows();
  projection.field_observations.id.proof = { integrity: "verified" };
  assert.throws(() => SHAPES.projection_row_v3(projection), /proof/);
});

test("a join observation with an invented component is rejected", () => {
  const { projection } = producerSpellRows();
  const join = projection.field_observations.cast_time_ms;
  join.components.invented = join.components.index;
  assert.throws(() => SHAPES.projection_row_v3(projection), /invented/);
});

test("a join's decoded value is a bare scalar, never an envelope", () => {
  // The variance that a transcribed implementation would have got wrong in both languages at once.
  const { projection } = producerSpellRows();
  projection.field_observations.cast_time_ms.decoded = { kind: "int32", value: 1500 };
  assert.throws(() => SHAPES.projection_row_v3(projection), /bare scalar/);
});

test("a string observation may resolve to null but not to a number", () => {
  const row = goldenRows("full_spell_row_v3");
  row.raw.name.resolved = null;
  SHAPES.full_spell_row_v3(row);       // an unresolved string is a recorded observation
  row.raw.name.resolved = 7;
  assert.throws(() => SHAPES.full_spell_row_v3(row), /resolved/);
});

// --- mechanics nullability ---

test("mechanics values may be null but the keys may not be absent", () => {
  const { full } = producerSpellRows();
  for (const key of Object.keys(full.mechanics)) full.mechanics[key] = null;
  SHAPES.full_spell_row_v4(full);
  full.mechanics.power_type = "3";
  assert.throws(() => SHAPES.full_spell_row_v4(full), /power_type/);
});

test("a domain-gated school_mask row is structurally valid", () => {
  const { full } = producerSpellRows();
  full.mechanics.school_mask = null;
  full.raw.school_mask.d = WIRE_REASONS.value_out_of_domain;   // v4: the interned code, not the name
  SHAPES.full_spell_row_v4(full);
});

// --- ancillary rows ---

test("an attribution without is_coa is rejected", () => {
  const row = goldenRows("advancement_row_v1");
  delete row.coa_attribution.is_coa;
  assert.throws(() => SHAPES.advancement_row_v1(row), /is_coa/);
});

test("a raw cols map keyed by a name is rejected", () => {
  const row = goldenRows("essence_row_v1");
  row.cols = { required_level: 60 };
  assert.throws(() => SHAPES.essence_row_v1(row), /decimal cell index/);
});

test("a content row missing its provenance digest is rejected", () => {
  const row = goldenRows("content_row_v1");
  delete row.provenance.file_sha256;
  assert.throws(() => SHAPES.content_row_v1(row), /file_sha256/);
});

test("a class type row with a non-integer id is rejected", () => {
  const row = goldenRows("class_type_row_v1");
  row.class_type_id = "14";
  assert.throws(() => SHAPES.class_type_row_v1(row), /class_type_id/);
});

test("a tab type row with a float id is rejected", () => {
  const row = goldenRows("tab_type_row_v1");
  row.tab_type_id = 1.5;
  assert.throws(() => SHAPES.tab_type_row_v1(row), /tab_type_id/);
});
