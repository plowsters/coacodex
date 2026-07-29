// coa_scraper/tests/helpers/candidate.mjs
// Assemble a COMPLETE candidate generation on disk (every REQUIRED_CHILDREN + policy child + a manifest with
// a correct candidate_trust_sha256 and per-child hashes), from the shared golden corpus. Tests then either
// validate the valid candidate or apply a single mutation (drop a child, corrupt the trust digest, swap in a
// corpus reject row, or point at a mismatching lock) to exercise one failure.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { candidateTrustSha256FromText } from "../../scripts/lib/canonical.mjs";
import { GENERATION_CONTRACT_CHILD, GENERATION_CONTRACT_SCHEMA, REQUIRED_CHILDREN,
         generationContractSha256, loadCurrentContract } from "../../scripts/lib/generation.mjs";
import { FIELD_DESCRIPTORS_CHILD, WIRE_SCHEMA_CHILD, buildFieldDescriptors }
  from "../../scripts/lib/mechanics-projection.mjs";
import { goldenRows } from "./golden.mjs";

const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");
const CORPUS = new URL("../../../tests/golden/e0r1_corpus/", import.meta.url);
const CORPUS_V4 = new URL("../../../tests/golden/e0r2_corpus_v4/", import.meta.url);
const WIRE_SCHEMA_PATH = new URL("../../../coa_client_extract/data/observation_wire_schema.json", import.meta.url);

// E0R.2 T2.1: a fixture must stage a policy that actually BINDS a source domain, sized to what it
// stages, or the cardinality rules have nothing to resolve against. Mirrors tests/_e0r2_fixtures.py.
export const ANCILLARY_TABLES = ["CharacterAdvancement", "CharacterAdvancementClassTypes",
                                 "CharacterAdvancementTabTypes", "CharacterAdvancementEssence"];
const ANCILLARY_CHILD_FOR = {
  CharacterAdvancementClassTypes: "coa_client_class_types.jsonl",
  CharacterAdvancementTabTypes: "coa_client_tab_types.jsonl",
  CharacterAdvancementEssence: "coa_client_essence.jsonl",
};
const CLIENT_BUILD = "3.3.5a+fixture";

function sortDeep(v) {
  if (Array.isArray(v)) return v.map(sortDeep);
  if (v && typeof v === "object") {
    const out = {};
    for (const k of Object.keys(v).sort()) out[k] = sortDeep(v[k]);
    return out;
  }
  return v;
}

// The SAME canonical policy digest Python's compute_policy_sha256 produces (sha256 field excluded).
function policySha256(doc) {
  const { sha256: _omit, ...rest } = doc;
  return crypto.createHash("sha256").update(JSON.stringify(sortDeep(rest))).digest("hex");
}

function fakeTableBinding(name, recordCount) {
  return {
    sha256: sha(Buffer.from(`fixture:${name}`, "utf8")),
    header: { magic: "WDBC", record_count: recordCount, field_count: 2, record_size: 8, string_block_size: 1 },
    source: { member: `DBFilesClient\\${name}.dbc`, effective_archive: "common.MPQ", patch_chain: [] },
  };
}

export function bindPolicyDoc(doc, { spellRecords, ancillaryRecords = {}, contentEntries = 2 } = {}) {
  const out = structuredClone(doc);
  for (const name of ANCILLARY_TABLES) {
    if (!out.tables[name]) out.tables[name] = { expected_field_count: 2, key_cell: 0, unique: true };
  }
  out.required_tables = Object.keys(out.tables).sort();
  out.expected_absent = [];
  const counts = {};
  for (const name of Object.keys(out.tables)) counts[name] = ancillaryRecords[name] ?? 1;
  counts.Spell = spellRecords;
  out.bound = { client_build: CLIENT_BUILD, expected_absent: [], tables: {} };
  for (const name of Object.keys(out.tables)) out.bound.tables[name] = fakeTableBinding(name, counts[name]);
  out.content_sources = { directory: "Content", required_files: {
    "SpellRankData.json": { kind: "spell_rank", sha256: "0".repeat(64), source_entries: contentEntries } } };
  delete out.sha256;
  out.sha256 = policySha256(out);
  return out;
}

// A policy with `bound: null` was never proven against a client capture. Rehashed so the lock still
// matches it honestly — the validator must refuse it for being unbound, not for a hash mismatch.
export function unbindPolicyDoc(doc) {
  const out = structuredClone(doc);
  out.bound = null;
  delete out.sha256;
  out.sha256 = policySha256(out);
  return out;
}

