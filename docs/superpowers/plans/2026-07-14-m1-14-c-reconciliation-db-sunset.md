# M1.14C Reconciliation and DB Sunset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the CoA client the authoritative per-field mechanical source in `coa_mechanics.jsonl` via an attribution-scoped projection and a per-field, source-identified reconciliation engine, demoting db.ascension.gg to fallback-only — with full audit provenance, fail-closed integrity, and consumer contract preserved.

**Architecture:** Python (`coa_client_extract`) emits a compact `is_coa`-scoped client-spell projection (with per-DBC-table confidence) plus a projection manifest. The Node mechanics builder (`build-mechanics-artifacts.mjs`) reworks its join into per-field candidate selection (`client_dbc ▸ verified_builder ▸ ascension_db ▸ inferred`), a record-level DB identity gate, deterministic one-row-per-`spell_id` construction, and a checksum-bound mechanics manifest with canonical/fallback modes. `coa_meta/mechanics.py` gains optional `schools` + `field_provenance` round-trip. Item generation is split out. No consumer is rewired (consumption is M1.16).

**Tech Stack:** Python 3 (pytest, `coa_client_extract`, `coa_meta`), Node ESM (`node:test`, `coa_scraper/scripts`), JSONL artifacts.

**Spec:** [M1.14C Reconciliation and DB Sunset Design](../specs/2026-07-14-m1-14-c-reconciliation-db-sunset-design.md).

## Global Constraints

- **Mechanics schema stays `coa-mechanics-v1`.** `coa_meta/mechanics.py::mechanic_from_raw` hard-rejects any other `schema_version`. All additions (`schools`, `field_provenance`) are optional fields; a `coa-mechanics-v2` is out of scope.
- **Precedence, per field, first-*eligible*:** `client_dbc` ▸ `verified_builder` ▸ `ascension_db` ▸ `inferred`. `source`, `precedence_tier`, and `eligible` are three distinct properties; a Builder-*inferred* field lands in the `inferred` tier but stays eligible there.
- **Single malformed-input rule:** `--allow-fallback-mechanics` authorizes an **absent** projection only. Any present-but-invalid projection (bad schema/checksum, per-table drift on a used field, unknown mask/enum, `is_coa:false` row, coverage gap) **fails even with the flag**.
- **Output domain = Builder `spell_id`s**, one row per distinct `spell_id`; `builder_missing_from_projection == 0` required for a canonical build. Projection is `is_coa`-scoped (never Builder-scoped).
- **Missing ≠ zero:** JSON `null`/absent is "no candidate"; `0` is a real value. Never coerce `null` to `0`.
- **DB identity gate:** identity reference = client name → consensus verified-Builder name → db name; compare normalized db name to it; the Builder-based `name_match` is audit-only. On mismatch the db row supplies **nothing** (fields, effects, `kind`, `tags`, selected provenance).
- **Redistribution boundary:** real projection, real mechanics artifacts, and their manifests stay **untracked** (file-specific `.gitignore`). Commit only schemas, synthetic fixtures, tests, ignore rules, regeneration docs.
- **No consumer rewire / no user-facing change.** `reporting.py` is untouched; consumption is deferred to M1.16.
- **Node tests:** run from `coa_scraper/` with `node --test tests/pipeline-scripts.test.mjs`. Python tests: `pytest` from repo root.
- **Atomic writes:** JSONL and manifest each written via temp-path + rename; the previous manifest is removed **before** the JSONL is replaced (manifest is the validity marker).

---

## File Structure

**Python — `coa_client_extract/`**
- Modify `artifacts.py`: add `schema_match_confidence_by_dbc` in `build_client_spell_records`; add `write_client_spell_projection(records, out_dir, *, source_sha, source_path, source_bytes, client_build, extractor_commit) -> dict`.
- Modify `cli.py`: call the projection writer in `regenerate` after `fill_spell_attribution`; add its outputs to the manifest.

**Python — `coa_meta/`**
- Modify `mechanics.py`: optional `schools: tuple[str,...]` and `field_provenance: dict` on `MechanicRecord`; read/emit both; accept legacy effect `period_ms` on input, always reserialize `tick_interval_ms`.

**Node — `coa_scraper/scripts/`**
- Create `lib/mechanics-normalize.mjs`: `isPresent`, `normalizeSchoolMask`, `normalizePowerType`, `normalizeDurationMs`, enum maps.
- Create `lib/mechanics-reconcile.mjs`: `reconcileField`, `dbIdentityReference`, `applyDbIdentityGate`, reason-code constants.
- Modify `build-mechanics-artifacts.mjs`: rework `buildMechanicsRows` into projection-validated, per-field, one-row-per-`spell_id` construction + manifest + fail-closed/fallback + atomic writes; remove `buildItemRows` (moved).
- Create `build-item-artifacts.mjs`: `buildItemRows` (moved verbatim) + its own CLI.
- Modify `write-artifact-manifest.mjs`: include the split item script + the mechanics manifests.
- Modify `package.json`: `build-mechanics` (canonical), `build-mechanics:fallback`, `build-items`, `pipeline:m1.9`, `pipeline:m1.9:fallback`.

**Tests**
- Modify `coa_scraper/tests/pipeline-scripts.test.mjs`: fix the `period_ms` assertion; add reconciliation/normalize/gate/manifest tests.
- Create `tests/test_client_spell_projection.py` (Python, projection emitter + per-table confidence).
- Create `tests/test_mechanics_field_provenance.py` (Python, loader round-trip integration exit test).
- Modify `tests/test_client_extract_acceptance.py` (client-tier `805775` assertions).

**Docs**
- Modify `docs/data/mechanics-schema.md` (schools, field_provenance, mechanics manifest).
- Modify `docs/data/client-spell-schema.md` (per-table confidence, projection + its manifest, enum maps, sentinels).
- Modify `.gitignore` (file-specific client-derived outputs).
- Create `coa_scraper/scripts/README-regeneration.md` or extend existing regen docs (regeneration + canonical-vs-fallback).

---

## Task 1: Recon — enum maps and numeric sentinels

**Files:**
- Create: `coa_scraper/scripts/lib/mechanics-normalize.mjs`
- Create: `tests/test_client_enum_coverage.py`

**Interfaces:**
- Produces: `SCHOOL_MASK_BITS`, `POWER_TYPE_MAP`, `DURATION_SENTINELS`, `isPresent(v)`, `normalizeSchoolMask(mask)`, `normalizePowerType(pt)`, `normalizeDurationMs(ms)` — consumed by Tasks 5–8.

- [ ] **Step 1: Write the normalization module with documented maps**

Create `coa_scraper/scripts/lib/mechanics-normalize.mjs`:

```js
// WotLK 3.3.5a spell school mask bits (validated against observed CoA data by the recon test).
// Serialized in ascending bit order — order is documentation, NOT priority.
export const SCHOOL_MASK_BITS = Object.freeze({
  1: "physical", 2: "holy", 4: "fire", 8: "nature", 16: "frost", 32: "shadow", 64: "arcane",
});

// Spell.dbc PowerType enum → resource name.
export const POWER_TYPE_MAP = Object.freeze({
  "-2": "health", "0": "mana", "1": "rage", "2": "focus", "3": "energy",
  "4": "happiness", "5": "runes", "6": "runic_power",
});

// Legitimate numeric sentinels that must be preserved, not treated as parse errors.
export const DURATION_SENTINELS = Object.freeze({ INFINITE: -1 });

export function isPresent(value) {
  return value !== null && value !== undefined;
}

// mask → { schools: string[], unknownBits: number[] }. Absent mask → empty schools, no unknowns.
export function normalizeSchoolMask(mask) {
  if (!isPresent(mask)) return { schools: [], unknownBits: [] };
  const schools = [];
  const unknownBits = [];
  for (let bit = 1; bit <= mask && bit > 0; bit <<= 1) {
    if ((mask & bit) === 0) continue;
    const name = SCHOOL_MASK_BITS[bit];
    if (name) schools.push(name);
    else unknownBits.push(bit);
  }
  return { schools, unknownBits };
}

// int → { value: string|null, unknown: boolean }. Absent → { value: null, unknown: false }.
export function normalizePowerType(powerType) {
  if (!isPresent(powerType)) return { value: null, unknown: false };
  const name = POWER_TYPE_MAP[String(powerType)];
  return name ? { value: name, unknown: false } : { value: null, unknown: true };
}

// -1 (infinite) is preserved; absent → null.
export function normalizeDurationMs(ms) {
  if (!isPresent(ms)) return null;
  return ms;
}
```

- [ ] **Step 2: Write a default-tier Node test proving unknown bits/enums are flagged**

Add to `coa_scraper/tests/pipeline-scripts.test.mjs` (runs without a client — proves the flagging mechanism the canonical build relies on):

```js
import { normalizeSchoolMask, normalizePowerType } from "../scripts/lib/mechanics-normalize.mjs";

test("normalizeSchoolMask flags unknown bits; normalizePowerType flags unknown enum", () => {
  assert.deepEqual(normalizeSchoolMask(8), { schools: ["nature"], unknownBits: [] });
  assert.deepEqual(normalizeSchoolMask(12), { schools: ["fire", "nature"], unknownBits: [] }); // 4|8
  assert.deepEqual(normalizeSchoolMask(128), { schools: [], unknownBits: [128] });            // undocumented bit
  assert.equal(normalizePowerType(3).value, "energy");
  assert.equal(normalizePowerType(999).unknown, true);                                          // undocumented enum
});
```

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs` → PASS.

- [ ] **Step 3: Write the client-tier coverage recon test**

Create `tests/test_client_enum_coverage.py`. It runs at the client tier (skips only when the real projection is absent) and asserts every observed `school_mask` bit and `power_type` value is covered by the documented maps.

```python
import json
import re
from pathlib import Path

import pytest

NORMALIZE = Path("coa_scraper/scripts/lib/mechanics-normalize.mjs")
PROJECTION = Path("reports/client_extract/coa_client_spell_coa.jsonl")


def _documented():
    text = NORMALIZE.read_text(encoding="utf-8")
    bits = set(int(m) for m in re.findall(r'(\d+):\s*"', text.split("SCHOOL_MASK_BITS")[1].split("}")[0]))
    powers = set(int(m) for m in re.findall(r'"(-?\d+)":\s*"', text.split("POWER_TYPE_MAP")[1].split("}")[0]))
    return bits, powers


@pytest.mark.client
def test_observed_enums_covered_by_documented_maps():
    if not PROJECTION.is_file():
        pytest.skip("projection not present (client tier)")
    bits, powers = _documented()
    seen_bits, seen_powers = set(), set()
    for line in PROJECTION.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        mech = json.loads(line).get("mechanics", {})
        mask = mech.get("school_mask")
        if isinstance(mask, int) and mask > 0:
            b = 1
            while b <= mask:
                if mask & b:
                    seen_bits.add(b)
                b <<= 1
        pt = mech.get("power_type")
        if isinstance(pt, int):
            seen_powers.add(pt)
    assert seen_bits <= bits, f"undocumented school-mask bits: {sorted(seen_bits - bits)}"
    assert seen_powers <= powers, f"undocumented power_type values: {sorted(seen_powers - powers)}"
```

- [ ] **Step 4: Run the coverage test**

Run: `pytest tests/test_client_enum_coverage.py -v`
Expected: PASS (skips if the real projection is absent; on a client machine it asserts coverage — if it FAILS with undocumented bits/values, add them to the maps in `mechanics-normalize.mjs` and record them in `docs/data/client-spell-schema.md` in Task 13, then re-run).

- [ ] **Step 5: Commit**

```bash
git add coa_scraper/scripts/lib/mechanics-normalize.mjs coa_scraper/tests/pipeline-scripts.test.mjs tests/test_client_enum_coverage.py
git commit -m "M1.14C Task 1: mechanics normalization maps + unknown-flagging + enum coverage recon"
```

---

## Task 2: Python — per-DBC-table confidence in client-spell records

**Files:**
- Modify: `coa_client_extract/artifacts.py:52-66` (`build_client_spell_records`)
- Test: `tests/test_client_spell_projection.py` (created here, extended in Task 3)

**Interfaces:**
- Consumes: `build_client_spell_records(spell, cast_times, durations, ranges, *, provenance)` (existing signature unchanged).
- Produces: each record's `provenance.schema_match_confidence_by_dbc = {"Spell","SpellCastTimes","SpellDuration","SpellRange"}` with `"high"`/`"low"` values.

- [ ] **Step 1: Write the failing test**

Create `tests/test_client_spell_projection.py`:

```python
from coa_client_extract.artifacts import build_client_spell_records
from coa_client_extract.wdbc import DbcTable


def _table(name, rows, drift=False):
    return DbcTable(name=name, field_count=1, record_size=4, record_count=len(rows), rows=rows, drift=drift)


def _spell_family(*, spell_drift=False, cast_drift=False):
    spell = _table("Spell", [{
        "id": 805775, "name": "Adrenal Venom", "school_mask": 8, "power_type": 3,
        "casting_time_index": 1, "duration_index": 1, "range_index": 1,
        "category": 0, "spell_icon_id": 4583,
    }], drift=spell_drift)
    cast = _table("SpellCastTimes", [{"id": 1, "base_ms": 0}], drift=cast_drift)
    dur = _table("SpellDuration", [{"id": 1, "base_ms": 12000}])
    rng = _table("SpellRange", [{"id": 1, "min_yd": 0, "max_yd": 30}])
    return spell, cast, dur, rng


def test_per_table_confidence_high_when_no_drift():
    spell, cast, dur, rng = _spell_family()
    rec = build_client_spell_records(spell, cast, dur, rng, provenance={"effective_archive": "patch-T.MPQ"})[0]
    by_dbc = rec["provenance"]["schema_match_confidence_by_dbc"]
    assert by_dbc == {"Spell": "high", "SpellCastTimes": "high", "SpellDuration": "high", "SpellRange": "high"}


def test_per_table_confidence_low_for_drifted_table_only():
    spell, cast, dur, rng = _spell_family(cast_drift=True)
    rec = build_client_spell_records(spell, cast, dur, rng, provenance={"effective_archive": "patch-T.MPQ"})[0]
    by_dbc = rec["provenance"]["schema_match_confidence_by_dbc"]
    assert by_dbc["SpellCastTimes"] == "low"
    assert by_dbc["Spell"] == "high"


def test_absent_table_is_low_confidence():
    spell, cast, dur, rng = _spell_family()
    rec = build_client_spell_records(spell, cast, dur, None, provenance={"effective_archive": "patch-T.MPQ"})[0]
    assert rec["provenance"]["schema_match_confidence_by_dbc"]["SpellRange"] == "low"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_client_spell_projection.py -v`
Expected: FAIL with `KeyError: 'schema_match_confidence_by_dbc'`.

- [ ] **Step 3: Implement per-table confidence**

In `coa_client_extract/artifacts.py`, inside `build_client_spell_records`, replace the `provenance` block of the appended record. Change:

```python
            "provenance": {
                **provenance,
                "schema_match_confidence": "low" if spell.drift else "high",
            },
