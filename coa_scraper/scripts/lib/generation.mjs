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

// === the GENERATION CONTRACT registry (E0R.2 T1.3) ===
// The required-child list used to be a hand-mirrored constant here, restating a Python constant. A mirrored
// constant is what drifts. Node now reads the SAME immutable registry files Python ships, validates the
// selected revision with an INDEPENDENT implementation (so a bug in one language cannot be laundered
// through the other), and performs the same three-way comparison: staged bytes, bound hash, and membership
// in its own supported set.
export const GENERATION_CONTRACT_SCHEMA = "coa-generation-contract-v1";
export const CONTRACT_INDEX_SCHEMA = "coa-generation-contract-index-v1";
export const GENERATION_CONTRACT_CHILD = "generation_contract.json";
const DEFAULT_CONTRACTS_DIR = new URL("../../../coa_client_extract/data/generation_contracts/", import.meta.url);

const CHILD_KEYS = ["cardinality", "child_schema_version", "kind", "optional", "row_schema_version", "shape"];
// rule -> the EXACT key set its cardinality object must carry (`single_document` carrying a `min` or a
// `source_table` is a contradiction, not a harmless extra).
const CARDINALITY_KEYS_BY_RULE = {
  reviewed_bound_record_count: ["rule", "source_table"],
  derived_from_source_topology: ["rule", "source_table"],
  declared_derivation: ["rule", "source_table"],
  declared_content_derivation: ["rule"],
  equals_full_spell_records: ["rule"],
  equals_is_coa_full_records: ["rule"],
  single_document: ["rule"],
  min: ["min", "rule"],
};
const SAFE_CHILD_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const SAFE_REVISION_PATH = /^[a-z0-9][a-z0-9.-]*\.json$/;

// Canonical JSON: recursively key-sorted, no whitespace — reproducing Python's
// json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False). Contract keys are ASCII, where
// JS's UTF-16 sort and Python's code-point sort agree; the cross-language hash test proves the equality
// for the actual documents rather than assuming it.
function sortDeep(value) {
  if (Array.isArray(value)) return value.map(sortDeep);
  if (value && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = sortDeep(value[key]);
    return out;
  }
  return value;
}

export function generationContractSha256(doc) {
  return crypto.createHash("sha256").update(Buffer.from(JSON.stringify(sortDeep(doc)), "utf8")).digest("hex");
}

const sameSet = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);

