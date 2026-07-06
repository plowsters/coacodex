import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export const ASCENSIONDB_CACHE_SCHEMA_VERSION = "coa-ascensiondb-cache-manifest-v1";

export function cacheKeyForUrl(url) {
  return crypto.createHash("sha256").update(String(url || "")).digest("hex");
}

export function loadCacheManifest(filePath) {
  if (!filePath || !fs.existsSync(filePath)) {
    return [];
  }

  const text = fs.readFileSync(filePath, "utf8").trim();
  if (!text) {
    return [];
  }

  const parsed = JSON.parse(text);
  if (Array.isArray(parsed)) {
    return parsed;
  }
  if (Array.isArray(parsed.resources)) {
    return parsed.resources;
  }
  return [];
}

export function writeCacheManifest(filePath, rows) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(
    filePath,
    `${JSON.stringify({
      schema_version: ASCENSIONDB_CACHE_SCHEMA_VERSION,
      resources: rows
    }, null, 2)}\n`
  );
}

export function isFresh(row, staleDays, now = new Date()) {
  if (!row || staleDays <= 0) {
    return false;
  }
  if (!freshEligibleStatus(row.status)) {
    return false;
  }
  if ((row.errors || []).length > 0 || !row.body_path) {
    return false;
  }

  const checkedAt = row.validated_at || row.fetched_at || row.checked_at;
  if (!checkedAt) {
    return false;
  }

  const checkedTime = Date.parse(checkedAt);
  if (!Number.isFinite(checkedTime)) {
    return false;
  }

  const nowTime = now instanceof Date ? now.getTime() : Date.parse(now);
  if (!Number.isFinite(nowTime)) {
    return false;
  }

  return nowTime - checkedTime < Number(staleDays) * 24 * 60 * 60 * 1000;
}

function freshEligibleStatus(status) {
  return !status || ["fetched", "fresh_cache", "not_modified"].includes(status);
}

export async function fetchCachedResource({
  url,
  resourceKind,
  sourceKind,
  sourceId,
  parserVersion,
  manifestRows = [],
  staleDays = 7,
  force = false,
  bodyRoot = "cache/ascensiondb/bodies",
  now = new Date(),
  fetchText = defaultFetchText,
  readBody = defaultReadBody,
  writeBody = defaultWriteBody
}) {
  const cacheKey = cacheKeyForUrl(url);
  const previous = manifestRows.find(row => row.cache_key === cacheKey || row.url === url) || null;
  const timestamp = toIso(now);

  if (!force && previous && isFresh(previous, staleDays, now)) {
    const body = previous.body_path ? await readBody(previous.body_path) : "";
    return {
      status: "fresh_cache",
      body,
      row: {
        ...baseRow({ url, cacheKey, resourceKind, sourceKind, sourceId, parserVersion, timestamp }),
        ...previous,
        status: "fresh_cache",
        validated_at: timestamp,
        errors: previous.errors || [],
        warnings: previous.warnings || []
      }
    };
  }

  const conditionalHeaders = conditionalRequestHeaders(previous);

  try {
    const fetched = normalizeFetchResult(await fetchText(url, { headers: conditionalHeaders }));

    if (fetched.status === 304 && previous) {
      const body = previous.body_path ? await readBody(previous.body_path) : "";
      return {
        status: "not_modified",
        body,
        row: {
          ...baseRow({ url, cacheKey, resourceKind, sourceKind, sourceId, parserVersion, timestamp }),
          ...previous,
          status: "not_modified",
          http_status: 304,
          validated_at: timestamp,
          errors: previous.errors || [],
          warnings: previous.warnings || []
        }
      };
    }

    if (fetched.status < 200 || fetched.status >= 300) {
      throw new Error(`HTTP ${fetched.status} for ${url}`);
    }

    const bodyPath = previous?.body_path || path.posix.join(bodyRoot, `${cacheKey}.body`);
    await writeBody(bodyPath, fetched.text);

    const row = {
      ...baseRow({ url, cacheKey, resourceKind, sourceKind, sourceId, parserVersion, timestamp }),
      status: "fetched",
      http_status: fetched.status,
      etag: headerValue(fetched.headers, "etag"),
      last_modified: headerValue(fetched.headers, "last-modified"),
      cache_control: headerValue(fetched.headers, "cache-control"),
      content_type: headerValue(fetched.headers, "content-type"),
      fetched_at: timestamp,
      validated_at: timestamp,
      body_path: bodyPath,
      content_sha256: sha256(fetched.text),
      byte_length: Buffer.byteLength(fetched.text, "utf8"),
      warnings: [],
      errors: []
    };

    return {
      status: "fetched",
      body: fetched.text,
      row
    };
  } catch (error) {
    return {
      status: "fetch_failed",
      body: "",
      row: {
        ...baseRow({ url, cacheKey, resourceKind, sourceKind, sourceId, parserVersion, timestamp }),
        ...(previous || {}),
        status: "fetch_failed",
        validated_at: timestamp,
        errors: [String(error?.message || error)],
        warnings: previous?.warnings || []
      }
    };
  }
}

function baseRow({ url, cacheKey, resourceKind, sourceKind, sourceId, parserVersion, timestamp }) {
  return {
    cache_key: cacheKey,
    url,
    resource_kind: resourceKind || null,
    source_kind: sourceKind || null,
    source_id: sourceId ?? null,
    parser_version: parserVersion || null,
    validated_at: timestamp
  };
}

function conditionalRequestHeaders(row) {
  const headers = {};
  if (row?.etag) {
    headers["If-None-Match"] = row.etag;
  }
  if (row?.last_modified) {
    headers["If-Modified-Since"] = row.last_modified;
  }
  return headers;
}

function normalizeFetchResult(result) {
  if (typeof result === "string") {
    return {
      status: 200,
      headers: {},
      text: result
    };
  }

  return {
    status: Number(result?.status ?? 200),
    headers: result?.headers || {},
    text: String(result?.text ?? "")
  };
}

function headerValue(headers, name) {
  if (!headers) {
    return null;
  }

  if (typeof headers.get === "function") {
    return headers.get(name) || null;
  }

  const lowerName = name.toLowerCase();
  for (const [key, value] of Object.entries(headers)) {
    if (key.toLowerCase() === lowerName) {
      return value == null ? null : String(value);
    }
  }
  return null;
}

function sha256(text) {
  return crypto.createHash("sha256").update(String(text || "")).digest("hex");
}

function toIso(value) {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

async function defaultFetchText(url, options = {}) {
  const response = await fetch(url, options);
  return {
    status: response.status,
    headers: response.headers,
    text: await response.text()
  };
}

async function defaultReadBody(bodyPath) {
  return fs.readFileSync(bodyPath, "utf8");
}

async function defaultWriteBody(bodyPath, text) {
  fs.mkdirSync(path.dirname(bodyPath), { recursive: true });
  fs.writeFileSync(bodyPath, text);
}