```

to:

```python
            "provenance": {
                **provenance,
                "schema_match_confidence": "low" if spell.drift else "high",
                "schema_match_confidence_by_dbc": {
                    "Spell": "low" if spell.drift else "high",
                    "SpellCastTimes": _table_conf(cast_times),
                    "SpellDuration": _table_conf(durations),
                    "SpellRange": _table_conf(ranges),
                },
            },
```

And add this helper near the top of the module (after `_index_lookup`):

```python
def _table_conf(table: DbcTable | None) -> str:
    """A contributing side-table is 'high' only if present and drift-free; absent or drifted is 'low'."""
    if table is None or table.drift:
        return "low"
    return "high"
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_client_spell_projection.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/artifacts.py tests/test_client_spell_projection.py
git commit -m "M1.14C Task 2: per-DBC-table schema-match confidence on client-spell records"
```

---

## Task 3: Python — projection emitter + manifest

**Files:**
- Modify: `coa_client_extract/artifacts.py` (add `write_client_spell_projection`)
- Modify: `coa_client_extract/cli.py:160-171` (`regenerate` wiring)
- Test: `tests/test_client_spell_projection.py` (extend)

**Interfaces:**
- Consumes: filled `spell_records` (each with `coa_attribution.is_coa`), `write_jsonl`, `_sha256_bytes`.
- Produces: `write_client_spell_projection(records, out_dir, *, source_path, source_sha, source_bytes, client_build, extractor_commit) -> dict` writing `coa_client_spell_coa.jsonl` + `coa_client_spell_projection.manifest.json`; returns the manifest dict.

- [ ] **Step 1: Write the failing test (append to `tests/test_client_spell_projection.py`)**

```python
import json
from pathlib import Path
from coa_client_extract.artifacts import write_client_spell_projection


def _coa_rec(spell_id, is_coa, conf="high", modes=("coa",)):
    return {
        "schema_version": "coa-client-spell-v1", "spell_id": spell_id, "name": f"S{spell_id}",
        "mechanics": {"school_mask": 8, "power_type": 3, "cast_time_ms": 0, "duration_ms": 12000,
                      "range_min_yd": 0, "range_max_yd": 30, "category": 0, "spell_icon_id": 1},
        "provenance": {"schema_match_confidence": "high",
                       "schema_match_confidence_by_dbc": {"Spell": "high", "SpellCastTimes": "high",
                                                          "SpellDuration": "high", "SpellRange": "high"}},
        "coa_attribution": {"is_coa": is_coa, "modes": list(modes), "exclusive_mode": modes[0] if modes else None,
                            "confidence": conf},
    }


def test_projection_keeps_only_is_coa_and_writes_manifest(tmp_path):
    records = [_coa_rec(1, True), _coa_rec(2, False, conf="low", modes=()), _coa_rec(3, True, conf="medium")]
    manifest = write_client_spell_projection(
        records, tmp_path, source_path="coa_client_spell.jsonl", source_sha="abc", source_bytes=100,
        client_build="3.3.5a+patch-T", extractor_commit="deadbeef")
    proj = [json.loads(l) for l in (tmp_path / "coa_client_spell_coa.jsonl").read_text().splitlines() if l.strip()]
    assert sorted(r["spell_id"] for r in proj) == [1, 3]
    assert manifest["schema_version"] == "coa-client-spell-projection-v1"
    assert manifest["counts"]["projected_records"] == 2
    assert manifest["counts"]["by_confidence"] == {"high": 1, "medium": 1}
    assert manifest["source_artifact"]["sha256"] == "abc"
    written = json.loads((tmp_path / "coa_client_spell_projection.manifest.json").read_text())
    assert written["projection"]["sha256"] == manifest["projection"]["sha256"]