// An INDEPENDENT implementation of the contract self-validation, not a port: a broken gate that loads is
// worse than no gate, and two boundaries agreeing only because they share code is not agreement.
export function validateGenerationContract(doc) {
  const fail = (m) => { throw new GenerationResolveError(`generation contract invalid: ${m}`); };
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) fail("must be an object");
  if (doc.schema_version !== GENERATION_CONTRACT_SCHEMA) fail(`schema_version ${doc.schema_version}`);
  const extraTop = Object.keys(doc).filter((k) =>
    !["schema_version", "revision", "note", "observation_wire_schema", "children"].includes(k));
  if (extraTop.length) fail(`unexpected top-level key(s) ${extraTop.sort().join(", ")}`);
  if (typeof doc.revision !== "string" || !doc.revision) fail("revision must be a non-empty string");
  const wire = doc.observation_wire_schema;
  if (!wire || typeof wire !== "object" || !wire.schema_version || String(wire.sha256 || "").length !== 64) {
    fail("must pin the observation wire schema by schema_version + sha256");
  }
  const children = doc.children;
  if (!children || typeof children !== "object" || Array.isArray(children) || !Object.keys(children).length) {
    fail("declares no children");
  }
  const shapes = new Set();
  for (const [name, spec] of Object.entries(children)) {
    if (!SAFE_CHILD_NAME.test(name)) fail(`unsafe child name ${name}: plain filenames only`);
    if (!spec || typeof spec !== "object" || Array.isArray(spec)) fail(`child ${name} spec must be an object`);
    if (!sameSet(Object.keys(spec).sort(), CHILD_KEYS)) {
      fail(`child ${name} keys ${Object.keys(spec).sort().join(", ")} != ${CHILD_KEYS.join(", ")}`);
    }
    if (spec.kind !== "jsonl" && spec.kind !== "json") fail(`child ${name} kind ${spec.kind}`);
    if (typeof spec.child_schema_version !== "string" || !spec.child_schema_version) {
      fail(`child ${name} child_schema_version must be a non-empty string`);
    }
    if (spec.kind === "jsonl") {
      if (typeof spec.row_schema_version !== "string" || !spec.row_schema_version) {
        fail(`child ${name} jsonl child needs a row_schema_version`);
      }
    } else if (spec.row_schema_version !== null) {
      fail(`child ${name} json child must have row_schema_version null`);
    }
    if (typeof spec.optional !== "boolean") fail(`child ${name} optional must be a boolean`);
    if (typeof spec.shape !== "string" || !spec.shape) fail(`child ${name} shape must name a validator`);
    if (shapes.has(spec.shape)) fail(`shape ${spec.shape} is reused; each child needs its own shape`);
    shapes.add(spec.shape);

    const card = spec.cardinality;
    if (!card || typeof card !== "object" || Array.isArray(card)) fail(`child ${name} cardinality must be an object`);
    const expected = CARDINALITY_KEYS_BY_RULE[card.rule];
    if (!expected) fail(`child ${name} cardinality rule ${card.rule} is not a known rule`);
    if (!sameSet(Object.keys(card).sort(), expected)) {
      fail(`child ${name} cardinality for rule ${card.rule} must have exactly ${expected.join(", ")}`);
    }
    if (card.rule === "min" && (!Number.isInteger(card.min) || card.min < 1)) {
      fail(`child ${name} min cardinality needs a positive integer floor`);
    }
    if (expected.includes("source_table") && (typeof card.source_table !== "string" || !card.source_table)) {
      fail(`child ${name} rule ${card.rule} needs a non-empty source_table`);
    }
  }
  return doc;
}

export function validateContractRegistry(doc) {
  const fail = (m) => { throw new GenerationResolveError(`generation contract registry invalid: ${m}`); };
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) fail("must be an object");
  if (doc.schema_version !== CONTRACT_INDEX_SCHEMA) fail(`schema_version ${doc.schema_version}`);
  const extra = Object.keys(doc).filter((k) => !["schema_version", "current", "supported", "note"].includes(k));
  if (extra.length) fail(`unexpected key(s) ${extra.sort().join(", ")}`);
  const supported = doc.supported;
  if (!supported || typeof supported !== "object" || Array.isArray(supported) || !Object.keys(supported).length) {
    fail("lists no supported revisions");
  }
  for (const [revision, entry] of Object.entries(supported)) {
    if (!entry || typeof entry !== "object" || !sameSet(Object.keys(entry).sort(), ["path", "sha256"])) {
      fail(`entry ${revision} must have exactly path, sha256`);
    }
    if (typeof entry.path !== "string" || !SAFE_REVISION_PATH.test(entry.path)) fail(`entry ${revision} path ${entry.path} is unsafe`);
    if (typeof entry.sha256 !== "string" || entry.sha256.length !== 64) fail(`entry ${revision} sha256 must be a 64-char digest`);
  }
  if (!Object.prototype.hasOwnProperty.call(supported, doc.current)) fail(`current ${doc.current} is not a supported revision`);
  return doc;
}

export function loadContractRegistry(contractsDir = DEFAULT_CONTRACTS_DIR) {
  const indexPath = new URL("index.json", contractsDir);
  let doc;
  try { doc = JSON.parse(fs.readFileSync(indexPath, "utf8")); }
  catch (e) { throw new GenerationResolveError(`generation contract registry unreadable: ${e.message}`); }
  return validateContractRegistry(doc);
}

