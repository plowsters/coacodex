import assert from "node:assert/strict";
import test from "node:test";

import {
  resolveIconAsset,
  sanitizeIconToken
} from "../scripts/lib/icon-assets.mjs";

const NOW = new Date("2026-07-06T12:00:00.000Z");

test("icon resolver reuses fresh fetched asset rows", async () => {
  let fetchCalled = false;
  const result = await resolveIconAsset({
    iconToken: "INV_Misc_Test",
    manifestRows: [
      {
        resource_kind: "icon",
        icon_token: "inv_misc_test",
        status: "fetched",
        fetched_at: "2026-07-05T12:00:00.000Z",
        asset_path: "dist/assets/icons/inv_misc_test.png",
        content_sha256: "abc123"
      }
    ],
    assetRoot: "dist/assets",
    now: NOW,
    staleDays: 7,
    fetchBinary: async () => {
      fetchCalled = true;
      throw new Error("fetch should not be called");
    }
  });

  assert.equal(fetchCalled, false);
  assert.equal(result.status, "fresh_cache");
  assert.equal(result.asset_path, "dist/assets/icons/inv_misc_test.png");
  assert.equal(result.row.validated_at, NOW.toISOString());
});

test("icon resolver writes metadata for successful asset fetch", async () => {
  const writes = [];
  const result = await resolveIconAsset({
    iconToken: "Ability_Test_Icon",
    manifestRows: [],
    assetRoot: "dist/assets",
    now: NOW,
    templates: ["https://assets.test/icons/{icon}.png"],
    writeAsset: async (assetPath, body) => {
      writes.push({ assetPath, body: Buffer.from(body).toString("utf8") });
    },
    fetchBinary: async url => ({
      status: 200,
      headers: { "content-type": "image/png" },
      body: Buffer.from("png-bytes"),
      url
    })
  });

  assert.equal(result.status, "fetched");
  assert.equal(result.row.status, "fetched");
  assert.equal(result.row.source_url, "https://assets.test/icons/ability_test_icon.png");
  assert.equal(result.row.asset_path, "dist/assets/icons/ability_test_icon.png");
  assert.equal(result.row.content_type, "image/png");
  assert.equal(result.row.byte_length, Buffer.byteLength("png-bytes"));
  assert.match(result.row.content_sha256, /^[a-f0-9]{64}$/);
  assert.equal(result.row.fetched_at, NOW.toISOString());
  assert.deepEqual(writes, [
    {
      assetPath: "dist/assets/icons/ability_test_icon.png",
      body: "png-bytes"
    }
  ]);
});

test("icon resolver caches missing assets and does not retry fresh misses", async () => {
  let attempts = 0;
  const first = await resolveIconAsset({
    iconToken: "missing_icon",
    manifestRows: [],
    assetRoot: "dist/assets",
    now: NOW,
    templates: ["https://assets.test/icons/{icon}.png", "https://fallback.test/{icon}.jpg"],
    fetchBinary: async () => {
      attempts++;
      return { status: 404, headers: {}, body: Buffer.from("") };
    }
  });

  assert.equal(attempts, 2);
  assert.equal(first.status, "asset_missing");
  assert.equal(first.row.status, "asset_missing");
  assert.equal(first.row.icon_token, "missing_icon");
  assert(first.row.warnings.some(item => item.includes("asset_missing")));

  const second = await resolveIconAsset({
    iconToken: "missing_icon",
    manifestRows: [first.row],
    assetRoot: "dist/assets",
    now: new Date("2026-07-07T12:00:00.000Z"),
    staleDays: 7,
    fetchBinary: async () => {
      throw new Error("fresh misses should not be retried");
    }
  });

  assert.equal(second.status, "asset_missing");
  assert.equal(second.row.validated_at, "2026-07-07T12:00:00.000Z");
});

test("icon resolver stops probing after first successful template", async () => {
  const urls = [];
  const result = await resolveIconAsset({
    iconToken: "spell_stop_after_success",
    manifestRows: [],
    assetRoot: "dist/assets",
    now: NOW,
    templates: [
      "https://first.test/{icon}.jpg",
      "https://second.test/{icon}.png",
      "https://third.test/{icon}.webp"
    ],
    writeAsset: async () => {},
    fetchBinary: async url => {
      urls.push(url);
      return {
        status: url.includes("second.test") ? 200 : 404,
        headers: { "content-type": "image/png" },
        body: Buffer.from("ok")
      };
    }
  });

  assert.deepEqual(urls, [
    "https://first.test/spell_stop_after_success.jpg",
    "https://second.test/spell_stop_after_success.png"
  ]);
  assert.equal(result.status, "fetched");
});

test("icon tokens are sanitized for local paths and URLs", () => {
  assert.equal(sanitizeIconToken("Interface\\Icons\\INV Misc-Test.blp"), "inv_misc_test");
  assert.equal(sanitizeIconToken("../bad/icon name"), "icon_name");
});
