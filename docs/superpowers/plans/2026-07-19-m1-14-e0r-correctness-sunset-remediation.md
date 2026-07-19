# M1.14E0R Correctness & Sunset Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: execute **inline** (superpowers:executing-plans) with task-sized commits. Reviews are **human check-ins**, not subagent/inline reviews: a mandatory recon-adjudication gate after Task 8 (a human authors the reviewed, client-bound policy + lock — an agent cannot), and an end-of-E0R check-in after Task 16. Steps use `- [ ]`. **Do not begin code execution (Task 2+) until the design-lock (Task 1) is committed and its four invariants appear in both the design and this plan.**

**Goal:** Make the merged M1.14E0 evidence model enforced and non-bypassable at every boundary, and hard-cut db.ascension.gg (AscensionDB) from the canonical spell-mechanics pipeline, before M1.14E1.

**Architecture:** Fix-forward from `main@f76da24` on branch `m1-14-e0r`. Reuse the E0 substrate (`spell_proof` two-gate envelopes, `recordview`, `spell_layout`, `publish` generation writer, `spell_mechanics` recon). Add a frozen contracts module, a v2 policy carrying join promotion + a structured topology binding, one shared topology verifier used by recon and regenerate, a streaming compact-raw v3 producer with hoisted provenance + `policy_ref`, a client spell-icon catalog, an independently-verifying Node consumer, a transactional candidate→pointer publisher with a trust digest + cross-child validation, `coa-mechanics-v2`, and a fail-closed consumer interlock. Remove AscensionDB from the canonical path entirely.

**Tech Stack:** Python 3.11 stdlib (`struct`, `json`, `hashlib`, `uuid`, `math`, `resource`, `subprocess`, `time`, `zlib`/`tarfile`, `fcntl`, `dataclasses`, `pathlib`); pytest with the existing `stormlib`/`client` markers; Node 18 (`node:fs`, `node:crypto`, `node:zlib`); GitHub Actions.

## Global Constraints

Copied from `docs/superpowers/specs/2026-07-19-m1-14-e0r-correctness-sunset-remediation-design.md`. Every task's requirements implicitly include these.

- **Evidence ≠ authorization.** `_proof()` stays evidence-only; the emitter authorizes a normalized value only when `promotion == "normalized"`. A field may be fully decodable yet intentionally raw-only.
- **Join promotion predicate (exact).** A join emits a normalized value iff `join.promotion == "normalized"` AND every contributing `FieldPolicy.promotion == "normalized"` (index, side_id, side_value) AND `semantic_promotion_eligible(composed_proof)` AND `observation.state == "resolved"`.
- **Full-topology hard hold.** One shared `verify_source_topology` used by recon **and** regenerate, binding every required table's sha256 + full 5-field header (`magic, record_count, field_count, record_size, string_block_size`) + logical archive/member + patch chain, plus `expected_absent`. Archive identities are logical/relative names, never absolute paths.
- **Independent Node boundary (bounded).** Node re-derives layout/interpretation/promotion via `policy_ref` from a **pinned** policy child; re-decodes numeric `raw_u32`; for strings verifies `state`/normalization/`resolved` equality; validates transport integrity but **not** source integrity.
- **Streaming + three-part budget.** Iterator/two-pass everywhere (incl. `generation.mjs`); repeated provenance/evidence hoisted to the manifest; `within_budget` = serialized bytes **and** subprocess peak RSS **and** elapsed; per-child and whole-generation, uncompressed bytes; a full real-client regenerate is measured and recorded.
- **Compact-raw retention.** A full-table row never carries a normalized value without enough compact raw (scalar `u32`/string offset, join component cells, `state`) to reconstruct eligibility.
- **Transactional candidate→pointer.** Stage children → candidate manifest (`publication_state: "candidate"`, `candidate_trust_sha256` over all trust-critical fields) → Python+Node validate by path (incl. cross-child merge-join) → final manifest changes only `/validation`+`/budget` and reproduces the digest → pointer last. The manifest is **not** a child. Process file lock over predecessor-read → replace.
- **AscensionDB-free canonical.** Canonical `build-mechanics` is pointer-only, network-free, no `--db-spells`; `ascension_db` is not a selectable canonical tier; a negative-dependency test enforces it. Frozen payloads survive only as fixtures/diagnostic.
- **Missing ≠ default.** Unknown load-bearing mechanics are `null` with a closed `reason_code`; never `0`/`1500`/free; a quantitative scope with unready load-bearing data fails closed.
- **Schema versions (explicit).** `coa-spell-layout-v2`, `coa-client-spell-v3`, `coa-client-spell-projection-v3` (+ `coa-client-spell-projection-manifest-v3`), `coa-client-spell-icons-v1`, `coa-client-extract-manifest-v3` (the generation manifest, not a child), `coa-mechanics-v2`. Pre-E0R generations are rejected.
- **Never `git add -A`** (a dirty-tree gotcha swept 60 MB into an E0 commit); stage only named paths.

---

## File Structure

**Create:**
- `coa_client_extract/contracts.py` — the frozen design-lock contracts (Task 1): `policy_ref`, readiness/`reason_code` enums, `TRUST_CRITICAL_MANIFEST_KEYS`, `CROSS_CHILD_CHECKS`, icon-asset statuses, the `bound` shape. The single authority the rest of E0R imports.
- `coa_client_extract/topology.py` — shared `verify_source_topology` + `topology_matches_bound` (Task 4).
- `coa_client_extract/spell_icons.py` — `coa-client-spell-icons-v1` catalog builder (Task 6).
- `coa_client_extract/data/spell_layout_v2.json` — the v2 policy (schema authored in Task 2; cells filled at the Task 8 recon gate).
- `coa_scraper/config/spell_layout.lock.json` — the pinned canonical policy hash (authored at the Task 8 gate).
- `coa_scraper/scripts/lib/jsonl.mjs` — generic `readJsonl`, moved off `ascensiondb.mjs` (Task 11).
- `.github/workflows/ci.yml` — CI (Task 16).
- Tests: `tests/test_contracts.py`, `tests/test_spell_layout_v2.py`, `tests/test_spell_proof_string_join.py`, `tests/test_topology.py`, `tests/test_spell_mechanics_recon_e0r.py`, `tests/test_spell_record.py`, `tests/test_spell_icons.py`, `tests/test_publish_e0r.py`, `tests/test_e0r_end_to_end.py`, `tests/test_mechanics_v2.py`, `tests/test_action_catalog_interlock.py`, `tests/test_simulation_interlock.py`, `tests/test_guide_icons.py`, `tests/test_e0r_hygiene.py`, `tests/test_e0r_acceptance_summary.py`, `tests/test_e0r_client.py`; `coa_scraper/tests/mechanics-projection-e0r.test.mjs`, `generation-e0r.test.mjs`, `no-ascensiondb.test.mjs`, `mechanics-v2.test.mjs`, `icon-assets-e0r.test.mjs`.

**Modify:**
- `coa_client_extract/spell_proof.py` — add `make_string_join` (Task 3).
- `coa_client_extract/spell_layout.py` — v2 loader: `JoinPolicy.promotion`, per-table key cell + uniqueness, structured `bound`, `policy_ref` resolution (Task 2).
- `coa_client_extract/spell_mechanics.py` — joined-pair discovery for all four joins, static `power_type` negative anchor, three-part budget; uses `verify_source_topology` (Task 5).
- `coa_client_extract/spell_v2.py` → rename to `spell_record.py` — streaming compact-raw v3 producer + `policy_ref` (Task 6).
- `coa_client_extract/publish.py`, `manifest.py` — required-child registry, candidate/final trust digest, cross-child validation, icon-bundle enforcement, process lock, manifest-v3 (Task 9).
- `coa_client_extract/cli.py` — shared hard hold; stage → candidate-validate → publish (Tasks 8, 10).
- `coa_scraper/scripts/lib/generation.mjs` — streaming validate + policy-lock + cross-child (Task 10).
- `coa_scraper/scripts/lib/mechanics-projection.mjs` — numeric/string re-derivation via `policy_ref` (Task 7).
- `coa_scraper/scripts/lib/mechanics-reconcile.mjs`, `build-mechanics-artifacts.mjs`, `package.json`, root `package.json` — AscensionDB hard-cut (Task 11).
- `coa_meta/mechanics.py`, `mechanics_repository.py` — `coa-mechanics-v2` (Task 12).
- `coa_meta/action_catalog.py`, `simulation.py`, `reporting.py` — fail-closed interlock (Task 13).
- `coa_meta/guide_assets.py`, `coa_scraper/scripts/lib/icon-assets.mjs` — client-native spell icons (Task 14).
- `coa_scraper/scripts/write-artifact-manifest.mjs`, `.gitignore` — repo hygiene (Task 15).
- `docs/DECISIONS.md`, `docs/data/*.md`, `docs/ROADMAP.md` — schema/decision docs (Task 16).

---

## Task 1: Design-lock — freeze the four invariants as committed contracts

**Files:**
- Create: `coa_client_extract/contracts.py`
- Test: `tests/test_contracts.py`

**Interfaces:**
- Produces: `policy_ref(table, field) -> str` (JSON Pointer `/tables/<t>/fields/<f>`); `policy_ref_component(join, part) -> str` (`/joins/<j>/<part>`, `part ∈ {index, side_id, side_value}`); `resolve_policy_ref(policy_doc, ref) -> dict`; `READINESS_STATUSES`, `READINESS_REASON_CODES`, `ICON_ASSET_STATUSES` (closed `frozenset`s); `TRUST_CRITICAL_MANIFEST_KEYS` (the set `candidate_trust_sha256` covers); `CROSS_CHILD_CHECKS` (the named merge-join predicates); `BOUND_HEADER_FIELDS`, `BOUND_SOURCE_FIELDS`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contracts.py
import pytest
from coa_client_extract.contracts import (
    policy_ref, policy_ref_component, resolve_policy_ref,
    READINESS_STATUSES, READINESS_REASON_CODES, ICON_ASSET_STATUSES,
    TRUST_CRITICAL_MANIFEST_KEYS, CROSS_CHILD_CHECKS, BOUND_HEADER_FIELDS,
)


def test_policy_ref_is_json_pointer():
    assert policy_ref("Spell", "power_type") == "/tables/Spell/fields/power_type"
    assert policy_ref_component("cast_time_ms", "side_value") == "/joins/cast_time_ms/side_value"
    with pytest.raises(ValueError):
        policy_ref_component("cast_time_ms", "bogus")


def test_resolve_policy_ref_walks_the_document():
    doc = {"tables": {"Spell": {"fields": {"power_type": {"cell": 41, "kind": "int32"}}}}}
    assert resolve_policy_ref(doc, "/tables/Spell/fields/power_type")["cell"] == 41


def test_enums_are_closed_frozensets():
    assert isinstance(READINESS_STATUSES, frozenset)
    assert {"available", "unavailable", "not_applicable", "ambiguous", "verified_empty"} == READINESS_STATUSES
    assert "pending_e1_operand" in READINESS_REASON_CODES
    assert ICON_ASSET_STATUSES == frozenset({"converted", "source_only", "missing", "placeholder"})


def test_trust_critical_excludes_validation_and_budget():
    assert "validation" not in TRUST_CRITICAL_MANIFEST_KEYS
    assert "budget" not in TRUST_CRITICAL_MANIFEST_KEYS
    assert {"children", "binding", "generation_id", "schema_version"} <= TRUST_CRITICAL_MANIFEST_KEYS