// Set MEMBERSHIP, never equality with `current`: a generation published under an older supported revision
// must stay resolvable, or rollback and the predecessor chain break the moment a new revision ships.
export function loadSupportedContract(revision, sha256Expected, contractsDir = DEFAULT_CONTRACTS_DIR) {
  const registry = loadContractRegistry(contractsDir);
  const entry = registry.supported[revision];
  if (!entry) {
    throw new GenerationResolveError(
      `generation_contract: not the supported contract — unsupported revision ${revision} ` +
      `(supported: ${Object.keys(registry.supported).sort().join(", ")})`);
  }
  let doc;
  try { doc = JSON.parse(fs.readFileSync(new URL(entry.path, contractsDir), "utf8")); }
  catch (e) { throw new GenerationResolveError(`generation contract ${revision} unreadable: ${e.message}`); }
  validateGenerationContract(doc);
  if (doc.revision !== revision) throw new GenerationResolveError(`contract file ${entry.path} declares revision ${doc.revision}`);
  const actual = generationContractSha256(doc);
  if (actual !== entry.sha256) {
    throw new GenerationResolveError(
      `generation contract ${revision} sha256 ${actual.slice(0, 16)} != registry pin ${entry.sha256.slice(0, 16)}: ` +
      "the revision was edited in place; add a new revision instead");
  }
  if (sha256Expected !== entry.sha256) {
    throw new GenerationResolveError(
      `generation_contract: not the supported contract — ${revision} sha256 ` +
      `${String(sha256Expected).slice(0, 16)} != trusted ${entry.sha256.slice(0, 16)}`);
  }
  return doc;
}

export function loadCurrentContract(contractsDir = DEFAULT_CONTRACTS_DIR) {
  const registry = loadContractRegistry(contractsDir);
  return [registry.current, loadSupportedContract(registry.current, registry.supported[registry.current].sha256, contractsDir)];
}

// A RESOLVER's requirement comes from the generation's own verified staged contract, never from `current`.
export function requiredChildrenFor(contract) {
  return Object.entries(contract.children).filter(([, spec]) => !spec.optional).map(([name]) => name).sort();
}

// The PRODUCER-side view, derived rather than mirrored. Kept as an export because tests and callers refer
// to "what a complete generation carries today".
export const REQUIRED_CHILDREN = requiredChildrenFor(loadCurrentContract()[1]);

// The three-way agreement: staged child, manifest binding, own registry. Mirrors Python
// publish._staged_contract; returns the REGISTRY copy, identical by hash but never the staged bytes.
function stagedContract(genDir, manifest, contractsDir) {
  const childPath = path.join(genDir, GENERATION_CONTRACT_CHILD);
  if (!fs.existsSync(childPath)) {
    throw new GenerationResolveError(
      `required child ${GENERATION_CONTRACT_CHILD} missing: the generation does not declare the contract it was produced under`);
  }
  let staged;
  try { staged = JSON.parse(fs.readFileSync(childPath, "utf8")); }
  catch (e) { throw new GenerationResolveError(`staged generation contract is not valid JSON: ${e.message}`); }
  validateGenerationContract(staged);

  const stagedSha = generationContractSha256(staged);
  const bound = (manifest.binding || {}).generation_contract;
  if (!bound || typeof bound !== "object" || Array.isArray(bound)) {
    throw new GenerationResolveError(
      "manifest binding.generation_contract missing: the generation stages a contract but does not bind it");
  }
  if (bound.schema_version !== GENERATION_CONTRACT_SCHEMA) {
    throw new GenerationResolveError(`binding.generation_contract schema_version ${bound.schema_version}`);
  }
  if (bound.sha256 !== stagedSha) {
    throw new GenerationResolveError(
      `binding.generation_contract: the staged child hashes ${stagedSha.slice(0, 16)} but the binding names ${String(bound.sha256).slice(0, 16)}`);
  }
  if (bound.revision !== staged.revision) {
    throw new GenerationResolveError(
      `binding.generation_contract: staged revision ${staged.revision} != bound revision ${bound.revision}`);
  }
  return loadSupportedContract(bound.revision, stagedSha, contractsDir);
}

