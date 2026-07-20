import fs from "node:fs";
import crypto from "node:crypto";
import { normalizeSchoolMask, normalizePowerType, isPresent } from "./mechanics-normalize.mjs";

export class MechanicsBuildError extends Error {}

const NUMERIC_FIELDS = ["cast_time_ms", "duration_ms", "range_min_yd", "range_max_yd"];
const INT_FIELDS = ["school_mask", "power_type", "spell_icon_id"];   // v2 omits category
// Populated numeric mechanics values whose observation must agree (proof-authoritative consistency).
const OBSERVED_FIELDS = ["cast_time_ms", "duration_ms", "range_min_yd", "range_max_yd", "school_mask", "power_type", "spell_icon_id"];

function isNumOrNull(v) { return v === null || v === undefined || (typeof v === "number" && Number.isFinite(v)); }
function isIntOrNull(v) { return v === null || v === undefined || Number.isInteger(v); }

function parseJson(text, what) {
  try { return JSON.parse(text); }
  catch (e) { throw new MechanicsBuildError(`${what}: invalid JSON: ${e.message}`); }
}

// The normalized value a field_observation exposes: an Envelope carries {decoded:{kind,value}}, a
// JoinObservation carries {decoded:<number|null>}. Absence/withheld => null.
function observationValue(o) {
  if (!o) return undefined;
  if (o.decoded && typeof o.decoded === "object") return o.decoded.value;
  return o.decoded ?? null;
}

// v2: per-field/per-value observation proof is authoritative (the table-level
// schema_match_confidence_by_dbc certification is retired). Throws on any malformed value that could
// reach a canonical artifact: wrong types, negative/unknown mask, unknown power enum, or a populated
// normalized value that disagrees with its field_observation. Runs BEFORE reconciliation.
function assertRecordSemantics(rec) {
  if (rec.name !== null && typeof rec.name !== "string") throw new MechanicsBuildError(`projection ${rec.spell_id}: name must be string|null`);
  const m = rec.mechanics || {};
  for (const f of NUMERIC_FIELDS) if (!isNumOrNull(m[f])) throw new MechanicsBuildError(`projection ${rec.spell_id}: ${f} must be number|null`);
  for (const f of INT_FIELDS) if (!isIntOrNull(m[f])) throw new MechanicsBuildError(`projection ${rec.spell_id}: ${f} must be integer|null`);
  if (isPresent(m.school_mask) && (!Number.isInteger(m.school_mask) || m.school_mask < 0)) {
    throw new MechanicsBuildError(`projection ${rec.spell_id}: school_mask must be a non-negative integer`);
  }
  if (isPresent(m.school_mask) && m.school_mask > 0) {
    const { unknownBits } = normalizeSchoolMask(m.school_mask);
    if (unknownBits.length) throw new MechanicsBuildError(`projection ${rec.spell_id}: unknown school-mask bits ${unknownBits}`);
  }
  if (isPresent(m.power_type) && normalizePowerType(m.power_type).unknown) {
    throw new MechanicsBuildError(`projection ${rec.spell_id}: unknown power_type ${m.power_type}`);
  }
  // Every populated numeric normalized value must have an eligible matching observation.
  const fobs = rec.field_observations || {};
  for (const f of OBSERVED_FIELDS) {
    if (!isPresent(m[f])) continue;
    if (!(f in fobs)) throw new MechanicsBuildError(`projection ${rec.spell_id}: ${f} populated but has no field_observation`);
    const ov = observationValue(fobs[f]);
    if (ov !== m[f]) throw new MechanicsBuildError(`projection ${rec.spell_id}: ${f} normalized ${m[f]} disagrees with observation ${ov}`);
  }
}

