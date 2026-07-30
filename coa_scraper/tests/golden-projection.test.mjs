// coa_scraper/tests/golden-projection.test.mjs
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import { verifyRowAgainstPolicy } from "../scripts/lib/mechanics-projection.mjs";

const policy = JSON.parse(fs.readFileSync(new URL("../../tests/golden/e0r_policy.json", import.meta.url)));
const rows = fs.readFileSync(new URL("../../tests/golden/e0r_projection_rows.jsonl", import.meta.url), "utf8")
  .split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));

test("Node agrees with the golden verdict for every row", () => {
  for (const row of rows) {
    if (row.golden_accept) assert.doesNotThrow(() => verifyRowAgainstPolicy(row, policy), `row ${row.spell_id}`);
    else assert.throws(() => verifyRowAgainstPolicy(row, policy), `row ${row.spell_id} should reject`);
  }
});