const DEFAULT_LOCK_PATH = new URL("../../config/spell_layout.lock.json", import.meta.url);

const CHUNK = 1 << 20;

// Sync generator over a JSONL child: fixed-size reads with a byte-level carry (utf8-safe across chunk
// boundaries), yielding one parsed row at a time — never a whole-child string or row array (E0R.1 T4.2).
function* readJsonlLines(childPath) {
  const fd = fs.openSync(childPath, "r");
  try {
    const buf = Buffer.allocUnsafe(CHUNK);
    let rem = Buffer.alloc(0);
    while (true) {
      const n = fs.readSync(fd, buf, 0, CHUNK, null);
      if (n === 0) break;
      const data = rem.length ? Buffer.concat([rem, buf.subarray(0, n)]) : buf.subarray(0, n);
      let start = 0, idx;
      while ((idx = data.indexOf(0x0a, start)) !== -1) {
        const line = data.toString("utf8", start, idx);
        if (line.trim()) yield JSON.parse(line);
        start = idx + 1;
      }
      rem = Buffer.from(data.subarray(start));   // copy: `buf` is reused by the next read
    }
    const tail = rem.toString("utf8");
    if (tail.trim()) yield JSON.parse(tail);
  } finally {
    fs.closeSync(fd);
  }
}

// Chunked integrity scan: sha256 + byte length + record count (non-empty lines) without holding the child
// in memory — the streaming twin of Python publish._scan_child (E0R.1 T4.2).
function scanChild(childPath, jsonl) {
  const fd = fs.openSync(childPath, "r");
  try {
    const buf = Buffer.allocUnsafe(CHUNK);
    const hash = crypto.createHash("sha256");
    let bytes = 0, records = 0, lineHasContent = false;
    while (true) {
      const n = fs.readSync(fd, buf, 0, CHUNK, null);
      if (n === 0) break;
      const chunk = buf.subarray(0, n);
      hash.update(chunk);
      bytes += n;
      if (jsonl) {
        for (let i = 0; i < n; i++) {
          const b = chunk[i];
          if (b === 0x0a) { if (lineHasContent) records++; lineHasContent = false; }
          else if (b !== 0x0d && b !== 0x20 && b !== 0x09) lineHasContent = true;
        }
      }
    }
    if (jsonl && lineHasContent) records++;
    return { sha256: hash.digest("hex"), byteLength: bytes, records: jsonl ? records : 1 };
  } finally {
    fs.closeSync(fd);
  }
}

