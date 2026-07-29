// coa_scraper/tests/helpers/streaming-probe.mjs
// E0R.1 T4.2 RSS probe. `build N dir` writes a complete candidate generation with N corpus-template rows
// (full + projection + icons all N-scale, is_coa everywhere) using STREAMED writes + incremental hashing,
// so the builder itself never skews the measurement. `validate dir` runs validateCandidateByPath in THIS
// process and prints its peak RSS — the parent test spawns it isolated and asserts bounded growth.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { ANCILLARY_TABLES, bindPolicyDoc, loadCorpus, topologyReportFor } from "./candidate.mjs";
import { goldenRows } from "./golden.mjs";
import { FIELD_DESCRIPTORS_CHILD, WIRE_SCHEMA_CHILD, buildFieldDescriptors, expandCompact }
  from "../../scripts/lib/mechanics-projection.mjs";
import { candidateTrustSha256FromText } from "../../scripts/lib/canonical.mjs";
import { GENERATION_CONTRACT_CHILD, GENERATION_CONTRACT_SCHEMA, generationContractSha256,
         loadCurrentContract, validateCandidateByPath } from "../../scripts/lib/generation.mjs";

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

function writeChild(genDir, name, lineIter) {
  const fd = fs.openSync(path.join(genDir, name), "w");
  const hash = crypto.createHash("sha256");
  let bytes = 0, records = 0;
  for (const line of lineIter) {
    const buf = Buffer.from(line);
    fs.writeSync(fd, buf);
    hash.update(buf);
    bytes += buf.length;
    records += 1;
  }
  fs.closeSync(fd);
  return { sha256: hash.digest("hex"), byte_length: bytes, records, schema_version: SCHEMA_FOR[name] };
}

function writeDoc(genDir, name, doc) {
  const buf = Buffer.from(JSON.stringify(doc));
  fs.writeFileSync(path.join(genDir, name), buf);
  return { sha256: crypto.createHash("sha256").update(buf).digest("hex"), byte_length: buf.length,
           records: 1, schema_version: SCHEMA_FOR[name] };
}