export function loadAndValidateProjection({ projectionPath, manifestPath, builderSpellIds }) {
  const hasProj = fs.existsSync(projectionPath);
  const hasMan = fs.existsSync(manifestPath);
  if (!hasProj && !hasMan) return { absent: true };
  if (hasProj !== hasMan) {
    throw new MechanicsBuildError(`torn projection pair: projection=${hasProj} manifest=${hasMan} (need both, or neither for fallback)`);
  }

  const manifestBytes = fs.readFileSync(manifestPath);
  const manifest = parseJson(manifestBytes.toString("utf8"), "projection manifest");
  if (manifest.schema_version === "coa-client-spell-projection-v1") {
    throw new MechanicsBuildError("projection manifest is v1; regenerate with M1.14E (coa-client-spell-projection-v2)");
  }
  if (manifest.schema_version !== "coa-client-spell-projection-v2") {
    throw new MechanicsBuildError(`projection manifest bad schema_version: ${manifest.schema_version}`);
  }
  const p = manifest.projection;
  if (!p || typeof p.path !== "string" || typeof p.sha256 !== "string" || !p.sha256 || !Number.isInteger(p.byte_length)) {
    throw new MechanicsBuildError("projection manifest.projection must have {path:string, sha256:string, byte_length:int}");
  }
  const c = manifest.counts;
  if (!c || !Number.isInteger(c.projected_records) || !Number.isInteger(c.unique_spell_ids) || !Number.isInteger(c.source_records)) {
    throw new MechanicsBuildError("projection manifest.counts must have integer {projected_records, unique_spell_ids, source_records}");
  }

  const bytes = fs.readFileSync(projectionPath);
  const sha = crypto.createHash("sha256").update(bytes).digest("hex");
  if (p.sha256 !== sha) throw new MechanicsBuildError(`projection sha256 mismatch: ${projectionPath}`);
  if (p.byte_length !== bytes.length) throw new MechanicsBuildError(`projection byte_length mismatch: manifest ${p.byte_length} != actual ${bytes.length}`);

  const projection = [];
  const seen = new Set();
  let lineNo = 0;
  for (const line of bytes.toString("utf8").split("\n")) {
    lineNo += 1;
    if (!line.trim()) continue;
    const rec = parseJson(line, `projection line ${lineNo}`);
    if (rec.schema_version === "coa-client-spell-v1") throw new MechanicsBuildError(`projection row ${rec.spell_id}: v1 schema; regenerate with M1.14E (coa-client-spell-v2)`);
    if (rec.schema_version !== "coa-client-spell-v2") throw new MechanicsBuildError(`projection row bad schema_version: ${rec.schema_version}`);
    if (rec.coa_attribution?.is_coa !== true) throw new MechanicsBuildError(`projection row not is_coa: ${rec.spell_id}`);
    if (!Number.isInteger(rec.spell_id) || rec.spell_id <= 0) throw new MechanicsBuildError(`projection non-positive-integer spell_id: ${rec.spell_id}`);
    if (seen.has(rec.spell_id)) throw new MechanicsBuildError(`projection duplicate spell_id: ${rec.spell_id}`);
    assertRecordSemantics(rec);
    seen.add(rec.spell_id);
    projection.push(rec);
  }
  if (c.projected_records !== projection.length) throw new MechanicsBuildError(`projection count mismatch: manifest ${c.projected_records} != actual ${projection.length}`);
  if (c.unique_spell_ids !== seen.size) throw new MechanicsBuildError(`projection unique_spell_ids mismatch: manifest ${c.unique_spell_ids} != actual ${seen.size}`);

  const joined = [...builderSpellIds].filter((s) => seen.has(s));
  const missing = [...builderSpellIds].filter((s) => !seen.has(s));
  if (missing.length > 0) {
    throw new MechanicsBuildError(`builder_missing_from_projection: ${missing.length} spell(s), e.g. ${missing.slice(0, 5)}`);
  }
  const coverage = {
    builder_joined_to_projection: joined.length,
    builder_missing_from_projection: missing.length,
    projection_only: [...seen].filter((s) => !builderSpellIds.has(s)).length,
  };
  return {
    absent: false, projection, coverage, projection_sha256: sha,
    manifest_sha256: crypto.createHash("sha256").update(manifestBytes).digest("hex"),
    client_build: manifest.client_build ?? null,
  };
}

// --- E0R independent projection-v3 verification --------------------------------------------------
// Node holds the artifact + the pinned policy but NOT the client DBC bytes, so it re-derives
// layout/interpretation/promotion via each observation's policy_ref and re-decodes numeric raw_u32 (a
// string is verified against `resolved`). It validates transport integrity, not source integrity.

