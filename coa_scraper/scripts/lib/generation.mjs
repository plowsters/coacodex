import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { isDeepStrictEqual } from "node:util";
import { candidateTrustSha256FromText } from "./canonical.mjs";
import { CHUNK, readJsonlLines } from "./jsonl-stream.mjs";
import { decodedReasonName } from "./mechanics-projection.mjs";
import { assertPolicyLock, verifyRowAgainstPolicy, verifyFullRowAgainstPolicy, expandCompact,
         buildFieldDescriptors, requireFieldDescriptors, requireObservationWire,
         FIELD_DESCRIPTORS_CHILD, WIRE_SCHEMA_CHILD } from "./mechanics-projection.mjs";
import { SHAPES, ShapeError, installContractValidator } from "./shapes.mjs";

export class GenerationResolveError extends Error {}

// E0R.2 T2.5: `converted` (and its icon bundle) is PROHIBITED in this schema — it promised tar path
// containment, per-entry bundle-manifest verification and per-asset content hashes, of which E0R.1
// shipped only an existence test for the bundle child, and nothing ever produced the status.
// Reintroducing it requires all three checks plus a producer, in the same change.
const ICON_ASSET_STATUSES = new Set(["source_only", "missing", "placeholder"]);

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
// E0R.2 T6.3: the normalized icon asset child.
export const ICON_ASSET_CHILD = "coa_client_icon_assets.jsonl";
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
  equals_referenced_asset_set: ["rule"],

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

installContractValidator(validateGenerationContract);

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

// === POLICY-ROOTED CARDINALITY (E0R.2 T2.1) ===
// `min_records: 1` was never a domain gate: a one-spell generation passes it, and so does a
// one-class-type generation. Deriving the expectation from `manifest.binding.topology` would be
// circular — a malformed candidate sets that count to 1, writes one row, recomputes the trust digest and
// satisfies the equality. The REVIEWED POLICY states the count, and the policy is pinned by the lock.

// Facet-for-facet comparison of a recorded topology report against a policy's structured `bound`
// (mirrors Python topology.topology_matches_bound). Returns the list of mismatches; empty means the
// recorded topology IS the reviewed capture.
function topologyMismatches(report, bound) {
  if (!bound) return [{ table: "*", field: "bound", reason: "policy has no bound" }];
  const mism = [];
  const tables = (report && report.tables) || {};
  if (report?.client_build !== bound.client_build) mism.push({ table: "*", field: "client_build", reason: "build_mismatch" });
  const want = bound.tables || {};
  const wantNames = Object.keys(want).sort(), gotNames = Object.keys(tables).sort();
  if (!sameSet(wantNames, gotNames)) mism.push({ table: "*", field: "table_set", reason: "required_table_set_differs" });
  for (const [name, w] of Object.entries(want)) {
    const got = tables[name];
    if (!got) { mism.push({ table: name, field: "*", reason: "missing_from_client" }); continue; }
    const pairs = [["sha256", got.sha256, w.sha256], ["header", got.header, w.header],
                   ["member", got.member, w.source.member],
                   ["effective_archive", got.effective_archive, w.source.effective_archive],
                   ["patch_chain", got.patch_chain, w.source.patch_chain]];
    for (const [field, a, b] of pairs) {
      if (!isDeepStrictEqual(a, b)) mism.push({ table: name, field, reason: `${field}_differs` });
    }
  }
  const wantAbsent = [...(bound.expected_absent || [])].sort();
  const gotAbsent = [...((report && report.expected_absent_set) || [])].sort();
  if (!sameSet(wantAbsent, gotAbsent)) mism.push({ table: "*", field: "expected_absent", reason: "expected_absent_set_differs" });
  if (report && report.expected_absent_ok !== true) mism.push({ table: "*", field: "expected_absent", reason: "expected_absent_present" });
  return mism;
}

