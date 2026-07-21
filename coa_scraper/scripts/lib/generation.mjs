import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { isDeepStrictEqual } from "node:util";
import { candidateTrustSha256FromText } from "./canonical.mjs";
import { assertPolicyLock, verifyRowAgainstPolicy, verifyFullRowAgainstPolicy, expandCompact } from "./mechanics-projection.mjs";

export class GenerationResolveError extends Error {}

const ICON_ASSET_STATUSES = new Set(["converted", "source_only", "missing", "placeholder"]);

const POINTER_SCHEMA = "coa-client-extract-pointer-v1";
const POINTER_NAME = "coa_client_extract.pointer.json";
const MANIFEST_NAME = "manifest.json";
const RESERVED = new Set([MANIFEST_NAME, POINTER_NAME]);

// The E0R required-child registry (mirrors coa_client_extract.publish.REQUIRED_CHILDREN): a candidate is
// only trustworthy if EVERY one of these is registered + valid, so an empty or partial generation is caught.
export const REQUIRED_CHILDREN = [
  "coa_client_spell.jsonl", "coa_client_spell_coa.jsonl",
  "coa_client_spell_projection.manifest.json", "coa_client_spell_icons.jsonl",
  "coa_client_content.jsonl", "coa_client_archive_plan.json",
  "coa_client_advancement.jsonl", "coa_client_class_types.jsonl",
  "coa_client_tab_types.jsonl", "coa_client_essence.jsonl", "spell_layout_v2.json",
];

const DEFAULT_LOCK_PATH = new URL("../../config/spell_layout.lock.json", import.meta.url);

function readJsonlRows(childPath) {
  return fs.readFileSync(childPath, "utf8").split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
}

function assertSortedUnique(rows, label) {
  let prev = null;
  for (const r of rows) {
    const sid = r.spell_id;
    if (prev !== null && sid <= prev) {
      throw new GenerationResolveError(`sorted_unique_ids: ${label} duplicate/out-of-order spell_id ${sid}`);
    }
    prev = sid;
  }
}

function identityAgrees(frow, prow) {
  if (frow.name !== prow.name) {
    throw new GenerationResolveError(`identity_agrees: spell ${frow.spell_id} name differs full vs projection`);
  }
  if (!isDeepStrictEqual(frow.mechanics, prow.mechanics)) {
    throw new GenerationResolveError(`identity_agrees: spell ${frow.spell_id} mechanics differ full vs projection`);
  }
  if (!isDeepStrictEqual(frow.coa_attribution, prow.coa_attribution)) {
    throw new GenerationResolveError(`identity_agrees: spell ${frow.spell_id} attribution differs full vs projection`);
  }
}

// Icon id/path agreement + bundle consistency (mirrors Python publish._icon_bundle): a valid asset_status,
// a placeholder (unresolved join) has a null client_path while a resolved status carries one, and only a
// `converted` row may reference a bundle asset.
function verifyIconRow(r) {
  if (!ICON_ASSET_STATUSES.has(r.asset_status)) {
    throw new GenerationResolveError(`icon asset_status ${JSON.stringify(r.asset_status)} not in ${[...ICON_ASSET_STATUSES]}`);
  }
  if (r.asset_status !== "converted" && r.converted_ref) {
    throw new GenerationResolveError(`icon ${r.spell_id}: non-converted row carries a converted_ref`);
  }
  if (r.asset_status === "converted" && !r.converted_ref) {
    throw new GenerationResolveError(`icon ${r.spell_id}: converted row missing converted_ref`);
  }
  if (r.asset_status === "placeholder" && r.client_path != null) {
    throw new GenerationResolveError(`icon id/path: placeholder spell ${r.spell_id} carries a client_path`);
  }
  if ((r.asset_status === "source_only" || r.asset_status === "converted") && r.client_path == null) {
    throw new GenerationResolveError(`icon id/path: ${r.asset_status} spell ${r.spell_id} missing client_path`);
  }
}

