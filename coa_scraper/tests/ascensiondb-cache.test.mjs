import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  ASCENSIONDB_CACHE_SCHEMA_VERSION,
  cacheKeyForUrl,
  fetchCachedResource,
  isFresh,
  loadCacheManifest,
  writeCacheManifest
} from "../scripts/lib/ascensiondb-cache.mjs";

const NOW = new Date("2026-07-06T12:00:00.000Z");
const URL = "https://db.ascension.gg/?spell=123&power";

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "coa-ascensiondb-cache-test-"));
}

test("cache keys are stable and filesystem safe", () => {
  const key = cacheKeyForUrl(URL);

  assert.equal(key, cacheKeyForUrl(URL));
  assert.match(key, /^[a-f0-9]{64}$/);
  assert.notEqual(key, cacheKeyForUrl("https://db.ascension.gg/?spell=124&power"));
});

test("manifest rows can be written and loaded", () => {
  const dir = tmpDir();
  const manifestPath = path.join(dir, "manifest.json");
  const rows = [
    {
      cache_key: cacheKeyForUrl(URL),
      url: URL,
      status: "fetched",
      fetched_at: NOW.toISOString()
    }
  ];

  writeCacheManifest(manifestPath, rows);
  const data = JSON.parse(fs.readFileSync(manifestPath, "utf8"));

  assert.equal(data.schema_version, ASCENSIONDB_CACHE_SCHEMA_VERSION);
  assert.deepEqual(loadCacheManifest(manifestPath), rows);
  assert.deepEqual(loadCacheManifest(path.join(dir, "missing.json")), []);
});

test("fresh cache rows skip network fetches", async () => {
  let fetchCalled = false;
  const cachedBody = "$WowheadPower.registerSpell(123, 0, {});";
  const row = {
    cache_key: cacheKeyForUrl(URL),
    url: URL,
    status: "fetched",
    fetched_at: "2026-07-05T12:00:00.000Z",
    body_path: "bodies/spell-123.js"
  };

  assert.equal(isFresh(row, 7, NOW), true);

  const result = await fetchCachedResource({
    url: URL,
    resourceKind: "spell",
    sourceKind: "spell",
    sourceId: 123,
    parserVersion: "test-parser-v1",
    manifestRows: [row],
    staleDays: 7,
    now: NOW,
    readBody: async bodyPath => {
      assert.equal(bodyPath, "bodies/spell-123.js");
      return cachedBody;
    },
    writeBody: async () => {
      throw new Error("write should not be called for fresh cache");
    },
    fetchText: async () => {
      fetchCalled = true;
      throw new Error("fetch should not be called for fresh cache");
    }
  });

  assert.equal(fetchCalled, false);
  assert.equal(result.status, "fresh_cache");
  assert.equal(result.body, cachedBody);
  assert.equal(result.row.status, "fresh_cache");
  assert.equal(result.row.validated_at, NOW.toISOString());
});

test("fresh failed rows are retried instead of reused", async () => {
  let fetchCalled = false;
  const row = {
    cache_key: cacheKeyForUrl(URL),
    url: URL,
    status: "fetch_failed",
    validated_at: "2026-07-06T11:00:00.000Z",
    errors: ["network blocked"]
  };

  assert.equal(isFresh(row, 7, NOW), false);
  assert.equal(isFresh({ ...row, status: "fresh_cache" }, 7, NOW), false);

  const result = await fetchCachedResource({
    url: URL,
    resourceKind: "spell",
    sourceKind: "spell",
    sourceId: 123,
    parserVersion: "test-parser-v1",
    manifestRows: [row],
    staleDays: 7,
    now: NOW,
    fetchText: async () => {
      fetchCalled = true;
      return {
        status: 200,
        headers: {},
        text: "$WowheadPower.registerSpell(123, 0, {});"
      };
    },
    writeBody: async () => {}
  });

  assert.equal(fetchCalled, true);
  assert.equal(result.status, "fetched");
});

