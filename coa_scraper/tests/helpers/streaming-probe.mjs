// coa_scraper/tests/helpers/streaming-probe.mjs
// E0R.1 T4.2 RSS probe. `build N dir` writes a complete candidate generation with N corpus-template rows
// (full + projection + icons all N-scale, is_coa everywhere) using STREAMED writes + incremental hashing,
// so the builder itself never skews the measurement. `validate dir` runs validateCandidateByPath in THIS
// process and prints its peak RSS — the parent test spawns it isolated and asserts bounded growth.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { loadCorpus } from "./candidate.mjs";
import { expandCompact } from "../../scripts/lib/mechanics-projection.mjs";
import { candidateTrustSha256FromText } from "../../scripts/lib/canonical.mjs";
import { GENERATION_CONTRACT_CHILD, GENERATION_CONTRACT_SCHEMA, generationContractSha256,
         loadCurrentContract, validateCandidateByPath } from "../../scripts/lib/generation.mjs";

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
  const fullT = corpus.validFull()[0];               // spell-1 template (is_coa)
  const iconT = corpus.validIcons()[0];
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
      for (const [f, cell] of Object.entries(full.raw)) fobs[f] = expandCompact(cell, corpus.policy);
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
  children["coa_client_spell_projection.manifest.json"] =
    writeDoc(genDir, "coa_client_spell_projection.manifest.json", { schema_version: SCHEMA_FOR["coa_client_spell_projection.manifest.json"] });
  for (const name of ["coa_client_content.jsonl", "coa_client_advancement.jsonl", "coa_client_class_types.jsonl",
                      "coa_client_tab_types.jsonl", "coa_client_essence.jsonl"]) {
    children[name] = writeChild(genDir, name, []);
  }
  children["coa_client_archive_plan.json"] = writeDoc(genDir, "coa_client_archive_plan.json", { schema_version: SCHEMA_FOR["coa_client_archive_plan.json"] });
  children["spell_layout_v2.json"] = writeDoc(genDir, "spell_layout_v2.json", corpus.policy);
  const [contractRevision, contract] = loadCurrentContract();
  children[GENERATION_CONTRACT_CHILD] = writeDoc(genDir, GENERATION_CONTRACT_CHILD, contract);

  const manifest = { schema_version: "coa-client-extract-manifest-v3", generation_id: "c1",
                     publication_state: "candidate", published_at: 1753100000123456789,
                     predecessor_generation_id: null, children,
                     binding: { generation_contract: {
                       schema_version: GENERATION_CONTRACT_SCHEMA, revision: contractRevision,
                       sha256: generationContractSha256(contract) } } };
  manifest.candidate_trust_sha256 = candidateTrustSha256FromText(JSON.stringify(manifest));
  fs.writeFileSync(path.join(genDir, "manifest.json"), JSON.stringify(manifest, null, 2));
  fs.writeFileSync(path.join(root, "spell_layout.lock.json"),
                   JSON.stringify({ schema_version: "coa-spell-layout-lock-v1", sha256: corpus.policy.sha256 }));
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