function resolvePolicyRef(doc, ref) {
  return ref.split("/").slice(1).reduce((n, t) => n[t.replace(/~1/g, "/").replace(/~0/g, "~")], doc);
}

function redecode(rawU32, kind) {
  const buf = Buffer.alloc(4);
  buf.writeUInt32LE(rawU32 >>> 0, 0);
  if (kind === "int32") return buf.readInt32LE(0);
  if (kind === "float") return buf.readFloatLE(0);
  return buf.readUInt32LE(0);
}

// Recursively key-sort so JSON.stringify(sortDeep(x)) mirrors Python
// json.dumps(sort_keys=True, separators=(",",":")).
function sortDeep(v) {
  if (Array.isArray(v)) return v.map(sortDeep);
  if (v && typeof v === "object") {
    return Object.keys(v).sort().reduce((acc, k) => { acc[k] = sortDeep(v[k]); return acc; }, {});
  }
  return v;
}

function canonicalSha256(doc) {
  const { sha256: _omit, ...rest } = doc;
  return crypto.createHash("sha256").update(JSON.stringify(sortDeep(rest))).digest("hex");
}

// Recompute the policy hash with the SAME canonical algorithm as Python compute_policy_sha256, so Node
// does not trust the policy's self-declared field, and compare to the committed lock.
export function assertPolicyLock(policyDoc, lock) {
  const actual = canonicalSha256(policyDoc);
  if (!lock || actual !== lock.sha256) {
    throw new MechanicsBuildError(`policy lock mismatch: recomputed ${actual} != lock ${lock?.sha256}`);
  }
  if (policyDoc.sha256 && policyDoc.sha256 !== actual) {
    throw new MechanicsBuildError(`policy self-declared sha256 ${policyDoc.sha256} != recomputed ${actual}`);
  }
}

// Biconditional eligibility recomputed from (policy, obs). A join's OWN promotion is consulted via
// policyDoc.joins[...], not just its components' — otherwise a normalized component set under a raw_only
// join would wrongly read as eligible.
export function eligibleFromPolicy(field, obs, policyDoc) {
  if (obs.components) {
    const join = (policyDoc.joins || {})[obs.join_name || field] || {};
    if (join.promotion !== "normalized" || obs.state !== "resolved") return false;
    return Object.entries(obs.components).every(([, c]) => {
      const cp = resolvePolicyRef(policyDoc, c.policy_ref);
      return cp.promotion === "normalized" && cp.layout === "verified" && cp.interpretation === "verified";
    });
  }
  const pol = resolvePolicyRef(policyDoc, obs.policy_ref);
  return pol.promotion === "normalized" && pol.layout === "verified" && pol.interpretation === "verified"
    && (obs.state === "present" || obs.state === "resolved") && obs.decoded_reason === "decoded";
}

// For EVERY field: eligible <=> populated (both halves of the biconditional), and a populated value must
// agree with a re-decode of raw_u32 (numeric) or the resolved string.
export function verifyRowAgainstPolicy(row, policyDoc) {
  const mech = row.mechanics || {};
  for (const [field, obs] of Object.entries(row.raw || {})) {
    const value = mech[field];
    const pol = obs.components
      ? resolvePolicyRef(policyDoc, obs.components.side_value.policy_ref)
      : resolvePolicyRef(policyDoc, obs.policy_ref);
    const eligible = eligibleFromPolicy(field, obs, policyDoc);
    const populated = value !== null && value !== undefined;
    if (eligible !== populated) {
      throw new MechanicsBuildError(`projection ${row.spell_id}: ${field} eligible=${eligible} but populated=${populated} (biconditional violation)`);
    }
    if (!populated) continue;
    if (pol.kind === "string") {
      const resolved = obs.components ? obs.components.side_value.resolved : obs.resolved;
      if (value !== resolved) throw new MechanicsBuildError(`projection ${row.spell_id}: ${field} != resolved`);
    } else {
      const raw = obs.components ? obs.components.side_value.raw_u32 : obs.raw_u32;
      if (redecode(raw, pol.kind) !== value) throw new MechanicsBuildError(`projection ${row.spell_id}: ${field} re-decode disagrees`);
    }
  }
}