test("stale cache rows send conditional request headers and reuse body on 304", async () => {
  const cachedBody = "$WowheadPower.registerSpell(123, 0, {});";
  const staleRow = {
    cache_key: cacheKeyForUrl(URL),
    url: URL,
    status: "fetched",
    fetched_at: "2026-06-01T12:00:00.000Z",
    body_path: "bodies/spell-123.js",
    etag: "\"spell-123\"",
    last_modified: "Wed, 01 Jul 2026 00:00:00 GMT"
  };
  let requestOptions = null;

  const result = await fetchCachedResource({
    url: URL,
    resourceKind: "spell",
    sourceKind: "spell",
    sourceId: 123,
    parserVersion: "test-parser-v1",
    manifestRows: [staleRow],
    staleDays: 7,
    now: NOW,
    readBody: async () => cachedBody,
    writeBody: async () => {
      throw new Error("write should not be called for 304");
    },
    fetchText: async (requestedUrl, options) => {
      assert.equal(requestedUrl, URL);
      requestOptions = options;
      return {
        status: 304,
        headers: {},
        text: ""
      };
    }
  });

  assert.deepEqual(requestOptions.headers, {
    "If-None-Match": "\"spell-123\"",
    "If-Modified-Since": "Wed, 01 Jul 2026 00:00:00 GMT"
  });
  assert.equal(result.status, "not_modified");
  assert.equal(result.body, cachedBody);
  assert.equal(result.row.status, "not_modified");
  assert.equal(result.row.validated_at, NOW.toISOString());
  assert.equal(result.row.body_path, "bodies/spell-123.js");
});

test("new 200 responses write body metadata and hashes", async () => {
  const body = fs.readFileSync(
    path.join(import.meta.dirname, "fixtures", "ascensiondb", "spell-123-power.js"),
    "utf8"
  );
  const writes = [];

  const result = await fetchCachedResource({
    url: URL,
    resourceKind: "spell",
    sourceKind: "spell",
    sourceId: 123,
    parserVersion: "test-parser-v1",
    manifestRows: [],
    bodyRoot: "cache/bodies",
    now: NOW,
    readBody: async () => {
      throw new Error("read should not be needed for new 200");
    },
    writeBody: async (bodyPath, text) => {
      writes.push({ bodyPath, text });
    },
    fetchText: async () => ({
      status: 200,
      headers: {
        etag: "\"fresh\"",
        "last-modified": "Mon, 06 Jul 2026 00:00:00 GMT",
        "content-type": "application/javascript"
      },
      text: body
    })
  });

  assert.equal(result.status, "fetched");
  assert.equal(result.body, body);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].text, body);
  assert.match(writes[0].bodyPath, /^cache\/bodies\/[a-f0-9]{64}\.body$/);
  assert.match(result.row.content_sha256, /^[a-f0-9]{64}$/);
  assert.equal(result.row.byte_length, Buffer.byteLength(body, "utf8"));
  assert.equal(result.row.fetched_at, NOW.toISOString());
  assert.equal(result.row.validated_at, NOW.toISOString());
  assert.equal(result.row.etag, "\"fresh\"");
  assert.equal(result.row.last_modified, "Mon, 06 Jul 2026 00:00:00 GMT");
  assert.equal(result.row.content_type, "application/javascript");
  assert.equal(result.row.resource_kind, "spell");
  assert.equal(result.row.source_id, 123);
});

test("fetch failures become manifest rows without throwing", async () => {
  const result = await fetchCachedResource({
    url: URL,
    resourceKind: "spell",
    sourceKind: "spell",
    sourceId: 123,
    parserVersion: "test-parser-v1",
    manifestRows: [],
    now: NOW,
    fetchText: async () => {
      throw new Error("temporary network failure");
    }
  });

  assert.equal(result.status, "fetch_failed");
  assert.equal(result.body, "");
  assert.equal(result.row.status, "fetch_failed");
  assert.match(result.row.errors[0], /temporary network failure/);
  assert.equal(result.row.validated_at, NOW.toISOString());
});
