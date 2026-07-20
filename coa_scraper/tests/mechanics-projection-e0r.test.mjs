// coa_scraper/tests/mechanics-projection-e0r.test.mjs
import { test } from "node:test";
import assert from "node:assert";
import { verifyRowAgainstPolicy, assertPolicyLock } from "../scripts/lib/mechanics-projection.mjs";

const policy = { sha256: "abc", tables: { Spell: { fields: {
  power_type: { kind: "int32", layout: "verified", interpretation: "verified", promotion: "normalized" } } } } };

test("rejects a numeric value that disagrees with a re-decode of its raw", () => {
  const row = { spell_id: 1, mechanics: { power_type: 5 },
    raw: { power_type: { state: "present", raw_u32: 3, decoded_reason: "decoded",
                         policy_ref: "/tables/Spell/fields/power_type" } } };
  assert.throws(() => verifyRowAgainstPolicy(row, policy), /power_type.*re-decode/);
});

test("accepts a numeric value that matches the re-decode", () => {
  const row = { spell_id: 1, mechanics: { power_type: 3 },
    raw: { power_type: { state: "present", raw_u32: 3, decoded_reason: "decoded",
                         policy_ref: "/tables/Spell/fields/power_type" } } };
  assert.doesNotThrow(() => verifyRowAgainstPolicy(row, policy));
});

test("policy lock mismatch is rejected", () => {
  assert.throws(() => assertPolicyLock({ sha256: "zzz" }, { sha256: "abc" }), /policy lock/);
});