def test_named_cross_child_checks_and_header_fields():
    assert "projection_is_coa_subset" in CROSS_CHILD_CHECKS
    assert "compact_raw_expands_to_envelope" in CROSS_CHILD_CHECKS
    assert BOUND_HEADER_FIELDS == ("magic", "record_count", "field_count", "record_size", "string_block_size")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_contracts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'coa_client_extract.contracts'`.

- [ ] **Step 3: Implement `contracts.py`**

```python
# coa_client_extract/contracts.py  (complete)
from __future__ import annotations

READINESS_STATUSES = frozenset({"available", "unavailable", "not_applicable", "ambiguous", "verified_empty"})
READINESS_REASON_CODES = frozenset({
    "pending_e1_operand", "join_ambiguous", "unknown_symbol", "side_row_missing",
    "index_zero", "no_static_anchor", "not_extracted",
})
ICON_ASSET_STATUSES = frozenset({"converted", "source_only", "missing", "placeholder"})

# The manifest fields candidate_trust_sha256 covers: everything a consumer trusts EXCEPT the
# post-validation /validation and /budget results (which legitimately differ candidate->final).
TRUST_CRITICAL_MANIFEST_KEYS = frozenset({
    "schema_version", "generation_id", "predecessor_generation_id", "children",
    "binding", "unknown_symbol_inventory", "outputs",
})

# The named cross-child consistency checks a candidate validator MUST run (design A5).
CROSS_CHILD_CHECKS = (
    "projection_is_coa_subset", "projection_within_domain", "identity_agrees",
    "compact_raw_expands_to_envelope", "icons_agree", "sorted_unique_ids",
)

# The structured `bound` per-table shape (design A2).
BOUND_HEADER_FIELDS = ("magic", "record_count", "field_count", "record_size", "string_block_size")
BOUND_SOURCE_FIELDS = ("member", "effective_archive", "patch_chain")


def policy_ref(table: str, field: str) -> str:
    """A JSON Pointer into coa-spell-layout-v2, e.g. '/tables/Spell/fields/power_type'. The ONLY thing a
    row carries to reference its policy; the policy supplies kind/proof/promotion/evidence."""
    if not table or not field:
        raise ValueError("policy_ref requires a table and a field")
    return f"/tables/{table}/fields/{field}"


def policy_ref_component(join: str, part: str) -> str:
    """A JSON Pointer to a join component's policy, e.g. '/joins/cast_time_ms/index'."""
    if part not in ("index", "side_id", "side_value"):
        raise ValueError(f"join component {part!r} not in (index, side_id, side_value)")
    if not join:
        raise ValueError("policy_ref_component requires a join name")
    return f"/joins/{join}/{part}"


def resolve_policy_ref(policy_doc: dict, ref: str) -> dict:
    """Resolve an RFC-6901 JSON Pointer against a policy document."""
    node = policy_doc
    for token in ref.split("/")[1:]:
        node = node[token.replace("~1", "/").replace("~0", "~")]
    return node
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_contracts.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/contracts.py tests/test_contracts.py
git commit -m "M1.14E0R Task 1: design-lock contracts (policy_ref, readiness/reason enums, trust keys, cross-child checks, bound shape)"
```

---

## Task 2: `coa-spell-layout-v2` — join promotion, key/uniqueness, structured bound

**Files:**
- Modify: `coa_client_extract/spell_layout.py`
- Create: `coa_client_extract/data/spell_layout_v2.json` (schema only — join cells stay `null` until the Task 8 recon gate)
- Test: `tests/test_spell_layout_v2.py`

**Interfaces:**
- Consumes: `contracts.BOUND_HEADER_FIELDS`, `contracts.BOUND_SOURCE_FIELDS`.
- Produces: `JoinPolicy(index_field, side_table, side_value_field, promotion)`; per-table `key_cell: int` + `unique: bool`; `SpellPolicy.bound` as the structured A2 record (`client_build`, `tables[t] = {sha256, header{5}, source{member, effective_archive, patch_chain}}`, `expected_absent`); `SCHEMA = "coa-spell-layout-v2"`; `load_spell_policy` rejects the flat `bound` shape and a v1 `schema_version`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spell_layout_v2.py
import copy
import pytest
from coa_client_extract.spell_layout import load_spell_policy, SpellPolicyError, compute_policy_sha256


def _f(cell, kind, promo="normalized", layout="verified", interp="verified"):
    return {"cell": cell, "kind": kind, "layout": layout, "interpretation": interp,
            "promotion": promo, "evidence": "fixture"}


def _v2():
    tables = {
        "Spell": {"expected_field_count": 234, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32"), "power_type": _f(41, "int32"),
            "casting_time_index": _f(28, "uint32", promo="normalized")}},
        "SpellCastTimes": {"expected_field_count": 4, "key_cell": 0, "unique": True, "fields": {
            "id": _f(0, "uint32", promo="raw_only", interp="verified"),
            "base_ms": _f(1, "int32", promo="normalized")}},
    }
    joins = {"cast_time_ms": {"index_field": "casting_time_index", "side_table": "SpellCastTimes",
                              "side_value_field": "base_ms", "promotion": "normalized"}}
    enum = {"power_types": [-2, 0, 1, 2, 3, 4, 5, 6], "school_bits": [1, 2, 4, 8, 16, 32, 64]}
    enum["sha256"] = compute_policy_sha256(enum)
    anchor = {"spells": [{"id": 133, "name": "Fireball", "power_type": 0, "school_mask": 4}]}
    anchor["sha256"] = compute_policy_sha256(anchor)
    bound = {"client_build": "3.3.5a+patch-CZZ", "expected_absent": ["SpellEffect"], "tables": {
        "Spell": {"sha256": "a" * 64, "header": {"magic": "WDBC", "record_count": 1, "field_count": 234,
                  "record_size": 936, "string_block_size": 10},
                  "source": {"member": "DBFilesClient\\Spell.dbc", "effective_archive": "patch-T.MPQ",
                             "patch_chain": []}}}}
    p = {"schema_version": "coa-spell-layout-v2", "reviewed": True, "bound": bound,
         "required_tables": ["Spell", "SpellCastTimes"], "expected_absent": ["SpellEffect"],
         "enum_policy": enum, "anchor_set": anchor, "tables": tables, "joins": joins}
    p["sha256"] = compute_policy_sha256(p)
    return p


def test_v2_loads_join_promotion_and_key_uniqueness():
    pol = load_spell_policy(_v2())
    assert pol.schema_version == "coa-spell-layout-v2"
    assert pol.joins["cast_time_ms"].promotion == "normalized"
    assert pol.tables["Spell"]["key_cell"] == 0 and pol.tables["Spell"]["unique"] is True
    assert pol.bound["tables"]["Spell"]["header"]["field_count"] == 234


def test_v2_rejects_flat_bound_shape():
    p = _v2(); p["bound"] = {"client_build": "x", "source_dbc_sha256": {"Spell": "a" * 64}}
    p["sha256"] = compute_policy_sha256(p)
    with pytest.raises(SpellPolicyError, match="bound.tables"):
        load_spell_policy(p)


def test_v2_rejects_normalized_join_with_raw_only_component():
    p = _v2()
    p["tables"]["SpellCastTimes"]["fields"]["base_ms"]["promotion"] = "raw_only"
    p["sha256"] = compute_policy_sha256(p)
    with pytest.raises(SpellPolicyError, match="raw_only component"):
        load_spell_policy(p)


def test_v1_schema_is_rejected():
    p = _v2(); p["schema_version"] = "coa-spell-layout-v1"; p["sha256"] = compute_policy_sha256(p)
    with pytest.raises(SpellPolicyError, match="coa-spell-layout-v2"):
        load_spell_policy(p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_spell_layout_v2.py -v`
Expected: FAIL — the loader still asserts `coa-spell-layout-v1` and has no `promotion`/`key_cell`/structured-`bound` handling.

- [ ] **Step 3: Implement the v2 loader changes in `spell_layout.py`**

```python
# coa_client_extract/spell_layout.py  (changed regions)
from .contracts import BOUND_HEADER_FIELDS, BOUND_SOURCE_FIELDS

SCHEMA = "coa-spell-layout-v2"


@dataclass(frozen=True)
class JoinPolicy:
    index_field: str
    side_table: str
    side_value_field: str
    promotion: str          # "normalized" | "raw_only" — the emitted value's authorization


def _validate_bound(bound: dict) -> dict:
    if "source_dbc_sha256" in bound:
        raise SpellPolicyError("bound uses the flat source_dbc_sha256 shape; E0R requires bound.tables{}")
    if not isinstance(bound.get("client_build"), str):
        raise SpellPolicyError("bound.client_build must be a string")
    tables = bound.get("tables")
    if not isinstance(tables, dict) or not tables:
        raise SpellPolicyError("bound.tables must be a non-empty dict")
    for tname, spec in tables.items():
        if not isinstance(spec.get("sha256"), str) or len(spec["sha256"]) != 64:
            raise SpellPolicyError(f"bound.tables.{tname}.sha256 must be a 64-char hex digest")
        header = spec.get("header", {})
        for h in BOUND_HEADER_FIELDS:
            if h not in header:
                raise SpellPolicyError(f"bound.tables.{tname}.header missing {h!r}")
        source = spec.get("source", {})
        for s in BOUND_SOURCE_FIELDS:
            if s not in source:
                raise SpellPolicyError(f"bound.tables.{tname}.source missing {s!r}")
        if os.path.isabs(str(source["effective_archive"])):
            raise SpellPolicyError(f"bound.tables.{tname}.source.effective_archive must be a logical name")
    return bound
```

Then, inside `load_spell_policy`: require `schema_version == SCHEMA` (message names `coa-spell-layout-v2`); for each table read `key_cell:int` (`0 <= key_cell < expected_field_count`) and `unique:bool` into `tables[tname]`; parse joins with the extra `promotion` field validated against `_PROMOTIONS`, and enforce that a `normalized` join's index/`id`/`side_value` fields are all `promotion == "normalized"` (else `SpellPolicyError(f"join {jname}: normalized join has a raw_only component {fname}")`); call `_validate_bound(bound)` when `bound is not None`.

```python
    # inside load_spell_policy, per-table:
    key_cell = tspec.get("key_cell")
    if type(key_cell) is not int or isinstance(key_cell, bool) or not (0 <= key_cell < fc):
        raise SpellPolicyError(f"{tname}: key_cell {key_cell!r} out of [0,{fc})")
    unique = tspec.get("unique")
    if not isinstance(unique, bool):
        raise SpellPolicyError(f"{tname}: unique must be a bool")
    tables[tname] = {"expected_field_count": fc, "key_cell": key_cell, "unique": unique, "fields": fields}

    # per join:
    promo = jspec.get("promotion")
    if promo not in _PROMOTIONS:
        raise SpellPolicyError(f"join {jname}: promotion {promo!r} not in {_PROMOTIONS}")
    if promo == "normalized":
        for role, fname in (("index", idx), ("side_value", val), ("side_id", "id")):
            if tables[side if role != "index" else "Spell"]["fields"][fname].promotion != "normalized":
                raise SpellPolicyError(f"join {jname}: normalized join has a raw_only component {fname}")
    joins[jname] = JoinPolicy(idx, side, val, promo)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_spell_layout_v2.py tests/test_spell_layout.py -v`
Expected: PASS (the v2 tests pass; port the legacy `tests/test_spell_layout.py` fixtures to v2 in the same commit — add `key_cell`/`unique`/join `promotion`/structured `bound` — and enumerate each changed assertion in the commit body).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/spell_layout.py coa_client_extract/data/spell_layout_v2.json \
        tests/test_spell_layout_v2.py tests/test_spell_layout.py