function build(n, root) {
  const corpus = loadCorpus();
  const fullT = corpus.validFull()[0];               // spell-1 template (is_coa), v4-encoded
  const iconT = corpus.validIconsV2()[0];      // E0R.2 T6.3: the association dialect
  const genDir = path.join(root, "gen-c1");
  fs.mkdirSync(genDir, { recursive: true });

  function* fullLines() {
    for (let i = 1; i <= n; i++) {
      const row = structuredClone(fullT);
      row.spell_id = i;
      row.raw.id.raw_u32 = i;
      yield JSON.stringify(row) + "\n";
    }
  }
  function* projLines() {
    for (let i = 1; i <= n; i++) {
      const full = structuredClone(fullT);
      full.spell_id = i;
      full.raw.id.raw_u32 = i;
      const fobs = {};
      const descriptors = buildFieldDescriptors(corpus.policy);
      for (const [f, cell] of Object.entries(full.raw)) {
        fobs[f] = expandCompact(cell, corpus.policy, { field: f, descriptors, rowSchema: full.schema_version });
      }
      yield JSON.stringify({ schema_version: "coa-client-spell-projection-v3", spell_id: i,
                             name: full.name, mechanics: full.mechanics,
                             coa_attribution: full.coa_attribution, field_observations: fobs }) + "\n";
    }
  }
  function* iconLines() {
    for (let i = 1; i <= n; i++) {
      const row = structuredClone(iconT);
      row.spell_id = i;
      yield JSON.stringify(row) + "\n";
    }
  }

  const children = {};
  children["coa_client_spell.jsonl"] = writeChild(genDir, "coa_client_spell.jsonl", fullLines());
  children["coa_client_spell_coa.jsonl"] = writeChild(genDir, "coa_client_spell_coa.jsonl", projLines());
  children["coa_client_spell_icons.jsonl"] = writeChild(genDir, "coa_client_spell_icons.jsonl", iconLines());
  // E0R.2 T6.3: every probe association references the SAME asset, so the asset child stays one row
  // while the association child scales — which is the normalization the probe should be measuring.
  children["coa_client_icon_assets.jsonl"] = writeChild(
    genDir, "coa_client_icon_assets.jsonl", [JSON.stringify(corpus.validIconAssets()[0]) + "\n"]);
  children["coa_client_spell_projection.manifest.json"] =
    writeDoc(genDir, "coa_client_spell_projection.manifest.json", goldenRows("projection_manifest_v3"));
  for (const name of ["coa_client_content.jsonl", "coa_client_advancement.jsonl", "coa_client_class_types.jsonl",
                      "coa_client_tab_types.jsonl", "coa_client_essence.jsonl"]) {
    children[name] = writeChild(genDir, name, []);
  }
  children["coa_client_archive_plan.json"] = writeDoc(genDir, "coa_client_archive_plan.json", goldenRows("archive_plan_v1"));
  // E0R.2 T2.1: the probe's policy is bound and sized to what it stages, so the candidate validator's
  // cardinality gate is part of what the RSS measurement covers rather than something it skips.
  const policy = bindPolicyDoc(corpus.policy, {
    spellRecords: n, ancillaryRecords: Object.fromEntries(ANCILLARY_TABLES.map((t) => [t, 0])),
    contentEntries: 0 });
  children["spell_layout_v2.json"] = writeDoc(genDir, "spell_layout_v2.json", policy);
  // E0R.2 T6.2: a v4 row needs both to be decodable, so the probe stages what a real generation ships.
  children[FIELD_DESCRIPTORS_CHILD] = writeDoc(genDir, FIELD_DESCRIPTORS_CHILD, buildFieldDescriptors(policy));
  children[WIRE_SCHEMA_CHILD] = writeDoc(genDir, WIRE_SCHEMA_CHILD, JSON.parse(fs.readFileSync(
    new URL("../../../coa_client_extract/data/observation_wire_schema.json", import.meta.url), "utf8")));
  const [contractRevision, contract] = loadCurrentContract();
  children[GENERATION_CONTRACT_CHILD] = writeDoc(genDir, GENERATION_CONTRACT_CHILD, contract);

  const manifest = { schema_version: "coa-client-extract-manifest-v3", generation_id: "c1",
                     publication_state: "candidate", published_at: 1753100000123456789,
                     predecessor_generation_id: null, children,
                     binding: {
                       policy_sha256: policy.sha256, topology: topologyReportFor(policy),
                       derivations: {
                         "coa_client_advancement.jsonl": { source: "CharacterAdvancement", kept: 0, rejected: 0 },
                         "coa_client_content.jsonl": { source: "content_json", source_entries: 0, kept: 0, rejected: 0 } },
                       generation_contract: {
                       schema_version: GENERATION_CONTRACT_SCHEMA, revision: contractRevision,
                       sha256: generationContractSha256(contract) } } };
  manifest.candidate_trust_sha256 = candidateTrustSha256FromText(JSON.stringify(manifest));
  fs.writeFileSync(path.join(genDir, "manifest.json"), JSON.stringify(manifest, null, 2));
  fs.writeFileSync(path.join(root, "spell_layout.lock.json"),
                   JSON.stringify({ schema_version: "coa-spell-layout-lock-v1", sha256: policy.sha256 }));
}

const [mode, a, b] = process.argv.slice(2);
if (mode === "build") {
  build(Number(a), b);
} else if (mode === "validate") {
  const r = validateCandidateByPath(path.join(a, "gen-c1"), { lockPath: path.join(a, "spell_layout.lock.json") });
  const n = r.manifest.children["coa_client_spell.jsonl"].records;
  console.log(JSON.stringify({ n, peak_rss_mb: Math.round(process.resourceUsage().maxRSS / 1024 * 10) / 10 }));
} else {
  console.error(`unknown mode ${mode} (${fileURLToPath(import.meta.url)})`);
  process.exit(2);
}