def test_projection_rejects_duplicate_spell_ids(tmp_path):
    import pytest
    records = [_coa_rec(1, True), _coa_rec(1, True)]
    with pytest.raises(ValueError, match="duplicate spell_ids"):
        write_client_spell_projection(records, tmp_path, source_path="x", source_sha="a", source_bytes=1,
                                      client_build="b", extractor_commit="c")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_client_spell_projection.py::test_projection_keeps_only_is_coa_and_writes_manifest -v`
Expected: FAIL with `ImportError: cannot import name 'write_client_spell_projection'`.

- [ ] **Step 3: Implement the emitter**

Add to `coa_client_extract/artifacts.py`:

```python
def write_client_spell_projection(
    records: list[dict],
    out_dir: Path,
    *,
    source_path: str,
    source_sha: str,
    source_bytes: int,
    client_build: str,
    extractor_commit: str,
) -> dict:
    """Filter coa-client-spell-v1 records to the CoA set (coa_attribution.is_coa) and write the
    projection + its manifest. Scoped by client-native attribution, never by Builder spell IDs.
    Uses the manifest-as-validity-marker protocol: reject duplicate projected spell ids, remove the
    old manifest first, write the JSONL atomically, then write the manifest atomically last — so an
    interruption never leaves a new JSONL beside a stale manifest."""
    projected = [r for r in records if r.get("coa_attribution", {}).get("is_coa") is True]
    spell_ids = [r["spell_id"] for r in projected]
    dupes = sorted(s for s, n in Counter(spell_ids).items() if n > 1)  # single pass, not O(n^2)
    if dupes:
        raise ValueError(f"projection has duplicate spell_ids: {dupes[:5]}")

    proj_path = out_dir / "coa_client_spell_coa.jsonl"
    manifest_path = out_dir / "coa_client_spell_projection.manifest.json"

    body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in projected).encode("utf-8")
    proj_sha = _sha256_bytes(body)

    by_conf: dict[str, int] = {}
    by_dbc_low = 0
    for r in projected:
        c = r.get("coa_attribution", {}).get("confidence", "low")
        by_conf[c] = by_conf.get(c, 0) + 1
        vals = r.get("provenance", {}).get("schema_match_confidence_by_dbc", {}).values()
        if any(v != "high" for v in vals):
            by_dbc_low += 1

    manifest = {
        "schema_version": "coa-client-spell-projection-v1",
        "inclusion_rule": {"predicate": "coa_attribution.is_coa == true", "version": "m1.14c-1"},
        "source_artifact": {"path": source_path, "sha256": source_sha, "byte_length": source_bytes},
        "projection": {"path": proj_path.name, "sha256": proj_sha, "byte_length": len(body)},
        "client_build": client_build,
        "extractor_commit": extractor_commit,
        "extraction_date": date.today().isoformat(),
        "counts": {"source_records": len(records), "projected_records": len(projected),
                   "unique_spell_ids": len(set(spell_ids)),
                   "by_confidence": by_conf},
        "schema_confidence_summary": {"records_with_any_low_table": by_dbc_low,
                                      "records_all_high": len(projected) - by_dbc_low},
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    # manifest-as-validity-marker: remove old manifest first, then JSONL, then manifest — each atomic.
    out_dir.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        manifest_path.unlink()
    _atomic_write_bytes(body, proj_path)
    _atomic_write_bytes(manifest_bytes, manifest_path)
    return manifest
```

Add `from datetime import date`, `import os`, and `from collections import Counter` to the top of `artifacts.py`, and add this atomic helper near `_sha256_bytes`:

```python
def _atomic_write_bytes(data: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_client_spell_projection.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Wire it into `regenerate`**

In `coa_client_extract/cli.py`, after line 160 (`spell_records = fill_spell_attribution(spell_records, spell_attr)`) and after the `outputs` dict is populated with `coa_client_spell.jsonl` (line 164), add the projection write. Insert right after line 171 (`outputs["coa_client_essence.jsonl"] = ...`):

```python
    from .artifacts import write_client_spell_projection
    spell_full_path = out_dir / "coa_client_spell.jsonl"
    projection_manifest = write_client_spell_projection(
        spell_records, out_dir,
        source_path=spell_full_path.name,
        source_sha=outputs["coa_client_spell.jsonl"],
        source_bytes=spell_full_path.stat().st_size,
        client_build=_client_build(plan),
        extractor_commit=_extractor_commit(),
    )
    outputs["coa_client_spell_coa.jsonl"] = projection_manifest["projection"]["sha256"]
    outputs["coa_client_spell_projection.manifest.json"] = _sha256_bytes(
        (out_dir / "coa_client_spell_projection.manifest.json").read_bytes())
```

Add `_sha256_bytes` to the `from .artifacts import (...)` line already present at cli.py:79-82, or import it alongside. (It is defined in `artifacts.py`.)

- [ ] **Step 6: Run the full extractor test suite (regression)**

Run: `pytest tests/test_client_spell_projection.py tests/test_client_extract_advancement_semantic.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add coa_client_extract/artifacts.py coa_client_extract/cli.py tests/test_client_spell_projection.py
git commit -m "M1.14C Task 3: attribution-scoped client-spell projection + manifest"
```

---

## Task 4: Python loader — schools + field_provenance round-trip, legacy period_ms

**Files:**
- Modify: `coa_meta/mechanics.py` (`MechanicRecord`, `mechanic_from_raw`, `to_dict`, `_effect_from_raw`)
- Test: `tests/test_mechanics_field_provenance.py` (create)

**Interfaces:**
- Consumes: `mechanic_from_raw(raw, source)`, `MechanicRecord.to_dict()`.
- Produces: `MechanicRecord.schools: tuple[str,...]`, `MechanicRecord.field_provenance: dict`; effect input accepts `period_ms`, output always `tick_interval_ms`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_mechanics_field_provenance.py`:

```python
from coa_meta.mechanics import mechanic_from_raw


def _raw(**over):
    base = {
        "schema_version": "coa-mechanics-v1", "spell_id": 805775, "name": "Adrenal Venom",
        "kind": "ability", "school": "nature", "schools": ["nature"],
        "field_provenance": {"schools": {"selected_source": "client_dbc", "selected_tier": "client_dbc",
                                         "selected_value": ["nature"], "selection_reason": "highest_precedence_eligible",
                                         "warnings": [], "candidates": []}},
        "effects": [{"effect_type": "damage", "period_ms": 3000}],
    }
    base.update(over)
    return base


def test_schools_and_field_provenance_round_trip():
    rec = mechanic_from_raw(_raw(), "<test>")
    assert rec.schools == ("nature",)
    assert rec.field_provenance["schools"]["selected_source"] == "client_dbc"
    out = rec.to_dict()
    assert out["schools"] == ["nature"]
    assert out["field_provenance"]["schools"]["selected_tier"] == "client_dbc"


def test_effect_accepts_legacy_period_ms_reserializes_tick_interval():
    rec = mechanic_from_raw(_raw(), "<test>")
    assert rec.effects[0].tick_interval_ms == 3000
    out = rec.to_dict()
    assert out["effects"][0]["tick_interval_ms"] == 3000
    assert "period_ms" not in out["effects"][0]
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_mechanics_field_provenance.py -v`
Expected: FAIL (`AttributeError: 'MechanicRecord' object has no attribute 'schools'`).

- [ ] **Step 3: Add `schools` + `field_provenance` to `MechanicRecord`**

In `coa_meta/mechanics.py`, in the `MechanicRecord` dataclass (after `power_type: str = ""`), add:

```python
    schools: tuple[str, ...] = tuple()
    field_provenance: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)
```

In `MechanicRecord.to_dict`, add to the `_drop_none({...})` dict (near `"power_type": self.power_type,`):

```python
                "school": self.school,
                "schools": list(self.schools),
```

and after the `_drop_none(...)` result assignment (before `if self.raw:`), add:

```python
        if self.field_provenance:
            data["field_provenance"] = self.field_provenance
```

In `mechanic_from_raw`, add to the `MechanicRecord(...)` constructor call:

```python
        schools=tuple(str(item) for item in raw.get("schools") or []),
        field_provenance=dict(raw.get("field_provenance") or {}),
```

- [ ] **Step 4: Accept legacy `period_ms` on effect input**

In `coa_meta/mechanics.py`, in `_effect_from_raw`, change:

```python
        tick_interval_ms=_as_int_or_none(raw.get("tick_interval_ms")),
```

to:

```python
        tick_interval_ms=_as_int_or_none(
            raw.get("tick_interval_ms") if raw.get("tick_interval_ms") is not None else raw.get("period_ms")
        ),
```

(`MechanicEffect.to_dict` already emits only `tick_interval_ms`, so output is always canonical.)

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/test_mechanics_field_provenance.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the existing mechanics schema tests (regression)**

Run: `pytest tests/test_mechanics_schema.py tests/test_mechanics_inference.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add coa_meta/mechanics.py tests/test_mechanics_field_provenance.py
git commit -m "M1.14C Task 4: loader round-trips schools + field_provenance; accepts legacy period_ms"
```

---

## Task 5: Node — reconciliation engine (`reconcileField`)

**Files:**
- Create: `coa_scraper/scripts/lib/mechanics-reconcile.mjs`
- Test: `coa_scraper/tests/pipeline-scripts.test.mjs` (add a `test(...)` block)

**Interfaces:**
- Consumes: `isPresent` from `lib/mechanics-normalize.mjs`.
- Produces: `TIERS`, `REASON`, `reconcileField({ field, candidates })` → `{ field, selected, provenance, hadConflict }` (`selected` is `undefined` when omitted) where each `candidate` is `{ source, precedence_tier, source_id, source_field, raw_value, normalized_value, confidence, eligible, eligibility_reasons }`.

- [ ] **Step 1: Write the failing test (append a `test` block in `pipeline-scripts.test.mjs`)**

Add near the other imports at top of `coa_scraper/tests/pipeline-scripts.test.mjs`:

```js
import { reconcileField, REASON } from "../scripts/lib/mechanics-reconcile.mjs";
```

Add this test:

```js
test("reconcileField picks first eligible by tier and records all candidates", () => {
  const cand = (over) => ({
    source: "x", precedence_tier: "inferred", source_id: "s", source_field: "f",
    raw_value: null, normalized_value: null, confidence: "low", eligible: true, eligibility_reasons: [],
    ...over,
  });
  // client wins over db even though both eligible
  const out = reconcileField({
    field: "cast_time_ms",
    candidates: [
      cand({ source: "client_dbc", precedence_tier: "client_dbc", normalized_value: 1500, confidence: "high" }),
      cand({ source: "ascension_db", precedence_tier: "ascension_db", normalized_value: 2000, confidence: "medium" }),
    ],
  });
  assert.equal(out.selected, 1500);
  assert.equal(out.provenance.selected_source, "client_dbc");
  assert.equal(out.provenance.selected_tier, "client_dbc");
  assert.equal(out.provenance.selection_reason, REASON.HIGHEST_PRECEDENCE_ELIGIBLE);
  assert.equal(out.provenance.candidates.length, 2);
});

test("reconcileField marks ALL same-tier conflicters ineligible and falls through", () => {
  const b = (id, v) => ({
    source: "builder", precedence_tier: "inferred", source_id: `builder_node:${id}`, source_field: "damage_schools",
    raw_value: v, normalized_value: v, confidence: "medium", eligible: true, eligibility_reasons: [],
  });
  const out = reconcileField({
    field: "schools",
    candidates: [
      { source: "client_dbc", precedence_tier: "client_dbc", source_id: "client_spell:1", source_field: "school_mask",
        raw_value: 8, normalized_value: ["nature"], confidence: "high", eligible: true, eligibility_reasons: [] },
      b(7131, ["nature"]), b(12264, ["shadow"]),
    ],
  });
  assert.deepEqual(out.selected, ["nature"]); // client wins
  const builders = out.provenance.candidates.filter((c) => c.source === "builder");
  assert(builders.every((c) => c.eligible === false));
  assert(builders.every((c) => c.eligibility_reasons.includes(REASON.SAME_TIER_CONFLICT)));
});

test("reconcileField omits field when only tier conflicts", () => {
  const b = (id, v) => ({
    source: "builder", precedence_tier: "inferred", source_id: `builder_node:${id}`, source_field: "damage_schools",
    raw_value: v, normalized_value: v, confidence: "medium", eligible: true, eligibility_reasons: [],
  });
  const out = reconcileField({ field: "schools", candidates: [b(1, ["nature"]), b(2, ["shadow"])] });
  assert.equal(out.selected, undefined);
  assert.equal(out.provenance.selection_reason, REASON.OMITTED_UNRESOLVED_CONFLICT);
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: FAIL — cannot find module `lib/mechanics-reconcile.mjs`.

- [ ] **Step 3: Implement `reconcileField`**

Create `coa_scraper/scripts/lib/mechanics-reconcile.mjs`:

```js
export const TIERS = Object.freeze(["client_dbc", "verified_builder", "ascension_db", "inferred"]);

export const REASON = Object.freeze({
  HIGHEST_PRECEDENCE_ELIGIBLE: "highest_precedence_eligible",
  ONLY_CANDIDATE: "only_candidate",
  DB_FALLBACK: "db_fallback",
  INFERRED_LAST_RESORT: "inferred_last_resort",
  INFERRED_FROM_TEXT: "inferred_from_text",
  KIND_NODE_DISAGREEMENT_RESOLVED: "kind_node_disagreement_resolved",
  OMITTED_UNRESOLVED_CONFLICT: "omitted_unresolved_conflict",
  OMITTED_NO_ELIGIBLE_CANDIDATE: "omitted_no_eligible_candidate",
  SAME_TIER_CONFLICT: "same_tier_conflict",
  CLIENT_TABLE_DRIFT: "client_table_drift",
  DB_IDENTITY_MISMATCH: "db_identity_mismatch",
  DB_IDENTITY_UNVERIFIABLE: "db_identity_unverifiable",
  UNKNOWN_ENUM: "unknown_enum",
  UNKNOWN_MASK_BIT: "unknown_mask_bit",
  ABSENT: "absent",
});

// Note: the conditions that FATALLY fail a canonical build — per-table drift on a populated field,
// unknown school-mask bit, unknown power enum — are thrown directly by the projection validator
// (`assertRecordSemantics`, Task 9) BEFORE reconciliation. Candidate assembly (Task 7) additionally
// marks the corresponding client candidates ineligible as belt-and-suspenders, but the hard failure
// is the validator's; there is no separate "fatal reasons" lookup to keep in sync.

function sameValue(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

// Mutates candidates: within each tier, if >1 present candidate disagrees, mark them all ineligible.
function applyTierConflicts(candidates) {
  for (const tier of TIERS) {
    const present = candidates.filter(
      (c) => c.precedence_tier === tier && c.normalized_value !== null && c.normalized_value !== undefined,
    );
    if (present.length < 2) continue;
    const first = present[0].normalized_value;
    if (present.some((c) => !sameValue(c.normalized_value, first))) {
      for (const c of present) {
        c.eligible = false;
        if (!c.eligibility_reasons.includes(REASON.SAME_TIER_CONFLICT)) {
          c.eligibility_reasons.push(REASON.SAME_TIER_CONFLICT);
        }
      }
    }
  }
}

export function reconcileField({ field, candidates }) {
  applyTierConflicts(candidates);
  let selected;
  let provenance = {
    selected_source: null, selected_tier: null, selected_value: null,
    selection_reason: null, warnings: [], candidates,
  };
  for (const tier of TIERS) {
    const winner = candidates.find(
      (c) => c.precedence_tier === tier && c.eligible &&
        c.normalized_value !== null && c.normalized_value !== undefined,
    );
    if (!winner) continue;
    selected = winner.normalized_value;
    const hadConflict = candidates.some((c) => c.eligibility_reasons.includes(REASON.SAME_TIER_CONFLICT));
    provenance.selected_source = winner.source;
    provenance.selected_tier = winner.precedence_tier;
    provenance.selected_value = selected;
    provenance.selection_reason =
      winner.precedence_tier === "ascension_db" ? REASON.DB_FALLBACK
      : winner.precedence_tier === "inferred" ? REASON.INFERRED_LAST_RESORT
      : candidates.length === 1 ? REASON.ONLY_CANDIDATE
      : REASON.HIGHEST_PRECEDENCE_ELIGIBLE;
    return { field, selected, provenance, hadConflict };
  }
  const anyConflict = candidates.some((c) => c.eligibility_reasons.includes(REASON.SAME_TIER_CONFLICT));
  provenance.selection_reason = anyConflict
    ? REASON.OMITTED_UNRESOLVED_CONFLICT
    : REASON.OMITTED_NO_ELIGIBLE_CANDIDATE;
  return { field, selected: undefined, provenance, hadConflict: anyConflict };
}
```

- [ ] **Step 4: Run to verify it passes**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: PASS for the three new reconcile tests (pre-existing tests may still fail until Task 12 — that is expected; check the new tests pass).

- [ ] **Step 5: Commit**

```bash
git add coa_scraper/scripts/lib/mechanics-reconcile.mjs coa_scraper/tests/pipeline-scripts.test.mjs
git commit -m "M1.14C Task 5: per-field reconciliation engine (tier/eligibility/conflict)"
```

---

## Task 6: Node — DB identity gate

**Files:**
- Modify: `coa_scraper/scripts/lib/mechanics-reconcile.mjs` (add `dbIdentityReference`, `applyDbIdentityGate`)
- Test: `coa_scraper/tests/pipeline-scripts.test.mjs` (add a `test` block)

**Interfaces:**
- Consumes: `normalizeName` from `lib/ascensiondb.mjs`.
- Produces: `dbIdentityReference({ clientName, builderNames, dbName })` → string|null; `applyDbIdentityGate({ dbRow, referenceName })` → `{ excluded: boolean, reason: string|null }` (`reason` is a `REASON` code — `db_identity_mismatch`/`db_identity_unverifiable` — consumed by Task 8 to bar an identity-mismatched db row from every contribution and record why).

- [ ] **Step 1: Write the failing test**

Add to `pipeline-scripts.test.mjs`:

```js
import { dbIdentityReference, applyDbIdentityGate } from "../scripts/lib/mechanics-reconcile.mjs";

test("dbIdentityReference prefers client name, then consensus builder, then db", () => {
  assert.equal(dbIdentityReference({ clientName: "Adrenal Venom", builderNames: ["X"], dbName: "Y" }), "Adrenal Venom");
  assert.equal(dbIdentityReference({ clientName: "", builderNames: ["Ward", "Ward"], dbName: "Y" }), "Ward");
  assert.equal(dbIdentityReference({ clientName: "", builderNames: ["A", "B"], dbName: "Y" }), "Y");
});

test("applyDbIdentityGate excludes a name-mismatched db row (name_match ignored as veto)", () => {
  const stale = { name: "Fang Venom: Lifeblood", name_match: false };
  const fresh = { name: "Adrenal Venom", name_match: false }; // builder-based name_match is audit-only
  assert.equal(applyDbIdentityGate({ dbRow: stale, referenceName: "Adrenal Venom" }).excluded, true);
  assert.equal(applyDbIdentityGate({ dbRow: fresh, referenceName: "Adrenal Venom" }).excluded, false);
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: FAIL — `dbIdentityReference` is not exported.

- [ ] **Step 3: Implement the gate**

Append to `coa_scraper/scripts/lib/mechanics-reconcile.mjs`:

```js
import { normalizeName } from "./ascensiondb.mjs";

// Identity reference: client name → consensus verified-Builder name → db name.
export function dbIdentityReference({ clientName, builderNames, dbName }) {
  if (clientName) return clientName;
  const names = (builderNames || []).filter(Boolean).map(String);
  if (names.length) {
    const first = names[0];
    if (names.every((n) => normalizeName(n) === normalizeName(first))) return first;
  }
  return dbName || null;
}

// A db row is excluded from every contribution when its normalized name != the reference.
// The existing Builder-based name_match is NOT consulted as a veto (audit-only). A row that cannot
// be identity-checked (no db name, or no reference to check against) is excluded as UNVERIFIABLE,
// never silently allowed.
export function applyDbIdentityGate({ dbRow, referenceName }) {
  if (!dbRow) return { excluded: false, reason: null };
  if (!dbRow.name || !referenceName) return { excluded: true, reason: REASON.DB_IDENTITY_UNVERIFIABLE };
  const mismatch = normalizeName(dbRow.name) !== normalizeName(referenceName);
  return { excluded: mismatch, reason: mismatch ? REASON.DB_IDENTITY_MISMATCH : null };
}
```

Confirm `normalizeName` is exported from `coa_scraper/scripts/lib/ascensiondb.mjs` (it is, used by the enrichment row builder). If it is not exported, add `export` to its declaration.

- [ ] **Step 4: Run to verify it passes**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: PASS for the two gate tests.

- [ ] **Step 5: Commit**

```bash
git add coa_scraper/scripts/lib/mechanics-reconcile.mjs coa_scraper/tests/pipeline-scripts.test.mjs
git commit -m "M1.14C Task 6: record-level DB identity gate (client-first reference)"
```

---

## Task 7: Node — build candidate lists per field (source → candidate mapping)

**Files:**
- Create: `coa_scraper/scripts/lib/mechanics-candidates.mjs`
- Test: `coa_scraper/tests/pipeline-scripts.test.mjs` (add a `test` block)

**Interfaces:**
- Consumes: `normalizeSchoolMask`, `normalizePowerType`, `normalizeDurationMs`, `isPresent` (normalize lib); `REASON` (reconcile lib).
- Produces: `fieldCandidates({ field, clientRec, builderNodes, dbRow, dbExcluded })` → candidate array for `reconcileField`. Fields handled: `cast_time_ms`, `duration_ms`, `range_yards`, `schools`, `power_type`.

- [ ] **Step 1: Write the failing test**

Add to `pipeline-scripts.test.mjs`:

```js
import { fieldCandidates } from "../scripts/lib/mechanics-candidates.mjs";

test("fieldCandidates: client cast_time 0 is present (missing != zero), db excluded contributes nothing", () => {
  const clientRec = {
    mechanics: { cast_time_ms: 0, school_mask: 8, power_type: 3, duration_ms: null, range_max_yd: 30 },
    provenance: { schema_match_confidence_by_dbc: { Spell: "high", SpellCastTimes: "high", SpellDuration: "high", SpellRange: "high" } },
    coa_attribution: { confidence: "high" },
    spell_id: 42,
  };
  const dbRow = { id: 42, cast_time_ms: 2000, name: "Stale" };
  const cands = fieldCandidates({ field: "cast_time_ms", clientRec, builderNodes: [], dbRow, dbExcluded: true });
  const client = cands.find((c) => c.source === "client_dbc");
  assert.equal(client.normalized_value, 0);
  assert.equal(client.eligible, true);
  // db excluded → either absent or ineligible db_identity_mismatch
  const db = cands.find((c) => c.source === "ascension_db");
  assert(!db || db.eligible === false);
});

test("fieldCandidates: client cast_time ineligible when SpellCastTimes drifted", () => {
  const clientRec = {
    mechanics: { cast_time_ms: 1500 },
    provenance: { schema_match_confidence_by_dbc: { Spell: "high", SpellCastTimes: "low", SpellDuration: "high", SpellRange: "high" } },
    coa_attribution: { confidence: "high" }, spell_id: 7,
  };
  const cands = fieldCandidates({ field: "cast_time_ms", clientRec, builderNodes: [], dbRow: null, dbExcluded: false });
  const client = cands.find((c) => c.source === "client_dbc");
  assert.equal(client.eligible, false);
  assert(client.eligibility_reasons.includes("client_table_drift"));
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: FAIL — cannot find `lib/mechanics-candidates.mjs`.

- [ ] **Step 3: Implement candidate assembly**

Create `coa_scraper/scripts/lib/mechanics-candidates.mjs`:

```js
import { isPresent, normalizeSchoolMask, normalizePowerType, normalizeDurationMs } from "./mechanics-normalize.mjs";
import { REASON } from "./mechanics-reconcile.mjs";

// Which client DBC tables each field depends on (all must be "high" for client eligibility).
const CLIENT_TABLES = {
  cast_time_ms: ["Spell", "SpellCastTimes"],
  duration_ms: ["Spell", "SpellDuration"],
  range_yards: ["Spell", "SpellRange"],
  schools: ["Spell"],
  power_type: ["Spell"],
};

// The real client Spell-family column each mechanics field is sourced from (for candidate source_field).
const CLIENT_SOURCE_FIELD = {
  cast_time_ms: "cast_time_ms", duration_ms: "duration_ms", range_yards: "range_max_yd",
  schools: "school_mask", power_type: "power_type",
};

function clientTablesHigh(clientRec, field) {
  const byDbc = clientRec?.provenance?.schema_match_confidence_by_dbc || {};
  return (CLIENT_TABLES[field] || []).every((t) => byDbc[t] === "high");
}

function clientNormalized(clientRec, field) {
  const m = clientRec?.mechanics || {};
  switch (field) {
    case "cast_time_ms": return { raw: m.cast_time_ms, value: isPresent(m.cast_time_ms) ? m.cast_time_ms : null };
    case "duration_ms": return { raw: m.duration_ms, value: normalizeDurationMs(m.duration_ms) };
    case "range_yards": return { raw: { min: m.range_min_yd, max: m.range_max_yd }, value: isPresent(m.range_max_yd) ? m.range_max_yd : null };
    case "schools": {
      const { schools, unknownBits } = normalizeSchoolMask(m.school_mask);
      return { raw: m.school_mask, value: schools.length ? schools : null, unknownBits };
    }
    case "power_type": {
      const { value, unknown } = normalizePowerType(m.power_type);
      return { raw: m.power_type, value, unknown };
    }
    default: return { raw: null, value: null };
  }
}

// Builder inferred fields (source/inferred split): damage_schools → schools, resources → power_type.
function builderNormalized(node, field) {
  if (field === "schools") {
    const v = Array.isArray(node.damage_schools) ? node.damage_schools.map(String) : [];
    return { raw: node.damage_schools, value: v.length ? v : null, inferred: true };
  }
  if (field === "power_type") {
    const v = Array.isArray(node.resources) && node.resources.length ? String(node.resources[0]).toLowerCase() : null;
    return { raw: node.resources, value: v, inferred: true };
  }
  return { raw: null, value: null, inferred: true };
}

function dbNormalized(dbRow, field) {
  if (!dbRow) return { raw: null, value: null };
  switch (field) {
    case "cast_time_ms": return { raw: dbRow.cast_time_ms, value: isPresent(dbRow.cast_time_ms) ? dbRow.cast_time_ms : null };
    case "duration_ms": return { raw: dbRow.duration_ms, value: isPresent(dbRow.duration_ms) ? dbRow.duration_ms : null };
    case "range_yards": return { raw: dbRow.range_yards, value: isPresent(dbRow.range_yards) ? dbRow.range_yards : null };
    default: return { raw: null, value: null };
  }
}

export function fieldCandidates({ field, clientRec, builderNodes, dbRow, dbExcluded, dbExclusionReason = null }) {
  const out = [];
  if (clientRec) {
    const { raw, value, unknownBits, unknown } = clientNormalized(clientRec, field);
    const reasons = [];
    let eligible = value !== null && value !== undefined;
    if (eligible && !clientTablesHigh(clientRec, field)) { eligible = false; reasons.push(REASON.CLIENT_TABLE_DRIFT); }
    if (unknownBits && unknownBits.length) { eligible = false; reasons.push(REASON.UNKNOWN_MASK_BIT); }
    if (unknown) { eligible = false; reasons.push(REASON.UNKNOWN_ENUM); }
    out.push({
      source: "client_dbc", precedence_tier: "client_dbc", source_id: `client_spell:${clientRec.spell_id}`,
      source_field: CLIENT_SOURCE_FIELD[field] || field, raw_value: raw,
      normalized_value: eligible ? value : (value ?? null),
      confidence: clientRec?.coa_attribution?.confidence || "low", eligible, eligibility_reasons: reasons,
    });
  }
  for (const node of builderNodes || []) {
    const { raw, value } = builderNormalized(node, field);
    if (value === null) continue;
    out.push({
      source: "builder", precedence_tier: "inferred", source_id: `builder_node:${node.entry_id}`,
      source_field: field === "schools" ? "damage_schools" : "resources",
      raw_value: raw, normalized_value: value, confidence: "medium", eligible: true, eligibility_reasons: [],
    });
  }
  if (dbRow) {
    const { raw, value } = dbNormalized(dbRow, field);
    if (value !== null) {
      const reasons = dbExcluded ? [dbExclusionReason || REASON.DB_IDENTITY_MISMATCH] : [];
      out.push({
        source: "ascension_db", precedence_tier: "ascension_db", source_id: `ascension_db:${dbRow.id}`,
        source_field: field, raw_value: raw, normalized_value: value, confidence: "medium",
        eligible: !dbExcluded, eligibility_reasons: reasons,
      });
    }
  }
  return out;
}
```

**Note:** `dbNormalized` handles only db-provided fields — `cast_time_ms`, `duration_ms`, `range_yards`. The db-only fields `cooldown_ms`/`gcd_ms`/`costs` are NOT reconciled here (the client never carries them); Task 8 attaches them with their own single-source `field_provenance` so record-level provenance stays complete. Fields `schools`/`power_type` have no db candidate (db tooltips carry no structured mask/power enum), which is correct.

- [ ] **Step 4: Run to verify it passes**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: PASS for the two candidate tests.

- [ ] **Step 5: Commit**

```bash
git add coa_scraper/scripts/lib/mechanics-candidates.mjs coa_scraper/tests/pipeline-scripts.test.mjs
git commit -m "M1.14C Task 7: per-field candidate assembly with tables/tier/eligibility"
```

---

## Task 8: Node — reworked `buildMechanicsRows` (one row per spell_id, full record)

**Files:**
- Modify: `coa_scraper/scripts/build-mechanics-artifacts.mjs` (`buildMechanicsRows`, imports; remove `buildItemRows` in Task 11)
- Test: `coa_scraper/tests/pipeline-scripts.test.mjs`

**Interfaces:**
- Consumes: `reconcileField`, `dbIdentityReference`, `applyDbIdentityGate`, `fieldCandidates`.
- Produces: `buildMechanicsRows({ entries, spellRows, projection })` → one row per distinct `spell_id`, each carrying `schools`, `field_provenance`, aggregated `source_node_ids`, reconciled `name`/`kind`/mechanical fields, and `provenance[]`.

- [ ] **Step 1: Write the failing test**

Add to `pipeline-scripts.test.mjs`:

```js
test("buildMechanicsRows: one row per spell_id, client field wins, schools + field_provenance present", () => {
  const projection = [{
    spell_id: 92117, name: "Adrenal Venom",
    mechanics: { school_mask: 8, power_type: 3, cast_time_ms: 0, duration_ms: 12000, range_min_yd: 0, range_max_yd: 30, category: 0, spell_icon_id: 1 },
    provenance: { schema_match_confidence_by_dbc: { Spell: "high", SpellCastTimes: "high", SpellDuration: "high", SpellRange: "high" } },
    coa_attribution: { is_coa: true, confidence: "high" },
  }];
  const entryA = { spell_id: 92117, entry_id: 501, entry_type: "Ability", name: "Adrenal Venom", damage_schools: ["nature"], resources: ["energy"], tags: ["damage"] };
  const entryB = { spell_id: 92117, entry_id: 777, entry_type: "Talent", name: "Adrenal Venom", damage_schools: ["nature"], resources: ["energy"], tags: ["damage"] };
  const dbRow = { id: 92117, name: "Adrenal Venom", name_match: true, cast_time_ms: 2000, cooldown_ms: 30000, gcd_ms: 1500, tooltip_text: "Deals Nature damage." };
  const rows = buildMechanicsRows({ entries: [entryA, entryB], spellRows: [dbRow], projection });
  assert.equal(rows.length, 1);
  const r = rows[0];
  assert.equal(r.spell_id, 92117);
  assert.deepEqual(r.source_node_ids, [501, 777]);
  assert.equal(r.cast_time_ms, 0); // client 0 beats db 2000 (missing != zero)
  assert.deepEqual(r.schools, ["nature"]);
  assert.equal(r.cooldown_ms, 30000); // db-only field survives (identity matched)
  assert.equal(r.field_provenance.cast_time_ms.selected_source, "client_dbc");
  assert.equal(r.field_provenance.effects.selected_source, "inferred"); // effects field has provenance
  assert.deepEqual(r.raw.tags, ["damage"]); // builder tags carried under raw, not a top-level v1 field
  assert.equal(r.tags, undefined); // NOT a top-level field (would be dropped by the v1 loader)
  // the identity-matched db tooltip participated in classifying kind → recorded as a db candidate
  assert(r.field_provenance.kind.candidates.some((c) => c.source === "ascension_db" && c.source_field === "tooltip_text"));
});

test("buildMechanicsRows: identity-mismatched db row supplies zero fields", () => {
  const projection = [{
    spell_id: 5, name: "Adrenal Venom",
    mechanics: { school_mask: 8, power_type: 3, cast_time_ms: 1500, duration_ms: null, range_min_yd: null, range_max_yd: null, category: 0, spell_icon_id: 1 },
    provenance: { schema_match_confidence_by_dbc: { Spell: "high", SpellCastTimes: "high", SpellDuration: "high", SpellRange: "high" } },
    coa_attribution: { is_coa: true, confidence: "high" },
  }];
  const entry = { spell_id: 5, entry_id: 9, entry_type: "Ability", name: "Adrenal Venom", damage_schools: [], resources: [] };
  const staleDb = { id: 5, name: "Fang Venom: Lifeblood", name_match: false, cooldown_ms: 999, gcd_ms: 1500 };
  const rows = buildMechanicsRows({ entries: [entry], spellRows: [staleDb], projection });
  assert.equal(rows[0].cooldown_ms ?? null, null); // db excluded → no cooldown leaks
  // and the excluded db cooldown candidate is recorded as ineligible (audit retained)
  assert.equal(rows[0].field_provenance.cooldown_ms.candidates[0].eligible, false);
  // the excluded db row must not leak into kind classification either (no db tooltip candidate)
  assert(!rows[0].field_provenance.kind.candidates.some((c) => c.source === "ascension_db"));
  assert(!rows[0].provenance.some((p) => p.source === "ascension_db")); // nothing db survives
});

test("buildMechanicsRows: output is input-node-order-independent (canonicalized by entry_id)", () => {
  const projection = [{
    spell_id: 92117, name: "Adrenal Venom",
    mechanics: { school_mask: 8, power_type: 3, cast_time_ms: 0, duration_ms: 12000, range_min_yd: 0, range_max_yd: 30, category: 0, spell_icon_id: 1 },
    provenance: { schema_match_confidence_by_dbc: { Spell: "high", SpellCastTimes: "high", SpellDuration: "high", SpellRange: "high" } },
    coa_attribution: { is_coa: true, confidence: "high" },
  }];
  const a = { spell_id: 92117, entry_id: 501, entry_type: "Ability", name: "Adrenal Venom", damage_schools: ["nature"], resources: ["energy"], tags: ["damage"] };
  const b = { spell_id: 92117, entry_id: 777, entry_type: "Talent", name: "Adrenal Venom", damage_schools: ["nature"], resources: ["energy"], tags: ["dot"] };
  const forward = buildMechanicsRows({ entries: [a, b], spellRows: [], projection });
  const reversed = buildMechanicsRows({ entries: [b, a], spellRows: [], projection });
  assert.equal(JSON.stringify(forward), JSON.stringify(reversed));
  assert.deepEqual(forward[0].raw.tags, ["damage", "dot"]); // set-like union, sorted, under raw
});

test("buildMechanicsRows: db-derived cooldown always leaves a db provenance entry", () => {
  const projection = [{
    spell_id: 9, name: "X",
    mechanics: { school_mask: 8, power_type: 3, cast_time_ms: 0, duration_ms: null, range_min_yd: null, range_max_yd: null, category: 0, spell_icon_id: 1 },
    provenance: { schema_match_confidence_by_dbc: { Spell: "high", SpellCastTimes: "high", SpellDuration: "high", SpellRange: "high" } },
    coa_attribution: { is_coa: true, confidence: "high" },
  }];
  const entry = { spell_id: 9, entry_id: 1, entry_type: "Ability", name: "X", damage_schools: [], resources: [] };
  const dbRow = { id: 9, name: "X", name_match: true, cooldown_ms: 30000 };
  const rows = buildMechanicsRows({ entries: [entry], spellRows: [dbRow], projection });
  assert.equal(rows[0].cooldown_ms, 30000);
  assert(rows[0].provenance.some((p) => p.source === "ascension_db")); // union includes db
  assert.equal(rows[0].field_provenance.cooldown_ms.selected_source, "ascension_db");
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: FAIL (new signature / behavior not implemented).

- [ ] **Step 3: Rework `buildMechanicsRows`**

In `coa_scraper/scripts/build-mechanics-artifacts.mjs`, add imports at top:

```js
import { reconcileField, dbIdentityReference, applyDbIdentityGate, REASON } from "./lib/mechanics-reconcile.mjs";
import { fieldCandidates } from "./lib/mechanics-candidates.mjs";
import { isPresent } from "./lib/mechanics-normalize.mjs";
```

Replace the entire `buildMechanicsRows` function with the version below. Every emitted factual field
either passes through `reconcileField` (`name`, the five mechanical fields) or gets an equivalent
single-source `field_provenance` entry (`kind`, `cooldown_ms`, `gcd_ms`, `costs`), so record-level
`provenance` is the union of every actual contribution — a db-derived cooldown always leaves a db
provenance entry. Nodes are canonicalized by `entry_id` so output is input-order-independent, and
set-like fields (`tags`) are aggregated.

```js
const CLIENT_FIELDS = ["cast_time_ms", "duration_ms", "range_yards", "schools", "power_type"];
const DB_ONLY_FIELDS = ["cooldown_ms", "gcd_ms", "costs"];
const KIND_BEHAVIOR_ORDER = { pet_action: 0, cooldown: 1, ability: 2, debuff: 3, passive: 4 };

export function buildMechanicsRows({ entries, spellRows, projection = [] }) {
  const clientById = new Map(projection.map((r) => [Number(r.spell_id), r]));
  const dbById = new Map(spellRows.map((r) => [Number(r.id ?? r.spell_id), r]));

  const bySpell = new Map();
  for (const entry of entries) {
    const sid = Number(entry.spell_id);
    if (!Number.isFinite(sid)) continue;
    if (!bySpell.has(sid)) bySpell.set(sid, []);
    bySpell.get(sid).push(entry);
  }

  const rows = [];
  for (const [sid, rawNodes] of [...bySpell.entries()].sort((a, b) => a[0] - b[0])) {
    // Determinism: canonicalize nodes by entry_id so reversing input order is byte-identical.
    const nodes = [...rawNodes].sort((a, b) => Number(a.entry_id) - Number(b.entry_id));
    const clientRec = clientById.get(sid) || null;
    const dbRow = dbById.get(sid) || null;

    const clientName = clientRec?.name || "";
    const builderNames = nodes.map((n) => n.name).filter(Boolean);
    const referenceName = dbIdentityReference({ clientName, builderNames, dbName: dbRow?.name || "" });
    const gate = dbRow ? applyDbIdentityGate({ dbRow, referenceName }) : { excluded: false, reason: null };
    const dbUsable = Boolean(dbRow && !gate.excluded);

    const fieldProvenance = {};
    const selected = {};

    // name: client_dbc → verified_builder (consensus) → ascension_db (only if identity-usable)
    const nameOut = reconcileField({ field: "name", candidates: nameCandidates({ clientRec, nodes, dbRow, dbUsable }) });
    fieldProvenance.name = nameOut.provenance;
    const name = nameOut.selected ?? (clientName || builderNames[0] || dbRow?.name || "");

    // reconciled mechanical fields (client/builder/db)
    for (const field of CLIENT_FIELDS) {
      const candidates = fieldCandidates({ field, clientRec, builderNodes: nodes, dbRow, dbExcluded: gate.excluded, dbExclusionReason: gate.reason });
      if (candidates.length === 0) continue;
      const { selected: value, provenance } = reconcileField({ field, candidates });
      fieldProvenance[field] = provenance;
      if (value !== undefined) selected[field] = value;
    }

    // db-only fields: single-source field_provenance (barred when the db row failed identity)
    for (const field of DB_ONLY_FIELDS) {
      const fp = dbOnlyProvenance({ field, dbRow, dbUsable, gate });
      if (fp) fieldProvenance[field] = fp;
    }

    // Tooltip used to classify kind and infer effects. When the identity-matched db row supplies
    // the tooltip, that participation is recorded in provenance (not silently attributed to the
    // builder); otherwise fall back to the first builder description in entry_id order.
    const dbTooltip = dbUsable && dbRow.tooltip_text ? String(dbRow.tooltip_text) : "";
    const builderTooltip = nodes.map((n) => n.description_text).filter(Boolean)[0] || "";
    const tooltipText = dbTooltip || builderTooltip;
    const tooltipMeta = dbTooltip
      ? { text: dbTooltip, source: "ascension_db", tier: "ascension_db", source_id: `ascension_db:${dbRow.id}` }
      : { text: builderTooltip, source: "builder", tier: "verified_builder", source_id: `builder_node:${nodes[0]?.entry_id}` };

    // kind: derived from ALL nodes (order-independent) + the tooltip's real source
    const { kind, provenance: kindProv } = resolveKind(nodes, tooltipText, tooltipMeta);
    fieldProvenance.kind = kindProv;

    const schools = selected.schools || [];
    // Effects derive from a deterministic MERGED node view (tags unioned across all nodes, sorted)
    // plus the tooltip — never one arbitrary node — so output is input-order-independent.
    const mergedTags = [...new Set(nodes.flatMap((n) => n.tags || []))].sort();
    const mergedEntry = { tags: mergedTags, description_text: builderTooltip };
    const effects = inferEffects({ entry: mergedEntry, tooltipText, spellRow: dbUsable ? dbRow : null, schools, durationMs: selected.duration_ms ?? null });
    fieldProvenance.effects = effectsProvenance({ effects, tooltip: tooltipMeta });

    rows.push({
      schema_version: MECHANICS_SCHEMA_VERSION,
      spell_id: sid,
      name,
      kind,
      source_node_ids: [...new Set(nodes.map((n) => Number(n.entry_id)).filter(Number.isFinite))].sort((a, b) => a - b),
      source_urls: dbUsable ? sourceUrls(dbRow) : [],
      school: schools.length === 1 ? schools[0] : "",
      schools,
      power_type: selected.power_type || "",
      cast_time_ms: selected.cast_time_ms ?? null,
      duration_ms: selected.duration_ms ?? null,
      range_yards: selected.range_yards ?? null,
      cooldown_ms: dbUsable ? numberOrNull(dbRow.cooldown_ms) : null,
      gcd_ms: dbUsable ? numberOrNull(dbRow.gcd_ms) : null,
      costs: dbUsable ? costsObject(dbRow.power_costs) : {},
      generates: {},
      spends: {},
      effects,
      field_provenance: fieldProvenance,
      provenance: buildProvenance(fieldProvenance),
      confidence: recordConfidence(fieldProvenance),
      raw: {
        tags: mergedTags, // set-like builder tags; not a top-level coa-mechanics-v1 field, so carried in raw
        category: clientRec?.mechanics?.category ?? null,
        spell_icon_id: clientRec?.mechanics?.spell_icon_id ?? null,
        school_mask: clientRec?.mechanics?.school_mask ?? null,
        db_status: dbRow?.status || null,
        db_excluded: gate.excluded,
        db_exclusion_reason: gate.reason,
        linked_item_ids: dbUsable ? (dbRow.linked_item_ids || []) : [],
      },
    });
  }
  return rows;
}

function nameCandidates({ clientRec, nodes, dbRow, dbUsable }) {
  const out = [];
  if (clientRec?.name) out.push({ source: "client_dbc", precedence_tier: "client_dbc", source_id: `client_spell:${clientRec.spell_id}`, source_field: "name", raw_value: clientRec.name, normalized_value: clientRec.name, confidence: clientRec?.coa_attribution?.confidence || "low", eligible: true, eligibility_reasons: [] });
  for (const n of nodes) if (n.name) out.push({ source: "builder", precedence_tier: "verified_builder", source_id: `builder_node:${n.entry_id}`, source_field: "name", raw_value: n.name, normalized_value: n.name, confidence: "high", eligible: true, eligibility_reasons: [] });
  if (dbUsable && dbRow?.name) out.push({ source: "ascension_db", precedence_tier: "ascension_db", source_id: `ascension_db:${dbRow.id}`, source_field: "name", raw_value: dbRow.name, normalized_value: dbRow.name, confidence: "medium", eligible: true, eligibility_reasons: [] });
  return out;
}

function dbOnlyProvenance({ field, dbRow, dbUsable, gate }) {
  if (!dbRow) return null;
  const rawByField = { cooldown_ms: dbRow.cooldown_ms, gcd_ms: dbRow.gcd_ms, costs: dbRow.power_costs };
  const raw = rawByField[field];
  if (!isPresent(raw)) return null;
  const value = field === "costs" ? costsObject(raw) : numberOrNull(raw);
  const eligible = dbUsable;
  return {
    selected_source: eligible ? "ascension_db" : null,
    selected_tier: eligible ? "ascension_db" : null,
    selected_value: eligible ? value : null,
    selection_reason: eligible ? REASON.DB_FALLBACK : REASON.OMITTED_NO_ELIGIBLE_CANDIDATE,
    warnings: [],
    candidates: [{
      source: "ascension_db", precedence_tier: "ascension_db", source_id: `ascension_db:${dbRow.id}`,
      source_field: field, raw_value: raw, normalized_value: value, confidence: "medium",
      eligible, eligibility_reasons: eligible ? [] : [gate.reason || REASON.DB_IDENTITY_MISMATCH],
    }],
  };
}

// kind is classified from every node's entry_type AND the tooltip text (the tooltip can flip the
// classification). The tooltip candidate carries its REAL source, and is marked `contributed` when
// it is db-derived so the db's participation surfaces in record-level provenance.
function resolveKind(nodes, tooltipText, tooltip) {
  const perNode = nodes.map((n) => ({ node: n, kind: classifyMechanicKind(n, tooltipText) }));
  const distinct = [...new Set(perNode.map((x) => x.kind))];
  const chosen = distinct.slice().sort((a, b) => (KIND_BEHAVIOR_ORDER[a] ?? 9) - (KIND_BEHAVIOR_ORDER[b] ?? 9))[0];
  const candidates = perNode.map((x) => ({
    source: "builder", precedence_tier: "verified_builder", source_id: `builder_node:${x.node.entry_id}`,
    source_field: "entry_type", raw_value: x.node.entry_type, normalized_value: x.kind,
    confidence: "medium", eligible: true, eligibility_reasons: [], contributed: true,
  }));
  if (tooltip && tooltip.text) {
    candidates.push({
      source: tooltip.source, precedence_tier: tooltip.tier, source_id: tooltip.source_id,
      source_field: "tooltip_text", raw_value: null, normalized_value: chosen,
      confidence: "low", eligible: true, eligibility_reasons: [], contributed: tooltip.source === "ascension_db",
    });
  }
  return {
    kind: chosen,
    provenance: {
      selected_source: "builder", selected_tier: "verified_builder", selected_value: chosen,
      selection_reason: distinct.length > 1 ? REASON.KIND_NODE_DISAGREEMENT_RESOLVED : REASON.ONLY_CANDIDATE,
      warnings: distinct.length > 1 ? ["kind_node_disagreement"] : [],
      candidates,
    },
  };
}

// effects are heuristically inferred from the tooltip + merged builder tags. Provenance records the
// tooltip's real source (db participation marked `contributed`); when no effects were inferred the
// field contributes nothing.
function effectsProvenance({ effects, tooltip }) {
  const has = effects.length > 0;
  const candidates = [];
  if (has && tooltip && tooltip.text) {
    candidates.push({
      source: tooltip.source, precedence_tier: tooltip.tier, source_id: tooltip.source_id,
      source_field: "tooltip_text", raw_value: null, normalized_value: effects.length,
      confidence: "low", eligible: true, eligibility_reasons: [], contributed: tooltip.source === "ascension_db",
    });
  }
  return {
    selected_source: has ? "inferred" : null,
    selected_tier: has ? "inferred" : null,
    selected_value: effects.length,
    selection_reason: has ? REASON.INFERRED_FROM_TEXT : REASON.OMITTED_NO_ELIGIBLE_CANDIDATE,
    warnings: [], candidates,
  };
}

// Record-level provenance is the union of every field's selected source PLUS every candidate that
// actually shaped an emitted value (`contributed`) — so a db tooltip that informed kind/effects, or
// a db-fallback cooldown, always leaves a db provenance entry even when no db value was "selected".
function buildProvenance(fieldProvenance) {
  const used = new Set();
  for (const fp of Object.values(fieldProvenance)) {
    if (!fp) continue;
    if (fp.selected_source) used.add(fp.selected_source);
    for (const c of fp.candidates || []) if (c.contributed) used.add(c.source);
  }
  const conf = { client_dbc: "high", builder: "medium", ascension_db: "medium", inferred: "low" };
  const notes = { client_dbc: "client_dbc_mechanical", builder: "verified_builder_or_inferred", ascension_db: "db_fallback", inferred: "inferred" };
  const out = [];
  for (const src of ["client_dbc", "builder", "ascension_db", "inferred"]) {
    if (used.has(src)) out.push({ source: src, parser: "build-mechanics-artifacts", confidence: conf[src], notes: [notes[src]] });
  }
  if (out.length === 0) out.push({ source: "inferred", parser: "build-mechanics-artifacts", confidence: "low", notes: ["no_source"] });
  return out;
}

function recordConfidence(fp) {
  const src = (f) => fp[f]?.selected_source;
  const core = ["schools", "power_type"].every((f) => src(f) === "client_dbc");
  const timing = src("cast_time_ms") === "client_dbc" || src("duration_ms") === "client_dbc";
  if (core && timing) return "high";
  const anyClient = Object.values(fp).some((p) => p && p.selected_source === "client_dbc");
  return anyClient ? "medium" : "low";
}
```

Then update `inferEffects` to accept the reconciled `schools`/`durationMs` and emit `tick_interval_ms` (not `period_ms`). Change its signature and the returned effect objects: replace every `period_ms: periodMs` with `tick_interval_ms: periodMs`, replace `school` computed locally with the passed `schools` (scalar only when single), and use the passed `durationMs` when present. Concretely, change the `inferEffects` header to:

```js
function inferEffects({ entry, tooltipText, spellRow, schools = [], durationMs = null }) {
  const tags = entry?.tags || [];
  const school = schools.length === 1 ? schools[0] : (schools.length ? "" : inferSchool(tooltipText));
  const resolvedDuration = durationMs ?? numberOrNull(spellRow?.duration_ms) ?? inferDurationMs(tooltipText);
  const periodMs = numberOrNull(spellRow?.period_ms);
  const amount = inferAmount(tooltipText);
```

and in each returned effect object replace `duration_ms: durationMs` with `duration_ms: resolvedDuration` and `period_ms: periodMs` with `tick_interval_ms: periodMs`. Because the merged entry no longer carries `damage_schools`, also update the damage branch condition from `if (tags.includes("dot") || entry.damage_schools?.length || /\bdamage\b/i.test(tooltipText))` to `if (tags.includes("dot") || schools.length || /\bdamage\b/i.test(tooltipText))` so the reconciled schools drive the damage effect.

- [ ] **Step 4: Run to verify it passes**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: PASS for the four new `buildMechanicsRows` tests (client field wins + effects/kind provenance + raw.tags; identity-mismatched db supplies zero fields and leaks nothing; input-order independence; db cooldown always leaves a db provenance entry).

- [ ] **Step 5: Commit**

```bash
git add coa_scraper/scripts/build-mechanics-artifacts.mjs coa_scraper/tests/pipeline-scripts.test.mjs
git commit -m "M1.14C Task 8: per-field reconciled mechanics rows (one per spell_id, DB identity gate, tick_interval_ms)"
```

---

## Task 9: Node — projection load + validation + coverage accounting

**Files:**
- Create: `coa_scraper/scripts/lib/mechanics-projection.mjs`
- Test: `coa_scraper/tests/pipeline-scripts.test.mjs`

**Interfaces:**
- Produces: `loadAndValidateProjection({ projectionPath, manifestPath, builderSpellIds })` → `{ absent: false, projection, coverage, projection_sha256, manifest_sha256 }` on success, or `{ absent: true }` when **both** files are missing. Throws `MechanicsBuildError` on any malformed present projection (bad JSON, wrong schema, torn pair, type/enum/mask violations, confidence drift, sha/byte/count mismatch, or a Builder coverage gap).

- [ ] **Step 1: Write the failing test**

Add `import crypto from "node:crypto";` to the module-scope imports at the top of `pipeline-scripts.test.mjs` (ESM — never `require()`), plus:

```js
import { loadAndValidateProjection, MechanicsBuildError } from "../scripts/lib/mechanics-projection.mjs";

function writeProjectionFixture(dir, records) {
  const proj = path.join(dir, "p.jsonl");
  const man = path.join(dir, "p.manifest.json");
  const body = records.map((r) => JSON.stringify(r)).join("\n") + (records.length ? "\n" : "");
  fs.writeFileSync(proj, body);
  const sha = crypto.createHash("sha256").update(body).digest("hex");
  const uniq = new Set(records.map((r) => r.spell_id)).size;
  fs.writeFileSync(man, JSON.stringify({
    schema_version: "coa-client-spell-projection-v1",
    projection: { path: "p.jsonl", sha256: sha, byte_length: Buffer.byteLength(body) },
    counts: { projected_records: records.length, unique_spell_ids: uniq, source_records: records.length },
  }));
  return { proj, man };
}

function validProjRec(spell_id) {
  return {
    schema_version: "coa-client-spell-v1", spell_id, name: `S${spell_id}`,
    mechanics: { school_mask: 8, power_type: 3, cast_time_ms: 0, duration_ms: 12000, range_min_yd: 0, range_max_yd: 30, category: 0, spell_icon_id: 1 },
    provenance: { schema_match_confidence_by_dbc: { Spell: "high", SpellCastTimes: "high", SpellDuration: "high", SpellRange: "high" } },
    coa_attribution: { is_coa: true, confidence: "high" },
  };
}

test("loadAndValidateProjection: coverage gap fails", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "proj-"));
  const { proj, man } = writeProjectionFixture(dir, [validProjRec(1)]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1, 2]) }),
    /builder_missing_from_projection/,
  );
});

