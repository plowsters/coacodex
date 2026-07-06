import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export const DEFAULT_ICON_URL_TEMPLATES = [
  "https://db.ascension.gg/static/images/wow/icons/large/{icon}.jpg",
  "https://db.ascension.gg/static/images/wow/icons/medium/{icon}.jpg",
  "https://db.ascension.gg/static/images/wow/icons/small/{icon}.jpg"
];

export function sanitizeIconToken(iconToken) {
  const raw = String(iconToken || "")
    .replaceAll("\\", "/")
    .split("/")
    .pop()
    .replace(/\.(blp|png|jpg|jpeg|webp)$/i, "");

  return raw
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_+/g, "_");
}

export async function resolveIconAsset({
  iconToken,
  manifestRows = [],
  assetRoot = "dist/assets",
  fetchBinary = defaultFetchBinary,
  writeAsset = defaultWriteAsset,
  templates = DEFAULT_ICON_URL_TEMPLATES,
  staleDays = 7,
  now = new Date()
}) {
  const sanitized = sanitizeIconToken(iconToken);
  const timestamp = toIso(now);
  const previous = manifestRows.find(row =>
    row.resource_kind === "icon" && row.icon_token === sanitized
  );

  if (!sanitized) {
    return {
      status: "asset_missing",
      asset_path: null,
      row: missingRow({ iconToken: sanitized, assetRoot, timestamp, warnings: ["asset_missing:empty_icon_token"] })
    };
  }

  if (previous && isFresh(previous, staleDays, now)) {
    return {
      status: previous.status === "asset_missing" ? "asset_missing" : "fresh_cache",
      asset_path: previous.asset_path || null,
      row: {
        ...previous,
        status: previous.status === "asset_missing" ? "asset_missing" : "fresh_cache",
        validated_at: timestamp,
        warnings: previous.warnings || [],
        errors: previous.errors || []
      }
    };
  }

  const attempts = [];
  for (const template of templates) {
    const sourceUrl = renderTemplate(template, sanitized);
    attempts.push(sourceUrl);
    try {
      const response = normalizeBinaryResponse(await fetchBinary(sourceUrl));
      if (response.status < 200 || response.status >= 300) {
        continue;
      }

      const contentType = headerValue(response.headers, "content-type") || contentTypeFromUrl(sourceUrl);
      const ext = extensionForContentType(contentType) || extensionFromUrl(sourceUrl) || "jpg";
      const assetPath = path.posix.join(assetRoot.replaceAll("\\", "/"), "icons", `${sanitized}.${ext}`);
      await writeAsset(assetPath, response.body);

      const row = {
        schema_version: "coa-db-asset-record-v1",
        cache_key: cacheKeyForIcon(sanitized),
        resource_kind: "icon",
        asset_kind: "icon",
        icon_token: sanitized,
        source_url: sourceUrl,
        local_path: assetPath,
        asset_path: assetPath,
        content_type: contentType,
        width: null,
        height: null,
        content_sha256: sha256(response.body),
        byte_length: response.body.length,
        fetched_at: timestamp,
        validated_at: timestamp,
        status: "fetched",
        warnings: [],
        errors: []
      };

      return {
        status: "fetched",
        asset_path: assetPath,
        row
      };
    } catch (error) {
      attempts.push(`error:${String(error?.message || error)}`);
    }
  }

  const row = missingRow({
    iconToken: sanitized,
    assetRoot,
    timestamp,
    warnings: [`asset_missing:${attempts.join(",")}`]
  });

  return {
    status: "asset_missing",
    asset_path: null,
    row
  };
}

function missingRow({ iconToken, timestamp, warnings }) {
  return {
    schema_version: "coa-db-asset-record-v1",
    cache_key: cacheKeyForIcon(iconToken),
    resource_kind: "icon",
    asset_kind: "icon",
    icon_token: iconToken,
    source_url: null,
    local_path: null,
    asset_path: null,
    content_type: null,
    width: null,
    height: null,
    content_sha256: null,
    byte_length: 0,
    fetched_at: null,
    validated_at: timestamp,
    status: "asset_missing",
    warnings,
    errors: []
  };
}

function isFresh(row, staleDays, now) {
  if (!row || staleDays <= 0) {
    return false;
  }
  const checkedAt = row.validated_at || row.fetched_at;
  if (!checkedAt) {
    return false;
  }
  const checkedTime = Date.parse(checkedAt);
  const nowTime = now instanceof Date ? now.getTime() : Date.parse(now);
  if (!Number.isFinite(checkedTime) || !Number.isFinite(nowTime)) {
    return false;
  }
  return nowTime - checkedTime < Number(staleDays) * 24 * 60 * 60 * 1000;
}

function renderTemplate(template, iconToken) {
  if (typeof template === "function") {
    return template(iconToken);
  }
  return String(template).replaceAll("{icon}", iconToken);
}

function normalizeBinaryResponse(response) {
  if (Buffer.isBuffer(response) || response instanceof Uint8Array) {
    return {
      status: 200,
      headers: {},
      body: Buffer.from(response)
    };
  }
  return {
    status: Number(response?.status ?? 200),
    headers: response?.headers || {},
    body: Buffer.from(response?.body || "")
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

function extensionForContentType(contentType) {
  const value = String(contentType || "").toLowerCase();
  if (value.includes("png")) return "png";
  if (value.includes("webp")) return "webp";
  if (value.includes("jpeg") || value.includes("jpg")) return "jpg";
  if (value.includes("gif")) return "gif";
  return null;
}

function contentTypeFromUrl(url) {
  const ext = extensionFromUrl(url);
  if (ext === "png") return "image/png";
  if (ext === "webp") return "image/webp";
  if (ext === "gif") return "image/gif";
  return "image/jpeg";
}

function extensionFromUrl(url) {
  const match = String(url || "").match(/\.([a-z0-9]+)(?:\?|#|$)/i);
  return match ? match[1].toLowerCase() : null;
}

function cacheKeyForIcon(iconToken) {
  return crypto.createHash("sha256").update(`icon:${iconToken}`).digest("hex");
}

function sha256(body) {
  return crypto.createHash("sha256").update(Buffer.from(body)).digest("hex");
}

function toIso(value) {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

async function defaultFetchBinary(url) {
  const response = await fetch(url);
  return {
    status: response.status,
    headers: response.headers,
    body: Buffer.from(await response.arrayBuffer())
  };
}

async function defaultWriteAsset(assetPath, body) {
  fs.mkdirSync(path.dirname(assetPath), { recursive: true });
  fs.writeFileSync(assetPath, body);
}
