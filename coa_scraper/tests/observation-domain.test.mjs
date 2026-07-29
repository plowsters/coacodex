// coa_scraper/tests/observation-domain.test.mjs
// E0R.2 T2.3 — the full observation domain is declared by the REVIEWED policy and this side reads it
// from there. Before this, the check was `policyDoc.required_scalar_fields || []` against a production
// policy that never carried that key: the `|| []` turned an absent contract into an empty one, so the
// domain check silently asked nothing of any real row. It now fails CLOSED.
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import { verifyFullRowAgainstPolicy } from "../scripts/lib/mechanics-projection.mjs";

const CORPUS = new URL("../../tests/golden/e0r1_corpus/", import.meta.url);
const POLICY = JSON.parse(fs.readFileSync(new URL("policy.json", CORPUS)));

function fullRow() {
  for (const line of fs.readFileSync(new URL("full_rows.jsonl", CORPUS), "utf8").split("\n")) {
    if (!line.trim()) continue;
    const { case: label, golden_accept: _a, ...row } = JSON.parse(line);
    if (label === "valid_full") return structuredClone(row);
  }
  throw new Error("no valid_full row in the corpus");
}

test("the corpus baseline satisfies the domain its own policy declares", () => {
  verifyFullRowAgainstPolicy(fullRow(), POLICY);
});

test("a policy with no artifact_contract fails closed", () => {
  const { artifact_contract: _c, ...policy } = POLICY;
  assert.throws(() => verifyFullRowAgainstPolicy(fullRow(), policy),
                /declares no artifact_contract/);
});

test("an artifact_contract that is not a domain fails closed", () => {
  // The `|| []` shape of the old bug: a malformed contract must not degrade to "check nothing".
  for (const contract of [null, {}, { required_raw_observations: "id,name" }]) {
    assert.throws(() => verifyFullRowAgainstPolicy(fullRow(), { ...POLICY, artifact_contract: contract }),
                  /declares no artifact_contract/);
  }
});

test("an observation omitted from raw is loss, even when it has no normalized value", () => {
  // duration_ms is the unresolved join — no value, but the envelope is still a required observation.
  const row = fullRow();
  assert.equal(row.mechanics.duration_ms, null);
  delete row.raw.duration_ms;
  assert.throws(() => verifyFullRowAgainstPolicy(row, POLICY), /duration_ms omitted from raw/);
});

test("a mechanics key may hold null but may not be absent", () => {
  const row = fullRow();
  for (const key of Object.keys(row.mechanics)) row.mechanics[key] = null;
  verifyFullRowAgainstPolicy(row, POLICY);          // a null is a recorded observation
  delete row.mechanics.school_mask;
  assert.throws(() => verifyFullRowAgainstPolicy(row, POLICY), /school_mask absent/);
});

test("the icon join is not part of the spell row's domain", () => {
  // It lands in the icon child; requiring it here would make every full row fail.
  assert.deepEqual(POLICY.artifact_contract.icon_observation_domain, ["spell_icon_id"]);
  assert.ok(!POLICY.artifact_contract.required_raw_observations.includes("spell_icon_id"));
  verifyFullRowAgainstPolicy(fullRow(), POLICY);
});

test("both languages read the same domain from the same policy", () => {
  // The Python mirror is coa_client_extract/publish.py::_observation_domain, held to this same corpus
  // policy in tests/test_e0r2_observation_domain.py.
  const c = POLICY.artifact_contract;
  assert.deepEqual(c.required_mechanics_keys, c.nullable_mechanics_keys);
  assert.deepEqual([...c.required_mechanics_keys].sort(),
                   c.required_raw_observations.filter((f) => !["id", "name", "description"].includes(f)).sort());
});