test("loadAndValidateProjection: torn pair (only one file) throws even though it looks 'absent'", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "torn-"));
  const { proj } = writeProjectionFixture(dir, [validProjRec(1)]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: path.join(dir, "missing.json"), builderSpellIds: new Set([1]) }),
    /torn projection pair/,
  );
});

test("loadAndValidateProjection: per-table drift on a populated field throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "drift-"));
  const rec = validProjRec(1);
  rec.provenance.schema_match_confidence_by_dbc.SpellCastTimes = "low"; // cast_time_ms is populated (0)
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /SpellCastTimes drift/,
  );
});

test("loadAndValidateProjection: both files absent returns { absent: true }", () => {
  const out = loadAndValidateProjection({ projectionPath: "/no/such.jsonl", manifestPath: "/no/such.json", builderSpellIds: new Set() });
  assert.equal(out.absent, true);
});

test("loadAndValidateProjection: non-numeric cast_time_ms throws (no string leaks to canonical)", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "badnum-"));
  const rec = validProjRec(1);
  rec.mechanics.cast_time_ms = "2000"; // string, not number
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /cast_time_ms must be number\|null/,
  );
});

test("loadAndValidateProjection: negative school_mask throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "negmask-"));
  const rec = validProjRec(1);
  rec.mechanics.school_mask = -8;
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /school_mask must be a non-negative integer/,
  );
});

