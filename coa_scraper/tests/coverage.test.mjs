// coa_scraper/tests/coverage.test.mjs
// E0R.2 T4.1 — field_readiness_coverage on the MECHANICS side.
//
// The manifest already carried `source_coverage` (per_field_winner_counts_by_source): which source won
// each field, for the rows that HAVE a winner. That says nothing about the fields with no source at all
// — the null-honest ones carrying a readiness reason — which is exactly the population a consumer needs
// to size before trusting the artifact.
//
// The denominator is rows x READINESS_FIELDS, not "the readiness entries we happened to emit". A row
// that silently stops carrying a readiness entry must show up as `absent`, not shrink the denominator
// until the percentage looks fine again.
import test from "node:test";
import assert from "node:assert/strict";
import { READINESS_FIELDS, fieldReadinessCoverage } from "../scripts/build-mechanics-artifacts.mjs";

const ready = (over = {}) => ({
  cooldown_ms: { status: "unavailable", reason_code: "pending_e1_operand" },
  gcd_ms: { status: "unavailable", reason_code: "pending_e1_operand" },
  costs: { status: "unavailable", reason_code: "pending_e1_operand" },
  ...over,
});

const row = (field_readiness) => ({ spell_id: 1, field_readiness });

test("the readiness field set is explicit and reviewable", () => {
  assert.deepEqual([...READINESS_FIELDS].sort(), ["cooldown_ms", "costs", "gcd_ms", "power_type"]);
});

test("the denominator is rows x fields, exactly", () => {
  const cov = fieldReadinessCoverage([row(ready()), row(ready())]);
  assert.equal(cov.rows, 2);
  assert.equal(cov.fields_considered, 2 * READINESS_FIELDS.length);
  assert.equal(Object.values(cov.statuses).reduce((a, b) => a + b, 0), cov.fields_considered);
  assert.equal(Object.values(cov.reason_codes).reduce((a, b) => a + b, 0), cov.fields_considered);
});

test("every field's parts sum to its own denominator", () => {
  const cov = fieldReadinessCoverage([row(ready()), row(ready({ power_type: { status: "unavailable", reason_code: "no_static_anchor" } }))]);
  for (const field of READINESS_FIELDS) {
    const f = cov.fields[field];
    assert.equal(f.considered, cov.rows, field);
    assert.equal(Object.values(f.statuses).reduce((a, b) => a + b, 0), f.considered, field);
    assert.equal(Object.values(f.reason_codes).reduce((a, b) => a + b, 0), f.considered, field);
  }
});

test("a field with no readiness entry is counted as absent, not dropped", () => {
  // The regression this denominator exists to catch: a row silently stops declaring readiness for a
  // field, and a "readiness entries we emitted" denominator shrinks with it so the ratio never moves.
  const cov = fieldReadinessCoverage([row(ready()), row(ready())]);
  assert.equal(cov.fields.power_type.statuses.absent, 2);
  assert.equal(cov.fields_considered, 2 * READINESS_FIELDS.length);
});

test("a declared status is counted under its own name and reason", () => {
  const cov = fieldReadinessCoverage([
    row(ready({ power_type: { status: "unavailable", reason_code: "no_static_anchor" } })),
    row(ready({ power_type: { status: "available", reason_code: "extracted" } })),
  ]);
  assert.deepEqual(cov.fields.power_type.statuses, { unavailable: 1, available: 1 });
  assert.deepEqual(cov.fields.power_type.reason_codes, { no_static_anchor: 1, extracted: 1 });
});

test("an empty build reports nothing rather than everything", () => {
  const cov = fieldReadinessCoverage([]);
  assert.equal(cov.rows, 0);
  assert.equal(cov.fields_considered, 0);
  assert.deepEqual(cov.statuses, {});
  for (const field of READINESS_FIELDS) assert.equal(cov.fields[field].considered, 0);
});

test("a readiness entry missing its reason_code is recorded, never silently counted as fine", () => {
  const cov = fieldReadinessCoverage([row(ready({ power_type: { status: "unavailable" } }))]);
  assert.equal(cov.fields.power_type.statuses.unavailable, 1);
  assert.equal(cov.fields.power_type.reason_codes.unspecified, 1);
});

test("readiness coverage is a different population from source coverage", () => {
  // source_coverage counts fields that HAVE a winning source; readiness coverage counts the fields that
  // do not. Reporting either as "coverage" without its denominator is the conflation this task splits.
  const cov = fieldReadinessCoverage([row(ready())]);
  assert.ok(!("per_field_winner_counts_by_source" in cov));
  assert.equal(cov.schema_version, "coa-mechanics-readiness-coverage-v1");
});
