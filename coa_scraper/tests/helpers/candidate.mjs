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
import { REQUIRED_CHILDREN } from "../../scripts/lib/generation.mjs";

const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");
const CORPUS = new URL("../../../tests/golden/e0r1_corpus/", import.meta.url);

export function loadCorpus() {
  const rows = (name) => fs.readFileSync(new URL(name, CORPUS), "utf8")
    .split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
  const strip = (r) => { const { case: _c, golden_accept: _g, ...rest } = r; return rest; };
  const pick = (list, ...cases) => list.filter((r) => cases.includes(r.case)).map(strip);
  return {
    policy: JSON.parse(fs.readFileSync(new URL("policy.json", CORPUS), "utf8")),
    projection: rows("projection_rows.jsonl"),
    full: rows("full_rows.jsonl"),
    icons: rows("icons.jsonl"),
    pick, strip,
    // the valid baselines (case "valid"/"valid_full"/"valid_icon"), stripped of the corpus labels
    validFull() { return pick(rows("full_rows.jsonl"), "valid_full"); },
    validProj() { return pick(rows("projection_rows.jsonl"), "valid"); },
    validIcons() { return pick(rows("icons.jsonl"), "valid_icon"); },
  };
}

function countRecords(buf) {
  return buf.toString("utf8").split("\n").filter((l) => l.trim()).length;
}

const SCHEMA_FOR = {
  "coa_client_spell.jsonl": "coa-client-spell-v3",
  "coa_client_spell_coa.jsonl": "coa-client-spell-projection-v3",
  "coa_client_spell_projection.manifest.json": "coa-client-spell-projection-manifest-v3",
  "coa_client_spell_icons.jsonl": "coa-client-spell-icons-v1",
  "coa_client_content.jsonl": "coa-client-content-v1",
  "coa_client_archive_plan.json": "coa-client-archive-plan-v1",
  "coa_client_advancement.jsonl": "coa-client-advancement-v1",
  "coa_client_class_types.jsonl": "coa-client-class-types-v1",
  "coa_client_tab_types.jsonl": "coa-client-tab-types-v1",
  "coa_client_essence.jsonl": "coa-client-essence-v1",
  "spell_layout_v2.json": "coa-spell-layout-v2",
};

// Options: {full, proj, icons, policy, lock} override corpus defaults; {drop:[names]} removes children;
// {trustOverride} replaces the computed digest; {mutateManifest} edits trust-covered fields before hashing.
export function buildCandidate(opts = {}) {
  const corpus = loadCorpus();
  const full = opts.full || corpus.validFull();
  const proj = opts.proj || corpus.validProj();
  const icons = opts.icons || corpus.validIcons();
  const policy = opts.policy || corpus.policy;
  const drop = new Set(opts.drop || []);

  const root = fs.mkdtempSync(path.join(os.tmpdir(), "e0r1cand-"));
  const genDir = path.join(root, "gen-c1");
  fs.mkdirSync(genDir, { recursive: true });

  const jsonl = (rows) => Buffer.from(rows.map((r) => JSON.stringify(r)).join("\n") + (rows.length ? "\n" : ""));
  const contents = {
    "coa_client_spell.jsonl": jsonl(full),
    "coa_client_spell_coa.jsonl": jsonl(proj),
    "coa_client_spell_icons.jsonl": jsonl(icons),
    "coa_client_spell_projection.manifest.json": Buffer.from(JSON.stringify({ schema_version: "coa-client-spell-projection-manifest-v3" })),
    "coa_client_content.jsonl": jsonl([]),
    "coa_client_archive_plan.json": Buffer.from(JSON.stringify({ schema_version: "coa-client-archive-plan-v1" })),
    "coa_client_advancement.jsonl": jsonl([]),
    "coa_client_class_types.jsonl": jsonl([]),
    "coa_client_tab_types.jsonl": jsonl([]),
    "coa_client_essence.jsonl": jsonl([]),
    "spell_layout_v2.json": Buffer.from(JSON.stringify(policy)),
  };
  const children = {};
  for (const [name, body] of Object.entries(contents)) {
    if (drop.has(name)) continue;
    fs.writeFileSync(path.join(genDir, name), body);
    const records = name.endsWith(".jsonl") ? countRecords(body) : 1;
    children[name] = { sha256: sha(body), byte_length: body.length, records, schema_version: SCHEMA_FOR[name] };
  }

  let manifest = {
    schema_version: "coa-client-extract-manifest-v3", generation_id: "c1",
    publication_state: "candidate", published_at: 1753100000123456789,
    predecessor_generation_id: null, children,
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