git commit -m "M1.14E0R Task 2: coa-spell-layout-v2 (join promotion + key/uniqueness + structured bound + v1 rejection)"
```

---

## Task 3: Promotion authorization + string-valued join in the proof layer

**Files:**
- Modify: `coa_client_extract/spell_proof.py`
- Test: `tests/test_spell_proof_string_join.py`

**Interfaces:**
- Consumes: `StringObservation`, `compose_proof`, `semantic_promotion_eligible`, `make_string_observation`.
- Produces: `make_string_join(components, *, resolution, side_key="side_value") -> JoinObservation` where the resolved value is the side `StringObservation.resolved` only when the composed proof is promotion-eligible and `resolution == "resolved"`; `index_zero -> not_applicable`, `side_row_missing -> unresolved`. `_proof` and the numeric `make_join` are unchanged (evidence-only).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spell_proof_string_join.py
import pytest
from coa_client_extract.spell_proof import (
    FieldProof, make_envelope, make_string_observation, make_string_join,
)

VER = FieldProof("verified", "verified", "verified")
REF = FieldProof("verified", "verified", "reference")


def _idx(): return make_envelope(5, kind="uint32", proof=VER, evidence_ref="/joins/icon/index")


def test_string_join_resolves_when_all_verified():
    side = make_string_observation(12, "Ability_Fireball", proof=VER, evidence_ref="/joins/icon/side_value")
    sid = make_envelope(5, kind="uint32", proof=VER, evidence_ref="/joins/icon/side_id")
    jo = make_string_join({"index": _idx(), "side_id": sid, "side_value": side}, resolution="resolved")
    assert jo.state == "resolved" and jo.decoded == "Ability_Fireball"


def test_string_join_withholds_when_side_reference_only():
    side = make_string_observation(12, None, proof=REF, evidence_ref="/joins/icon/side_value")
    jo = make_string_join({"index": _idx(), "side_value": side}, resolution="resolved")
    assert jo.state == "resolved" and jo.decoded is None and jo.decoded_reason == "proof_withheld"


def test_string_join_index_zero_and_missing():
    side = make_string_observation(0, "", proof=VER, evidence_ref="/joins/icon/side_value")
    assert make_string_join({"index": _idx(), "side_value": side}, resolution="index_zero").state == "not_applicable"
    assert make_string_join({"index": _idx(), "side_value": side}, resolution="side_row_missing").state == "unresolved"
    with pytest.raises(ValueError):
        make_string_join({}, resolution="resolved")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_spell_proof_string_join.py -v`
Expected: FAIL with `ImportError: cannot import name 'make_string_join'`.

- [ ] **Step 3: Implement `make_string_join` in `spell_proof.py`**

```python
# coa_client_extract/spell_proof.py  (append)
def make_string_join(components: dict, *, resolution, side_key: str = "side_value") -> JoinObservation:
    """A join whose side value is a StringObservation (e.g. SpellIcon.path). Mirrors make_join's states,
    but the resolved value is the side observation's `resolved` text; a string cannot be re-decoded from
    an offset, so consumers verify equality against `resolved`."""
    if not components:
        raise ValueError("string join requires components")
    composed = compose_proof(*(c.proof for c in components.values()))
    if resolution == "index_zero":
        return JoinObservation("not_applicable", components, composed, None, "index_zero", _TOKEN)
    if resolution == "side_row_missing":
        return JoinObservation("unresolved", components, composed, None, "side_row_missing", _TOKEN)
    if resolution != "resolved":
        raise ValueError(f"invalid string-join resolution {resolution!r} (fail closed)")
    side = components[side_key]
    if not semantic_promotion_eligible(composed) or side.resolved is None:
        return JoinObservation("resolved", components, composed, None, "proof_withheld", _TOKEN)
    return JoinObservation("resolved", components, composed, side.resolved, "decoded", _TOKEN)
```

`JoinObservation.to_dict` already serializes `components` via each part's `to_dict`; `StringObservation.to_dict` exists, so a mixed component map round-trips.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_spell_proof_string_join.py tests/test_spell_proof.py -v`
Expected: PASS (new string-join tests pass; the existing `test_spell_proof.py` is unchanged).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/spell_proof.py tests/test_spell_proof_string_join.py
git commit -m "M1.14E0R Task 3: string-valued join observation; proof layer stays evidence-only"
```

---

## Task 4: Shared `verify_source_topology`

**Files:**
- Create: `coa_client_extract/topology.py`
- Test: `tests/test_topology.py`

**Interfaces:**
- Consumes: `recordview.open_view`, the backend's `read_effective_file`/`has_file`.
- Produces: `verify_source_topology(policy, backend, root, attach) -> dict` with `tables[t] = {sha256, header{5 fields}, effective_archive, patch_chain, key_unique: bool}`, `expected_absent_ok: bool`, and `blocking: list[dict]`; `topology_matches_bound(report, bound) -> list[dict]` (empty ⇒ match). Used by recon (Task 5) **and** regenerate (Task 10).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_topology.py
import hashlib, struct
import pytest
from coa_client_extract.topology import verify_source_topology, topology_matches_bound


def _dbc(rows: list[tuple[int, int]], field_count=2) -> bytes:
    rs = field_count * 4
    body = b"".join(struct.pack("<II", a, b) for a, b in rows)
    return struct.pack("<4sIIII", b"WDBC", len(rows), field_count, rs, 0) + body


class _Member:
    def __init__(self, data, archive="patch-T.MPQ"):
        self.data = data
        self.effective_archive = type("A", (), {"name": archive})()
        self.patch_chain = []


class _Backend:
    def __init__(self, files): self.files = files
    def has_file(self, root, attach, name): return name in self.files
    def read_effective_file(self, root, attach, name):
        if name not in self.files: raise KeyError(name)
        return _Member(self.files[name])


class _Policy:
    required_tables = ("Spell",)
    expected_absent = ("SpellEffect",)
    def __init__(self, key_cell=0, unique=True):
        self.tables = {"Spell": {"key_cell": key_cell, "unique": unique, "expected_field_count": 2}}
        self.bound = None


def test_topology_report_captures_header_and_uniqueness():
    data = _dbc([(1, 10), (2, 20)])
    be = _Backend({"DBFilesClient\\Spell.dbc": data})
    rep = verify_source_topology(_Policy(), be, None, None)
    t = rep["tables"]["Spell"]
    assert t["sha256"] == hashlib.sha256(data).hexdigest()
    assert t["header"]["field_count"] == 2 and t["header"]["magic"] == "WDBC"
    assert t["key_unique"] is True and rep["expected_absent_ok"] is True and rep["blocking"] == []


def test_duplicate_key_and_expected_absent_present_block():
    dup = _dbc([(1, 10), (1, 20)])
    be = _Backend({"DBFilesClient\\Spell.dbc": dup, "DBFilesClient\\SpellEffect.dbc": dup})
    rep = verify_source_topology(_Policy(), be, None, None)
    assert rep["tables"]["Spell"]["key_unique"] is False
    assert rep["expected_absent_ok"] is False
    reasons = {b["reason"] for b in rep["blocking"]}
    assert {"duplicate_key", "expected_absent_present"} <= reasons


def test_topology_matches_bound_reports_mismatch():
    data = _dbc([(1, 10)])
    be = _Backend({"DBFilesClient\\Spell.dbc": data})
    rep = verify_source_topology(_Policy(), be, None, None)
    bound = {"client_build": "x", "tables": {"Spell": {"sha256": "0" * 64,
             "header": rep["tables"]["Spell"]["header"], "source": {"member": "DBFilesClient\\Spell.dbc",
             "effective_archive": "patch-T.MPQ", "patch_chain": []}}}, "expected_absent": ["SpellEffect"]}
    mism = topology_matches_bound(rep, bound)
    assert any(m["table"] == "Spell" and m["field"] == "sha256" for m in mism)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_topology.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'coa_client_extract.topology'`.

- [ ] **Step 3: Implement `topology.py`**

```python
# coa_client_extract/topology.py  (complete)
from __future__ import annotations

import hashlib
import struct

from .recordview import open_view
from .errors import ArchiveError, DbcDriftError

_H = struct.Struct("<4sIIII")


def _header(data: bytes) -> dict:
    magic, rc, fc, rs, ss = _H.unpack_from(data, 0)
    return {"magic": magic.decode("latin-1"), "record_count": rc, "field_count": fc,
            "record_size": rs, "string_block_size": ss}


def verify_source_topology(policy, backend, root, attach) -> dict:
    """Independently open + verify every required table (sha256, full 5-field header, archive/member,
    patch chain, id-uniqueness under the policy key cell) and the expected-absent set. Shared by recon
    AND regenerate so they can never diverge."""
    tables: dict[str, dict] = {}
    blocking: list[dict] = []
    for name in policy.required_tables:
        member_name = f"DBFilesClient\\{name}.dbc"
        try:
            member = backend.read_effective_file(root, attach, member_name)
            view = open_view(member.data)
        except (ArchiveError, DbcDriftError, KeyError) as exc:
            blocking.append({"table": name, "reason": "required_table_unreadable", "detail": str(exc)})
            continue
        key_cell = policy.tables[name]["key_cell"]
        seen, unique = set(), True
        for rec in view.records():
            k = rec.u32(key_cell)
            if k in seen:
                unique = False
                break
            seen.add(k)
        tables[name] = {
            "sha256": hashlib.sha256(member.data).hexdigest(), "header": _header(member.data),
            "effective_archive": member.effective_archive.name,
            "patch_chain": [p.name for p in member.patch_chain], "key_unique": unique,
        }
        if policy.tables[name].get("unique", True) and not unique:
            blocking.append({"table": name, "reason": "duplicate_key", "key_cell": key_cell})

    expected_absent_ok = True
    for name in policy.expected_absent:
        if backend.has_file(root, attach, f"DBFilesClient\\{name}.dbc"):
            expected_absent_ok = False
            blocking.append({"table": name, "reason": "expected_absent_present"})

    return {"tables": tables, "expected_absent_ok": expected_absent_ok, "blocking": blocking}


def topology_matches_bound(report: dict, bound: dict | None) -> list[dict]:
    """Return the list of mismatches between an opened-client topology report and a policy's structured
    `bound`. Empty ⇒ the opened client is the client the policy was proven against."""
    if not bound:
        return [{"table": "*", "field": "bound", "reason": "policy has no bound"}]
    mism: list[dict] = []
    want = bound.get("tables", {})
    for name, w in want.items():
        got = report["tables"].get(name)
        if got is None:
            mism.append({"table": name, "field": "*", "reason": "missing_from_client"})
            continue
        if got["sha256"] != w["sha256"]:
            mism.append({"table": name, "field": "sha256", "reason": "sha_mismatch"})
        if got["header"] != w["header"]:
            mism.append({"table": name, "field": "header", "reason": "header_mismatch"})
        if got["effective_archive"] != w["source"]["effective_archive"]:
            mism.append({"table": name, "field": "effective_archive", "reason": "archive_moved"})
    if not report["expected_absent_ok"]:
        mism.append({"table": "*", "field": "expected_absent", "reason": "expected_absent_present"})
    return mism
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_topology.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/topology.py tests/test_topology.py
git commit -m "M1.14E0R Task 4: shared verify_source_topology (full header + archive + key-uniqueness + expected-absent binding)"
```

---

## Task 5: Recon — joined-pair discovery (all four joins) + static `power_type` anchor + three-part budget