test("loadAndValidateProjection: fractional school_mask throws (bitmask must be integer)", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fracmask-"));
  const rec = validProjRec(1);
  rec.mechanics.school_mask = 8.5;
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /school_mask must be integer\|null/,
  );
});

test("loadAndValidateProjection: unknown school-mask bit throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "badbit-"));
  const rec = validProjRec(1);
  rec.mechanics.school_mask = 1 << 20; // no such school
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /unknown school-mask bits/,
  );
});

test("loadAndValidateProjection: unknown power_type enum throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "badpwr-"));
  const rec = validProjRec(1);
  rec.mechanics.power_type = 99;
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /unknown power_type/,
  );
});

test("loadAndValidateProjection: confidence value outside {high,low} throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "badconf-"));
  const rec = validProjRec(1);
  rec.provenance.schema_match_confidence_by_dbc.SpellDuration = "medium";
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /must map .* to high\|low/,
  );
});

test("loadAndValidateProjection: low Spell confidence throws (name + every field unreliable)", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "spelldrift-"));
  const rec = validProjRec(1);
  rec.provenance.schema_match_confidence_by_dbc.Spell = "low";
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /Spell table drift/,
  );
});

test("loadAndValidateProjection: missing manifest.counts member throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "nocounts-"));
  const { proj, man } = writeProjectionFixture(dir, [validProjRec(1)]);
  const parsed = JSON.parse(fs.readFileSync(man, "utf8"));
  delete parsed.counts.unique_spell_ids;
  fs.writeFileSync(man, JSON.stringify(parsed));
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /manifest.counts must have integer/,
  );
});

