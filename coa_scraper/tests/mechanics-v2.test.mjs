// coa-mechanics-v2: the canonical Node builder writes cooldown/gcd/costs as explicit null (unknown) with
// a readiness reason — never a defaulted 0/1500/{} — and the row is accepted by the Python v2 loader.
import { test } from "node:test";
import assert from "node:assert";
import { execFileSync } from "node:child_process";
import { buildCanonicalMechanics, buildMechanicsArtifact, numberOrNull } from "../scripts/build-mechanics-artifacts.mjs";

function oneRow() {
  const projection = [{
    spell_id: 92117, name: "Adrenal Venom",
    mechanics: { school_mask: 8, power_type: 3, cast_time_ms: 0, duration_ms: 12000, range_min_yd: 0, range_max_yd: 30 },
    coa_attribution: { is_coa: true, confidence: "high" },
  }];
  const entry = { spell_id: 92117, entry_id: 1, entry_type: "Ability", name: "Adrenal Venom", damage_schools: ["nature"], resources: ["energy"], tags: ["damage"] };
  return buildCanonicalMechanics({ entries: [entry], projection })[0];
}

test("the builder emits coa-mechanics-v2 with null cooldown/gcd/costs (missing != default)", () => {
  const row = oneRow();
  assert.equal(row.schema_version, "coa-mechanics-v2");
  assert.equal(row.cooldown_ms, null);
  assert.equal(row.gcd_ms, null);
  assert.equal(row.costs, null);                    // unknown, NOT {}
});

test("null cooldown/gcd/costs each carry an explicit readiness reason", () => {
  const row = oneRow();
  for (const f of ["cooldown_ms", "gcd_ms", "costs"]) {
    assert.equal(row.field_readiness[f].status, "unavailable");
    assert.equal(row.field_readiness[f].reason_code, "pending_e1_operand");
  }
});

test("a v2 row round-trips through the Python coa-mechanics-v2 loader", () => {
  const row = oneRow();
  const py = [
    "import json,sys",
    "from coa_meta.mechanics import mechanic_from_raw",
    "r = mechanic_from_raw(json.loads(sys.argv[1]))",
    "assert r.costs is None, r.costs",
    "assert r.field_readiness['costs']['status'] == 'unavailable'",
    "print('ok')",
  ].join("\n");
  const out = execFileSync("python3", ["-c", py, JSON.stringify(row)], { encoding: "utf8" });
  assert.match(out, /ok/);
});

// --- E0R.1 T5.3: null is unknown, never 0; and the DB-era spellRows input is gone ------------------

test("numberOrNull(null) is null — a missing number never coerces to a real 0", () => {
  assert.equal(numberOrNull(null), null);
  assert.equal(numberOrNull(undefined), null);
  assert.equal(numberOrNull(""), null);
  assert.equal(numberOrNull("  "), null);
  assert.equal(numberOrNull([]), null);
  assert.equal(numberOrNull(NaN), null);
  // a REAL zero still survives — missing != zero cuts both ways
  assert.equal(numberOrNull(0), 0);
  assert.equal(numberOrNull("0"), 0);
  assert.equal(numberOrNull(1500), 1500);
});

test("buildCanonicalMechanics has no spellRows parameter", () => {
  const declared = buildCanonicalMechanics.toString().slice(0, buildCanonicalMechanics.toString().indexOf(")"));
  assert.ok(!/spellRows/.test(declared), `spellRows survives in the signature: ${declared}`);
  assert.ok(!/spellRows/.test(buildMechanicsArtifact.toString().slice(0, buildMechanicsArtifact.toString().indexOf(")"))));
  // an unknown caller passing the retired input cannot smuggle it back in
  const rows = buildCanonicalMechanics({
    entries: [{ spell_id: 7, entry_id: 1, entry_type: "Ability", name: "X", damage_schools: [], resources: [] }],
    spellRows: [{ spell_id: 7, duration_ms: 9999, period_ms: 3000 }],
    projection: [{ spell_id: 7, name: "X", mechanics: {}, raw: {}, coa_attribution: { is_coa: true } }],
  });
  assert.equal(rows[0].duration_ms, null);
  for (const effect of rows[0].effects) assert.equal(effect.tick_interval_ms ?? null, null);
});