// The reviewed policy the cardinality rules resolve against, in three separately-messaged steps.
// The staged descriptor/wire children must equal what this validator derives itself. Skipped for a
// revision that does not register them, so an `e0r-v1` generation still resolves — the revision decides
// which children exist, not the code.
function requireStagedDecoders(genDir, contract, policyDoc) {
  const checks = [
    [FIELD_DESCRIPTORS_CHILD, (doc) => requireFieldDescriptors(doc, policyDoc)],
    [WIRE_SCHEMA_CHILD, requireObservationWire],
  ];
  for (const [name, check] of checks) {
    if (!(name in contract.children)) continue;
    try {
      check(JSON.parse(fs.readFileSync(path.join(genDir, name), "utf8")));
    } catch (e) {
      throw new GenerationResolveError(`${name}: ${e.message}`);
    }
  }
}

function trustedPolicy(genDir, manifest, policyDoc, lock) {
  // 1. the staged policy IS the locally supported policy (recomputed, never self-declared).
  try { assertPolicyLock(policyDoc, lock); }
  catch (e) { throw new GenerationResolveError(`staged policy is not the supported policy: ${e.message}`); }
  // 2. the manifest binds that same policy.
  const bound = (manifest.binding || {}).policy_sha256;
  if (bound !== policyDoc.sha256) {
    throw new GenerationResolveError(
      `binding.policy_sha256 ${String(bound).slice(0, 16)} != the staged policy child ${String(policyDoc.sha256).slice(0, 16)}`);
  }
  if (!policyDoc.bound) {
    throw new GenerationResolveError(
      "staged policy is unbound (bound: null): it was never proven against a client capture, so the " +
      "generation has no provable source domain");
  }
  // 3. the recorded topology IS the reviewed bound, facet for facet.
  const mism = topologyMismatches((manifest.binding || {}).topology || {}, policyDoc.bound);
  if (mism.length) {
    throw new GenerationResolveError(`binding.topology does not match the reviewed bound: ${JSON.stringify(mism)}`);
  }
  return policyDoc;
}

function sourceRecordCount(policyDoc, table, child) {
  const t = (policyDoc.bound.tables || {})[table];
  if (!t) {
    throw new GenerationResolveError(
      `child ${child} cites source table ${table}, which the reviewed policy does not bind; its cardinality cannot be evaluated`);
  }
  return t.header.record_count;
}

function declaredDerivation(manifest, child, keys) {
  const declared = (((manifest.binding || {}).derivations) || {})[child];
  const got = declared && typeof declared === "object" && !Array.isArray(declared) ? Object.keys(declared).sort() : null;
  if (!got || !sameSet(got, [...keys].sort())) {
    throw new GenerationResolveError(
      `child ${child} needs a binding.derivations entry with exactly ${[...keys].sort().join(", ")}`);
  }
  for (const key of keys) {
    if (key === "source") continue;
    if (!Number.isInteger(declared[key]) || declared[key] < 0) {
      throw new GenerationResolveError(`child ${child} derivation ${key} must be a non-negative integer`);
    }
  }
  return declared;
}

// Rules whose expectation the streaming merge-join derives, resolved AFTER it. They cross-check two
// independently-derived numbers; the merge-join stays the authoritative row-level enforcement.
const CROSS_CHILD_RULES = new Set(["equals_full_spell_records", "equals_is_coa_full_records",
                                   "equals_referenced_asset_set"]);