export function topologyReportFor(doc) {
  const tables = {};
  for (const [name, t] of Object.entries(doc.bound.tables)) {
    tables[name] = { sha256: t.sha256, header: t.header, member: t.source.member,
                     effective_archive: t.source.effective_archive, patch_chain: t.source.patch_chain,
                     key_unique: true, dense: true };
  }
  return { client_build: doc.bound.client_build, tables,
           expected_absent_ok: true, expected_absent_set: [...(doc.bound.expected_absent || [])],
           blocking: [] };
}

export function loadCorpus() {
  const rows = (name) => fs.readFileSync(new URL(name, CORPUS), "utf8")
    .split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
  // E0R.2 T6.2: the v4 full rows live BESIDE the v3 ones (e0r-v1 stays supported, so the v3 baseline
  // must keep validating). Everything else — policy, projection, icons — is shared: the projection
  // dialect does not change in v4, and a second copy could only drift.
  const v4Rows = (name) => fs.readFileSync(new URL(name, CORPUS_V4), "utf8")
    .split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
  const strip = (r) => { const { case: _c, golden_accept: _g, ...rest } = r; return rest; };
  const pick = (list, ...cases) => list.filter((r) => cases.includes(r.case)).map(strip);
  return {
    policy: JSON.parse(fs.readFileSync(new URL("policy.json", CORPUS), "utf8")),
    projection: rows("projection_rows.jsonl"),
    full: rows("full_rows.jsonl"),
    fullV4: v4Rows("full_rows.jsonl"),
    icons: rows("icons.jsonl"),
    pick, strip,
    // the valid baselines (case "valid"/"valid_full"/"valid_icon"), stripped of the corpus labels
    validFull() { return pick(v4Rows("full_rows.jsonl"), "valid_full"); },
    validFullV3() { return pick(rows("full_rows.jsonl"), "valid_full"); },
    // E0R.2 T6.3: the NORMALIZED icon baselines (association + asset), beside the v1 ones.
    iconsV2: v4Rows("icons.jsonl"),
    iconAssets: v4Rows("icon_assets.jsonl"),
    validIconsV2() { return pick(v4Rows("icons.jsonl"), "valid_icon"); },
    validIconAssets() { return pick(v4Rows("icon_assets.jsonl"), "valid_asset"); },
    validProj() { return pick(rows("projection_rows.jsonl"), "valid"); },
    validIcons() { return pick(rows("icons.jsonl"), "valid_icon"); },
  };
}

function countRecords(buf) {
  return buf.toString("utf8").split("\n").filter((l) => l.trim()).length;
}

const SCHEMA_FOR = {
  "coa_client_spell.jsonl": "coa-client-spell-v4",
  "coa_client_spell_coa.jsonl": "coa-client-spell-projection-v3",
  "coa_client_spell_projection.manifest.json": "coa-client-spell-projection-manifest-v3",
  "coa_client_spell_icons.jsonl": "coa-client-spell-icons-v2",
  "coa_client_icon_assets.jsonl": "coa-client-icon-assets-v1",
  "coa_client_content.jsonl": "coa-client-content-v1",
  "coa_client_archive_plan.json": "coa-client-archive-plan-v1",
  "coa_client_advancement.jsonl": "coa-client-advancement-v1",
  "coa_client_class_types.jsonl": "coa-client-class-types-v1",
  "coa_client_tab_types.jsonl": "coa-client-tab-types-v1",
  "coa_client_essence.jsonl": "coa-client-essence-v1",
  "spell_layout_v2.json": "coa-spell-layout-v2",
  [FIELD_DESCRIPTORS_CHILD]: "coa-client-spell-fields-v1",
  [WIRE_SCHEMA_CHILD]: "coa-observation-wire-v1",
  [GENERATION_CONTRACT_CHILD]: GENERATION_CONTRACT_SCHEMA,
};

// Write a two-revision registry to disk so a test can prove that membership — not equality with
// `current` — is what the validator checks. Nothing is faked: both files are real, validated documents.
export function writeTwoRevisionRegistry(dir) {
  const [, v1] = loadCurrentContract();
  const v2 = { ...structuredClone(v1), revision: "e0r-test-successor",
               note: "IMMUTABLE. Successor revision used to prove an older revision stays resolvable." };
  fs.mkdirSync(dir, { recursive: true });
  for (const [doc, name] of [[v1, "e0r-current.json"], [v2, "e0r-test-successor.json"]]) {
    fs.writeFileSync(path.join(dir, name), JSON.stringify(doc, null, 2) + "\n");
  }
  fs.writeFileSync(path.join(dir, "index.json"), JSON.stringify({
    schema_version: "coa-generation-contract-index-v1",
    current: "e0r-test-successor",
    supported: {
      [v1.revision]: { path: "e0r-current.json", sha256: generationContractSha256(v1) },
      "e0r-test-successor": { path: "e0r-test-successor.json", sha256: generationContractSha256(v2) },
    },
  }, null, 2) + "\n");
  // A directory URL (trailing slash) so `new URL(entry.path, dir)` resolves inside it.
  return { contractsDir: new URL(`file://${path.resolve(dir)}/`), v1, v2 };
}