test("loadAndValidateProjection: manifest byte_length disagreeing with the file throws", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "badlen-"));
  const { proj, man } = writeProjectionFixture(dir, [validProjRec(1)]);
  const parsed = JSON.parse(fs.readFileSync(man, "utf8"));
  parsed.projection.byte_length += 1; // still an integer, but wrong
  fs.writeFileSync(man, JSON.stringify(parsed));
  assert.throws(
    () => loadAndValidateProjection({ projectionPath: proj, manifestPath: man, builderSpellIds: new Set([1]) }),
    /byte_length mismatch/,
  );
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

Create `coa_scraper/scripts/lib/mechanics-projection.mjs`:

```js
import fs from "node:fs";
import crypto from "node:crypto";
import { normalizeSchoolMask, normalizePowerType, isPresent } from "./mechanics-normalize.mjs";

export class MechanicsBuildError extends Error {}

// Which client DBC tables each populated client mechanics field depends on (must all be "high").
const FIELD_TABLES = {
  cast_time_ms: ["Spell", "SpellCastTimes"],
  duration_ms: ["Spell", "SpellDuration"],
  range_max_yd: ["Spell", "SpellRange"],
  school_mask: ["Spell"],
  power_type: ["Spell"],
};

const NUMERIC_FIELDS = ["cast_time_ms", "duration_ms", "range_min_yd", "range_max_yd"];
const INT_FIELDS = ["school_mask", "power_type", "category", "spell_icon_id"];
const CONF = new Set(["high", "low"]);

function isNumOrNull(v) { return v === null || v === undefined || (typeof v === "number" && Number.isFinite(v)); }
function isIntOrNull(v) { return v === null || v === undefined || Number.isInteger(v); }

function parseJson(text, what) {
  try { return JSON.parse(text); }
  catch (e) { throw new MechanicsBuildError(`${what}: invalid JSON: ${e.message}`); }
}

// Throws on ANY malformed value that could reach a canonical artifact: wrong types, negative mask,
// bad confidence enum, unknown mask bit / power enum, or per-table drift on a populated field (Spell
// is foundational — name + every field depends on it). Runs BEFORE reconciliation.
function assertRecordSemantics(rec) {
  if (typeof rec.name !== "string") throw new MechanicsBuildError(`projection ${rec.spell_id}: name must be a string`);
  const m = rec.mechanics || {};
  for (const f of NUMERIC_FIELDS) if (!isNumOrNull(m[f])) throw new MechanicsBuildError(`projection ${rec.spell_id}: ${f} must be number|null`);
  for (const f of INT_FIELDS) if (!isIntOrNull(m[f])) throw new MechanicsBuildError(`projection ${rec.spell_id}: ${f} must be integer|null`);
  if (isPresent(m.school_mask) && (!Number.isInteger(m.school_mask) || m.school_mask < 0)) {
    throw new MechanicsBuildError(`projection ${rec.spell_id}: school_mask must be a non-negative integer`);
  }

  const byDbc = rec.provenance?.schema_match_confidence_by_dbc;
  const tables = ["Spell", "SpellCastTimes", "SpellDuration", "SpellRange"];
  if (!byDbc || tables.some((t) => !CONF.has(byDbc[t]))) {
    throw new MechanicsBuildError(`projection ${rec.spell_id}: schema_match_confidence_by_dbc must map ${tables} to high|low`);
  }
  if (byDbc.Spell !== "high") throw new MechanicsBuildError(`projection ${rec.spell_id}: Spell table drift (name + all fields unreliable)`);

  if (isPresent(m.school_mask) && m.school_mask > 0) {
    const { unknownBits } = normalizeSchoolMask(m.school_mask);
    if (unknownBits.length) throw new MechanicsBuildError(`projection ${rec.spell_id}: unknown school-mask bits ${unknownBits}`);
  }
  if (isPresent(m.power_type) && normalizePowerType(m.power_type).unknown) {
    throw new MechanicsBuildError(`projection ${rec.spell_id}: unknown power_type ${m.power_type}`);
  }
  for (const [field, needs] of Object.entries(FIELD_TABLES)) {
    if (!isPresent(m[field])) continue;
    const bad = needs.find((t) => byDbc[t] !== "high");
    if (bad) throw new MechanicsBuildError(`projection ${rec.spell_id}: table ${bad} drift on populated field ${field}`);
  }
}

export function loadAndValidateProjection({ projectionPath, manifestPath, builderSpellIds }) {
  const hasProj = fs.existsSync(projectionPath);
  const hasMan = fs.existsSync(manifestPath);
  if (!hasProj && !hasMan) return { absent: true };
  if (hasProj !== hasMan) {
    throw new MechanicsBuildError(`torn projection pair: projection=${hasProj} manifest=${hasMan} (need both, or neither for fallback)`);
  }

  const manifestBytes = fs.readFileSync(manifestPath);
  const manifest = parseJson(manifestBytes.toString("utf8"), "projection manifest");
  if (manifest.schema_version !== "coa-client-spell-projection-v1") {
    throw new MechanicsBuildError(`projection manifest bad schema_version: ${manifest.schema_version}`);
  }
  const p = manifest.projection;
  if (!p || typeof p.path !== "string" || typeof p.sha256 !== "string" || !p.sha256 || !Number.isInteger(p.byte_length)) {
    throw new MechanicsBuildError("projection manifest.projection must have {path:string, sha256:string, byte_length:int}");
  }
  const c = manifest.counts;
  if (!c || !Number.isInteger(c.projected_records) || !Number.isInteger(c.unique_spell_ids) || !Number.isInteger(c.source_records)) {
    throw new MechanicsBuildError("projection manifest.counts must have integer {projected_records, unique_spell_ids, source_records}");
  }

  const bytes = fs.readFileSync(projectionPath);
  const sha = crypto.createHash("sha256").update(bytes).digest("hex");
  if (p.sha256 !== sha) throw new MechanicsBuildError(`projection sha256 mismatch: ${projectionPath}`);
  if (p.byte_length !== bytes.length) throw new MechanicsBuildError(`projection byte_length mismatch: manifest ${p.byte_length} != actual ${bytes.length}`);

  const projection = [];
  const seen = new Set();
  let lineNo = 0;
  for (const line of bytes.toString("utf8").split("\n")) {
    lineNo += 1;
    if (!line.trim()) continue;
    const rec = parseJson(line, `projection line ${lineNo}`);
    if (rec.schema_version !== "coa-client-spell-v1") throw new MechanicsBuildError(`projection row bad schema_version: ${rec.schema_version}`);
    if (rec.coa_attribution?.is_coa !== true) throw new MechanicsBuildError(`projection row not is_coa: ${rec.spell_id}`);
    if (!Number.isInteger(rec.spell_id) || rec.spell_id <= 0) throw new MechanicsBuildError(`projection non-positive-integer spell_id: ${rec.spell_id}`);
    if (seen.has(rec.spell_id)) throw new MechanicsBuildError(`projection duplicate spell_id: ${rec.spell_id}`);
    assertRecordSemantics(rec);
    seen.add(rec.spell_id);
    projection.push(rec);
  }
  if (c.projected_records !== projection.length) throw new MechanicsBuildError(`projection count mismatch: manifest ${c.projected_records} != actual ${projection.length}`);
  if (c.unique_spell_ids !== seen.size) throw new MechanicsBuildError(`projection unique_spell_ids mismatch: manifest ${c.unique_spell_ids} != actual ${seen.size}`);

  const joined = [...builderSpellIds].filter((s) => seen.has(s));
  const missing = [...builderSpellIds].filter((s) => !seen.has(s));
  if (missing.length > 0) {
    throw new MechanicsBuildError(`builder_missing_from_projection: ${missing.length} spell(s), e.g. ${missing.slice(0, 5)}`);
  }
  const coverage = {
    builder_joined_to_projection: joined.length,
    builder_missing_from_projection: missing.length,
    projection_only: [...seen].filter((s) => !builderSpellIds.has(s)).length,
  };
  return {
    absent: false, projection, coverage, projection_sha256: sha,
    manifest_sha256: crypto.createHash("sha256").update(manifestBytes).digest("hex"),
  };
}
```

- [ ] **Step 4: Run to verify it passes**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: PASS for all projection tests — the four structural ones (coverage gap, torn pair, per-table drift, both-absent) plus the malformed-value guards (non-numeric field, negative/fractional/unknown mask, unknown power_type, bad confidence enum, low Spell confidence, missing counts member, byte_length mismatch).

- [ ] **Step 5: Commit**

```bash
git add coa_scraper/scripts/lib/mechanics-projection.mjs coa_scraper/tests/pipeline-scripts.test.mjs
git commit -m "M1.14C Task 9: projection load/validation + coverage accounting (fail-closed on torn pair/drift/gap)"
```

---

## Task 10: Node — CLI entrypoint: canonical/fallback modes, manifest, atomic writes

**Files:**
- Modify: `coa_scraper/scripts/build-mechanics-artifacts.mjs` (CLI block at the bottom; add manifest + atomic helpers)
- Test: `coa_scraper/tests/pipeline-scripts.test.mjs`

**Interfaces:**
- Consumes: `loadAndValidateProjection`, `buildMechanicsRows`.
- Produces: `buildMechanicsArtifact({ entries, spellRows, projectionPath, manifestPath, outDir, allowFallback, inputs })` → `{ canonical, manifest }`; writes JSONL + manifest atomically (creates `outDir`). A fallback build writes only `coa_mechanics.fallback.*` and never the canonical filename.

- [ ] **Step 1: Write the failing test**

Add to `pipeline-scripts.test.mjs`:

```js
import { buildMechanicsArtifact } from "../scripts/build-mechanics-artifacts.mjs";

test("buildMechanicsArtifact: absent projection without flag fails closed (writes nothing)", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mech-"));
  assert.throws(() => buildMechanicsArtifact({
    entries: [{ spell_id: 1, entry_id: 1, entry_type: "Ability", name: "X" }],
    spellRows: [], projectionPath: "/no.jsonl", manifestPath: "/no.json", outDir: dir, allowFallback: false,
  }), /projection/i);
  assert.equal(fs.existsSync(path.join(dir, "coa_mechanics.jsonl")), false);
});

test("buildMechanicsArtifact: absent projection + fallback writes degraded, canonical:false", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mech-"));
  const out = buildMechanicsArtifact({
    entries: [{ spell_id: 1, entry_id: 1, entry_type: "Ability", name: "X", damage_schools: [], resources: [] }],
    spellRows: [], projectionPath: "/no.jsonl", manifestPath: "/no.json", outDir: dir, allowFallback: true,
  });
  assert.equal(out.canonical, false);
  assert.equal(fs.existsSync(path.join(dir, "coa_mechanics.fallback.jsonl")), true);
  const man = JSON.parse(fs.readFileSync(path.join(dir, "coa_mechanics.fallback.manifest.json"), "utf8"));
  assert.equal(man.canonical, false);
  assert.equal(man.client_source, "absent");
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: FAIL — `buildMechanicsArtifact` not exported.

- [ ] **Step 3: Implement the entrypoint + manifest + atomic write**

Add to `coa_scraper/scripts/build-mechanics-artifacts.mjs`:

```js
import { loadAndValidateProjection, MechanicsBuildError } from "./lib/mechanics-projection.mjs";
import crypto from "node:crypto";

function atomicWrite(targetPath, data) {
  const tmp = `${targetPath}.tmp-${process.pid}-${Date.now()}`;
  fs.writeFileSync(tmp, data);
  fs.renameSync(tmp, targetPath);
}

function jsonlBytes(rows) {
  return rows.map((r) => JSON.stringify(r)).join("\n") + (rows.length ? "\n" : "");
}