// A forward, ascending-by-spell_id cursor enforcing sorted-unique order as it advances — the exact mirror
// of Python publish._Cursor, over ANY iterable (array or generator).
class Cursor {
  constructor(iterable, label) {
    this.it = iterable[Symbol.iterator]();
    this.label = label;
    this.prev = null;
    this.row = null;
    this.advance();
  }
  advance() {
    const nxt = this.it.next();
    this.row = nxt.done ? null : nxt.value;
    if (this.row !== null && this.row !== undefined) {
      const sid = this.row.spell_id;
      if (this.prev !== null && sid <= this.prev) {
        throw new GenerationResolveError(`sorted_unique_ids: ${this.label} duplicate/out-of-order spell_id ${sid}`);
      }
      this.prev = sid;
    } else {
      this.row = null;
    }
    return this.row;
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
  const full = new Cursor(fullRows, "full");
  const proj = new Cursor(projRows, "projection");
  const icons = new Cursor(iconRows, "icons");
  let anyConverted = false;
  while (full.row !== null) {
    const frow = full.row;
    const sid = frow.spell_id;
    // The icon catalog advances in LOCKSTEP with the full table (exact 1:1 domain): a missing, orphan, or
    // trailing icon row is a mismatch — identical to Python publish._cross_child.
    if (icons.row === null) {
      throw new GenerationResolveError(`icons_agree: spell ${sid} lacks an icon-catalog row`);
    }
    if (icons.row.spell_id !== sid) {
      throw new GenerationResolveError(`icons_agree: icon row spell_id ${icons.row.spell_id} != full ${sid}`);
    }
    verifyIconRow(icons.row);
    anyConverted = anyConverted || icons.row.asset_status === "converted";
    icons.advance();
    if (proj.row !== null && proj.row.spell_id < sid) {
      throw new GenerationResolveError(`projection_within_domain: ${proj.row.spell_id} outside is_coa domain`);
    }
    if (!("raw" in frow)) throw new GenerationResolveError(`full_is_compact: spell ${sid} missing compact raw`);
    if ("field_observations" in frow) throw new GenerationResolveError(`full_is_compact: spell ${sid} carries field_observations`);
    const expanded = {};
    for (const [f, cell] of Object.entries(frow.raw)) expanded[f] = expandCompact(cell, policyDoc);
    const isCoa = frow.coa_attribution && frow.coa_attribution.is_coa === true;
    if (isCoa) {
      if (proj.row === null || proj.row.spell_id !== sid) {
        throw new GenerationResolveError(`projection_is_coa_subset: ${sid} missing from projection`);
      }
      const prow = proj.row;
      if ("raw" in prow) throw new GenerationResolveError(`projection_is_rich: spell ${sid} carries compact raw`);
      if (!("field_observations" in prow)) throw new GenerationResolveError(`projection_is_rich: spell ${sid} missing field_observations`);
      identityAgrees(frow, prow);
      if (!isDeepStrictEqual(expanded, prow.field_observations)) {
        throw new GenerationResolveError(`compact_raw_expands_to_envelope: spell ${sid} full.raw expansion != projection.field_observations`);
      }
      proj.advance();
    }
    full.advance();
  }
  if (proj.row !== null) {
    throw new GenerationResolveError(`projection_within_domain: ${proj.row.spell_id} outside is_coa domain`);
  }
  if (icons.row !== null) {
    throw new GenerationResolveError(`icons_agree: trailing icon row ${icons.row.spell_id} beyond the full domain`);
  }
  if (anyConverted && !("coa_client_spell_icons.bundle.tar" in (manifest.children || {}))) {
    throw new GenerationResolveError("icon bundle required: a converted row exists but no bundle child is registered");
  }
}

function sha256(buf) { return crypto.createHash("sha256").update(buf).digest("hex"); }

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
    const scan = scanChild(childPath, name.endsWith(".jsonl"));
    if (scan.sha256 !== meta.sha256) throw new GenerationResolveError(`child ${name} sha256 mismatch`);
    if (scan.byteLength !== meta.byte_length) throw new GenerationResolveError(`child ${name} byte_length mismatch`);
    if (scan.records !== meta.records) throw new GenerationResolveError(`child ${name} record count mismatch (${scan.records} != ${meta.records})`);
    if (!meta.schema_version) throw new GenerationResolveError(`child ${name} missing schema_version`);
    resolved[name] = childPath;
  }
  return resolved;
}

