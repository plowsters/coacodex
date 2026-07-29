// coa_scraper/tests/helpers/mechanics-fixture.mjs
// A FIXED canonical-build input, shared by the streaming tests so the golden output hash they pin means
// the same thing in every one of them (E0R.2 T5.2). Nothing here varies with the environment: no
// timestamps, no commit, no paths inside the rows — only the manifest carries those, and the golden is
// over the JSONL.
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export const BUILDER_SPELLS = 40;

// Two nodes on some spells, deliberately out of entry_id order, so the row builder's canonicalization
// (sort by entry_id, sort ids ascending) is part of what the golden hash pins.
export function entries(n = BUILDER_SPELLS) {
  const out = [];
  for (let i = 1; i <= n; i++) {
    const sid = 100 + i;
    out.push({ entry_id: 2000 + i, spell_id: sid, entry_type: "Talent", name: `Builder ${sid} b`,
               damage_schools: ["nature"], resources: ["energy"], tags: ["dot"] });
    if (i % 3 === 0) {
      out.push({ entry_id: 1000 + i, spell_id: sid, entry_type: "Ability", name: `Builder ${sid} a`,
                 damage_schools: ["fire"], resources: [], tags: ["damage"] });
    }
  }
  return out;
}

export function projectionRow(spell_id) {
  return {
    schema_version: "coa-client-spell-v2", spell_id, name: `S${spell_id}`,
    mechanics: { school_mask: 8, power_type: 3, cast_time_ms: 0, duration_ms: 12000,
                 range_min_yd: 0, range_max_yd: 30, spell_icon_id: 1 },
    field_observations: {
      school_mask: envelope(8, "uint32"), power_type: envelope(3, "int32"),
      cast_time_ms: join(0), duration_ms: join(12000),
      range_min_yd: join(0), range_max_yd: join(30), spell_icon_id: join(1),
    },
    coa_attribution: { is_coa: true, confidence: "high" },
  };
}

const PROOF = { integrity: "verified", layout: "verified", interpretation: "verified" };
const envelope = (v, kind) => ({ state: "present", raw_u32: v, decoded: { kind, value: v },
                                 decoded_reason: "decoded", proof: PROOF, evidence_ref: "fx" });
const join = (v) => ({ state: "resolved", components: {}, composed_proof: PROOF, decoded: v,
                       decoded_reason: "decoded" });

// The v2 projection pair: enough client rows to cover the Builder domain plus some the domain never
// asks for, so `projection_only` is non-zero and the retention rule has something to leave behind.
export function projectionFixture(dir, { extra = 10 } = {}) {
  const records = [];
  for (let i = 1; i <= BUILDER_SPELLS + extra; i++) records.push(projectionRow(100 + i));
  const body = records.map((r) => JSON.stringify(r)).join("\n") + "\n";
  const proj = path.join(dir, "p.jsonl");
  const man = path.join(dir, "p.manifest.json");
  fs.writeFileSync(proj, body);
  fs.writeFileSync(man, JSON.stringify({
    schema_version: "coa-client-spell-projection-v2",
    projection: { path: "p.jsonl", sha256: crypto.createHash("sha256").update(body).digest("hex"),
                  byte_length: Buffer.byteLength(body) },
    counts: { projected_records: records.length, unique_spell_ids: records.length,
              source_records: records.length },
    client_build: "test-client-build",
  }));
  return { proj, man };
}

export function tempDir(prefix = "mechgolden-") {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}