function resolveCardinality(genDir, name, spec, records, policyDoc, manifest, counts) {
  const rule = spec.cardinality.rule;
  if (rule === "single_document") {
    if (records !== 1) throw new GenerationResolveError(`single_document: child ${name} carries ${records} records, not 1`);
    // scanChild registers `records: 1` for every non-JSONL child unconditionally, so only PARSING can
    // catch two concatenated documents — and this is the only thing checking a JSON child is well-formed.
    try { JSON.parse(fs.readFileSync(path.join(genDir, name), "utf8")); }
    catch (e) { throw new GenerationResolveError(`single_document: child ${name} is not a single JSON document (${e.message})`); }
  } else if (rule === "min") {
    if (records < spec.cardinality.min) {
      throw new GenerationResolveError(`min: child ${name} carries ${records} records, below the floor ${spec.cardinality.min}`);
    }
  } else if (rule === "reviewed_bound_record_count" || rule === "derived_from_source_topology") {
    const expected = sourceRecordCount(policyDoc, spec.cardinality.source_table, name);
    if (records !== expected) {
      throw new GenerationResolveError(
        `${rule}: child ${name} carries ${records} records but the reviewed bound for ${spec.cardinality.source_table} states ${expected}`);
    }
  } else if (rule === "declared_derivation") {
    const table = spec.cardinality.source_table;
    const declared = declaredDerivation(manifest, name, ["source", "kept", "rejected"]);
    if (declared.source !== table) {
      throw new GenerationResolveError(
        `declared_derivation: child ${name} derivation names source ${declared.source}, but the contract states ${table}`);
    }
    const expected = sourceRecordCount(policyDoc, table, name);
    if (declared.kept + declared.rejected !== expected) {
      throw new GenerationResolveError(
        `declared_derivation: child ${name} accounting does not close — kept ${declared.kept} + rejected ${declared.rejected} != reviewed source ${expected}`);
    }
    if (declared.kept !== records) {
      throw new GenerationResolveError(`declared_derivation: child ${name} declares ${declared.kept} kept but carries ${records} records`);
    }
  } else if (rule === "declared_content_derivation") {
    const declared = declaredDerivation(manifest, name, ["source", "source_entries", "kept", "rejected"]);
    if (declared.source !== "content_json") {
      throw new GenerationResolveError(
        `declared_content_derivation: child ${name} derivation names source ${declared.source}, not content_json`);
    }
    const reviewed = Object.values(((policyDoc.content_sources || {}).required_files) || {})
      .reduce((n, f) => n + f.source_entries, 0);
    if (declared.source_entries !== reviewed) {
      throw new GenerationResolveError(
        `declared_content_derivation: child ${name} declares ${declared.source_entries} source entries but the reviewed content_sources state ${reviewed}`);
    }
    if (declared.kept + declared.rejected !== reviewed) {
      throw new GenerationResolveError(
        `declared_content_derivation: child ${name} accounting does not close — kept ${declared.kept} + rejected ${declared.rejected} != reviewed source ${reviewed}`);
    }
    if (declared.kept !== records) {
      throw new GenerationResolveError(`declared_content_derivation: child ${name} declares ${declared.kept} kept but carries ${records} records`);
    }
  } else if (rule === "equals_full_spell_records") {
    if (records !== counts.full) {
      throw new GenerationResolveError(
        `equals_full_spell_records: child ${name} carries ${records} records but the full spell child carries ${counts.full}`);
    }
  } else if (rule === "equals_referenced_asset_set") {
    // E0R.2 T6.3: relational. With no-dangling (per association) and no-orphans (after the merge), the
    // asset child holds EXACTLY the distinct references the association child names.
    if (records !== counts.referenced_assets) {
      throw new GenerationResolveError(
        `equals_referenced_asset_set: child ${name} carries ${records} asset rows but the association child references ${counts.referenced_assets} distinct assets`);
    }
  } else if (rule === "equals_is_coa_full_records") {
    if (records !== counts.is_coa) {
      throw new GenerationResolveError(
        `equals_is_coa_full_records: child ${name} carries ${records} records but the full child holds ${counts.is_coa} is_coa spells`);
    }
  } else {
    throw new GenerationResolveError(`child ${name} cardinality rule ${rule} has no resolver`);
  }
}

// E0R.2 T2.2: every child is type-checked against the validator its contract names. An unimplemented
// shape is a gate that silently does nothing, so it is an error rather than a skip.
function shapeFor(name, spec) {
  const shape = SHAPES[spec.shape];
  if (!shape) {
    throw new GenerationResolveError(
      `child ${name} names shape ${spec.shape}, which this validator does not implement`);
  }
  return shape;
}

function checkShape(shape, doc, name) {
  try { shape(doc); }
  catch (e) {
    if (e instanceof ShapeError) throw new GenerationResolveError(`shape: child ${name} ${e.message}`);
    throw e;
  }
  return doc;
}

const DEFAULT_LOCK_PATH = new URL("../../config/spell_layout.lock.json", import.meta.url);