**Files:**
- Modify: `coa_client_extract/spell_mechanics.py`
- Test: `tests/test_spell_mechanics_recon_e0r.py`

**Interfaces:**
- Consumes: `topology.verify_source_topology`, `recordview.open_view`.
- Produces: `discover_join_pair(view, id_to_rec, side_view, *, side_value_cell, side_id_cell, anchors, side_ids) -> tuple[int | None, list[int]]` (value-anchor joined-pair scan; unique winner or ambiguous); `discover_power_type_signedness(view, id_to_rec, cell, anchors) -> bool` (True only when a static health-cost anchor reads `0xFFFFFFFE`); `three_part_budget(*, serialized_bytes, peak_rss_mb, elapsed_s, ceilings) -> dict` (`within_budget` requires **all three** under ceiling). Recon proposes a `proposed_policy_delta`; it never writes the policy.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spell_mechanics_recon_e0r.py
import struct
import pytest
from coa_client_extract.recordview import open_view
from coa_client_extract.spell_mechanics import (
    discover_join_pair, discover_power_type_signedness, three_part_budget,
)


def _spell(rows: list[list[int]], field_count: int) -> "DbcView":
    rs = field_count * 4
    body = b"".join(struct.pack("<%dI" % field_count, *r) for r in rows)
    return open_view(struct.pack("<4sIIII", b"WDBC", len(rows), field_count, rs, 0) + body)


def _side(rows: list[tuple[int, int]]) -> "DbcView":
    body = b"".join(struct.pack("<II", i, v) for i, v in rows)
    return open_view(struct.pack("<4sIIII", b"WDBC", len(rows), 2, 8, 0) + body)


def test_joined_pair_finds_unique_index_cell():
    # cell 2 holds the FK; the decoy cell 1 also falls in the id range but resolves to wrong values.
    spell = _spell([[133, 3, 2], [116, 2, 3], [400, 0, 0]], field_count=3)
    id_to_rec = {r.u32(0): r for r in spell.records()}
    side = _side([(2, 1500), (3, 3000)])
    anchors = [{"spell_id": 133, "expected_value": 1500}, {"spell_id": 116, "expected_value": 3000},
               {"spell_id": 400, "expected_value": 0}]
    cell, winners = discover_join_pair(spell, id_to_rec, side, side_value_cell=1, side_id_cell=0,
                                       anchors=anchors, side_ids={2, 3})
    assert cell == 2 and winners == [2]


def test_joined_pair_ambiguous_returns_none():
    spell = _spell([[133, 2, 2], [116, 3, 3], [400, 0, 0]], field_count=3)  # cells 1 and 2 identical
    id_to_rec = {r.u32(0): r for r in spell.records()}
    side = _side([(2, 1500), (3, 3000)])
    anchors = [{"spell_id": 133, "expected_value": 1500}, {"spell_id": 116, "expected_value": 3000}]
    cell, winners = discover_join_pair(spell, id_to_rec, side, side_value_cell=1, side_id_cell=0,
                                       anchors=anchors, side_ids={2, 3})
    assert cell is None and winners == [1, 2]


def test_power_type_signedness_requires_static_negative_anchor():
    spell = _spell([[5, 0xFFFFFFFE]], field_count=2)   # health cost reads -2 unsigned
    id_to_rec = {r.u32(0): r for r in spell.records()}
    assert discover_power_type_signedness(spell, id_to_rec, cell=1,
                                          anchors=[{"spell_id": 5, "expected_signed": -2}]) is True
    assert discover_power_type_signedness(spell, id_to_rec, cell=1, anchors=[]) is False


