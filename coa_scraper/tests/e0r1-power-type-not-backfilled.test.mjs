// coa_scraper/tests/e0r1-power-type-not-backfilled.test.mjs
// E0R.1 T1.4: once the client power_type decode is withheld (T1.3 demotion), the canonical mechanics row's
// power_type must stay null with an unavailable/no_static_anchor readiness. It must NEVER be backfilled from
// the Builder `resources` inference — that inference is a heuristic hint, admissible only as an ineligible,
// heuristic-tagged diagnostic candidate.
import { test } from "node:test";
import assert from "node:assert";
import { execFileSync } from "node:child_process";
import { buildCanonicalMechanics } from "../scripts/build-mechanics-artifacts.mjs";

function withheldRow() {
  // client power_type is WITHHELD (null); the Builder node still carries a resources hint (["energy"]).
  const projection = [{
    spell_id: 700001, name: "Test Spell",
    mechanics: { school_mask: 8, power_type: null, cast_time_ms: 0, duration_ms: 0, range_min_yd: 0, range_max_yd: 5 },
    coa_attribution: { is_coa: true, confidence: "high" },
  }];
  const entry = { spell_id: 700001, entry_id: 1, entry_type: "Ability", name: "Test Spell",
                  damage_schools: ["nature"], resources: ["energy"], tags: ["damage"] };
  return buildCanonicalMechanics({ entries: [entry], spellRows: [], projection })[0];
}

test("a withheld client power_type is NOT backfilled from the Builder resources hint", () => {
  const row = withheldRow();
  assert.strictEqual(row.power_type, null);        // null, never the Builder-derived "energy"
});

test("a withheld power_type carries an unavailable / no_static_anchor readiness", () => {
  const row = withheldRow();
  assert.equal(row.field_readiness.power_type.status, "unavailable");
  assert.equal(row.field_readiness.power_type.reason_code, "no_static_anchor");
});

test("the Builder resources hint survives only as an ineligible heuristic candidate", () => {
  const prov = withheldRow().field_provenance.power_type;
  assert.strictEqual(prov.selected_source, null);  // nothing selected — the field is omitted
  const builder = prov.candidates.find((c) => c.source === "builder");
  assert.ok(builder, "the Builder resources candidate is recorded for diagnostics");
  assert.strictEqual(builder.eligible, false);
  assert.strictEqual(builder.heuristic, true);
});

test("the withheld-power_type row still round-trips through the Python v2 loader", () => {
  const row = withheldRow();
  const py = [
    "import json,sys",
    "from coa_meta.mechanics import mechanic_from_raw",
    "r = mechanic_from_raw(json.loads(sys.argv[1]))",
    "assert r.power_type == '', repr(r.power_type)",
    "assert r.field_readiness['power_type']['status'] == 'unavailable'",
    "assert r.field_readiness['power_type']['reason_code'] == 'no_static_anchor'",
    "print('ok')",
  ].join("\n");
  const out = execFileSync("python3", ["-c", py, JSON.stringify(row)], { encoding: "utf8" });
  assert.match(out, /ok/);
});