// `readJsonlLines` moved to the leaf module jsonl-stream.mjs (E0R.2 T5.1) so the canonical mechanics
// build can stream over the same primitive: this module imports FROM mechanics-projection.mjs, so a
// primitive defined here was unreachable from there without a cycle.

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

// Icon id/path agreement (mirrors Python publish._verify_icon_row): a valid asset_status, and a
// placeholder (unresolved join) has a null client_path while a resolved status carries one. E0R.2 T2.5:
// `converted` is no longer admissible and neither is `converted_ref`.
function verifyIconRow(r) {
  if (!ICON_ASSET_STATUSES.has(r.asset_status)) {
    throw new GenerationResolveError(`icon asset_status ${JSON.stringify(r.asset_status)} not in ${[...ICON_ASSET_STATUSES].sort()} (converted assets are prohibited until their bundle validator exists)`);
  }
  if (r.converted_ref) {
    throw new GenerationResolveError(`icon ${r.spell_id}: carries a converted_ref, but converted assets are prohibited until the bundle validator (tar containment, bundle manifest, content hashes) exists`);
  }
  if (r.asset_status === "placeholder" && r.client_path != null) {
    throw new GenerationResolveError(`icon id/path: placeholder spell ${r.spell_id} carries a client_path`);
  }
  if (r.asset_status === "source_only" && r.client_path == null) {
    throw new GenerationResolveError(`icon id/path: ${r.asset_status} spell ${r.spell_id} missing client_path`);
  }
}

// E0R.2 T6.3: one association row against the asset table it references. Every leg is DERIVED, not
// read: `readiness` must equal what the referenced asset's availability implies, and a null reference
// must be explained by a decoded_reason that is not `decoded`. A stored verdict nobody re-derives is a
// claim, and normalizing exists to stop repeating claims.
function verifyIconAssociation(r, assets) {
  const reason = decodedReasonName(r.d);
  if (r.asset_ref == null) {
    if (reason === "decoded") {
      throw new GenerationResolveError(`icon ${r.spell_id}: no asset_ref but decoded_reason is 'decoded'; a decoded icon join HAS a path`);
    }
    if (r.readiness !== "unavailable") {
      throw new GenerationResolveError(`icon ${r.spell_id}: readiness ${r.readiness} with no asset_ref`);
    }
    return;
  }
  if (reason !== "decoded") {
    throw new GenerationResolveError(`icon ${r.spell_id}: carries an asset_ref but decoded_reason is ${reason}; only a decoded join yields a path`);
  }
  const asset = assets.get(r.asset_ref);
  if (asset === undefined) {
    throw new GenerationResolveError(`icon ${r.spell_id}: dangling asset_ref ${r.asset_ref} — no such row in the asset child`);
  }
  const want = asset.availability === "source_only" ? "available" : "unavailable";
  if (r.readiness !== want) {
    throw new GenerationResolveError(`icon ${r.spell_id}: readiness ${r.readiness} but its asset is ${asset.availability} (derived: ${want})`);
  }
}

// The asset child, read before the merge-join. Sorted-unique by asset_id is checked HERE so the child's
// ORDER is part of the contract rather than an accident of how paths were met.
function readIconAssets(rows, shape) {
  const assets = new Map();
  let previous = null;
  for (const row of rows) {
    if (shape) shape(row);
    if (previous !== null && row.asset_id <= previous) {
      throw new GenerationResolveError(`icon assets: ${row.asset_id} out of order/duplicated after ${previous}; the child is sorted-unique by asset_id so identical inputs produce identical bytes`);
    }
    previous = row.asset_id;
    assets.set(row.asset_id, row);
  }
  return assets;
}