// Streaming cross-child merge-join over ascending spell_id (mirrors Python publish._cross_child + _icon_bundle):
// per-child sorted uniqueness, the icon catalog is exactly the full domain (catching missing/extra/trailing
// icons), projection ⊆ is_coa within domain, the disjoint v3 dialects, identity/mechanics/attribution
// agreement, and compact_raw_expands_to_envelope (expand(full.raw) deep-equals projection.field_observations).
export function crossChild(fullRows, projRows, iconRows, policyDoc, manifest) {
  assertSortedUnique(fullRows, "full");
  assertSortedUnique(projRows, "projection");
  assertSortedUnique(iconRows, "icons");
  if (iconRows.length !== fullRows.length) {
    throw new GenerationResolveError(`icons_agree: icon catalog has ${iconRows.length} rows but the full table has ${fullRows.length} (missing/extra/trailing)`);
  }
  for (const r of iconRows) verifyIconRow(r);

  let pi = 0;
  for (let i = 0; i < fullRows.length; i++) {
    const frow = fullRows[i];
    const sid = frow.spell_id;
    if (iconRows[i].spell_id !== sid) {
      throw new GenerationResolveError(`icons_agree: icon row ${i} spell_id ${iconRows[i].spell_id} != full ${sid}`);
    }
    if (pi < projRows.length && projRows[pi].spell_id < sid) {
      throw new GenerationResolveError(`projection_within_domain: ${projRows[pi].spell_id} outside is_coa domain`);
    }
    if (!("raw" in frow)) throw new GenerationResolveError(`full_is_compact: spell ${sid} missing compact raw`);
    if ("field_observations" in frow) throw new GenerationResolveError(`full_is_compact: spell ${sid} carries field_observations`);
    const expanded = {};
    for (const [f, cell] of Object.entries(frow.raw)) expanded[f] = expandCompact(cell, policyDoc);
    const isCoa = frow.coa_attribution && frow.coa_attribution.is_coa === true;
    if (isCoa) {
      if (pi >= projRows.length || projRows[pi].spell_id !== sid) {
        throw new GenerationResolveError(`projection_is_coa_subset: ${sid} missing from projection`);
      }
      const prow = projRows[pi];
      if ("raw" in prow) throw new GenerationResolveError(`projection_is_rich: spell ${sid} carries compact raw`);
      if (!("field_observations" in prow)) throw new GenerationResolveError(`projection_is_rich: spell ${sid} missing field_observations`);
      identityAgrees(frow, prow);
      if (!isDeepStrictEqual(expanded, prow.field_observations)) {
        throw new GenerationResolveError(`compact_raw_expands_to_envelope: spell ${sid} full.raw expansion != projection.field_observations`);
      }
      pi++;
    }
  }
  if (pi < projRows.length) {
    throw new GenerationResolveError(`projection_within_domain: ${projRows[pi].spell_id} outside is_coa domain`);
  }
  const anyConverted = iconRows.some((r) => r.asset_status === "converted");
  if (anyConverted && !("coa_client_spell_icons.bundle.tar" in (manifest.children || {}))) {
    throw new GenerationResolveError("icon bundle required: a converted row exists but no bundle child is registered");
  }
}

function sha256(buf) { return crypto.createHash("sha256").update(buf).digest("hex"); }

// Count non-empty JSONL lines by scanning bytes — never builds (or retains) a row array (design A4:
// "hashing the byte stream without materializing a row array"). Whitespace-only lines don't count.
function countJsonlRecords(body) {
  let count = 0, lineHasContent = false;
  for (let i = 0; i < body.length; i++) {
    const b = body[i];
    if (b === 0x0a) { if (lineHasContent) count++; lineHasContent = false; }
    else if (b !== 0x0d && b !== 0x20 && b !== 0x09) lineHasContent = true;
  }
  if (lineHasContent) count++;
  return count;
}

const MANIFEST_SCHEMAS = new Set(["coa-client-extract-manifest-v3", "coa-client-extract-manifest-v2"]);

