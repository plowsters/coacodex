// coa_scraper/scripts/lib/canonical.mjs
// Canonicalization that reproduces Python json.dumps(x, sort_keys=True, ensure_ascii=False) BYTE-FOR-BYTE,
// preserving integer literals exactly. The generation manifest carries `published_at` as a time_ns() int
// beyond 2**53, which plain JSON.parse would round — so we parse the manifest TEXT keeping every number as
// its source token, then re-emit sorted keys with Python's default ", "/": " separators.
import crypto from "node:crypto";

// A JSON number kept as its exact source token (never rounded through a JS double).
class RawNumber { constructor(raw) { this.raw = raw; } }

// Source-preserving recursive-descent parse: numbers -> RawNumber(token); everything else -> normal JS.
export function parsePreservingNumbers(text) {
  let i = 0;
  const fail = (m) => { throw new SyntaxError(`canonical parse @${i}: ${m}`); };
  const ws = () => { while (i < text.length && " \t\n\r".includes(text[i])) i++; };

  function value() {
    ws();
    const c = text[i];
    if (c === "{") return object();
    if (c === "[") return array();
    if (c === '"') return string();
    if (c === "-" || (c >= "0" && c <= "9")) return number();
    if (text.startsWith("true", i)) { i += 4; return true; }
    if (text.startsWith("false", i)) { i += 5; return false; }
    if (text.startsWith("null", i)) { i += 4; return null; }
    fail(`unexpected token ${JSON.stringify(c)}`);
  }
  function object() {
    i++; const o = {}; ws();
    if (text[i] === "}") { i++; return o; }
    for (;;) {
      ws(); if (text[i] !== '"') fail("expected object key"); const k = string();
      ws(); if (text[i] !== ":") fail("expected ':'"); i++;
      o[k] = value(); ws();
      if (text[i] === ",") { i++; continue; }
      if (text[i] === "}") { i++; return o; }
      fail("expected ',' or '}'");
    }
  }
  function array() {
    i++; const a = []; ws();
    if (text[i] === "]") { i++; return a; }
    for (;;) {
      a.push(value()); ws();
      if (text[i] === ",") { i++; continue; }
      if (text[i] === "]") { i++; return a; }
      fail("expected ',' or ']'");
    }
  }
  function string() {
    const start = i; i++;                         // opening quote
    while (i < text.length) {
      if (text[i] === "\\") i += 2;
      else if (text[i] === '"') { i++; return JSON.parse(text.slice(start, i)); }
      else i++;
    }
    fail("unterminated string");
  }
  function number() {
    const start = i;
    if (text[i] === "-") i++;
    while (i < text.length && "0123456789.eE+-".includes(text[i])) i++;
    return new RawNumber(text.slice(start, i));
  }

  const v = value(); ws();
  if (i !== text.length) fail("trailing content");
  return v;
}

// Serialize byte-identical to Python json.dumps(sort_keys=True, ensure_ascii=False): recursively key-sorted,
// ", " between items and ": " between key and value; a RawNumber is emitted verbatim (integers round-trip
// exactly, and the only float-bearing manifest section — `budget` — is an excluded mutable key).
export function canonicalize(value) {
  if (value instanceof RawNumber) return value.raw;
  if (value === null || typeof value === "boolean" || typeof value === "string" || typeof value === "number") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return "[" + value.map(canonicalize).join(", ") + "]";
  const keys = Object.keys(value).sort();
  return "{" + keys.map((k) => JSON.stringify(k) + ": " + canonicalize(value[k])).join(", ") + "}";
}

const MUTABLE = new Set(["publication_state", "validation", "budget"]);

// Recompute candidate_trust_sha256 from the manifest TEXT exactly as Python publish.candidate_trust_sha256:
// the COMPLETE manifest minus the mutable keys (publication_state, validation, budget) and the digest field.
export function candidateTrustSha256FromText(manifestText) {
  const manifest = parsePreservingNumbers(manifestText);
  const trust = {};
  for (const k of Object.keys(manifest)) {
    if (!MUTABLE.has(k) && k !== "candidate_trust_sha256") trust[k] = manifest[k];
  }
  return crypto.createHash("sha256").update(canonicalize(trust), "utf8").digest("hex");
}