// Validate a staged CANDIDATE generation by path (no pointer), so the Node trust boundary runs BEFORE the
// pointer flips (design A5). Mirrors the Python validate_candidate_generation's structural checks; the
// cross-child merge-join stays authoritative in Python.
export function validateCandidateByPath(genDir, { lockPath = DEFAULT_LOCK_PATH, contractsDir } = {}) {
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
  // The contract is established BEFORE any per-child work: it is what says which children are required.
  const contract = stagedContract(dir, manifest, contractsDir);
  const children = validateChildrenByPath(dir, manifest);
  for (const name of requiredChildrenFor(contract)) {
    if (!(name in children)) throw new GenerationResolveError(`required child ${name} missing from the candidate generation`);
  }
  // The staged policy child must match the committed lock (recomputed, never self-trusted).
  const policyDoc = JSON.parse(fs.readFileSync(children["spell_layout_v2.json"], "utf8"));
  let lock;
  try { lock = JSON.parse(fs.readFileSync(lockPath, "utf8")); }
  catch (e) { throw new GenerationResolveError(`policy lock unreadable: ${e.message}`); }
  try { assertPolicyLock(policyDoc, lock); }
  catch (e) { throw new GenerationResolveError(`policy child not matched by the lock: ${e.message}`); }
  // Row semantics over the full required domain, verified AS the rows stream through the cross-child
  // cursors — one pass, no retained row arrays (E0R.1 T4.2). Every full row's required scalars are present
  // (not just in row.raw); every projection row's claims + biconditional + value agreement re-derive from
  // the policy; then dialects, identity/attribution, compact-raw expansion, icon domain/agreement, bundle.
  const verified = function* (iter, verify) {
    for (const row of iter) {
      try { verify(row, policyDoc); }
      catch (e) { throw new GenerationResolveError(e.message); }
      yield row;
    }
  };
  crossChild(
    verified(readJsonlLines(children["coa_client_spell.jsonl"]), verifyFullRowAgainstPolicy),
    verified(readJsonlLines(children["coa_client_spell_coa.jsonl"]), verifyRowAgainstPolicy),
    readJsonlLines(children["coa_client_spell_icons.jsonl"]),
    policyDoc, manifest);
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
export function resolveGeneration(rootOrPointer, { contractsDir } = {}) {
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
  const manifestText = manifestBytes.toString("utf8");
  const manifest = JSON.parse(manifestText);
  if (manifest.generation_id !== genId) throw new GenerationResolveError("manifest generation_id disagrees with the pointer");
  assertPublishedManifest(manifest, manifestText);

  // Identical rules to the candidate path, so a PUBLISHED generation under an older supported revision
  // resolves by exactly the three-way agreement it was validated under.
  const contract = stagedContract(genDir, manifest, contractsDir);
  const resolved = validateChildrenByPath(genDir, manifest);
  for (const name of requiredChildrenFor(contract)) {
    if (!(name in resolved)) throw new GenerationResolveError(`required child ${name} missing from the published generation`);
  }
  return { generationId: genId, genDir, manifest, children: resolved };
}

// A pointer may resolve ONLY a fully-published E0R generation. Mirrors Python publish._assert_published_manifest:
// a v3 manifest, publication_state 'published', a candidate_trust_sha256 that covers it (recomputed bigint-safe),
// `validation` BOTH python+node true, and a within-budget report. validation/budget are mutable (excluded from
// the trust digest), so they are re-checked independently here.
function assertPublishedManifest(manifest, manifestText) {
  if (manifest.schema_version !== "coa-client-extract-manifest-v3") {
    throw new GenerationResolveError(`unsupported manifest schema_version ${manifest.schema_version} (E0R requires v3)`);
  }
  if (manifest.publication_state !== "published") {
    throw new GenerationResolveError(`generation not published (publication_state=${manifest.publication_state})`);
  }
  const recomputedTrust = candidateTrustSha256FromText(manifestText);
  if (manifest.candidate_trust_sha256 !== recomputedTrust) {
    throw new GenerationResolveError(`candidate_trust_sha256 does not cover the published manifest (recomputed ${recomputedTrust})`);
  }
  const validation = manifest.validation || {};
  if (validation.python !== true || validation.node !== true) {
    throw new GenerationResolveError(`generation not validated by both trust boundaries (validation=${JSON.stringify(validation)})`);
  }
  const budget = manifest.budget || {};
  if (budget.within_budget !== true) {
    throw new GenerationResolveError(`generation exceeded its budget (within_budget=${budget.within_budget})`);
  }
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