// Validate every registered child by path (name safety, containment, sha256, byte_length, record count,
// schema) without materializing a row array. Shared by the pointer resolver and the candidate validator.
function validateChildrenByPath(genDir, manifest) {
  const children = manifest.children || {};
  const resolved = {};
  const seen = new Set();
  for (const [name, meta] of Object.entries(children)) {
    assertSafeChildName(name);
    if (seen.has(name)) throw new GenerationResolveError(`duplicate child ${name}`);
    seen.add(name);
    const childPath = path.resolve(genDir, name);
    if (path.dirname(childPath) !== path.resolve(genDir)) throw new GenerationResolveError(`child ${name} escapes the generation directory`);
    if (!fs.existsSync(childPath)) throw new GenerationResolveError(`child ${name} missing`);
    const body = fs.readFileSync(childPath);
    if (sha256(body) !== meta.sha256) throw new GenerationResolveError(`child ${name} sha256 mismatch`);
    if (body.length !== meta.byte_length) throw new GenerationResolveError(`child ${name} byte_length mismatch`);
    const records = name.endsWith(".jsonl") ? countJsonlRecords(body) : 1;
    if (records !== meta.records) throw new GenerationResolveError(`child ${name} record count mismatch (${records} != ${meta.records})`);
    if (!meta.schema_version) throw new GenerationResolveError(`child ${name} missing schema_version`);
    resolved[name] = childPath;
  }
  return resolved;
}

// Validate a staged CANDIDATE generation by path (no pointer), so the Node trust boundary runs BEFORE the
// pointer flips (design A5). Mirrors the Python validate_candidate_generation's structural checks; the
// cross-child merge-join stays authoritative in Python.
export function validateCandidateByPath(genDir, { lockPath = DEFAULT_LOCK_PATH } = {}) {
  const dir = path.resolve(genDir);
  const manifestPath = path.join(dir, MANIFEST_NAME);
  if (!fs.existsSync(manifestPath)) throw new GenerationResolveError("candidate manifest missing");
  const manifestText = fs.readFileSync(manifestPath, "utf8");
  let manifest;
  try { manifest = JSON.parse(manifestText); }
  catch (e) { throw new GenerationResolveError(`candidate manifest invalid JSON: ${e.message}`); }
  if (manifest.publication_state !== "candidate") throw new GenerationResolveError(`not a candidate generation (publication_state=${manifest.publication_state})`);
  if (manifest.schema_version !== "coa-client-extract-manifest-v3") throw new GenerationResolveError(`unsupported manifest schema_version ${manifest.schema_version}`);
  // The trust digest must cover the manifest (recomputed independently, bigint-safe) BEFORE trusting any field.
  const recomputedTrust = candidateTrustSha256FromText(manifestText);
  if (manifest.candidate_trust_sha256 !== recomputedTrust) {
    throw new GenerationResolveError(`candidate_trust_sha256 does not cover the manifest (recomputed ${recomputedTrust})`);
  }
  const children = validateChildrenByPath(dir, manifest);
  for (const name of REQUIRED_CHILDREN) {
    if (!(name in children)) throw new GenerationResolveError(`required child ${name} missing from the candidate generation`);
  }
  // The staged policy child must match the committed lock (recomputed, never self-trusted).
  const policyDoc = JSON.parse(fs.readFileSync(children["spell_layout_v2.json"], "utf8"));
  let lock;
  try { lock = JSON.parse(fs.readFileSync(lockPath, "utf8")); }
  catch (e) { throw new GenerationResolveError(`policy lock unreadable: ${e.message}`); }
  try { assertPolicyLock(policyDoc, lock); }
  catch (e) { throw new GenerationResolveError(`policy child not matched by the lock: ${e.message}`); }
  // Row semantics over the full required domain: every full row's required scalars are present (not just in
  // row.raw), and every projection row's claims + biconditional + value agreement re-derive from the policy.
  const fullRows = readJsonlRows(children["coa_client_spell.jsonl"]);
  const projRows = readJsonlRows(children["coa_client_spell_coa.jsonl"]);
  const iconRows = readJsonlRows(children["coa_client_spell_icons.jsonl"]);
  for (const row of fullRows) {
    try { verifyFullRowAgainstPolicy(row, policyDoc); }
    catch (e) { throw new GenerationResolveError(e.message); }
  }
  for (const row of projRows) {
    try { verifyRowAgainstPolicy(row, policyDoc); }
    catch (e) { throw new GenerationResolveError(e.message); }
  }
  // Streaming cross-child + bundle: dialects, identity/attribution, compact-raw expansion, icon domain/agreement.
  crossChild(fullRows, projRows, iconRows, policyDoc, manifest);
  return { genDir: dir, manifest, children };
}

