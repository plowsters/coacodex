// coa_scraper/tests/mechanics-projection-e0r.test.mjs
import { test } from "node:test";
import assert from "node:assert";
import { verifyRowAgainstPolicy, assertPolicyLock } from "../scripts/lib/mechanics-projection.mjs";

const policy = { sha256: "abc", tables: { Spell: { fields: {
  power_type: { kind: "int32", layout: "verified", interpretation: "verified", promotion: "normalized" } } } } };

// The projection is the RICH dialect: a self-describing field observation carrying substrate + claims.
const ptObs = (over = {}) => ({
  state: "present", raw_u32: 3, decoded_reason: "decoded", policy_ref: "/tables/Spell/fields/power_type",
  proof: { integrity: "verified", layout: "verified", interpretation: "verified" },
  promotion: "normalized", decoded: { kind: "int32", value: 3 }, ...over });

test("rejects a numeric value that disagrees with a re-decode of its raw", () => {
  const row = { spell_id: 1, mechanics: { power_type: 5 }, field_observations: { power_type: ptObs() } };
  assert.throws(() => verifyRowAgainstPolicy(row, policy), /power_type.*re-decode/);
});

test("accepts a numeric value that matches the re-decode", () => {
  const row = { spell_id: 1, mechanics: { power_type: 3 }, field_observations: { power_type: ptObs() } };
  assert.doesNotThrow(() => verifyRowAgainstPolicy(row, policy));
});

test("rejects a projection row that still carries compact raw (no two v3 dialects)", () => {
  const row = { spell_id: 1, mechanics: { power_type: 3 },
    field_observations: { power_type: ptObs() }, raw: {} };
  assert.throws(() => verifyRowAgainstPolicy(row, policy), /carries compact raw/);
});

test("rejects a projection row missing field_observations", () => {
  const row = { spell_id: 1, mechanics: { power_type: 3 } };
  assert.throws(() => verifyRowAgainstPolicy(row, policy), /missing field_observations/);
});

test("rejects a tampered proof claim", () => {
  const row = { spell_id: 1, mechanics: { power_type: 3 },
    field_observations: { power_type: ptObs({ proof: { integrity: "verified", layout: "verified", interpretation: "reference" } }) } };
  assert.throws(() => verifyRowAgainstPolicy(row, policy), /proof claim disagrees/);
});

test("rejects a tampered decoded claim", () => {
  const row = { spell_id: 1, mechanics: { power_type: 3 },
    field_observations: { power_type: ptObs({ decoded: { kind: "int32", value: 99 } }) } };
  assert.throws(() => verifyRowAgainstPolicy(row, policy), /decoded claim disagrees/);
});

test("policy lock mismatch is rejected", () => {
  assert.throws(() => assertPolicyLock({ sha256: "zzz" }, { sha256: "abc" }), /policy lock/);
});
