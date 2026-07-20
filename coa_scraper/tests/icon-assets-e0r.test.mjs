// E0R: icon-assets.mjs carries no db.ascension.gg URL template, and with no templates a resolve yields a
// placeholder/missing record rather than reaching out to a remote host.
import { test } from "node:test";
import assert from "node:assert";
import { DEFAULT_ICON_URL_TEMPLATES, resolveIconAsset } from "../scripts/lib/icon-assets.mjs";

test("no db.ascension.gg icon URL template survives", () => {
  assert.deepEqual(DEFAULT_ICON_URL_TEMPLATES, []);
  assert.ok(!JSON.stringify(DEFAULT_ICON_URL_TEMPLATES).includes("db.ascension.gg"));
});

test("resolve with no templates yields a missing record and makes no fetch", async () => {
  let fetched = false;
  const row = await resolveIconAsset({
    iconToken: "Spell_Fire_Fireball", assetRoot: "dist/assets",
    fetchBinary: async () => { fetched = true; throw new Error("must not fetch"); },
    existingRows: [],
  });
  const record = row.row || row;
  assert.equal(fetched, false);
  assert.ok(!JSON.stringify(record).includes("db.ascension.gg"));
});