function assertSafeChildName(name) {
  const parts = name.split(/[\\/]/);
  if (!name || RESERVED.has(name) || path.isAbsolute(name) || parts.includes("..") ||
      name.includes("/") || name.includes("\\")) {
    throw new GenerationResolveError(`unsafe child name ${name}`);
  }
}

// Equivalent validation to the Python resolve_active_generation: fails closed on pointer schema,
// gen-dir containment, manifest hash, and each child's path/sha256/byte_length/record-count/schema/
// uniqueness. `rootOrPointer` may be the directory holding the pointer OR the pointer file itself.
export function resolveGeneration(rootOrPointer) {
  let pointerPath = rootOrPointer;
  if (fs.existsSync(rootOrPointer) && fs.statSync(rootOrPointer).isDirectory()) {
    pointerPath = path.join(rootOrPointer, POINTER_NAME);
  }
  const root = path.resolve(path.dirname(pointerPath));
  if (!fs.existsSync(pointerPath)) throw new GenerationResolveError("no active generation pointer");

  let pointer;
  try { pointer = JSON.parse(fs.readFileSync(pointerPath, "utf8")); }
  catch (e) { throw new GenerationResolveError(`pointer invalid JSON: ${e.message}`); }
  if (pointer.schema_version !== POINTER_SCHEMA) throw new GenerationResolveError(`pointer bad schema_version ${pointer.schema_version}`);
  const genId = pointer.generation_id;
  if (typeof genId !== "string" || !genId) throw new GenerationResolveError("pointer missing generation_id");

  const genDir = path.resolve(root, `gen-${genId}`);
  if (path.relative(root, genDir).startsWith("..")) throw new GenerationResolveError("generation dir escapes root");
  const manifestPath = path.join(genDir, MANIFEST_NAME);
  if (!fs.existsSync(manifestPath)) throw new GenerationResolveError("generation manifest missing");

  const manifestBytes = fs.readFileSync(manifestPath);
  if (sha256(manifestBytes) !== pointer.manifest_sha256) throw new GenerationResolveError("manifest sha256 does not match the pointer");
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  if (manifest.generation_id !== genId) throw new GenerationResolveError("manifest generation_id disagrees with the pointer");
  // A candidate manifest is never consumable (an interrupted publish leaves no half-live generation).
  if (manifest.publication_state === "candidate") throw new GenerationResolveError("pointer resolves a candidate manifest (never publishable)");
  // Pre-E0R generations are rejected: E0R consumers require the manifest-v3 transaction.
  if (manifest.schema_version && !MANIFEST_SCHEMAS.has(manifest.schema_version)) {
    throw new GenerationResolveError(`unsupported manifest schema_version ${manifest.schema_version}`);
  }

  const resolved = validateChildrenByPath(genDir, manifest);
  return { generationId: genId, genDir, manifest, children: resolved };
}

// CLI: `node lib/generation.mjs <pointer-or-root>` prints the resolved child paths (exit 0) or the
// validation error (exit 3), so the transactional contract is scriptable from the shell / e2e test.
function isCliEntryPoint() {
  return process.argv[1] && import.meta.url === new URL(`file://${path.resolve(process.argv[1])}`).href;
}
if (isCliEntryPoint()) {
  const args = process.argv.slice(2);
  if (args[0] === "--candidate") {
    const genDir = args[1];
    if (!genDir) { console.error("usage: generation.mjs --candidate <gen-dir> [--lock <lock-path>]"); process.exit(2); }
    const lockIdx = args.indexOf("--lock");
    const opts = lockIdx >= 0 && args[lockIdx + 1] ? { lockPath: args[lockIdx + 1] } : {};
    try {
      const r = validateCandidateByPath(genDir, opts);
      console.log(JSON.stringify({ candidate: true, children: Object.keys(r.children) }, null, 2));
    } catch (e) { console.error(`error: ${e.message}`); process.exit(3); }
  } else {
    const target = args[0];
    if (!target) { console.error("usage: generation.mjs <pointer-or-root> | --candidate <gen-dir>"); process.exit(2); }
    try {
      const r = resolveGeneration(target);
      console.log(JSON.stringify({ generation_id: r.generationId, children: r.children }, null, 2));
    } catch (e) {
      console.error(`error: ${e.message}`);
      process.exit(3);
    }
  }
}
