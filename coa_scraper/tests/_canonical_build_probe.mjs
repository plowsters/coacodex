// coa_scraper/tests/_canonical_build_probe.mjs
// E0R.2 T5.3 RSS probe for the CANONICAL MECHANICS BUILD — the path E0R.1 named in scope and then
// measured somewhere else. T4.2's RSS test covers candidate validation; this one runs the actual
// `buildMechanicsArtifact` entry point, which is where Node peaked at 866 MB on the real client.
//
//   build N dir    write a v3 projection of N rows + its manifest + the reviewed policy child, with
//                  streamed writes and incremental hashing so the BUILDER never skews the measurement
//   run dir        run buildMechanicsArtifact in THIS process and print its peak RSS
//
// The parent test spawns each mode isolated, so the number is one process's own high-water mark rather
// than whatever the test runner had already allocated.
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { buildMechanicsArtifact } from "../scripts/build-mechanics-artifacts.mjs";

// A fixed Builder domain, independent of the projection size: the real corpus is ~3,600 spells against
// a 10,410-row projection, and the property under test is that the projection's size does not move RSS.
export const BUILDER_SPELLS = 3600;

const POLICY = {
  sha256: "canonical-build-probe-policy",
  tables: { Spell: { fields: {
    power_type: { kind: "int32", layout: "verified", interpretation: "verified", promotion: "normalized" },
    duration_ms: { kind: "int32", layout: "verified", interpretation: "verified", promotion: "normalized" },
  } } },
};

const PROOF = { integrity: "verified", layout: "verified", interpretation: "verified" };

// ~2.5 KB of payload per row: 100k rows is then a ~250 MB projection, in the same order as the real
// 400 MB one, and retaining it is unmistakable against a 150 MB delta gate.
export const ROW_BYTES = 2500;
const PADDING = "p".repeat(ROW_BYTES);

function projectionRow(spell_id) {
  const observation = (field, value) => ({
    state: "present", raw_u32: value, decoded_reason: "decoded",
    policy_ref: `/tables/Spell/fields/${field}`, proof: PROOF, promotion: "normalized",
    decoded: { kind: "int32", value },
  });
  return {
    schema_version: "coa-client-spell-projection-v3", spell_id,
    name: `Spell ${spell_id}`,
    mechanics: { power_type: 3, duration_ms: 12000 },
    field_observations: { power_type: observation("power_type", 3),
                          duration_ms: observation("duration_ms", 12000) },
    coa_attribution: { is_coa: true, confidence: "high" },
    // A row has to WEIGH something for retention to be visible. The real projection is ~400 MB over
    // 10,410 rows — roughly 38 KB a row — which is unusable at 100k rows in a test, so the probe uses
    // ROW_BYTES: enough that holding every row costs real memory, small enough that the fixture stays a
    // few hundred MB. A probe over tiny rows passes whether or not anything is retained, which is how
    // a memory gate ends up measuring nothing.
    padding: PADDING,
  };
}

function build(n, root) {
  fs.mkdirSync(root, { recursive: true });
  const projectionPath = path.join(root, "coa_client_spell_coa.jsonl");
  const fd = fs.openSync(projectionPath, "w");
  const hash = crypto.createHash("sha256");
  let bytes = 0;
  for (let i = 1; i <= n; i++) {
    const buf = Buffer.from(JSON.stringify(projectionRow(i)) + "\n");
    fs.writeSync(fd, buf);
    hash.update(buf);
    bytes += buf.length;
  }
  fs.closeSync(fd);
  fs.writeFileSync(path.join(root, "spell_layout_v2.json"), JSON.stringify(POLICY));
  fs.writeFileSync(path.join(root, "coa_client_spell_projection.manifest.json"), JSON.stringify({
    schema_version: "coa-client-spell-projection-manifest-v3",
    projection: { path: "coa_client_spell_coa.jsonl", sha256: hash.digest("hex"), byte_length: bytes },
    counts: { projected_records: n, unique_spell_ids: n, source_records: n },
    client_build: "probe-client-build",
  }));
}

function* builderEntries() {
  for (let i = 1; i <= BUILDER_SPELLS; i++) {
    yield { entry_id: i, spell_id: i, entry_type: "Ability", name: `Builder ${i}`,
            damage_schools: ["nature"], resources: ["energy"], tags: ["damage"] };
  }
}

function run(root) {
  const outDir = path.join(root, "out");
  const { manifest } = buildMechanicsArtifact({
    entries: [...builderEntries()],
    projectionPath: path.join(root, "coa_client_spell_coa.jsonl"),
    manifestPath: path.join(root, "coa_client_spell_projection.manifest.json"),
    policyPath: path.join(root, "spell_layout_v2.json"),
    outDir,
  });
  return {
    record_count: manifest.outputs.record_count,
    projection_rows: manifest.coverage.builder_joined_to_projection + manifest.coverage.projection_only,
    peak_rss_mb: Math.round(process.resourceUsage().maxRSS / 1024 * 10) / 10,
  };
}

const [mode, a, b] = process.argv.slice(2);
if (mode === "build") {
  build(Number(a), b);
} else if (mode === "run") {
  console.log(JSON.stringify(run(a)));
} else {
  console.error(`unknown mode ${mode} (${fileURLToPath(import.meta.url)})`);
  process.exit(2);
}