def test_three_part_budget_requires_all_three():
    ceilings = {"artifact_size_mb": 512, "peak_rss_mb": 4096, "elapsed_s": 600}
    ok = three_part_budget(serialized_bytes=10 * 1024 * 1024, peak_rss_mb=100, elapsed_s=5, ceilings=ceilings)
    assert ok["within_budget"] is True
    over_rss = three_part_budget(serialized_bytes=10 * 1024 * 1024, peak_rss_mb=9000, elapsed_s=5, ceilings=ceilings)
    assert over_rss["within_budget"] is False and over_rss["breach"] == ["peak_rss_mb"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_spell_mechanics_recon_e0r.py -v`
Expected: FAIL with `ImportError: cannot import name 'discover_join_pair'`.

- [ ] **Step 3: Implement the discovery + budget functions in `spell_mechanics.py`**

```python
# coa_client_extract/spell_mechanics.py  (append / integrate)
def _read_side(rec, cell, kind):
    raw = rec.u32(cell)
    if kind == "float":
        return struct.unpack("<f", struct.pack("<I", raw))[0]
    if kind == "int32":
        return struct.unpack("<i", struct.pack("<I", raw))[0]
    return raw


def discover_join_pair(view, id_to_rec, side_view, *, side_value_cell, side_id_cell, anchors, side_ids,
                       side_value_kind="int32"):
    """Resolve each anchor's expected value THROUGH the join (candidate index cell -> side row ->
    side_value_cell) and return the unique index cell that satisfies every anchor. A bare FK-validity
    scan is ambiguous (dozens of small-int columns fall in a side id range); the value anchors break it."""
    side_by_id = {r.u32(side_id_cell): r for r in side_view.records()}
    winners: list[int] = []
    for c in range(view.cell_count):
        nonzero = [r.u32(c) for r in view.records() if r.u32(c) != 0]
        if len(nonzero) < _MIN_SUPPORT or sum(1 for v in nonzero if v in side_ids) / len(nonzero) < 0.99:
            continue
        ok = True
        for a in anchors:
            rec = id_to_rec.get(a["spell_id"])
            if rec is None:
                ok = False; break
            fk = rec.u32(c)
            if a["expected_value"] == 0:
                ok = fk == 0
            else:
                side = side_by_id.get(fk)
                ok = side is not None and _read_side(side, side_value_cell, side_value_kind) == a["expected_value"]
            if not ok:
                break
        if ok:
            winners.append(c)
    return (winners[0] if len(winners) == 1 else None), winners


def discover_power_type_signedness(view, id_to_rec, *, cell, anchors) -> bool:
    """The signed int32 reading of power_type is admissible only when a STATIC health-cost anchor
    (expected_signed == -2) reads 0xFFFFFFFE at `cell`. No anchor -> stay raw_only (return False)."""
    if not anchors:
        return False
    for a in anchors:
        rec = id_to_rec.get(a["spell_id"])
        if rec is None or rec.u32(cell) != 0xFFFFFFFE or a.get("expected_signed") != -2:
            return False
    return True


def three_part_budget(*, serialized_bytes, peak_rss_mb, elapsed_s, ceilings) -> dict:
    """within_budget requires ALL THREE of serialized bytes, subprocess peak RSS, and elapsed to be
    under ceiling (the shipped code estimated raw DBC bytes and ignored RSS)."""
    size_mb = round(serialized_bytes / (1024 * 1024), 2)
    breach = []
    if size_mb > ceilings["artifact_size_mb"]: breach.append("artifact_size_mb")
    if peak_rss_mb > ceilings["peak_rss_mb"]: breach.append("peak_rss_mb")
    if elapsed_s > ceilings["elapsed_s"]: breach.append("elapsed_s")
    return {"serialized_mb": size_mb, "peak_rss_mb": peak_rss_mb, "elapsed_s": elapsed_s,
            "ceilings": dict(ceilings), "within_budget": not breach, "breach": breach}
```

Then integrate into `recon_spell_mechanics`: replace the ambiguous single-cell `_discover_index_cell` call with `discover_join_pair` for each of cast/duration/range/icon (using the frozen anchor set's `{spell_id, expected_value}` triples), add the `power_type` negative-anchor scan, call `verify_source_topology` for the topology section (replacing the `has_file`-only loop), and compute `budget` via `three_part_budget` from the **serialized** projection estimate + subprocess `ru_maxrss` + elapsed. The `proposed_policy_delta` now names the four discovered join index cells, the `SpellIcon.path` string cell, and the `power_type` signedness verdict. Recon still writes no policy.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_spell_mechanics_recon_e0r.py tests/test_spell_mechanics_recon.py -v`
Expected: PASS (new discovery/budget tests pass; the existing recon tests are updated in the same commit to the shared-topology + three-part-budget shapes, each changed assertion enumerated in the commit body).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/spell_mechanics.py tests/test_spell_mechanics_recon_e0r.py tests/test_spell_mechanics_recon.py
git commit -m "M1.14E0R Task 5: recon joined-pair discovery (4 joins) + static power_type negative anchor + three-part budget"
```

---

## Task 6: Streaming compact-raw v3 producer + `policy_ref` + icon catalog

**Files:**
- Rename: `git mv coa_client_extract/spell_v2.py coa_client_extract/spell_record.py`
- Create: `coa_client_extract/spell_icons.py`
- Test: `tests/test_spell_record.py`, `tests/test_spell_icons.py`

**Interfaces:**
- Consumes: `contracts.policy_ref`/`policy_ref_component`, `spell_proof`, `spell_layout` (v2).
- Produces: `iter_spell_records(spell_view, side_views, *, policy, provenance) -> Iterator[dict]` streaming compact `coa-client-spell-v3` rows (identity + normalized `mechanics` + attribution + a `raw` compact block; each field carries a `policy_ref`, no evidence text); the four-part join promotion gate; `iter_icon_catalog(spell_view, side_views, *, policy) -> Iterator[dict]` (`coa-client-spell-icons-v1`, full-table domain, dedup asset entries).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spell_record.py
import types
from coa_client_extract.spell_record import iter_spell_records
from coa_client_extract.contracts import policy_ref
# reuse the v2 policy + synthetic DBC builders from the Task 2/existing spell_v2 fixtures
from tests._spell_fixtures import v2_policy, spell_dbc, side_views   # a small shared fixture module


def test_iter_spell_records_is_a_generator_and_compact_raw():
    gen = iter_spell_records(spell_dbc(), side_views(), policy=v2_policy(),
                             provenance={"effective_archive": "patch-T.MPQ"})
    assert isinstance(gen, types.GeneratorType)          # streaming, not a materialized list
    rows = list(gen)
    r = rows[0]
    assert r["schema_version"] == "coa-client-spell-v3"
    # a normalized value is present ONLY with its compact raw retained
    assert r["mechanics"]["power_type"] == 3
    assert r["raw"]["power_type"]["raw_u32"] == 3 and r["raw"]["power_type"]["policy_ref"] == policy_ref("Spell", "power_type")
    # no free-form evidence text leaks into the row
    assert "evidence" not in r["raw"]["power_type"] and "evidence_ref" not in r["raw"]["power_type"]


def test_raw_only_join_withholds_normalized_but_keeps_compact_raw():
    rows = list(iter_spell_records(spell_dbc(), side_views(), policy=v2_policy(raw_only_cast=True),
                                   provenance={"effective_archive": "patch-T.MPQ"}))
    r = rows[0]
    assert r["mechanics"]["cast_time_ms"] is None                      # withheld
    assert r["raw"]["cast_time_ms"]["state"] in ("resolved", "not_applicable")   # compact raw retained
```

```python
# tests/test_spell_icons.py
from coa_client_extract.spell_icons import iter_icon_catalog
from tests._spell_fixtures import v2_icon_policy, spell_dbc, icon_side_views


def test_icon_catalog_full_domain_dedups_assets():
    rows = list(iter_icon_catalog(spell_dbc(), icon_side_views(), policy=v2_icon_policy()))
    by_id = {r["spell_id"]: r for r in rows}
    assert by_id[805775]["client_path"].endswith(".blp")
    assert by_id[805775]["asset_status"] in {"source_only", "placeholder"}
    # two spells sharing icon 100 produce one deduplicated source asset hash
    assert by_id[805775]["source_asset_sha256"] == by_id[133]["source_asset_sha256"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_spell_record.py tests/test_spell_icons.py -v`
Expected: FAIL with `ModuleNotFoundError` (module renamed / not yet created).

- [ ] **Step 3: Port `spell_v2.py` to a streaming `spell_record.py` + add `spell_icons.py`**

```python
# coa_client_extract/spell_record.py  (key changes vs the ported spell_v2.py)
SCHEMA = "coa-client-spell-v3"


def _compact(env_dict: dict, *, policy_ref_str: str) -> dict:
    """A compact raw cell: retain raw + state + a policy_ref, DROP the per-row proof/evidence text
    (Node re-derives proof/promotion from the policy via policy_ref)."""
    return {"state": env_dict["state"], "raw_u32": env_dict.get("raw_u32"),
            "decoded_reason": env_dict["decoded_reason"], "policy_ref": policy_ref_str}


def _join_normalized(join, idx_fp, id_fp, val_fp, jo) -> bool:
    """The exact four-part predicate (design A1)."""
    return (join.promotion == "normalized"
            and idx_fp.promotion == "normalized" and id_fp.promotion == "normalized"
            and val_fp.promotion == "normalized"
            and semantic_promotion_eligible(jo.composed_proof) and jo.state == "resolved")


def iter_spell_records(spell_view, side_views, *, policy, provenance):
    sf = policy.tables["Spell"]["fields"]
    # ... build side_id_maps once (as in spell_v2) ...
    for rec in spell_view.records():
        raw: dict = {}
        mech: dict = {}
        for name in ("power_type", "school_mask"):
            fp = sf[name]
            env = make_domain_gated_envelope(rec.u32(fp.cell), kind=fp.kind, proof=_proof(fp),
                                             evidence_ref=policy_ref("Spell", name), refine=_refiner(name, policy))
            raw[name] = _compact(env.to_dict(), policy_ref_str=policy_ref("Spell", name))
            mech[name] = env.decoded["value"] if (fp.promotion == "normalized" and env.decoded) else None
        for jname, join in policy.joins.items():
            value, jo_dict, jo = _resolve_join(rec, jname, join, sf, policy, side_views)
            idx_fp, id_fp, val_fp = _join_fps(join, policy)
            mech[jname] = value if _join_normalized(join, idx_fp, id_fp, val_fp, jo) else None
            raw[jname] = {"state": jo_dict["state"], "decoded_reason": jo_dict["decoded_reason"],
                          "components": {k: _compact(v, policy_ref_str=policy_ref_component(jname, k))
                                         for k, v in jo_dict["components"].items()}}
        yield {"schema_version": SCHEMA, "spell_id": rec.u32(sf["id"].cell), "name": _name(rec, sf, spell_view),
               "mechanics": mech, "raw": raw, "coa_attribution": _attr(rec, sf, provenance)}
```

```python
# coa_client_extract/spell_icons.py  (complete, key shape)
from .spell_proof import make_string_observation, make_string_join, FieldProof
from .contracts import policy_ref_component
import hashlib

SCHEMA = "coa-client-spell-icons-v1"


def iter_icon_catalog(spell_view, side_views, *, policy):
    """coa-client-spell-icons-v1 over the FULL-table domain (every spell whose icon join resolves),
    dedup asset entries by client_path. Emits {spell_id, spell_icon_id, client_path, source_asset_sha256,
    source_archive, asset_status, readiness}."""
    join = policy.joins["spell_icon_id"]
    icon_view = side_views.get(join.side_table)
    id_cell = policy.tables[join.side_table]["fields"]["id"].cell
    path_cell = policy.tables[join.side_table]["fields"][join.side_value_field].cell
    by_id = {r.u32(id_cell): r for r in icon_view.records()} if icon_view else {}
    asset_cache: dict[str, str] = {}
    idx_cell = policy.tables["Spell"]["fields"][join.index_field].cell
    for rec in spell_view.records():
        spell_id = rec.u32(policy.tables["Spell"]["fields"]["id"].cell)
        fk = rec.u32(idx_cell) if idx_cell is not None else 0
        side = by_id.get(fk)
        client_path = icon_view.read_string(side.u32(path_cell)) if side else None
        if client_path is None:
            yield {"schema_version": SCHEMA, "spell_id": spell_id, "spell_icon_id": fk,
                   "client_path": None, "asset_status": "missing", "readiness": "unavailable"}
            continue
        sha = asset_cache.setdefault(client_path, hashlib.sha256(client_path.encode()).hexdigest())
        yield {"schema_version": SCHEMA, "spell_id": spell_id, "spell_icon_id": fk,
               "client_path": client_path, "source_asset_sha256": sha, "source_archive": "client",
               "asset_status": "source_only", "readiness": "available"}
```

Update all `spell_v2`/`build_spell_v2_records` importers (`cli.py`, tests) to `spell_record`/`iter_spell_records`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_spell_record.py tests/test_spell_icons.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/spell_record.py coa_client_extract/spell_icons.py \
        tests/test_spell_record.py tests/test_spell_icons.py tests/_spell_fixtures.py coa_client_extract/cli.py
git commit -m "M1.14E0R Task 6: streaming compact-raw v3 producer + policy_ref + full-domain icon catalog"
```

---

## Task 7: Node projection-v3 — independent numeric/string verification via `policy_ref`

**Files:**
- Modify: `coa_scraper/scripts/lib/mechanics-projection.mjs`
- Create: `coa_scraper/config/spell_layout.lock.json` (placeholder digest until the Task 8 gate rebinds it)
- Test: `coa_scraper/tests/mechanics-projection-e0r.test.mjs`

**Interfaces:**
- Produces: `verifyRowAgainstPolicy(row, policyDoc)` — resolves each field's `policy_ref`, re-decodes numeric `raw_u32` (`Int32`/`Uint32`/`Float32`), verifies string `resolved` equality, recomputes the join predicate, and throws unless the producer's normalized value agrees; `assertPolicyLock(policyDoc, lock)` — rejects a policy whose `sha256` ≠ the committed lock.

- [ ] **Step 1: Write the failing test**

```javascript
// coa_scraper/tests/mechanics-projection-e0r.test.mjs
import { test } from "node:test";
import assert from "node:assert";
import { verifyRowAgainstPolicy, assertPolicyLock } from "../scripts/lib/mechanics-projection.mjs";

const policy = { sha256: "abc", tables: { Spell: { fields: { power_type: { kind: "int32", promotion: "normalized" } } } } };

test("rejects a numeric value that disagrees with a re-decode of its raw", () => {
  const row = { spell_id: 1, mechanics: { power_type: 5 },
    raw: { power_type: { state: "present", raw_u32: 3, decoded_reason: "decoded",
                         policy_ref: "/tables/Spell/fields/power_type" } } };
  assert.throws(() => verifyRowAgainstPolicy(row, policy), /power_type.*re-decode/);
});

test("accepts a numeric value that matches the re-decode", () => {
  const row = { spell_id: 1, mechanics: { power_type: 3 },
    raw: { power_type: { state: "present", raw_u32: 3, decoded_reason: "decoded",
                         policy_ref: "/tables/Spell/fields/power_type" } } };
  assert.doesNotThrow(() => verifyRowAgainstPolicy(row, policy));
});

test("policy lock mismatch is rejected", () => {
  assert.throws(() => assertPolicyLock({ sha256: "zzz" }, { sha256: "abc" }), /policy lock/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test coa_scraper/tests/mechanics-projection-e0r.test.mjs`
Expected: FAIL — `verifyRowAgainstPolicy`/`assertPolicyLock` are not exported.

- [ ] **Step 3: Implement the independent verifier in `mechanics-projection.mjs`**

```javascript
// coa_scraper/scripts/lib/mechanics-projection.mjs  (append)
function resolvePolicyRef(doc, ref) {
  return ref.split("/").slice(1).reduce((n, t) => n[t.replace(/~1/g, "/").replace(/~0/g, "~")], doc);
}

function redecode(rawU32, kind) {
  const buf = Buffer.alloc(4); buf.writeUInt32LE(rawU32 >>> 0, 0);
  if (kind === "int32") return buf.readInt32LE(0);
  if (kind === "float") return buf.readFloatLE(0);
  return buf.readUInt32LE(0);
}

export function assertPolicyLock(policyDoc, lock) {
  if (!lock || policyDoc.sha256 !== lock.sha256) {
    throw new MechanicsBuildError(`policy lock mismatch: policy ${policyDoc.sha256} != lock ${lock?.sha256}`);
  }
}

export function verifyRowAgainstPolicy(row, policyDoc) {
  for (const [field, value] of Object.entries(row.mechanics || {})) {
    if (value === null || value === undefined) continue;      // withheld: nothing to verify
    const obs = (row.raw || {})[field];
    if (!obs || !obs.policy_ref) throw new MechanicsBuildError(`projection ${row.spell_id}: ${field} populated without a policy_ref`);
    const pol = resolvePolicyRef(policyDoc, obs.policy_ref);
    if (pol.promotion !== "normalized") throw new MechanicsBuildError(`projection ${row.spell_id}: ${field} promoted under raw_only policy`);
    if (pol.kind === "string") {
      if (value !== obs.resolved) throw new MechanicsBuildError(`projection ${row.spell_id}: ${field} != StringObservation.resolved`);
    } else {
      if (obs.decoded_reason !== "decoded") throw new MechanicsBuildError(`projection ${row.spell_id}: ${field} decoded_reason ${obs.decoded_reason}`);
      if (redecode(obs.raw_u32, pol.kind) !== value) throw new MechanicsBuildError(`projection ${row.spell_id}: ${field} re-decode disagrees`);
    }
  }
}
```

Wire `verifyRowAgainstPolicy` + `assertPolicyLock` into `loadAndValidateProjection` (load the policy child + the committed lock; call per row), and reject a manifest lacking the policy child (pre-E0R).

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test coa_scraper/tests/mechanics-projection-e0r.test.mjs coa_scraper/tests/mechanics-projection.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add coa_scraper/scripts/lib/mechanics-projection.mjs coa_scraper/config/spell_layout.lock.json \
        coa_scraper/tests/mechanics-projection-e0r.test.mjs
git commit -m "M1.14E0R Task 7: Node projection-v3 independent verify (numeric re-decode + string resolved + policy lock)"
```

---

## Task 8: Recon CLI + the recon-adjudication artifacts (HARD HOLD — manual gate follows)

**Files:**
- Modify: `coa_client_extract/cli.py`
- Test: `tests/test_e0r_recon_cli.py`, `tests/test_e0r_client.py` (`@pytest.mark.client`)

**Interfaces:**
- Produces: `mechanics-recon` subcommand emitting the report + `proposed_policy_delta` (exit `3` blocked / `4` review_required / `0` verified); it **writes no policy**.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r_recon_cli.py
import json, subprocess, sys
from pathlib import Path


def test_recon_reports_delta_for_all_four_joins_and_power_type(tmp_path, monkeypatch):
    # Uses the synthetic StormLib-less backend fixture; asserts the delta shape + exit 4 when unbound.
    from coa_client_extract.spell_mechanics import recon_spell_mechanics
    report = recon_spell_mechanics(**_synthetic_unbound_kwargs(tmp_path))
    assert report["status"] == "review_required"
    delta = report["proposed_policy_delta"]
    assert {"casting_time_index", "duration_index", "range_index", "spell_icon_id"} <= set(delta)
    assert "power_type_signed" in delta
```

- [ ] **Step 2–4:** red → implement the `mechanics-recon` subcommand (exit 3/4/0 per lifecycle; exit 2 without StormLib) and the synthetic-backend recon test → green (`pytest tests/test_e0r_recon_cli.py -v`; `pytest -m client -q` on the real client asserts the delta is stable).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/cli.py tests/test_e0r_recon_cli.py tests/test_e0r_client.py
git commit -m "M1.14E0R Task 8: mechanics-recon CLI (proposes delta for 4 joins + icon string + power_type anchor; never writes policy)"
```

> ### ⛔ HUMAN CHECK-IN 1 — recon adjudication (mandatory, load-bearing; blocks Tasks 9+)
> **This gate produces no code — a human authors frozen, client-bound data an agent cannot.** It needs
> the local Ascension client + a built StormLib. If you cannot run the real client here, STOP and hand
> this to the maintainer before Task 9.
>
> - [ ] **Run recon against the real client:**
>   ```bash
>   COA_CLIENT_ROOT=/path/to/ascension-live/Data \
>   python -m coa_client_extract mechanics-recon --client-root "$COA_CLIENT_ROOT" --out reports/client_extract
>   ```
> - [ ] **Review `proposed_policy_delta`** — the four join `(index, side_value)` cells + evidence, the
>   `SpellIcon.path` layout/interpretation + icon-catalog coverage, the `power_type` static negative
>   anchor verdict, and the full topology. All findings must be clean on required tables.
> - [ ] **Author `coa_client_extract/data/spell_layout_v2.json`** — fill the four join index cells + the
>   icon path cell, set each join's `promotion` (`normalized` only when uniquely value-anchor-proven;
>   ambiguous → `cell: null`, `raw_only`), author the structured `bound` for every required table, set
>   `power_type` `promotion: normalized` **only** if the static negative anchor held (else `raw_only`),
>   and set `reviewed: true`.
> - [ ] **Author `coa_scraper/config/spell_layout.lock.json`** — `{schema_version, client_build, sha256}`
>   pinning the reviewed policy's hash.
> - [ ] **Re-run recon → `verified` (exit 0)**, then commit the frozen data:
>   ```bash
>   git add coa_client_extract/data/spell_layout_v2.json coa_scraper/config/spell_layout.lock.json
>   git commit -m "M1.14E0R: freeze reviewed client-bound spell-layout-v2 + policy lock from real-client recon"
>   ```

---

## Task 9: Transactional publication — registry, candidate/final trust digest, cross-child, icon bundle, lock

**Files:**
- Modify: `coa_client_extract/publish.py`, `coa_client_extract/manifest.py`
- Test: `tests/test_publish_e0r.py`

**Interfaces:**
- Consumes: `contracts.TRUST_CRITICAL_MANIFEST_KEYS`, `contracts.CROSS_CHILD_CHECKS`, `contracts.ICON_ASSET_STATUSES`.
- Produces: `candidate_trust_sha256(manifest) -> str`; `validate_candidate_generation(gen_dir) -> dict` (per-child + cross-child merge-join + icon-bundle enforcement; raises `ResolveError` on any failure); `finalize_and_publish(writer, *, base_manifest, binding, validation, budget) -> dict` (final manifest changes only `/validation`+`/budget`, must reproduce the candidate digest; holds a process file lock over predecessor-read → pointer replace; pointer written last); `build_manifest_v3(...)` (adds `publication_state`, `candidate_trust_sha256`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_publish_e0r.py
import json
import pytest
from pathlib import Path
from coa_client_extract.publish import (
    GenerationWriter, candidate_trust_sha256, validate_candidate_generation, ResolveError,
)


def _stage(root: Path):
    gw = GenerationWriter(root)
    gw.add_jsonl("coa_client_spell.jsonl", [{"schema_version": "coa-client-spell-v3", "spell_id": 1,
                 "coa_attribution": {"is_coa": True}, "mechanics": {}, "raw": {}}], schema_version="coa-client-spell-v3")
    gw.add_jsonl("coa_client_spell_coa.jsonl", [{"schema_version": "coa-client-spell-projection-v3",
                 "spell_id": 1, "coa_attribution": {"is_coa": True}, "mechanics": {}, "raw": {}}],
                 schema_version="coa-client-spell-projection-v3")
    gw.add_jsonl("coa_client_spell_icons.jsonl", [{"schema_version": "coa-client-spell-icons-v1",
                 "spell_id": 1, "asset_status": "source_only"}], schema_version="coa-client-spell-icons-v1")
    gw.add_json("spell_layout_v2.json", {"schema_version": "coa-spell-layout-v2"}, schema_version="coa-spell-layout-v2")
    return gw


def test_trust_digest_excludes_validation_and_budget(tmp_path):
    base = {"schema_version": "coa-client-extract-manifest-v3", "generation_id": "g", "children": {},
            "binding": {}, "outputs": {}, "unknown_symbol_inventory": {}, "predecessor_generation_id": None}
    d1 = candidate_trust_sha256({**base, "validation": {"ok": True}, "budget": {"within_budget": True}})
    d2 = candidate_trust_sha256({**base, "validation": {"ok": False}, "budget": {"within_budget": False}})
    assert d1 == d2                                            # /validation + /budget don't move the digest
    d3 = candidate_trust_sha256({**base, "binding": {"x": 1}})
    assert d3 != d1                                            # a trust-critical field does


def test_cross_child_rejects_is_coa_row_absent_from_projection(tmp_path):
    gw = _stage(tmp_path)
    # add a second is_coa full row with no projection row
    (gw.gen_dir / "coa_client_spell.jsonl").write_text(
        (gw.gen_dir / "coa_client_spell.jsonl").read_text() +
        json.dumps({"schema_version": "coa-client-spell-v3", "spell_id": 2,
                    "coa_attribution": {"is_coa": True}, "mechanics": {}, "raw": {}}) + "\n")
    gw.publish_candidate(base_manifest={}, binding={})
    with pytest.raises(ResolveError, match="projection_is_coa_subset"):
        validate_candidate_generation(gw.gen_dir)


def test_icon_bundle_required_when_any_converted(tmp_path):
    gw = _stage(tmp_path)
    (gw.gen_dir / "coa_client_spell_icons.jsonl").write_text(
        json.dumps({"schema_version": "coa-client-spell-icons-v1", "spell_id": 1,
                    "asset_status": "converted", "converted_ref": "icons.tar#a.png"}) + "\n")
    gw.publish_candidate(base_manifest={}, binding={})
    with pytest.raises(ResolveError, match="icon bundle required"):
        validate_candidate_generation(gw.gen_dir)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_publish_e0r.py -v`
Expected: FAIL with `ImportError: cannot import name 'candidate_trust_sha256'`.

- [ ] **Step 3: Implement the transactional additions in `publish.py`**

```python
# coa_client_extract/publish.py  (append / integrate)
import fcntl
from .contracts import TRUST_CRITICAL_MANIFEST_KEYS, ICON_ASSET_STATUSES

REQUIRED_CHILDREN = ("coa_client_spell.jsonl", "coa_client_spell_coa.jsonl",
                     "coa_client_spell_projection.manifest.json", "coa_client_spell_icons.jsonl",
                     "coa_client_content.jsonl", "coa_client_archive_plan.json",
                     "coa_client_advancement.jsonl", "coa_client_class_types.jsonl",
                     "coa_client_tab_types.jsonl", "coa_client_essence.jsonl", "spell_layout_v2.json")


def candidate_trust_sha256(manifest: dict) -> str:
    trust = {k: manifest[k] for k in sorted(TRUST_CRITICAL_MANIFEST_KEYS) if k in manifest}
    return _sha256(json.dumps(trust, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def _read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def _cross_child(gen_dir: Path) -> None:
    """Streaming merge-join over sorted spell_id across the three spell children (design A5)."""
    full = list(_read_jsonl(gen_dir / "coa_client_spell.jsonl"))
    proj_ids = {r["spell_id"] for r in _read_jsonl(gen_dir / "coa_client_spell_coa.jsonl")}
    icon_ids = {r["spell_id"] for r in _read_jsonl(gen_dir / "coa_client_spell_icons.jsonl")}
    is_coa = {r["spell_id"] for r in full if r.get("coa_attribution", {}).get("is_coa") is True}
    if is_coa - proj_ids:
        raise ResolveError(f"projection_is_coa_subset: {sorted(is_coa - proj_ids)[:5]} missing from projection")
    if proj_ids - is_coa:
        raise ResolveError(f"projection_within_domain: {sorted(proj_ids - is_coa)[:5]} outside is_coa domain")
    ids = [r["spell_id"] for r in full]
    if ids != sorted(set(ids)):
        raise ResolveError("sorted_unique_ids: full table has duplicate/out-of-order spell_id")
    if {r["spell_id"] for r in full} - icon_ids:
        raise ResolveError("icons_agree: some spells lack an icon-catalog row")


def _icon_bundle(gen_dir: Path, children: dict) -> None:
    rows = list(_read_jsonl(gen_dir / "coa_client_spell_icons.jsonl"))
    for r in rows:
        if r.get("asset_status") not in ICON_ASSET_STATUSES:
            raise ResolveError(f"icon asset_status {r.get('asset_status')!r} not in {ICON_ASSET_STATUSES}")
        if r.get("asset_status") != "converted" and r.get("converted_ref"):
            raise ResolveError("non-converted icon row carries a converted_ref")
    if any(r.get("asset_status") == "converted" for r in rows) and "coa_client_spell_icons.bundle.tar" not in children:
        raise ResolveError("icon bundle required: a converted row exists but no bundle child is registered")


def validate_candidate_generation(gen_dir: Path) -> dict:
    active = _resolve_by_path(gen_dir)          # per-child hash/bytes/records/schema (reuse resolver core)
    for name in REQUIRED_CHILDREN:
        if name not in active["children"]:
            raise ResolveError(f"required child {name!r} missing from the candidate generation")
    _cross_child(gen_dir)
    _icon_bundle(gen_dir, active["manifest"]["children"])
    return active
```

`GenerationWriter.publish_candidate` writes the candidate manifest (`publication_state: "candidate"`, `candidate_trust_sha256`) **without** touching the pointer. `finalize_and_publish` reopens under an `fcntl.flock` on a `root/.publish.lock`, asserts `candidate_trust_sha256(final) == candidate digest` (only `/validation`+`/budget` added), writes the final manifest, revalidates the predecessor, then `os.replace`s the pointer last. `resolve_active_generation` refuses any manifest whose `publication_state == "candidate"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_publish_e0r.py tests/test_publish_generation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/publish.py coa_client_extract/manifest.py tests/test_publish_e0r.py
git commit -m "M1.14E0R Task 9: transactional candidate->pointer publication (trust digest, cross-child merge-join, icon bundle, process lock)"
```

---

## Task 10: Streaming `regenerate` end-to-end + Node candidate validation + `generation.mjs` streaming

**Files:**
- Modify: `coa_client_extract/cli.py`, `coa_scraper/scripts/lib/generation.mjs`
- Test: `tests/test_e0r_end_to_end.py`, `coa_scraper/tests/generation-e0r.test.mjs`

**Interfaces:**
- Produces: `regenerate()` streams every child into the generation, runs `verify_source_topology` + `topology_matches_bound` as the hard hold, stages the candidate, runs the Python **and** Node validators by path, records the three-part budget, and publishes the pointer last; `generation.mjs` validates line-by-line (no row-array materialization) and rejects a `publication_state: candidate` or pre-E0R generation.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r_end_to_end.py
import subprocess, sys
from pathlib import Path
from coa_client_extract.publish import resolve_active_generation


def test_regenerate_streams_stages_and_publishes(tmp_path, synthetic_client):
    manifest = _run_regenerate(tmp_path, synthetic_client)     # uses the synthetic StormLib-less backend
    active = resolve_active_generation(tmp_path / "dist")
    assert active["manifest"]["schema_version"] == "coa-client-extract-manifest-v3"
    assert active["manifest"]["publication_state"] == "published"
    assert active["manifest"]["budget"]["within_budget"] is True
    # Node resolves + validates the same generation
    r = subprocess.run([sys.executable and "node", "coa_scraper/scripts/lib/generation.mjs",
                        str(tmp_path / "dist")], capture_output=True, text=True)
    assert r.returncode == 0
```

- [ ] **Step 2–4:** red → implement (iterator writers in `cli.regenerate`; the hard hold via the shared verifier; the candidate → Node-validate → publish sequence; `generation.mjs` streaming line-by-line validation + `publication_state`/pre-E0R rejection) → green (`pytest tests/test_e0r_end_to_end.py -v`; `node --test coa_scraper/tests/generation-e0r.test.mjs`).

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/cli.py coa_scraper/scripts/lib/generation.mjs \
        tests/test_e0r_end_to_end.py coa_scraper/tests/generation-e0r.test.mjs
git commit -m "M1.14E0R Task 10: streaming regenerate + shared hard hold + Node candidate validation + generation.mjs line-by-line"
```

---

## Task 11: AscensionDB hard-cut from canonical mechanics + negative-dependency gate

**Files:**
- Modify: `coa_scraper/scripts/lib/mechanics-reconcile.mjs`, `build-mechanics-artifacts.mjs`, `coa_scraper/package.json`, root `package.json`
- Create: `coa_scraper/scripts/lib/jsonl.mjs`
- Test: `coa_scraper/tests/no-ascensiondb.test.mjs`

**Interfaces:**
- Produces: canonical `TIERS = ["client_dbc", "verified_builder", "inferred"]` (no `ascension_db`); `buildCanonicalMechanics({ entries, spellRows, projection })` — a signature with **no** `dbRows` parameter; `readJsonl` re-exported from `jsonl.mjs`; `pipeline:m1.9` renamed `legacy:ascensiondb`.

- [ ] **Step 1: Write the failing test**

```javascript
// coa_scraper/tests/no-ascensiondb.test.mjs
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import { TIERS } from "../scripts/lib/mechanics-reconcile.mjs";

test("ascension_db is not a canonical reconciliation tier", () => {
  assert.ok(!TIERS.includes("ascension_db"));
});

test("canonical build script passes no --db-spells and no db.ascension.gg", () => {
  const pkg = JSON.parse(fs.readFileSync(new URL("../package.json", import.meta.url)));
  assert.ok(!pkg.scripts["build-mechanics"].includes("--db-spells"));
  assert.ok(pkg.scripts["build-mechanics"].includes("--client-extract-pointer"));
  assert.ok(!("pipeline:m1.9" in pkg.scripts) || pkg.scripts["pipeline:m1.9"] === undefined);
  assert.ok("legacy:ascensiondb" in pkg.scripts);
});

test("canonical build fn signature cannot accept db rows", async () => {
  const mod = await import("../scripts/build-mechanics-artifacts.mjs");
  assert.ok(!/dbRows|db-spells/.test(mod.buildCanonicalMechanics.toString()));
});
```

- [ ] **Step 2–4:** red → implement (drop `ascension_db` from `TIERS`; move `readJsonl` to `jsonl.mjs` and re-point imports; add `buildCanonicalMechanics` with no db parameter + keep a `buildLegacyMechanics` wrapper for the fallback; edit `build-mechanics` to `--client-extract-pointer` + no `--db-spells` in both `package.json`s; rename `pipeline:m1.9` → `legacy:ascensiondb`) → green (`node --test coa_scraper/tests/no-ascensiondb.test.mjs`; `npm run build-mechanics` runs pointer-only).

- [ ] **Step 5: Commit**

```bash
git add coa_scraper/scripts/lib/mechanics-reconcile.mjs coa_scraper/scripts/lib/jsonl.mjs \
        coa_scraper/scripts/build-mechanics-artifacts.mjs coa_scraper/package.json package.json \
        coa_scraper/tests/no-ascensiondb.test.mjs
git commit -m "M1.14E0R Task 11: hard-cut AscensionDB from canonical mechanics + negative-dependency gate"
```

---

## Task 12: `coa-mechanics-v2` — nullable costs + field readiness + reason codes

**Files:**
- Modify: `coa_meta/mechanics.py`, `coa_meta/mechanics_repository.py`, `coa_scraper/scripts/build-mechanics-artifacts.mjs`
- Test: `tests/test_mechanics_v2.py`, `coa_scraper/tests/mechanics-v2.test.mjs`

**Interfaces:**
- Produces: `MECHANICS_SCHEMA_VERSION = "coa-mechanics-v2"`; `MechanicRecord.costs: dict | None`; `field_readiness: dict[str, {status, reason_code}]`; `mechanic_from_raw` rejects `coa-mechanics-v1`; the Node builder writes `costs: null` when unknown (never `{}`) with the missing-vs-zero repair.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mechanics_v2.py
import pytest
from coa_meta.mechanics import mechanic_from_raw, MechanicsLoadError, MECHANICS_SCHEMA_VERSION


def _rec(**over):
    base = {"schema_version": "coa-mechanics-v2", "spell_id": 5, "name": "X", "kind": "ability"}
    base.update(over); return base


def test_unknown_costs_is_none_not_empty_dict():
    r = mechanic_from_raw(_rec(costs=None, field_readiness={"costs": {"status": "unavailable",
                          "reason_code": "pending_e1_operand"}}))
    assert r.costs is None                                     # unknown != free {}
    assert r.field_readiness["costs"]["status"] == "unavailable"


def test_verified_empty_costs_survives():
    r = mechanic_from_raw(_rec(costs={}, field_readiness={"costs": {"status": "verified_empty",
                          "reason_code": "not_extracted"}}))
    assert r.costs == {} and r.field_readiness["costs"]["status"] == "verified_empty"


def test_v1_is_rejected():
    with pytest.raises(MechanicsLoadError, match="coa-mechanics-v2"):
        mechanic_from_raw({"schema_version": "coa-mechanics-v1", "spell_id": 1, "name": "n", "kind": "k"})
```

- [ ] **Step 2–4:** red → implement (`MECHANICS_SCHEMA_VERSION = "coa-mechanics-v2"`; make `costs` `dict | None` — parse `None` as `None`, `{}` as `{}`; add a `field_readiness` field validated against `contracts.READINESS_STATUSES`/`READINESS_REASON_CODES`; reject v1; repair the Node `numberOrNull(null) -> null` so unknown timers/costs serialize as `null`) → green (`pytest tests/test_mechanics_v2.py -v`; `node --test coa_scraper/tests/mechanics-v2.test.mjs`).

- [ ] **Step 5: Commit**

```bash
git add coa_meta/mechanics.py coa_meta/mechanics_repository.py \
        coa_scraper/scripts/build-mechanics-artifacts.mjs tests/test_mechanics_v2.py coa_scraper/tests/mechanics-v2.test.mjs
git commit -m "M1.14E0R Task 12: coa-mechanics-v2 (nullable costs + field readiness + reason codes + v1 rejection)"
```

---

## Task 13: Consumer fail-closed interlock (behavioral)

**Files:**
- Modify: `coa_meta/action_catalog.py`, `coa_meta/simulation.py`, `coa_meta/reporting.py`
- Test: `tests/test_action_catalog_interlock.py`, `tests/test_simulation_interlock.py`

**Interfaces:**
- Produces: `CatalogAction.cooldown_ms: int | None`, `gcd_ms: int | None`, `costs: dict | None`; `ActionCatalog.quantitative_readiness -> {ready: bool, blocking: list[{action_key, field, reason_code}]}`; `simulate_apl`/combat conversion raise `QuantitativeScopeUnready` when `not ready`; `heuristic_combat_action(node, category)` is the **only** place invented `1500`/`45_000`/estimated costs live (default-off; tagged `source: "heuristic"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_action_catalog_interlock.py
import pytest
from coa_meta.action_catalog import build_action_catalog, CatalogAction, QuantitativeScopeUnready


def test_unknown_timing_is_null_not_defaulted():
    action = _catalog_action_for(_node(spell_id=5), mechanic=_mech(cooldown_ms=None, gcd_ms=None, costs=None))
    assert action.cooldown_ms is None and action.gcd_ms is None and action.costs is None   # never 0/1500/{}


def test_verified_zero_and_1500_are_preserved():
    action = _catalog_action_for(_node(spell_id=6), mechanic=_mech(cooldown_ms=0, gcd_ms=1500, costs={}))
    assert action.cooldown_ms == 0 and action.gcd_ms == 1500 and action.costs == {}


def test_quantitative_scope_fails_closed_when_any_action_unready():
    catalog = build_action_catalog(_nodes_with_one_unready(), _repo(), role="dps", encounter=_enc())
    rd = catalog.quantitative_readiness
    assert rd["ready"] is False and rd["blocking"][0]["field"] in ("gcd_ms", "cooldown_ms", "costs")
    with pytest.raises(QuantitativeScopeUnready):
        catalog.assert_quantitative_ready()          # no silent per-action drop
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_action_catalog_interlock.py -v`
Expected: FAIL — `CatalogAction` timers are non-null `int` and there is no `quantitative_readiness`/`QuantitativeScopeUnready`.

- [ ] **Step 3: Implement the interlock**

```python
# coa_meta/action_catalog.py  (changed regions)
class QuantitativeScopeUnready(RuntimeError):
    pass


@dataclass(frozen=True)
class CatalogAction:
    # ... existing fields ...
    costs: dict[str, float] | None
    cooldown_ms: int | None
    gcd_ms: int | None
    # ...


def _catalog_action_from_mechanic(node, mechanic, ...):
    return CatalogAction(
        # ... unchanged fields ...
        costs=mechanic.costs,                        # was dict(mechanic.costs) with {} coercion
        cooldown_ms=mechanic.cooldown_ms,            # was `mechanic.cooldown_ms or 0`
        gcd_ms=mechanic.gcd_ms,                       # was `... if not None else 1500`
    )
```

```python
# ActionCatalog gains readiness (design B5):
_LOAD_BEARING = ("gcd_ms", "cooldown_ms", "costs")


@property
def quantitative_readiness(self) -> dict:
    blocking = []
    for a in self.actions:
        for field in _LOAD_BEARING:
            if getattr(a, field) is None:
                blocking.append({"action_key": a.action_key, "field": field, "reason_code": "pending_e1_operand"})
    return {"ready": not blocking, "blocking": blocking}


def assert_quantitative_ready(self) -> None:
    rd = self.quantitative_readiness
    if not rd["ready"]:
        raise QuantitativeScopeUnready(f"{len(rd['blocking'])} action(s) lack load-bearing data")
```

In `simulation.py`, move the invented `gcd_ms=1500`/`cooldown_ms=45_000`/`_estimated_costs` into `heuristic_combat_action(node, category)` (tagged `source="heuristic"`), default the simulator off unless an explicit `mode="heuristic"` is passed, and call `catalog.assert_quantitative_ready()` before a quantitative loop. `reporting.py` labels the tooltip-inference path `heuristic`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_action_catalog_interlock.py tests/test_simulation_interlock.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add coa_meta/action_catalog.py coa_meta/simulation.py coa_meta/reporting.py \
        tests/test_action_catalog_interlock.py tests/test_simulation_interlock.py
git commit -m "M1.14E0R Task 13: consumer fail-closed interlock (nullable timers+costs, readiness gate, heuristic factory)"
```

---

## Task 14: Client-native spell icons in the guide

**Files:**
- Modify: `coa_meta/guide_assets.py`, `coa_scraper/scripts/lib/icon-assets.mjs`
- Test: `tests/test_guide_icons.py`, `coa_scraper/tests/icon-assets-e0r.test.mjs`

**Interfaces:**
- Produces: `GuideAssetCatalog(icon_catalog=<coa-client-spell-icons-v1 map>)` — resolves icons from the client catalog; when a catalog entry/asset is absent it returns a `source="placeholder"` asset, **never** an `ascension_db_remote` one. The `ASCENSIONDB_ICON_URL_TEMPLATE` and its use are deleted.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_guide_icons.py
from coa_meta.guide_assets import GuideAssetCatalog
import coa_meta.guide_assets as ga


def test_no_ascensiondb_icon_url_template():
    assert not hasattr(ga, "ASCENSIONDB_ICON_URL_TEMPLATE")


def test_absent_client_icon_is_placeholder_not_remote():
    cat = GuideAssetCatalog(icon_catalog={})           # empty client catalog
    asset = cat.icon_for(icon="Spell_Fire_Fireball", label="Fireball", spell_id=133)
    assert asset.source == "placeholder" and asset.missing is True
    assert asset.href is None or not str(asset.href).startswith("http")


def test_client_catalog_icon_is_used():
    cat = GuideAssetCatalog(icon_catalog={133: {"client_path": "Interface/Icons/Spell_Fire_Fireball.blp",
                                                 "asset_status": "source_only"}})
    asset = cat.icon_for(icon=None, label="Fireball", spell_id=133)
    assert asset.source in ("client_icon", "asset_root") and "db.ascension.gg" not in str(asset.href or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_guide_icons.py -v`
Expected: FAIL — `ASCENSIONDB_ICON_URL_TEMPLATE` still exists and `icon_for` has no `spell_id`/client-catalog path.

- [ ] **Step 3: Implement client-native icons**

- Delete `ASCENSIONDB_ICON_URL_TEMPLATE` and the `ascension_db_remote` branch in `guide_assets.py`; add an `icon_catalog` constructor arg; in `icon_for(..., spell_id=None)`, look up the client catalog by `spell_id` first (→ `source="client_icon"`, `href` from a client asset when present), else the existing `asset_root` search, else a `source="placeholder"` asset. Never construct a `db.ascension.gg` URL.
- In `icon-assets.mjs`, delete the three `https://db.ascension.gg/...` URL templates and any code that emits them; a missing asset yields a placeholder record.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_guide_icons.py -v`; `node --test coa_scraper/tests/icon-assets-e0r.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add coa_meta/guide_assets.py coa_scraper/scripts/lib/icon-assets.mjs \
        tests/test_guide_icons.py coa_scraper/tests/icon-assets-e0r.test.mjs
git commit -m "M1.14E0R Task 14: client-native spell icons (remove db.ascension.gg spell-icon fallbacks)"
```

---

## Task 15: Repo hygiene — relative manifest paths + untrack disposable outputs

**Files:**
- Modify: `coa_scraper/scripts/write-artifact-manifest.mjs`, `.gitignore`
- Test: `tests/test_e0r_hygiene.py`

**Interfaces:**
- Produces: `write-artifact-manifest.mjs` emits **repo-relative** paths only (no absolute `/home/...`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r_hygiene.py
import re
from pathlib import Path


def test_no_absolute_home_paths_in_tracked_manifest():
    p = Path("coa_scraper/reports/coa_artifact_manifest.json")
    if p.exists():
        assert not re.search(r"/home/[a-z]", p.read_text()), "machine-local absolute paths must be scrubbed"


def test_manifest_generator_emits_relative_paths(tmp_path):
    # run write-artifact-manifest.mjs against a temp tree; assert every "path" is relative
    import subprocess, json
    out = tmp_path / "m.json"
    subprocess.run(["node", "coa_scraper/scripts/write-artifact-manifest.mjs",
                    str(tmp_path), str(tmp_path), str(out)], check=True)
    doc = json.loads(out.read_text())
    for entry in _iter_paths(doc):
        assert not entry.startswith("/"), f"absolute path leaked: {entry}"
```

- [ ] **Step 2–4:** red → fix the generator to store paths relative to the repo root (`path.relative(repoRoot, abs)`); classify each E0-churn artifact as **source** / **committed fixture** / **disposable**; `git rm --cached` the disposable outputs (`.gitignore` does not untrack existing files) and add ignore rules; scrub the machine-local paths from the tracked `coa_artifact_manifest.json` → green.

- [ ] **Step 5: Commit (dedicated, intentional — do NOT mix with other tasks)**

```bash
git add coa_scraper/scripts/write-artifact-manifest.mjs .gitignore tests/test_e0r_hygiene.py
git rm --cached <each disposable generated artifact by name>   # never `git add -A`
git commit -m "M1.14E0R Task 15: relative artifact-manifest paths; untrack disposable generated data; ignore rules"
```

---

## Task 16: CI, schema/decision docs, and the recorded full real-client regenerate

**Files:**
- Create: `.github/workflows/ci.yml`, `docs/data/field-readiness-schema.md`
- Modify: `docs/DECISIONS.md`, `docs/data/client-spell-schema.md` (v3), `docs/data/mechanics-schema.md` (v2), `docs/data/client-extract-generation-schema.md` (v3), `docs/data/spell-mechanics-recon-schema.md`, `docs/data/client-dbc-reference.md`, `docs/ROADMAP.md`
- Test: `tests/test_e0r_acceptance_summary.py`

**Interfaces:**
- Produces: a CI workflow running the synthetic Python + Node suites on push/PR; `write_acceptance_summary(...)` emitting the schema-stable curated run record (`client_build`, `generation_id`, `manifest_sha256`, policy `sha256`, `extractor_commit`, `benchmark_env_id`, per-child `{sha256, byte_length, records}`, three-part budget, recon `status`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r_acceptance_summary.py
from coa_client_extract.cli import write_acceptance_summary   # or wherever it lands


def test_acceptance_summary_has_stable_fields(tmp_path):
    summary = write_acceptance_summary(tmp_path, _fake_manifest(), recon_status="verified",
                                       benchmark_env_id="local-x86-64")
    assert set(summary) >= {"client_build", "generation_id", "manifest_sha256", "policy_sha256",
                            "extractor_commit", "benchmark_env_id", "children", "budget", "recon_status"}
    assert summary["recon_status"] == "verified"
```

- [ ] **Step 2–3:** red → implement `write_acceptance_summary` + `.github/workflows/ci.yml` (checkout → `pip install -e .` → `pytest -q` → `npm --prefix coa_scraper ci` → `npm --prefix coa_scraper test`; the `client`/`stormlib` markers are excluded in CI and kept local); write the schema docs (client-spell v3, mechanics v2, generation v3, recon topology + negative anchor, the new field-readiness doc) and `DECISIONS.md` entries (evidence ≠ authorization; the generation manifest is authoritative, not a child, + candidate trust digest; full-topology hard hold; AscensionDB not a canonical source; missing ≠ default; client-native icons; explicit versioning); update `client-dbc-reference.md` confidence labels + `ROADMAP.md` (E0R inserted before E1) → green.

- [ ] **Step 4: Run every suite + record the real-client regenerate**

```bash
pytest -q                                   # synthetic
pytest -m client -q                         # real client (local only)
node --test coa_scraper/tests/*.test.mjs
# Full real-client regenerate (not just recon) — MUST be within the three-part budget:
COA_CLIENT_ROOT=/path/to/ascension-live/Data python -m coa_client_extract mechanics --client-root "$COA_CLIENT_ROOT" --out coa_scraper/dist
```

Confirm `manifest["budget"]["within_budget"] is True`; commit the hash-bound acceptance summary.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml docs/ tests/test_e0r_acceptance_summary.py \
        reports/client_extract/coa_e0r_acceptance_summary.json
git commit -m "M1.14E0R Task 16: CI + schema/decision docs + recorded full real-client regenerate within budget"
```

> ### ⛔ HUMAN CHECK-IN 2 — end of E0R
> Human review of the whole milestone against the [design](../specs/2026-07-19-m1-14-e0r-correctness-sunset-remediation-design.md) **Exit criteria**: canonical build pointer-only + AscensionDB-free; full-topology hard hold in recon **and** regenerate; `raw_only` never populates normalized + Node independent verification; transactional candidate→pointer with the trust digest + cross-child; streaming within the three-part budget with a recorded real-client regenerate; missing ≠ default with the consumer interlock; client-native icons; clean tree; CI green. On approval, E0R is ready to ff-merge and M1.14E1 planning begins against the realized interfaces.

---

## Self-Review

**Spec coverage:** design-lock invariants (T1, also the plan's Global Constraints); A1 promotion + string join (T2, T3, T6); A2 shared topology + structured bound (T2, T4, and the hard hold in T10); A3 Node boundary numeric/string via `policy_ref` + lock (T7, wired in T10); A4 streaming compact-raw + hoisted provenance + three-part budget (T5 budget, T6 producer, T10 regenerate); A5 registry + candidate/final trust digest + cross-child + icon bundle + process lock + manifest-not-a-child (T9, T10); A6 `power_type` static negative anchor (T5, adjudicated at the T8 gate); A7 hygiene (T15); B1/B2 AscensionDB hard-cut + negative-dependency gate (T11); B3 `coa-mechanics-v2` (T12); B4 icons (T6 catalog, T14 guide); B5 interlock (T13); B6 item/asset tracked (T11 quarantine + T16 docs); CI + docs + real-client regenerate (T16). Two human check-ins (recon adjudication after T8; end after T16).

**Placeholder scan:** none — `spell_layout_v2.json` join cells and `spell_layout.lock.json` are honestly authored at the T8 recon gate (a human step, code-gated), not stubbed; every code task carries full test + implementation code and a named commit; the two prose-summarized steps (T8 Step 2–4, T10/T11/T12/T15/T16 Step 2–4) each name the exact functions/files and the green command.

**Type consistency:** `contracts.policy_ref`/`policy_ref_component`/enums/`TRUST_CRITICAL_MANIFEST_KEYS`/`CROSS_CHILD_CHECKS` (T1) are consumed by T2/T6/T7/T9/T12; `JoinPolicy.promotion` + structured `bound` (T2) by T6's four-part gate and T4/T10's hard hold; `make_string_join` (T3) by T6/T14; `verify_source_topology`/`topology_matches_bound` (T4) by T5/T10; `iter_spell_records`/`iter_icon_catalog` (T6) by T9's cross-child + T14; `candidate_trust_sha256`/`validate_candidate_generation`/`REQUIRED_CHILDREN` (T9) by T10; `verifyRowAgainstPolicy`/`assertPolicyLock` (T7) by T10's Node validation; `MECHANICS_SCHEMA_VERSION = "coa-mechanics-v2"` + `field_readiness` (T12) by T13's readiness gate; the `spell_v2.py` → `spell_record.py` rename is applied from T6 onward.