// Streaming cross-child merge-join over ascending spell_id (mirrors Python publish._cross_child + _icon_bundle):
// per-child sorted uniqueness, the icon catalog is exactly the full domain (catching missing/extra/trailing
// icons), projection ⊆ is_coa within domain, the disjoint v3 dialects, identity/mechanics/attribution
// agreement, and compact_raw_expands_to_envelope (expand(full.raw) deep-equals projection.field_observations).
export function crossChild(fullRows, projRows, iconRows, policyDoc, manifest, iconAssets = null) {
  // E0R.2 T6.1: derived HERE from the staged policy, never read off the generation — a descriptor says
  // what every hoisted cell means, so taking one on its word would let the producer and the consumer
  // agree on a redefinition. Both cell encodings expand identically, so this is inert until T6.2.
  const descriptors = buildFieldDescriptors(policyDoc);
  const referenced = new Set();
  const full = new Cursor(fullRows, "full");
  const proj = new Cursor(projRows, "projection");
  const icons = new Cursor(iconRows, "icons");
  let fullCount = 0, isCoaCount = 0;
  while (full.row !== null) {
    fullCount += 1;
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
    if (iconAssets === null) {
      verifyIconRow(icons.row);                        // e0r-v1/e0r-v2: the flat v1 catalog
    } else {
      verifyIconAssociation(icons.row, iconAssets);
      if (icons.row.asset_ref != null) referenced.add(icons.row.asset_ref);
    }
    icons.advance();
    if (proj.row !== null && proj.row.spell_id < sid) {
      throw new GenerationResolveError(`projection_within_domain: ${proj.row.spell_id} outside is_coa domain`);
    }
    if (!("raw" in frow)) throw new GenerationResolveError(`full_is_compact: spell ${sid} missing compact raw`);
    if ("field_observations" in frow) throw new GenerationResolveError(`full_is_compact: spell ${sid} carries field_observations`);
    const expanded = {};
    for (const [f, cell] of Object.entries(frow.raw)) {
      expanded[f] = expandCompact(cell, policyDoc, { field: f, descriptors, rowSchema: frow.schema_version });
    }
    const isCoa = frow.coa_attribution && frow.coa_attribution.is_coa === true;
    if (isCoa) isCoaCount += 1;
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
  // E0R.2 T2.5: the converted->bundle-required check lived here and only asserted that a bundle child
  // EXISTED. `converted` is prohibited outright now, which makes the branch unreachable rather than
  // weakly guarded.
  if (iconAssets !== null) {
    // NO ORPHANS — the other direction from `no dangling`, and what makes the two children mutually
    // determined rather than consistent one way only.
    const orphans = [...iconAssets.keys()].filter((id) => !referenced.has(id)).sort();
    if (orphans.length) {
      throw new GenerationResolveError(`icon assets: ${orphans.length} asset row(s) referenced by no spell, e.g. ${orphans.slice(0, 5)}`);
    }
  }
  // Tallies the cursors derived themselves, so the contract can cross-check them against the
  // manifest-registered record counts (E0R.2 T2.1).
  return { full: fullCount, is_coa: isCoaCount, referenced_assets: referenced.size };
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
  // The contract is a WHITELIST. candidate_trust_sha256 AUTHENTICATES an added child — it covers
  // `children`, so a child added to both the manifest and the directory is self-consistent — but
  // authenticating is not rejecting. Unregistered files on disk are refused too.
  const registered = new Set(Object.keys(contract.children));
  const present = new Set([...Object.keys(children), ...fs.readdirSync(dir)]);
  for (const name of [...present].sort()) {
    if (!registered.has(name) && !RESERVED.has(name)) {
      throw new GenerationResolveError(
        `unregistered child ${name}: the contract is a whitelist, and candidate trust authenticates an ` +
        "added child rather than rejecting it");
    }
  }
  // The staged policy child must match the committed lock (recomputed, never self-trusted), the manifest
  // must bind that same policy, and the recorded topology must BE the reviewed capture (E0R.2 T2.1).
  const policyDoc = JSON.parse(fs.readFileSync(children["spell_layout_v2.json"], "utf8"));
  let lock;
  try { lock = JSON.parse(fs.readFileSync(lockPath, "utf8")); }
  catch (e) { throw new GenerationResolveError(`policy lock unreadable: ${e.message}`); }
  trustedPolicy(dir, manifest, policyDoc, lock);
  // E0R.2 T6.2: a v4 row is decodable only through these two, so they are checked against TRUSTED
  // sources rather than read. Derived INDEPENDENTLY of Python — two boundaries agreeing only because
  // one told the other is not agreement.
  requireStagedDecoders(dir, contract, policyDoc);
  const childrenMeta = manifest.children || {};
  // Cardinalities that do not depend on the merge-join first, so a truncated generation fails fast.
  for (const [name, spec] of Object.entries(contract.children)) {
    if (!CROSS_CHILD_RULES.has(spec.cardinality.rule) && name in childrenMeta) {
      resolveCardinality(dir, name, spec, childrenMeta[name].records, policyDoc, manifest, {});
    }
  }
  // The three spell children are shape-checked inside the merge-join below, so they are read exactly
  // once; every other child is streamed here.
  // The asset child joins this group (E0R.2 T6.3): it is read in the merge-join, against the
  // associations that reference it, rather than shape-checked in isolation and then read again.
  const SPELL_CHILDREN = new Set(["coa_client_spell.jsonl", "coa_client_spell_coa.jsonl",
                                  "coa_client_spell_icons.jsonl", ICON_ASSET_CHILD]);
  for (const [name, spec] of Object.entries(contract.children)) {
    if (!(name in childrenMeta) || SPELL_CHILDREN.has(name)) continue;
    const shape = shapeFor(name, spec);
    if (spec.kind === "json") {
      checkShape(shape, JSON.parse(fs.readFileSync(path.join(dir, name), "utf8")), name);
    } else {
      for (const row of readJsonlLines(path.join(dir, name))) checkShape(shape, row, name);
    }
  }
  // Row semantics over the full required domain, verified AS the rows stream through the cross-child
  // cursors — one pass, no retained row arrays (E0R.1 T4.2). Every full row's required scalars are present
  // (not just in row.raw); every projection row's claims + biconditional + value agreement re-derive from
  // the policy; then dialects, identity/attribution, compact-raw expansion, icon domain/agreement, bundle.
  const verified = function* (iter, verify, name) {
    const shape = shapeFor(name, contract.children[name]);
    for (const row of iter) {
      checkShape(shape, row, name);
      try { verify(row, policyDoc); }
      catch (e) { throw new GenerationResolveError(e.message); }
      yield row;
    }
  };
  const shaped = function* (iter, name) {
    const shape = shapeFor(name, contract.children[name]);
    for (const row of iter) yield checkShape(shape, row, name);
  };
  // E0R.2 T6.3: the asset child, when the contract registers one. Read first (14,022 rows against
  // 208,447 associations) so every association can be checked against the asset it names as it streams.
  const iconAssets = ICON_ASSET_CHILD in contract.children
    ? readIconAssets(readJsonlLines(children[ICON_ASSET_CHILD]),
                     (row) => checkShape(shapeFor(ICON_ASSET_CHILD, contract.children[ICON_ASSET_CHILD]),
                                         row, ICON_ASSET_CHILD))
    : null;
  const counts = crossChild(
    verified(readJsonlLines(children["coa_client_spell.jsonl"]), verifyFullRowAgainstPolicy, "coa_client_spell.jsonl"),
    verified(readJsonlLines(children["coa_client_spell_coa.jsonl"]), verifyRowAgainstPolicy, "coa_client_spell_coa.jsonl"),
    shaped(readJsonlLines(children["coa_client_spell_icons.jsonl"]), "coa_client_spell_icons.jsonl"),
    policyDoc, manifest, iconAssets);
  for (const [name, spec] of Object.entries(contract.children)) {
    if (CROSS_CHILD_RULES.has(spec.cardinality.rule) && name in childrenMeta) {
      resolveCardinality(dir, name, spec, childrenMeta[name].records, policyDoc, manifest, counts);
    }
  }
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
  // `pointerManifestSha256` is the pointer's own claim about WHICH manifest bytes are active — already
  // verified against the file above. A consumer records it so the producer's acceptance run can prove the
  // build read this generation and not one that replaced it mid-run (E0R.2 T4.3).
  return { generationId: genId, genDir, manifest, children: resolved,
           pointerManifestSha256: pointer.manifest_sha256 };
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
