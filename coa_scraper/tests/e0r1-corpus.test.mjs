// coa_scraper/tests/e0r1-corpus.test.mjs
// E0R.1 T3.0 — the Node projection verifier must agree with the SAME shared golden corpus the Python suite
// pins (tests/test_e0r1_corpus.py), so the two trust boundaries can never silently diverge.
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import { verifyRowAgainstPolicy } from "../scripts/lib/mechanics-projection.mjs";

const CORPUS = new URL("../../tests/golden/e0r1_corpus/", import.meta.url);
const policy = JSON.parse(fs.readFileSync(new URL("policy.json", CORPUS)));
const rows = fs.readFileSync(new URL("projection_rows.jsonl", CORPUS), "utf8")
  .split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));

test("Node agrees with every projection golden_accept in the shared corpus", () => {
  for (const r of rows) {
    const { case: _c, golden_accept, ...row } = r;
    if (golden_accept) assert.doesNotThrow(() => verifyRowAgainstPolicy(row, policy), `${r.case} should accept`);
    else assert.throws(() => verifyRowAgainstPolicy(row, policy), `${r.case} should reject`);
  }
});