function winnerCounts(rows) {
  const bySource = {}; const byTier = {};
  for (const r of rows) {
    for (const [f, fp] of Object.entries(r.field_provenance || {})) {
      if (!fp.selected_source) continue;
      bySource[f] = bySource[f] || {}; byTier[f] = byTier[f] || {};
      bySource[f][fp.selected_source] = (bySource[f][fp.selected_source] || 0) + 1;
      byTier[f][fp.selected_tier] = (byTier[f][fp.selected_tier] || 0) + 1;
    }
  }
  return { bySource, byTier };
}

export function buildMechanicsArtifact({ entries, spellRows, projectionPath, manifestPath, outDir, allowFallback = false, inputs = {} }) {
  const builderSpellIds = new Set(entries.map((e) => Number(e.spell_id)).filter(Number.isFinite));
  const loaded = loadAndValidateProjection({ projectionPath, manifestPath, builderSpellIds });

  if (loaded.absent) {
    if (!allowFallback) throw new MechanicsBuildError("projection absent; refusing canonical build (pass --allow-fallback-mechanics for a degraded build)");
    const rows = buildMechanicsRows({ entries, spellRows, projection: [] });
    // A degraded build writes ONLY the coa_mechanics.fallback.* files. It NEVER writes the canonical
    // filename — MechanicsRepository reads the JSONL directly and would ingest degraded bytes as
    // canonical regardless of a canonical:false marker. There is no override.
    return writeArtifact({ rows, outDir, canonical: false, clientSource: "absent", fallbackAuthorized: true, loaded, inputs, base: "coa_mechanics.fallback" });
  }

  const rows = buildMechanicsRows({ entries, spellRows, projection: loaded.projection });
  return writeArtifact({ rows, outDir, canonical: true, clientSource: "present", fallbackAuthorized: false, loaded, inputs, base: "coa_mechanics" });
}

function writeArtifact({ rows, outDir, canonical, clientSource, fallbackAuthorized, loaded, inputs, base }) {
  fs.mkdirSync(outDir, { recursive: true }); // outDir may not exist yet (e.g. a fresh temp dir)
  const jsonlName = `${base}.jsonl`;
  const manifestName = `${base}.manifest.json`;
  const jsonlPath = path.join(outDir, jsonlName);
  const manifestPath = path.join(outDir, manifestName);

  const body = jsonlBytes(rows);
  const sha = crypto.createHash("sha256").update(body).digest("hex");
  const { bySource, byTier } = winnerCounts(rows);
  const manifest = {
    schema_version: "coa-mechanics-manifest-v1",
    generated_at: new Date().toISOString(),
    canonical, client_source: clientSource, fallback_authorized: fallbackAuthorized,
    reconciliation_policy_version: "m1.14c-1",
    inputs: {
      builder_entries: inputs.builder_entries || null,
      db_spell_tooltips: inputs.db_spell_tooltips || null,
      projection: loaded.absent ? { path: null, sha256: null } : { path: inputs.projection_path || null, sha256: loaded.projection_sha256 },
      projection_manifest: loaded.absent ? { path: null, sha256: null } : { path: inputs.projection_manifest_path || null, sha256: loaded.manifest_sha256 },
    },
    outputs: { mechanics_jsonl: jsonlName, sha256: sha, record_count: rows.length },
    coverage: loaded.absent ? null : loaded.coverage,
    per_field_winner_counts_by_source: bySource,
    per_field_winner_counts_by_tier: byTier,
  };

  // manifest-as-validity-marker: remove previous manifest first, then JSONL, then manifest — each atomic.
  if (fs.existsSync(manifestPath)) fs.rmSync(manifestPath);
  atomicWrite(jsonlPath, body);
  atomicWrite(manifestPath, JSON.stringify(manifest, null, 2) + "\n");
  return { canonical, manifest };
}
```

- [ ] **Step 4: Run to verify it passes**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: PASS for the two artifact tests.

- [ ] **Step 5: Commit**

```bash
git add coa_scraper/scripts/build-mechanics-artifacts.mjs coa_scraper/tests/pipeline-scripts.test.mjs
git commit -m "M1.14C Task 10: canonical/fallback build, mechanics manifest, atomic writes"
```

---

## Task 11: Node — split item generation + CLI + npm scripts + artifact manifest

**Files:**
- Create: `coa_scraper/scripts/build-item-artifacts.mjs` (move `buildItemRows` + item CLI)
- Modify: `coa_scraper/scripts/build-mechanics-artifacts.mjs` (remove item building from its CLI; wire new flags/inputs)
- Modify: `coa_scraper/package.json` (scripts)
- Modify: `coa_scraper/scripts/write-artifact-manifest.mjs` (add split item script + mechanics manifests)
- Test: `coa_scraper/tests/pipeline-scripts.test.mjs`

**Interfaces:**
- Produces: `build-items` npm script → `coa_items.jsonl`; `build-mechanics` (canonical) / `build-mechanics:fallback` npm scripts.

- [ ] **Step 1: Move `buildItemRows` verbatim into a new file**

Create `coa_scraper/scripts/build-item-artifacts.mjs`. Move `buildItemRows` and its item-only helpers (`inferItemSlot`, `inferItemClass`, `inferWeaponType`, `inferArmorType`, `statsObject`, `ITEM_SCHEMA_VERSION`, `sourceUrls`, `numberOrNull`) into it (copy the functions verbatim from `build-mechanics-artifacts.mjs`; keep shared helpers in both files or import from a shared `lib`). Add a CLI entrypoint mirroring the old item path:

```js
#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readJsonl, writeJsonl } from "./lib/ascensiondb.mjs";