// Options: {full, proj, icons, policy, lock} override corpus defaults; {drop:[names]} removes children;
// {trustOverride} replaces the computed digest; {mutateManifest} edits trust-covered fields before hashing.
// Contract knobs, each isolating ONE leg of the three-way check (T1.3):
//   {contract: [revision, doc]} stages and binds an explicit revision instead of `current`;
//   {contractMutate} tampers the STAGED copy (the binding follows it, so the registry leg fires);
//   {bindOverride} desynchronizes the binding from the staged copy (so the binding leg fires).
// The two v4 decoder children, with knobs so a test can stage one that DISAGREES with the policy or
// with the trusted vocabulary — the only way to prove the validator derives them instead of reading them.
function stagedDescriptors(policy, opts) {
  const doc = buildFieldDescriptors(policy);
  if (opts.forgeDescriptors) opts.forgeDescriptors(doc);
  return doc;
}

function stagedWire(opts) {
  const doc = JSON.parse(fs.readFileSync(WIRE_SCHEMA_PATH, "utf8"));
  if (opts.forgeWire) opts.forgeWire(doc);
  return doc;
}

export function buildCandidate(opts = {}) {
  const corpus = loadCorpus();
  const full = opts.full || corpus.validFull();
  const proj = opts.proj || corpus.validProj();
  const icons = opts.icons || corpus.validIconsV2();
  const iconAssets = opts.iconAssets || corpus.validIconAssets();
  const drop = new Set(opts.drop || []);
  const ancillaryCounts = { ...Object.fromEntries(ANCILLARY_TABLES.map((t) => [t, 2])),
                            ...(opts.ancillaryCounts || {}) };
  const advancementSource = opts.advancementSource ?? 3;
  const advancementKept = opts.advancementKept ?? 2;
  const contentEntries = opts.contentEntries ?? 2;
  ancillaryCounts.CharacterAdvancement = advancementSource;
  // The policy is SIZED to what this fixture stages, so the honest case validates and a knob breaks
  // exactly one correspondence rather than the fixture never having established it.
  const policy = opts.policy || bindPolicyDoc(corpus.policy, {
    spellRecords: full.length, ancillaryRecords: ancillaryCounts, contentEntries });
  const [contractRevision, contractBase] = opts.contract || loadCurrentContract();
  const contract = structuredClone(contractBase);
  if (opts.contractMutate) opts.contractMutate(contract);

  const root = fs.mkdtempSync(path.join(os.tmpdir(), "e0r1cand-"));
  const genDir = path.join(root, "gen-c1");
  fs.mkdirSync(genDir, { recursive: true });

  const jsonl = (list) => Buffer.from(list.map((r) => JSON.stringify(r)).join("\n") + (list.length ? "\n" : ""));
  // Placeholder ancillary rows: their CONTENT is not validated until T2.2's shapes; what matters is
  // that the fixture can stage a count the policy's bound actually states.
  // `n` copies of the row the REAL producer emits for this child. T2.2 shape-checks every row, so a
  // placeholder would only prove the fixture can dodge its own gate.
  const rows = (shape, n) => Array.from({ length: n }, () => goldenRows(shape));
  const contents = {
    "coa_client_spell.jsonl": jsonl(full),
    "coa_client_spell_coa.jsonl": jsonl(proj),
    "coa_client_spell_icons.jsonl": jsonl(icons),
    "coa_client_icon_assets.jsonl": jsonl(iconAssets),
    "coa_client_spell_projection.manifest.json": Buffer.from(JSON.stringify(goldenRows("projection_manifest_v3"))),
    "coa_client_content.jsonl": jsonl(rows("content_row_v1", contentEntries)),
    "coa_client_archive_plan.json": Buffer.from(JSON.stringify(goldenRows("archive_plan_v1"))),
    "coa_client_advancement.jsonl": jsonl(rows("advancement_row_v1", advancementKept)),
    "coa_client_class_types.jsonl": jsonl(rows("class_type_row_v1", ancillaryCounts.CharacterAdvancementClassTypes)),
    "coa_client_tab_types.jsonl": jsonl(rows("tab_type_row_v1", ancillaryCounts.CharacterAdvancementTabTypes)),
    "coa_client_essence.jsonl": jsonl(rows("essence_row_v1", ancillaryCounts.CharacterAdvancementEssence)),
    "spell_layout_v2.json": Buffer.from(JSON.stringify(policy)),
    // E0R.2 T6.2: a v4 row is only decodable WITH these two, so a generation ships both.
    [FIELD_DESCRIPTORS_CHILD]: Buffer.from(JSON.stringify(stagedDescriptors(policy, opts))),
    [WIRE_SCHEMA_CHILD]: Buffer.from(JSON.stringify(stagedWire(opts))),
    [GENERATION_CONTRACT_CHILD]: Buffer.from(JSON.stringify(contract)),
  };
  if (opts.truncateChild) {
    // Applied AFTER the policy is sized, so the knob breaks the correspondence rather than the fixture
    // never having established it.
    const [name, keep] = opts.truncateChild;
    const kept = contents[name].toString("utf8").split("\n").filter((l) => l.trim()).slice(0, keep);
    contents[name] = Buffer.from(kept.length ? kept.join("\n") + "\n" : "");
  }
  if (opts.duplicateJsonDocument) {
    // Two concatenated documents, registered HONESTLY: scanChild counts every non-JSONL child as exactly
    // one record regardless of content, so only parsing can catch the second document.
    const name = opts.duplicateJsonDocument;
    contents[name] = Buffer.concat([contents[name], contents[name]]);
  }

  const children = {};
  for (const [name, body] of Object.entries(contents)) {
    if (drop.has(name)) continue;
    fs.writeFileSync(path.join(genDir, name), body);
    const records = name.endsWith(".jsonl") ? countRecords(body) : 1;
    children[name] = { sha256: sha(body), byte_length: body.length, records, schema_version: SCHEMA_FOR[name] };
  }
  if (opts.extraChild) {
    const [name, body] = opts.extraChild;      // on disk but NOT registered: the whitelist case
    fs.writeFileSync(path.join(genDir, name), Buffer.from(body));
  }

  // A staged generation BINDS what it stages by default; desynchronizing the two is something a test
  // opts into (`bindOverride`), which is what keeps the binding leg and the registry leg separable.
  const boundContract = opts.bindOverride !== undefined ? opts.bindOverride : {
    schema_version: GENERATION_CONTRACT_SCHEMA,
    revision: contract.revision !== undefined ? contract.revision : contractRevision,
    sha256: generationContractSha256(contract),
  };
  let manifest = {
    schema_version: "coa-client-extract-manifest-v3", generation_id: "c1",
    publication_state: "candidate", published_at: 1753100000123456789,
    predecessor_generation_id: null, children,
    binding: {
      policy_sha256: policy.sha256,
      topology: opts.topology || topologyReportFor(policy),
      derivations: opts.derivations || {
        "coa_client_advancement.jsonl": { source: "CharacterAdvancement", kept: advancementKept,
                                          rejected: advancementSource - advancementKept },
        "coa_client_content.jsonl": { source: "content_json", source_entries: contentEntries,
                                      kept: contentEntries, rejected: 0 },
      },
      ...(opts.dropBinding ? {} : { generation_contract: boundContract }),
    },
  };
  if (opts.mutateManifest) manifest = opts.mutateManifest(manifest) || manifest;
  manifest.candidate_trust_sha256 = opts.trustOverride || candidateTrustSha256FromText(JSON.stringify(manifest));

  const lock = opts.lock || { schema_version: "coa-spell-layout-lock-v1", sha256: policy.sha256 };
  const lockPath = path.join(root, "spell_layout.lock.json");
  fs.writeFileSync(lockPath, JSON.stringify(lock));

  if (opts.publish) {
    // Finalize to PUBLISHED: publication_state/validation/budget are mutable (excluded from the trust digest),
    // so the digest still covers the manifest. Write the pointer so resolveGeneration can resolve it.
    const published = {
      ...manifest, publication_state: "published",
      validation: opts.validation || { python: true, node: true },
      budget: opts.budget || { within_budget: true },
    };
    if (opts.mutatePublished) opts.mutatePublished(published);
    const body = Buffer.from(JSON.stringify(published, null, 2));
    fs.writeFileSync(path.join(genDir, "manifest.json"), body);
    const pointer = { schema_version: "coa-client-extract-pointer-v1", generation_id: "c1",
                      manifest_sha256: sha(body) };
    fs.writeFileSync(path.join(root, "coa_client_extract.pointer.json"), Buffer.from(JSON.stringify(pointer, null, 2)));
    return { root, genDir, lockPath, manifest: published, corpus, REQUIRED_CHILDREN };
  }
  fs.writeFileSync(path.join(genDir, "manifest.json"), Buffer.from(JSON.stringify(manifest, null, 2)));
  return { root, genDir, lockPath, manifest, corpus, REQUIRED_CHILDREN };
}
