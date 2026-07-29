import fs from "node:fs";
import crypto from "node:crypto";
import { isDeepStrictEqual } from "node:util";
import { JsonlParseError, readJsonlLinesHashed } from "./jsonl-stream.mjs";
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

export function loadAndValidateProjection({ projectionPath, manifestPath, builderSpellIds, policyPath = null }) {
  const hasProj = fs.existsSync(projectionPath);
  const hasMan = fs.existsSync(manifestPath);
  if (!hasProj && !hasMan) return { absent: true };
  if (hasProj !== hasMan) {
    throw new MechanicsBuildError(`torn projection pair: projection=${hasProj} manifest=${hasMan} (need both, or neither for fallback)`);
  }

  const manifestBytes = fs.readFileSync(manifestPath);
  const manifest = parseJson(manifestBytes.toString("utf8"), "projection manifest");
  // E0R v3: rows carry a compact `raw` block re-verified against the pinned policy child, not per-row
  // `field_observations`. The generation manifest already validated child integrity (sha/bytes/records).
  if (manifest.schema_version === "coa-client-spell-projection-manifest-v3") {
    return streamAndValidateProjectionV3({ projectionPath, manifestBytes, manifest, builderSpellIds, policyPath });
  }
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
    // The legacy v2 path still materializes its rows; `clientById` is derived here so the consumer sees
    // ONE shape from both paths and the canonical v3 path never has to hand back an array to match it.
    absent: false, projection, clientById: new Map(projection.map((r) => [Number(r.spell_id), r])),
    coverage, projection_sha256: sha,
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

// The rich field observation is SELF-DESCRIBING but never TRUSTED: Node re-derives proof/promotion from the
// staged policy and re-decodes the value from the raw substrate, then verifies the observation's claims
// (proof, promotion, decoded) match. A scalar carries {policy_ref, proof, promotion, raw_u32|raw_offset+
// resolved, decoded?}; a join carries per-component scalars under `components`.
function verifyScalarClaims(spellId, field, obs, policyDoc) {
  const pol = resolvePolicyRef(policyDoc, obs.policy_ref);
  const wantProof = { integrity: "verified", layout: pol.layout, interpretation: pol.interpretation };
  if (JSON.stringify(sortDeep(obs.proof)) !== JSON.stringify(sortDeep(wantProof))) {
    throw new MechanicsBuildError(`projection ${spellId}: ${field} proof claim disagrees with policy`);
  }
  if (obs.promotion !== pol.promotion) {
    throw new MechanicsBuildError(`projection ${spellId}: ${field} promotion claim disagrees with policy`);
  }
  if ("raw_offset" in obs) return;                    // string substrate: `resolved` is the value, no decoded dict
  const want = (obs.decoded_reason === "decoded" && obs.raw_u32 !== null && obs.raw_u32 !== undefined)
    ? { kind: pol.kind, value: redecode(obs.raw_u32, pol.kind) } : null;
  if (JSON.stringify(sortDeep(obs.decoded ?? null)) !== JSON.stringify(sortDeep(want))) {
    throw new MechanicsBuildError(`projection ${spellId}: ${field} decoded claim disagrees with re-decode`);
  }
}

// A projection row is the RICH dialect: it carries `field_observations`, never compact `raw`. For EVERY
// field: verify the self-describing claims, then eligible <=> populated (both halves of the biconditional),
// and a populated value agrees with a re-decode of raw_u32 (numeric) or the resolved string.
export function verifyRowAgainstPolicy(row, policyDoc) {
  const mech = row.mechanics || {};
  if (row.raw !== undefined) {
    throw new MechanicsBuildError(`projection ${row.spell_id}: carries compact raw (v3 projection is rich field_observations)`);
  }
  const fobs = row.field_observations;
  if (!fobs || typeof fobs !== "object") {
    throw new MechanicsBuildError(`projection ${row.spell_id}: missing field_observations`);
  }
  for (const [field, obs] of Object.entries(fobs)) {
    if (obs.components) {
      for (const [, c] of Object.entries(obs.components)) verifyScalarClaims(row.spell_id, field, c, policyDoc);
    } else {
      verifyScalarClaims(row.spell_id, field, obs, policyDoc);
    }
    // Identity fields live at the row level (id -> spell_id, name -> name); mechanics fields in `mechanics`.
    const value = field === "id" ? row.spell_id
      : (field in mech) ? mech[field]
      : (field in row) ? row[field]
      : undefined;
    const eligible = eligibleFromPolicy(field, obs, policyDoc);
    const populated = value !== null && value !== undefined;
    if (eligible !== populated) {
      throw new MechanicsBuildError(`projection ${row.spell_id}: ${field} eligible=${eligible} but populated=${populated} (biconditional violation)`);
    }
    if (!populated) continue;
    // Resolve the policy node ONLY when populated: an unresolved join (index_zero/side_row_missing) has no
    // side_value component, and a resolved join always does.
    const pol = obs.components
      ? resolvePolicyRef(policyDoc, obs.components.side_value.policy_ref)
      : resolvePolicyRef(policyDoc, obs.policy_ref);
    if (pol.kind === "string") {
      const resolved = obs.components ? obs.components.side_value.resolved : obs.resolved;
      if (value !== resolved) throw new MechanicsBuildError(`projection ${row.spell_id}: ${field} != resolved`);
    } else {
      const raw = obs.components ? obs.components.side_value.raw_u32 : obs.raw_u32;
      if (redecode(raw, pol.kind) !== value) throw new MechanicsBuildError(`projection ${row.spell_id}: ${field} re-decode disagrees`);
    }
  }
}

// Proof lattice (verified > reference > unproven > contradicted). composeProof takes the WEAKEST facet
// across contributing components — the exact mirror of Python spell_proof.compose_proof.
const PROOF_ORDER = { verified: 3, reference: 2, unproven: 1, contradicted: 0 };
const PROOF_INV = { 3: "verified", 2: "reference", 1: "unproven", 0: "contradicted" };
export function composeProof(proofs) {
  const facet = (k) => PROOF_INV[Math.min(...proofs.map((p) => PROOF_ORDER[p[k]]))];
  return { integrity: facet("integrity"), layout: facet("layout"), interpretation: facet("interpretation") };
}

// === E0R.2 T6.1: kind-aware field descriptors ===================================================
export const FIELD_DESCRIPTORS_SCHEMA = "coa-client-spell-fields-v1";

export class DescriptorError extends Error {}

// The Node twin of Python spell_record.build_field_descriptors. Derived from the policy, never read off
// a staged document: a descriptor defines what every hoisted cell MEANS, so accepting one on its own
// word would let a tampered document redefine a field's substrate while compact->rich expansion stayed
// perfectly self-consistent. KIND-AWARE, because a resolved join's three components each point at a
// DIFFERENT table-field through the join mapping and one pointer cannot reconstruct them.
export function buildFieldDescriptors(policyDoc) {
  const fields = {};
  for (const name of Object.keys(policyDoc.tables.Spell.fields)) {
    fields[name] = { kind: "scalar", policy_ref: policyRef("Spell", name) };
  }
  for (const [jname, join] of Object.entries(policyDoc.joins || {})) {
    fields[jname] = {
      kind: "join", join_name: jname,
      index_policy_ref: policyRef("Spell", join.index_field),
      components: {
        index: { policy_ref: policyRef("Spell", join.index_field) },
        side_id: { policy_ref: policyRef(join.side_table, "id") },
        side_value: { policy_ref: policyRef(join.side_table, join.side_value_field) },
      },
    };
  }
  return { schema_version: FIELD_DESCRIPTORS_SCHEMA, policy_sha256: policyDoc.sha256 ?? null, fields };
}

function policyRef(table, field) {
  if (!table || !field) throw new DescriptorError("policy_ref requires a table and a field");
  return `/tables/${table}/fields/${field}`;
}

// Re-derive from the policy and require the staged document to equal it, independently of what Python
// concluded — two trust boundaries, one canonical document.
export function requireFieldDescriptors(staged, policyDoc) {
  const expected = buildFieldDescriptors(policyDoc);
  if (!staged || typeof staged !== "object") throw new DescriptorError("field descriptors must be an object");
  if (staged.schema_version !== expected.schema_version) {
    throw new DescriptorError(`field descriptors schema_version ${staged.schema_version} is not ${expected.schema_version}`);
  }
  if (staged.policy_sha256 !== expected.policy_sha256) {
    throw new DescriptorError(`field descriptors policy_sha256 ${staged.policy_sha256} does not describe this policy (${expected.policy_sha256})`);
  }
  const got = staged.fields;
  if (!got || typeof got !== "object") throw new DescriptorError("field descriptors carry no `fields` object");
  for (const name of [...new Set([...Object.keys(got), ...Object.keys(expected.fields)])].sort()) {
    if (!(name in got) || !(name in expected.fields)) {
      throw new DescriptorError(`field descriptor set differs from the policy at ${name} (${name in got ? "staged only" : "policy only"})`);
    }
    if (!isDeepStrictEqual(got[name], expected.fields[name])) {
      throw new DescriptorError(`field descriptor ${name} differs from the policy-derived one`);
    }
  }
  return expected;
}

function descriptorFor(field, descriptors) {
  if (!descriptors || field === undefined || field === null) {
    throw new DescriptorError(
      `cell ${field} carries no inline policy_ref and no descriptors were supplied; refusing to guess ` +
      "which policy field it observes");
  }
  const entry = (descriptors.fields || {})[field];
  if (!entry) throw new DescriptorError(`no field descriptor for ${field}`);
  return entry;
}

// The pointer a cell observes: inline while both encodings are supported (T6.1), from the descriptor
// once T6.2 hoists it out of the row.
function cellPolicyRef(cell, field, descriptors, part = null) {
  if ("policy_ref" in cell) return cell.policy_ref;
  const entry = descriptorFor(field, descriptors);
  if (part !== null) return entry.components[part].policy_ref;
  return entry.kind === "join" ? entry.index_policy_ref : entry.policy_ref;
}

function isJoinCell(cell, field, descriptors) {
  if ("join_name" in cell || "components" in cell) return true;   // an ABSENT join carries no components
  if (!descriptors || field === undefined || field === null) return false;
  const entry = (descriptors.fields || {})[field];
  return Boolean(entry) && entry.kind === "join";
}

// Expand ONE compact scalar cell into its canonical rich observation — the exact inverse of the Python
// producer's _expand_scalar_cell: re-derive proof/promotion from the policy and re-decode from raw.
function expandScalarCell(cell, policyDoc, { field = null, descriptors = null, part = null } = {}) {
  const ref = cellPolicyRef(cell, field, descriptors, part);
  const fp = resolvePolicyRef(policyDoc, ref);
  const out = {
    state: cell.state, decoded_reason: cell.decoded_reason,
    proof: { integrity: "verified", layout: fp.layout, interpretation: fp.interpretation },
    promotion: fp.promotion, policy_ref: ref,
  };
  if ("raw_offset" in cell) {                             // string substrate
    out.raw_offset = cell.raw_offset;
    out.resolved = cell.resolved ?? null;
  } else {                                                // numeric substrate
    const rawU32 = cell.raw_u32 ?? null;
    out.raw_u32 = rawU32;
    out.decoded = (cell.decoded_reason === "decoded" && rawU32 !== null)
      ? { kind: fp.kind, value: redecode(rawU32, fp.kind) } : null;
  }
  return out;
}

// Expand a compact raw cell (scalar OR join) into its canonical rich field observation — the contract-
// critical inverse mirroring Python spell_record._expand_compact, so expandCompact(full.raw[f]) MUST
// deep-equal the projection's field_observations[f].
export function expandCompact(cell, policyDoc, { field = null, descriptors = null } = {}) {
  if (!isJoinCell(cell, field, descriptors)) return expandScalarCell(cell, policyDoc, { field, descriptors });
  const joinName = cell.join_name ?? descriptorFor(field, descriptors).join_name;
  if (!("components" in cell)) {                          // absent join (null index cell)
    const ref = cellPolicyRef(cell, field, descriptors);
    const fp = resolvePolicyRef(policyDoc, ref);
    return {
      join_name: joinName, state: cell.state, decoded_reason: cell.decoded_reason,
      policy_ref: ref,
      proof: { integrity: "verified", layout: fp.layout, interpretation: fp.interpretation },
      promotion: fp.promotion,
    };
  }
  const components = {};
  for (const [k, v] of Object.entries(cell.components)) {
    components[k] = expandScalarCell(v, policyDoc, { field, descriptors, part: k });
  }
  const composed = composeProof(Object.values(components).map((c) => c.proof));
  const join = (policyDoc.joins || {})[joinName];
  let decoded = null;
  if (cell.decoded_reason === "decoded" && "side_value" in components) {
    const sv = components.side_value;
    decoded = sv.decoded ? sv.decoded.value : (sv.resolved ?? null);
  }
  return {
    join_name: joinName, state: cell.state, decoded_reason: cell.decoded_reason,
    components, composed_proof: composed, decoded,
    promotion: join ? join.promotion : "raw_only",
  };
}

// A FULL row is the COMPACT dialect: it carries `raw`, never `field_observations`. Row validation iterates
// the policy-required scalar domain ∪ mechanics ∪ raw (NOT just `row.raw`), so a required field omitted from
// BOTH mechanics and raw is still visited and rejected — a bypass a raw-only iteration would miss.
export function verifyFullRowAgainstPolicy(row, policyDoc) {
  if (row.field_observations !== undefined) {
    throw new MechanicsBuildError(`full ${row.spell_id}: carries field_observations (full is the compact raw dialect)`);
  }
  const raw = row.raw;
  if (!raw || typeof raw !== "object") {
    throw new MechanicsBuildError(`full ${row.spell_id}: missing compact raw`);
  }
  const mech = row.mechanics || {};
  // E0R.2 T2.3: the observation domain comes from the policy's REVIEWED artifact_contract and this
  // fails CLOSED when it is absent. It used to read `policyDoc.required_scalar_fields || []` — and the
  // PRODUCTION policy never carried that key, so this check asked nothing of any real row.
  const contract = policyDoc.artifact_contract;
  if (!contract || !Array.isArray(contract.required_raw_observations)) {
    throw new MechanicsBuildError(
      `full ${row.spell_id}: staged policy declares no artifact_contract.required_raw_observations; ` +
      "the observation domain is unknown, so losslessness cannot be checked");
  }
  for (const field of contract.required_raw_observations) {
    // REQUIRED means the OBSERVATION exists, not that a normalized value does: a join in `unresolved`
    // state is still a required cell, and omitting it is the silent loss E0R exists to prevent.
    if (!(field in raw)) {
      throw new MechanicsBuildError(`full ${row.spell_id}: required field ${field} omitted from raw`);
    }
  }
  for (const key of contract.required_mechanics_keys) {
    if (!(key in mech)) {
      throw new MechanicsBuildError(`full ${row.spell_id}: required mechanics key ${key} absent (a null is a recorded observation; an absent key is loss)`);
    }
  }
}

// E0R: validate a coa-client-spell-projection-v3 projection (compact rows) against the pinned policy
// child. Per-row: v3 schema, is_coa, positive unique spell_id, and an independent numeric/string
// re-derivation via verifyRowAgainstPolicy. Child-byte integrity was already enforced by the generation
// manifest; here we re-hash for the input provenance record and count-check against the manifest.
//
// E0R.2 T5.1: STREAMED. The previous read was readFileSync -> toString -> split, accumulating every row
// into an array the caller then turned into a Map — the whole 400 MB projection held three ways. What
// the build actually needs is a LOOKUP for the ~3,600 Builder spells, so only those rows are retained;
// every row is still parsed and validated on its way past, because a corrupt row outside the Builder
// domain is still a corrupt generation. The sha256 accumulates over the exact bytes read, so the
// provenance hash is unchanged from the whole-file one it replaces.
export function streamAndValidateProjectionV3({ projectionPath, manifestBytes, manifest, builderSpellIds, policyPath }) {
  if (!policyPath || !fs.existsSync(policyPath)) {
    throw new MechanicsBuildError("v3 projection requires the reviewed spell_layout_v2 policy child");
  }
  const policyDoc = parseJson(fs.readFileSync(policyPath, "utf8"), "spell policy");
  const counts = manifest.counts || {};

  const clientById = new Map();
  const seen = new Set();          // counter-scale: ~10k integers, not rows
  let projected = 0, projectionOnly = 0;
  const stream = readJsonlLinesHashed(projectionPath);
  try {
    for (const { row: rec, lineNo } of stream.rows) {
      projected += 1;
      if (rec.schema_version !== "coa-client-spell-projection-v3") {
        throw new MechanicsBuildError(`projection row bad schema_version: ${rec.schema_version}`);
      }
      if (rec.coa_attribution?.is_coa !== true) throw new MechanicsBuildError(`projection row not is_coa: ${rec.spell_id}`);
      if (!Number.isInteger(rec.spell_id) || rec.spell_id <= 0) throw new MechanicsBuildError(`projection non-positive-integer spell_id: ${rec.spell_id}`);
      if (seen.has(rec.spell_id)) throw new MechanicsBuildError(`projection duplicate spell_id: ${rec.spell_id} (line ${lineNo})`);
      verifyRowAgainstPolicy(rec, policyDoc);            // independent numeric/string re-derivation
      seen.add(rec.spell_id);
      if (builderSpellIds.has(rec.spell_id)) clientById.set(rec.spell_id, rec);
      else projectionOnly += 1;
    }
  } catch (err) {
    if (err instanceof JsonlParseError) throw new MechanicsBuildError(`projection line ${err.lineNo}: invalid JSON: ${err.cause.message}`);
    throw err;
  }
  if (Number.isInteger(counts.projected_records) && counts.projected_records !== projected) {
    throw new MechanicsBuildError(`projection count mismatch: manifest ${counts.projected_records} != actual ${projected}`);
  }
  if (Number.isInteger(counts.unique_spell_ids) && counts.unique_spell_ids !== seen.size) {
    throw new MechanicsBuildError(`projection unique_spell_ids mismatch: manifest ${counts.unique_spell_ids} != actual ${seen.size}`);
  }

  const missing = [...builderSpellIds].filter((s) => !seen.has(s));
  if (missing.length > 0) {
    throw new MechanicsBuildError(`builder_missing_from_projection: ${missing.length} spell(s), e.g. ${missing.slice(0, 5)}`);
  }
  const coverage = {
    builder_joined_to_projection: clientById.size,
    builder_missing_from_projection: 0,
    projection_only: projectionOnly,
  };
  return {
    absent: false, clientById, coverage, projection_sha256: stream.sha256(),
    manifest_sha256: crypto.createHash("sha256").update(manifestBytes).digest("hex"),
    client_build: manifest.client_build ?? null,
  };
}