const ITEM_SCHEMA_VERSION = "coa-item-v1";
// ... buildItemRows + item helpers moved here ...

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const itemRowsPath = process.argv[2] || "dist/coa_db_item_tooltips.jsonl";
  const distDir = process.argv[3] || "dist";
  const itemPayloadRows = readJsonl(itemRowsPath);
  const itemRows = buildItemRows({ itemPayloadRows });
  fs.mkdirSync(distDir, { recursive: true });
  writeJsonl(path.join(distDir, "coa_items.jsonl"), itemRows);
  console.log(`Wrote ${itemRows.length} items`);
}
```

- [ ] **Step 2: Replace the CLI block of `build-mechanics-artifacts.mjs`**

Remove `buildItemRows`/item helpers and the item write from the CLI at the bottom of `build-mechanics-artifacts.mjs`. Replace the `isCliEntryPoint()` block with a flag-parsing entrypoint:

```js
if (isCliEntryPoint()) {
  const args = process.argv.slice(2);
  const flag = (name, def) => {
    const i = args.indexOf(name);
    return i >= 0 && args[i + 1] ? args[i + 1] : def;
  };
  const has = (name) => args.includes(name);
  const entriesPath = flag("--builder-entries", "dist/coa_entries.jsonl");
  const dbPath = flag("--db-spells", "dist/coa_db_spell_tooltips.jsonl");
  // npm runs scripts from coa_scraper/, but the extractor writes the projection to the REPO-ROOT
  // reports/client_extract/ — so the default (and the npm scripts) reach it via ../reports/...
  const projectionPath = flag("--projection", "../reports/client_extract/coa_client_spell_coa.jsonl");
  const projManifestPath = flag("--projection-manifest", "../reports/client_extract/coa_client_spell_projection.manifest.json");
  const outDir = flag("--out", "dist");
  if (!fs.existsSync(entriesPath)) { console.error(`required builder entries missing: ${entriesPath}`); process.exit(2); }
  const entries = readJsonl(entriesPath);
  const spellRows = fs.existsSync(dbPath) ? readJsonl(dbPath) : [];
  try {
    const { canonical, manifest } = buildMechanicsArtifact({
      entries, spellRows, projectionPath, manifestPath: projManifestPath, outDir,
      allowFallback: has("--allow-fallback-mechanics"),
      inputs: {
        builder_entries: { path: entriesPath, sha256: sha256File(entriesPath) },
        db_spell_tooltips: fs.existsSync(dbPath) ? { path: dbPath, sha256: sha256File(dbPath) } : null,
        projection_path: projectionPath, projection_manifest_path: projManifestPath,
      },
    });
    console.log(JSON.stringify({ canonical, record_count: manifest.outputs.record_count, coverage: manifest.coverage }, null, 2));
  } catch (err) {
    console.error(`error: ${err.message}`);
    process.exit(2);
  }
}
```

Add a `sha256File` helper near `atomicWrite`:

```js
function sha256File(p) { return crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex"); }
```

- [ ] **Step 3: Update `package.json` scripts**

In `coa_scraper/package.json`, replace the `build-mechanics` script and add siblings:

```json
    "build-items": "node scripts/build-item-artifacts.mjs dist/coa_db_item_tooltips.jsonl dist",
    "build-mechanics": "node scripts/build-mechanics-artifacts.mjs --builder-entries dist/coa_entries.jsonl --db-spells dist/coa_db_spell_tooltips.jsonl --projection ../reports/client_extract/coa_client_spell_coa.jsonl --projection-manifest ../reports/client_extract/coa_client_spell_projection.manifest.json --out dist",
    "build-mechanics:fallback": "npm run build-mechanics -- --allow-fallback-mechanics",
```

Update `pipeline:m1.9` to call the split item build + canonical mechanics, and add a fallback pipeline:

```json
    "pipeline:m1.9": "npm run pipeline:m1.8 && npm run enrich-items && npm run build-items && npm run build-mechanics && node scripts/write-artifact-manifest.mjs reports dist reports/coa_artifact_manifest.json",
    "pipeline:m1.9:fallback": "npm run pipeline:m1.8 && npm run enrich-items && npm run build-items && npm run build-mechanics:fallback && node scripts/write-artifact-manifest.mjs reports dist reports/coa_artifact_manifest.json",
```

- [ ] **Step 4: Update the artifact manifest writer**

In `coa_scraper/scripts/write-artifact-manifest.mjs`, add `scripts/build-item-artifacts.mjs` to the list of tracked scripts and add `dist/coa_mechanics.manifest.json` / `dist/coa_mechanics.fallback.manifest.json` to the tracked artifacts (mirror the existing entries). Update the existing test assertion at `pipeline-scripts.test.mjs:405` if it enumerates script paths.

- [ ] **Step 5: Run tests**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: PASS (item test now imports from `build-item-artifacts.mjs`; update its import line to `import { buildItemRows } from "../scripts/build-item-artifacts.mjs";` and remove `buildItemRows` from the mechanics import).

- [ ] **Step 6: Commit**

```bash
git add coa_scraper/scripts/build-item-artifacts.mjs coa_scraper/scripts/build-mechanics-artifacts.mjs coa_scraper/package.json coa_scraper/scripts/write-artifact-manifest.mjs coa_scraper/tests/pipeline-scripts.test.mjs
git commit -m "M1.14C Task 11: split item generation; canonical/fallback npm scripts; artifact-manifest wiring"
```

---

## Task 12: Node — fix the ossifying `period_ms` test

**Files:**
- Modify: `coa_scraper/tests/pipeline-scripts.test.mjs:637` (and the fixture around line 606 if needed)

**Interfaces:** none new.

- [ ] **Step 1: Update the existing mechanics test to the new signature and canonical field**

The existing `buildMechanicsRows({ entries, spellRows })` call (no `projection`) must still work (projection defaults to `[]`, so db+builder reconciliation applies). Update the assertions in the existing test block: the record is now built by reconciliation, so `cast_time_ms`/`range_yards`/`cooldown_ms`/`gcd_ms` still come from the (identity-matched) db row, and effect timing is now `tick_interval_ms`. Change:

```js
  assert.equal(mechanicsRows[0].effects[0].period_ms, 3000);
```

to:

```js
  assert.equal(mechanicsRows[0].effects[0].tick_interval_ms, 3000);
```

Ensure the fixture `spellRow` has `name: "..."` matching the entry name (so the DB identity gate does not exclude it); if the fixture entry name and db name differ, set the db `name` equal to the entry `name` (identity match) so its db-only fields remain eligible.

- [ ] **Step 2: Run the test**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: PASS — the corrected assertion and the whole file are green.

- [ ] **Step 3: Commit**

```bash
git add coa_scraper/tests/pipeline-scripts.test.mjs
git commit -m "M1.14C Task 12: correct ossifying effects.period_ms assertion to tick_interval_ms"
```

---

## Task 13: Docs — schemas, gitignore, regeneration

**Files:**
- Modify: `docs/data/mechanics-schema.md`
- Modify: `docs/data/client-spell-schema.md`
- Modify: `.gitignore`
- Create: `coa_scraper/scripts/README-regeneration.md`

**Interfaces:** none.

- [ ] **Step 1: Document the mechanics additions**

In `docs/data/mechanics-schema.md`, add sections for: the additive `schools` list (authoritative; `school` is a single-school convenience omitted when multi-bit); the `field_provenance` object (per-field `selected_source`/`selected_tier`/`selection_reason` + `candidates[]` with source identity, `precedence_tier`, `eligible`, `eligibility_reasons`); the `coa-mechanics-manifest-v1` (canonical/degraded, input hashes, coverage, `per_field_winner_counts_by_source`/`_by_tier`); and the record-level `confidence` aggregate rule.

- [ ] **Step 2: Document the projection + per-table confidence**

In `docs/data/client-spell-schema.md`, add: `provenance.schema_match_confidence_by_dbc`; the `coa-client-spell-projection-v1` projection + manifest (scope `is_coa`, fields); the `SCHOOL_MASK_BITS`/`POWER_TYPE_MAP` enum maps (copied from `mechanics-normalize.mjs`) and the `-1` infinite-duration sentinel; and a note that undocumented mask bits / enum values fail a canonical build.

- [ ] **Step 3: Add file-specific ignore rules**

Append to `.gitignore`:

```
# M1.14C client-derived factual outputs — regenerate from your own client (never committed)
reports/client_extract/coa_client_spell.jsonl
reports/client_extract/coa_client_spell_coa.jsonl
reports/client_extract/coa_client_spell_projection.manifest.json
coa_scraper/dist/coa_mechanics.jsonl
coa_scraper/dist/coa_mechanics.manifest.json
coa_scraper/dist/coa_mechanics.fallback.jsonl
coa_scraper/dist/coa_mechanics.fallback.manifest.json
```

(Do NOT add a blanket `reports/client_extract/` rule — `coa_ca_decode_report.json` and `client_only_adjudication.json` stay tracked.)

- [ ] **Step 4: Write regeneration docs**

Create `coa_scraper/scripts/README-regeneration.md` documenting: how to regenerate the projection (`python -m coa_client_extract regenerate ...`), the canonical vs fallback mechanics commands, and the explicit statement: *a fresh clone can reproduce the tests and the fallback mechanics, but cannot reproduce the canonical `coa_mechanics.jsonl` without the user's own client.* Include the forward redistribution-policy-gate note (mandatory before M1.16 / public release, covering all client-derived outputs).

- [ ] **Step 5: Verify no tracked artifacts are about to be committed**

Run: `git status --porcelain | grep -E 'coa_mechanics|coa_client_spell_coa|projection.manifest' || echo "clean"`
Expected: `clean` (the ignore rules keep them out).

- [ ] **Step 6: Commit**

```bash
git add docs/data/mechanics-schema.md docs/data/client-spell-schema.md .gitignore coa_scraper/scripts/README-regeneration.md
git commit -m "M1.14C Task 13: schema docs, file-specific ignore rules, regeneration + policy-gate docs"
```

---

## Task 14: Python — integration exit test (load through MechanicsRepository + round-trip)

**Files:**
- Modify: `tests/test_mechanics_field_provenance.py` (add integration test)
- Test fixture: reuse `mechanic_from_raw` round-trip

**Interfaces:**
- Consumes: `MechanicsRepository`, `mechanic_from_raw`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mechanics_field_provenance.py`:

```python
import json
from coa_meta.mechanics_repository import MechanicsRepository


def test_repository_loads_and_round_trips_field_provenance_and_schools(tmp_path):
    row = {
        "schema_version": "coa-mechanics-v1", "spell_id": 805775, "name": "Adrenal Venom",
        "kind": "ability", "schools": ["fire", "frost"],
        "field_provenance": {"schools": {"selected_source": "client_dbc", "selected_tier": "client_dbc",
                                         "selected_value": ["fire", "frost"], "selection_reason": "highest_precedence_eligible",
                                         "warnings": [], "candidates": []}},
        "effects": [{"effect_type": "damage", "tick_interval_ms": 3000}],
    }
    p = tmp_path / "coa_mechanics.jsonl"
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    repo = MechanicsRepository.from_jsonl(p)
    rec = repo.get_spell_id(805775)
    assert rec is not None
    assert rec.schools == ("fire", "frost")
    out = rec.to_dict()
    assert out["schools"] == ["fire", "frost"]
    assert out["field_provenance"]["schools"]["selected_tier"] == "client_dbc"
    assert out["effects"][0]["tick_interval_ms"] == 3000
```

- [ ] **Step 2: Run to verify it passes**

Run: `pytest tests/test_mechanics_field_provenance.py -v`
Expected: PASS (Task 4 already added the round-trip; this proves it through the real repository loader).

- [ ] **Step 3: Commit**

```bash
git add tests/test_mechanics_field_provenance.py
git commit -m "M1.14C Task 14: MechanicsRepository integration exit test (schools + field_provenance round-trip)"
```

---

## Task 15: Acceptance — default-tier build guarantees + client-tier `805775`

**Files:**
- Modify: `coa_scraper/tests/pipeline-scripts.test.mjs` (default-tier build guarantees)
- Modify: `tests/test_client_extract_acceptance.py` (client-tier, automated build into a temp dir)

**Interfaces:** none new.

- [ ] **Step 1: Default-tier build guarantees (deterministic, no client)**

Add to `pipeline-scripts.test.mjs`:

```js
test("acceptance: manifest binds the EXACT generated projection sha; canonical true", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "acc-"));
  const { proj, man } = writeProjectionFixture(dir, [validProjRec(42)]);
  const projSha = crypto.createHash("sha256").update(fs.readFileSync(proj)).digest("hex");
  const out = buildMechanicsArtifact({
    entries: [{ spell_id: 42, entry_id: 1, entry_type: "Ability", name: "S42", damage_schools: [], resources: [] }],
    spellRows: [], projectionPath: proj, manifestPath: man, outDir: dir, allowFallback: false,
    inputs: { projection_path: proj, projection_manifest_path: man },
  });
  assert.equal(out.canonical, true);
  assert.equal(out.manifest.inputs.projection.sha256, projSha);
  assert.equal(out.manifest.coverage.builder_missing_from_projection, 0);
});

test("acceptance: fallback does NOT modify a pre-existing canonical artifact", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "acc2-"));
  const canonical = path.join(dir, "coa_mechanics.jsonl");
  fs.writeFileSync(canonical, "SENTINEL-CANONICAL\n");
  buildMechanicsArtifact({
    entries: [{ spell_id: 1, entry_id: 1, entry_type: "Ability", name: "X", damage_schools: [], resources: [] }],
    spellRows: [], projectionPath: "/no.jsonl", manifestPath: "/no.json", outDir: dir, allowFallback: true,
  });
  assert.equal(fs.readFileSync(canonical, "utf8"), "SENTINEL-CANONICAL\n"); // untouched
  assert.equal(fs.existsSync(path.join(dir, "coa_mechanics.fallback.jsonl")), true);
});

test("acceptance: identity-mismatched db supplies zero fields AND zero db-derived effects end-to-end", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "acc3-"));
  // No client school and no builder tooltip → the ONLY thing that could produce an effect is the
  // db's "summon a pet" tooltip. Since the db row fails identity, it must be excluded → zero effects.
  const rec = validProjRec(7);
  rec.mechanics.school_mask = 0;
  rec.mechanics.duration_ms = null;
  rec.mechanics.range_min_yd = null;
  rec.mechanics.range_max_yd = null;
  const { proj, man } = writeProjectionFixture(dir, [rec]);
  buildMechanicsArtifact({
    entries: [{ spell_id: 7, entry_id: 1, entry_type: "Ability", name: "S7", damage_schools: [], resources: [] }],
    spellRows: [{ id: 7, name: "Totally Different", name_match: false, cooldown_ms: 999, gcd_ms: 1500, tooltip_text: "summon a pet" }],
    projectionPath: proj, manifestPath: man, outDir: dir, allowFallback: false,
  });
  const row = JSON.parse(fs.readFileSync(path.join(dir, "coa_mechanics.jsonl"), "utf8").trim());
  assert.equal(row.cooldown_ms ?? null, null);
  assert.equal(row.gcd_ms ?? null, null);
  assert.equal(row.raw.db_excluded, true);
  assert(!row.provenance.some((p) => p.source === "ascension_db")); // no db provenance leaked
  assert.equal(row.effects.length, 0); // the excluded db "summon a pet" tooltip yields NO effect
});
```

- [ ] **Step 2: Run the default-tier acceptance tests**

Run (from `coa_scraper/`): `node --test tests/pipeline-scripts.test.mjs`
Expected: PASS (three acceptance tests).

- [ ] **Step 3: Client-tier automated test (real `805775`, temp-dir build, no permissive skip)**

Append to `tests/test_client_extract_acceptance.py`. The fixture builds into a temp dir; it **skips only** when `COA_CLIENT_ROOT` is unset (the standard client-tier gate) — never a permissive "manual" skip — and the assertions are non-vacuous against the *observed* db name:

```python
import json, os, re, subprocess, sys
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[1]
DB = REPO / "coa_scraper/dist/coa_db_spell_tooltips.jsonl"


@pytest.fixture
def client_mechanics_dir(tmp_path):
    root = os.environ.get("COA_CLIENT_ROOT")
    if not root:
        pytest.skip("COA_CLIENT_ROOT unset (client tier)")
    ce = tmp_path / "client_extract"
    dist = tmp_path / "dist"
    subprocess.run([sys.executable, "-m", "coa_client_extract", "regenerate",
                    "--client-root", root, "--out", str(ce),
                    "--builder-entries", str(REPO / "coa_scraper/dist/coa_entries.jsonl")],
                   cwd=REPO, check=True)
    subprocess.run(["node", "coa_scraper/scripts/build-mechanics-artifacts.mjs",
                    "--builder-entries", "coa_scraper/dist/coa_entries.jsonl",
                    "--db-spells", "coa_scraper/dist/coa_db_spell_tooltips.jsonl",
                    "--projection", str(ce / "coa_client_spell_coa.jsonl"),
                    "--projection-manifest", str(ce / "coa_client_spell_projection.manifest.json"),
                    "--out", str(dist)], cwd=REPO, check=True)
    return dist


@pytest.mark.client
def test_805775_client_wins_and_db_gate_matches_observed(client_mechanics_dir):
    mech = client_mechanics_dir / "coa_mechanics.jsonl"
    row = next((json.loads(l) for l in mech.read_text().splitlines()
                if l.strip() and json.loads(l).get("spell_id") == 805775), None)
    assert row is not None, "805775 must be in the Builder-domain mechanics output"
    assert row["name"] == "Adrenal Venom"                      # client name wins
    fp = row["field_provenance"]
    assert any(fp.get(f, {}).get("selected_source") == "client_dbc"
               for f in ("power_type", "cast_time_ms", "duration_ms", "range_yards"))  # a client field wins
    # non-vacuous gate check vs the OBSERVED db name for 805775 — the db row MUST exist so the gate
    # is actually exercised (a missing row would make either branch vacuously true).
    db = next((json.loads(l) for l in DB.read_text().splitlines()
               if l.strip() and json.loads(l).get("id") == 805775), None)
    assert db is not None, "805775 must be present in coa_db_spell_tooltips.jsonl to exercise the identity gate"

    # EXACT port of Node's normalizeName (lib/ascensiondb.mjs): lowercase, non-alphanumeric runs → single
    # space, trim. Must match byte-for-byte or the test could assert the wrong gate branch.
    def norm(s): return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
    if norm(db.get("name")) != norm("Adrenal Venom"):
        # stale db → excluded → zero db contribution
        assert row["cooldown_ms"] is None and row["gcd_ms"] is None
        assert not any(p["source"] == "ascension_db" for p in row["provenance"])
        assert row["raw"]["db_excluded"] is True
    else:
        # db agrees → usable fallback (gate correctly vacuous), db provenance allowed
        assert row["raw"]["db_excluded"] is False
```

- [ ] **Step 4: Run (client tier — skips only without `COA_CLIENT_ROOT`)**

Run: `COA_CLIENT_ROOT=/path/to/client pytest tests/test_client_extract_acceptance.py -v -m client`
Expected: PASS on a client machine; SKIP (only) when `COA_CLIENT_ROOT` is unset.

- [ ] **Step 5: Commit**

```bash
git add coa_scraper/tests/pipeline-scripts.test.mjs tests/test_client_extract_acceptance.py
git commit -m "M1.14C Task 15: acceptance — build guarantees + automated client-tier 805775 (non-vacuous DB gate)"
```

---

## Task 16: Full regression + wiring verification

**Files:** none (verification only).

- [ ] **Step 1: Run the whole Node suite**

Run (from `coa_scraper/`): `npm run unit-test`
Expected: PASS (all `tests/*.test.mjs`).

- [ ] **Step 2: Run the whole Python suite (default tier, no client)**

Run: `pytest -q -m "not client"`
Expected: PASS.

- [ ] **Step 3: Dry-run the fallback pipeline without a client, into a clean temp dir (proves maintainer workflow)**

Run (from `coa_scraper/`):

```bash
TMP=$(mktemp -d)
node scripts/build-mechanics-artifacts.mjs --builder-entries dist/coa_entries.jsonl --db-spells dist/coa_db_spell_tooltips.jsonl --projection /nonexistent.jsonl --projection-manifest /nonexistent.json --out "$TMP" --allow-fallback-mechanics
ls "$TMP"
```

Expected: writes `$TMP/coa_mechanics.fallback.jsonl` + `$TMP/coa_mechanics.fallback.manifest.json` with `"canonical": false`; exits 0. Confirm `$TMP/coa_mechanics.jsonl` (canonical) is NOT produced (the clean temp dir avoids a false pass from a stale `dist/`). Also confirm the canonical path fails closed: rerun without `--allow-fallback-mechanics` and expect a non-zero exit and no files in a fresh temp dir.

- [ ] **Step 4: Confirm no client-derived artifact is staged**

Run: `git status --porcelain | grep -E 'coa_mechanics|coa_client_spell_coa' || echo "clean"`
Expected: `clean`.

- [ ] **Step 5: Commit any remaining test/wiring fixups**

```bash
git add -A
git commit -m "M1.14C Task 16: full-suite regression green; fallback pipeline verified" || echo "nothing to commit"
```

---

## Self-Review Notes (for the executor)

- **Spec coverage:** projection+manifest (T3, atomic + dup-rejected), per-table confidence (T2), per-field reconciliation with **separated** source/tier/eligibility + both-sides conflict fall-through (T5,T7,T8), DB identity gate incl. `db_identity_unverifiable` and `kind`/`tags` exclusion (T6,T8), schools+field_provenance loader round-trip (T4,T14), **fail-closed canonical validation** — torn pair, required checksum, per-table drift / unknown mask-enum throw before reconciliation, full row-schema + manifest validation, positive-int spell_id (T9); fallback build writes only `coa_mechanics.fallback.*` (never canonical) + checksum-bound manifest + atomic manifest-marker writes (T10); Builder-domain output + coverage (T8,T9); carried-in fixes missing≠zero/deterministic dedup/`tick_interval_ms` (T7,T8,T12); **complete provenance** — every emitted field reconciled or given single-source `field_provenance` (incl. `kind` + `effects`); record-level provenance = union of each field's selected source plus every `contributed` candidate, so a db tooltip informing kind/effects still leaves a db entry; set-like `tags` moved under `raw.tags` (round-tripped, not a phantom top-level v1 field) (T8); item split + npm (`../reports/...` paths) + artifact manifest (T11); ignore rules + regen docs + policy gate (T13); enum/sentinel recon + unknown-flagging (T1); acceptance — build guarantees + automated client-tier `805775` (T15).
- **Fail-closed is enforced in T9, not T7:** candidate assembly (T7) only *marks* client candidates ineligible; the hard failure for a canonical build (per-table drift on a populated field, unknown mask/enum) is thrown by `loadAndValidateProjection`'s `assertRecordSemantics` **before** any reconciliation, so a canonical artifact is never emitted on those. The fallback flag only rescues a *fully-absent* (both files missing) projection.
- **Determinism:** T8 sorts grouped nodes by `entry_id`, aggregates `tags` as a sorted set (into `raw.tags`), and derives `kind`/`name`/`effects` from a merged view of all nodes (never one arbitrary node) — the T8 reversibility test asserts byte-identical output under reversed input.
- **Deferred/verify during execution:** confirm `normalizeName` is exported from `lib/ascensiondb.mjs` (T6); confirm the `write-artifact-manifest.mjs` script-list assertion at `pipeline-scripts.test.mjs:405` (T11); in T12 set the fixture db `name` equal to the entry `name` so the identity gate keeps the db row usable.
- **Type consistency:** candidate shape (`source`/`precedence_tier`/`source_id`/`source_field`/`raw_value`/`normalized_value`/`confidence`/`eligible`/`eligibility_reasons`) is identical across T5/T6/T7/T8; `reconcileField` returns `{ field, selected, provenance, hadConflict }`; `applyDbIdentityGate` returns `{ excluded, reason }`; manifest schema `coa-mechanics-manifest-v1` (with `per_field_winner_counts_by_source`/`_by_tier`) matches T10 and the spec.
