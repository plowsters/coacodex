# M1.14E0R Correctness & Sunset Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: execute **inline** (superpowers:executing-plans) with task-sized commits. The recon adjudication (Task 8) is **agent-executable** — an agent runs recon against the real client and authors the reviewed, client-bound policy + lock from the frozen delta. The **single human check-in** is the **end-of-E0R acceptance review, performed on the pushed WIP branch** (after Task 16). **Commit locally throughout; push `m1-14-e0r` exactly once, at the end, for that review** — there are no intermediate pushes. Steps use `- [ ]`. **Do not begin code execution (Task 2+) until the design-lock (Task 1) is committed.**

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
- **Transactional candidate→pointer.** Stage children → candidate manifest (`publication_state: "candidate"`, `candidate_trust_sha256` over all trust-critical fields) → Python+Node validate by path (incl. cross-child merge-join) → final manifest changes only the `CANDIDATE_MUTABLE_KEYS` (`publication_state` candidate→published, `/validation`, `/budget` — all three excluded from the digest) and reproduces the digest → pointer last. The manifest is **not** a child. Process file lock over predecessor-read → replace.
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
- Produces: `policy_ref(table, field) -> str` (JSON Pointer `/tables/<t>/fields/<f>`); `policy_ref_component(join_spec, part) -> str` which resolves a join's `index`/`side_id`/`side_value` to its **underlying table-field** pointer (there is **no** synthetic `/joins/...` node); `resolve_policy_ref(policy_doc, ref) -> dict`; `READINESS_STATUSES`, `READINESS_REASON_CODES`, `ICON_ASSET_STATUSES` (closed `frozenset`s); `READINESS_INVARIANTS` (status → {value_null, blocking, set_valued_only} rules); `TRUST_CRITICAL_MANIFEST_KEYS`; `CANDIDATE_MUTABLE_KEYS` (the only keys that may change candidate→final); `CROSS_CHILD_CHECKS`; `BOUND_HEADER_FIELDS`, `BOUND_SOURCE_FIELDS`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contracts.py
import pytest
from coa_client_extract.contracts import (
    policy_ref, policy_ref_component, resolve_policy_ref,
    READINESS_STATUSES, READINESS_REASON_CODES, ICON_ASSET_STATUSES,
    TRUST_CRITICAL_MANIFEST_KEYS, CROSS_CHILD_CHECKS, BOUND_HEADER_FIELDS,
)


def test_policy_ref_and_component_resolve_to_table_fields():
    assert policy_ref("Spell", "power_type") == "/tables/Spell/fields/power_type"
    jspec = {"index_field": "casting_time_index", "side_table": "SpellCastTimes", "side_value_field": "base_ms"}
    assert policy_ref_component(jspec, "side_value") == "/tables/SpellCastTimes/fields/base_ms"
    assert policy_ref_component(jspec, "index") == "/tables/Spell/fields/casting_time_index"
    assert policy_ref_component(jspec, "side_id") == "/tables/SpellCastTimes/fields/id"
    with pytest.raises(ValueError):
        policy_ref_component(jspec, "bogus")


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
    "index_zero", "no_static_anchor", "not_extracted", "proven_empty",
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


def policy_ref_component(join_spec: dict, part: str) -> str:
    """Resolve a join component to its UNDERLYING table-field policy pointer via the join mapping — there
    is no synthetic /joins/... policy node. index -> Spell.<index_field>; side_id -> <side_table>.id;
    side_value -> <side_table>.<side_value_field>."""
    if part == "index":
        return policy_ref("Spell", join_spec["index_field"])
    if part == "side_id":
        return policy_ref(join_spec["side_table"], "id")
    if part == "side_value":
        return policy_ref(join_spec["side_table"], join_spec["side_value_field"])
    raise ValueError(f"join component {part!r} not in (index, side_id, side_value)")


# status -> (value must be null?, blocking?, set-valued-only?) — the readiness state machine (design B3).
READINESS_INVARIANTS = {
    "available": (False, False, False), "verified_empty": (False, False, True),
    "not_applicable": (True, False, False), "unavailable": (True, True, False),
    "ambiguous": (True, True, False),
}
# The ONLY manifest keys that may differ between the candidate and the final manifest.
CANDIDATE_MUTABLE_KEYS = frozenset({"publication_state", "validation", "budget"})


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

Then, inside `load_spell_policy`: require `schema_version == SCHEMA` (message names `coa-spell-layout-v2`); for each table read `key_cell:int` (`0 <= key_cell < expected_field_count`) and `unique:bool` into `tables[tname]`; parse joins with the extra `promotion` field validated against `_PROMOTIONS`, and enforce that a `normalized` join's index/`id`/`side_value` fields are all `promotion == "normalized"` (else `SpellPolicyError(f"join {jname}: normalized join has a raw_only component {fname}")`); call `_validate_bound(bound)` when `bound is not None` and additionally require `set(bound["tables"]) == set(required_tables)` and `set(bound["expected_absent"]) == set(top-level expected_absent)` (bound and policy topology must agree); validate the header field **types** (ints) and that `sha256` is 64 hex chars. Finally, **update `load_default_policy` to load `spell_layout_v2.json`** (not the hard-coded `spell_layout_v1.json` at line 205) and add a loader test that the shipped default file loads. Also fix the baseline `_v2()` fixture so its **success** case keeps every `normalized`-join component `normalized` (only the negative fixtures flip a component to `raw_only`).

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
- Consumes: `recordview.open_view`, the backend's `read_effective_file`/`has_file`/`client_build`.
- Produces: `require_dense(data, header) -> bool` (the file is exactly `20 + record_count*record_size + string_block_size` bytes — no gaps/trailing bytes); `verify_source_topology(policy, backend, root, attach) -> dict` with `client_build`, `tables[t] = {sha256, header{5 fields}, member, effective_archive, patch_chain, key_unique: bool, dense: bool}`, `expected_absent_ok: bool`, and `blocking: list[dict]`; `topology_matches_bound(report, bound) -> list[dict]` (empty ⇒ match) comparing **every** facet — `client_build`, exact required-table **set equality** (no missing, no extra), `sha256`, full `header`, `member`, `effective_archive`, `patch_chain`, and `expected_absent`. Used by recon (Task 5) **and** regenerate (Task 10).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_topology.py
import copy, hashlib, struct
import pytest
from coa_client_extract.topology import verify_source_topology, topology_matches_bound, require_dense

BUILD = "3.3.5a+patch-CZZ"


def _dbc(rows: list[tuple[int, int]], field_count=2, string_block=b"") -> bytes:
    rs = field_count * 4
    body = b"".join(struct.pack("<II", a, b) for a, b in rows)
    return struct.pack("<4sIIII", b"WDBC", len(rows), field_count, rs, len(string_block)) + body + string_block


class _Member:
    def __init__(self, data, name, archive="patch-CZZ.MPQ", patch_chain=()):
        self.data = data
        self.name = name
        self.effective_archive = type("A", (), {"name": archive})()
        self.patch_chain = [type("A", (), {"name": p})() for p in patch_chain]


class _Backend:
    def __init__(self, files, build=BUILD): self.files, self.client_build = files, build
    def has_file(self, root, attach, name): return name in self.files
    def read_effective_file(self, root, attach, name):
        if name not in self.files: raise KeyError(name)
        return _Member(self.files[name], name)


class _Policy:
    required_tables = ("Spell",)
    expected_absent = ("SpellEffect",)
    def __init__(self, key_cell=0, unique=True):
        self.tables = {"Spell": {"key_cell": key_cell, "unique": unique, "expected_field_count": 2}}
        self.bound = None


def _bound_from(rep):
    """The structured bound a matching client would carry (built from a good report)."""
    t = rep["tables"]["Spell"]
    return {"client_build": rep["client_build"], "expected_absent": ["SpellEffect"], "tables": {
        "Spell": {"sha256": t["sha256"], "header": t["header"], "source": {
            "member": t["member"], "effective_archive": t["effective_archive"], "patch_chain": t["patch_chain"]}}}}


def test_require_dense_rejects_trailing_bytes():
    good = _dbc([(1, 10)])
    hdr = {"record_count": 1, "field_count": 2, "record_size": 8, "string_block_size": 0}
    assert require_dense(good, hdr) is True
    assert require_dense(good + b"\x00\x00", hdr) is False       # trailing junk => not dense


def test_topology_report_captures_header_member_dense_and_uniqueness():
    data = _dbc([(1, 10), (2, 20)])
    be = _Backend({"DBFilesClient\\Spell.dbc": data})
    rep = verify_source_topology(_Policy(), be, None, None)
    t = rep["tables"]["Spell"]
    assert t["sha256"] == hashlib.sha256(data).hexdigest()
    assert t["header"]["field_count"] == 2 and t["header"]["magic"] == "WDBC"
    assert t["member"] == "DBFilesClient\\Spell.dbc" and t["dense"] is True
    assert rep["client_build"] == BUILD
    assert t["key_unique"] is True and rep["expected_absent_ok"] is True and rep["blocking"] == []


def test_duplicate_key_expected_absent_and_nondense_all_block():
    dup = _dbc([(1, 10), (1, 20)])
    be = _Backend({"DBFilesClient\\Spell.dbc": dup + b"\xff", "DBFilesClient\\SpellEffect.dbc": dup})
    rep = verify_source_topology(_Policy(), be, None, None)
    assert rep["tables"]["Spell"]["key_unique"] is False and rep["tables"]["Spell"]["dense"] is False
    assert rep["expected_absent_ok"] is False
    reasons = {b["reason"] for b in rep["blocking"]}
    assert {"duplicate_key", "expected_absent_present", "not_dense"} <= reasons


def test_matching_bound_reports_no_mismatch():
    be = _Backend({"DBFilesClient\\Spell.dbc": _dbc([(1, 10)])})
    rep = verify_source_topology(_Policy(), be, None, None)
    assert topology_matches_bound(rep, _bound_from(rep)) == []


@pytest.mark.parametrize("facet,mutate", [
    ("sha256", lambda b: b["tables"]["Spell"].__setitem__("sha256", "0" * 64)),
    ("header", lambda b: b["tables"]["Spell"]["header"].__setitem__("record_size", 999)),
    ("member", lambda b: b["tables"]["Spell"]["source"].__setitem__("member", "DBFilesClient\\Other.dbc")),
    ("effective_archive", lambda b: b["tables"]["Spell"]["source"].__setitem__("effective_archive", "patch-Z.MPQ")),
    ("patch_chain", lambda b: b["tables"]["Spell"]["source"].__setitem__("patch_chain", ["patch-A.MPQ"])),
    ("client_build", lambda b: b.__setitem__("client_build", "3.3.5a+patch-OLD")),
    ("expected_absent", lambda b: b.__setitem__("expected_absent", [])),
])
def test_each_bound_facet_is_independently_bound(facet, mutate):
    be = _Backend({"DBFilesClient\\Spell.dbc": _dbc([(1, 10)])})
    rep = verify_source_topology(_Policy(), be, None, None)
    bound = _bound_from(rep); mutate(bound)
    mism = topology_matches_bound(rep, bound)
    assert any(m["field"] == facet for m in mism), f"{facet} mutation not detected: {mism}"


def test_bound_table_set_must_match_exactly():
    be = _Backend({"DBFilesClient\\Spell.dbc": _dbc([(1, 10)])})
    rep = verify_source_topology(_Policy(), be, None, None)
    missing = _bound_from(rep); missing["tables"]["SpellExtra"] = missing["tables"]["Spell"]
    assert any(m["field"] == "table_set" for m in topology_matches_bound(rep, missing))
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
_HEADER_BYTES = 20


def _header(data: bytes) -> dict:
    magic, rc, fc, rs, ss = _H.unpack_from(data, 0)
    return {"magic": magic.decode("latin-1"), "record_count": rc, "field_count": fc,
            "record_size": rs, "string_block_size": ss}


def require_dense(data: bytes, header: dict) -> bool:
    """A WDBC file is dense iff its length is EXACTLY 20-byte header + record_count*record_size +
    string_block_size — no gaps, no trailing bytes. A non-dense file means the record region is not what
    the header claims and the layout cannot be trusted."""
    expected = _HEADER_BYTES + header["record_count"] * header["record_size"] + header["string_block_size"]
    return len(data) == expected


def verify_source_topology(policy, backend, root, attach) -> dict:
    """Independently open + verify every required table (sha256, full 5-field header, member,
    archive, patch chain, density, id-uniqueness under the policy key cell) and the expected-absent set.
    Shared by recon AND regenerate so they can never diverge."""
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
        header = _header(member.data)
        dense = require_dense(member.data, header)
        key_cell = policy.tables[name]["key_cell"]
        seen, unique = set(), True
        for rec in view.records():
            k = rec.u32(key_cell)
            if k in seen:
                unique = False
                break
            seen.add(k)
        tables[name] = {
            "sha256": hashlib.sha256(member.data).hexdigest(), "header": header,
            "member": member.name, "effective_archive": member.effective_archive.name,
            "patch_chain": [p.name for p in member.patch_chain], "key_unique": unique, "dense": dense,
        }
        if policy.tables[name].get("unique", True) and not unique:
            blocking.append({"table": name, "reason": "duplicate_key", "key_cell": key_cell})
        if not dense:
            blocking.append({"table": name, "reason": "not_dense"})

    expected_absent_ok = True
    for name in policy.expected_absent:
        if backend.has_file(root, attach, f"DBFilesClient\\{name}.dbc"):
            expected_absent_ok = False
            blocking.append({"table": name, "reason": "expected_absent_present"})

    return {"client_build": getattr(backend, "client_build", None), "tables": tables,
            "expected_absent_ok": expected_absent_ok, "expected_absent_set": list(policy.expected_absent),
            "blocking": blocking}


def topology_matches_bound(report: dict, bound: dict | None) -> list[dict]:
    """Return the list of mismatches between an opened-client topology report and a policy's structured
    `bound`. Empty ⇒ the opened client is the client the policy was proven against. EVERY facet is bound:
    client_build, exact required-table set equality, sha256, full header, member, effective_archive,
    patch_chain, and expected_absent topology."""
    if not bound:
        return [{"table": "*", "field": "bound", "reason": "policy has no bound"}]
    mism: list[dict] = []
    if report.get("client_build") != bound.get("client_build"):
        mism.append({"table": "*", "field": "client_build", "reason": "build_mismatch"})
    want = bound.get("tables", {})
    if set(want) != set(report["tables"]):
        mism.append({"table": "*", "field": "table_set", "reason": "required_table_set_differs",
                     "missing": sorted(set(want) - set(report["tables"])),
                     "extra": sorted(set(report["tables"]) - set(want))})
    for name, w in want.items():
        got = report["tables"].get(name)
        if got is None:
            mism.append({"table": name, "field": "*", "reason": "missing_from_client"})
            continue
        src = w["source"]
        for field, got_v, want_v in (
            ("sha256", got["sha256"], w["sha256"]),
            ("header", got["header"], w["header"]),
            ("member", got["member"], src["member"]),
            ("effective_archive", got["effective_archive"], src["effective_archive"]),
            ("patch_chain", got["patch_chain"], src["patch_chain"]),
        ):
            if got_v != want_v:
                mism.append({"table": name, "field": field, "reason": f"{field}_differs"})
    # expected-absent is two facts: the bound pins WHICH tables must be absent (set), and the report
    # proves they ARE absent on the opened client.
    if sorted(bound.get("expected_absent", [])) != sorted(report.get("expected_absent_set", [])):
        mism.append({"table": "*", "field": "expected_absent", "reason": "expected_absent_set_differs"})
    if not report["expected_absent_ok"]:
        mism.append({"table": "*", "field": "expected_absent", "reason": "expected_absent_present"})
    return mism
```

`verify_source_topology` also records `report["expected_absent_set"] = list(policy.expected_absent)` (add it to the returned dict) so `topology_matches_bound` can compare the **bound** absent set against the **policy** absent set; the `expected_absent` facet test mutates `bound["expected_absent"]` to `[]` and expects the `expected_absent` field flagged.

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
- Produces: `discover_join_pair(view, id_to_rec, side_view, *, side_id_cell, side_value_cells, anchors, side_value_kind="int32") -> tuple[tuple[int, int] | None, list[tuple[int, int]]]` — discovers **both** the Spell index cell **and** the side value cell as a jointly-unique pair (not a known-side-cell single-cell scan); anchors are **state-bearing** (`{spell_id, expected_state, expected_value}`, `expected_state ∈ {"resolved", "not_applicable"}`) so a legitimately resolved-zero side row is distinguished from `index_zero`; `discover_power_type_signedness(view, id_to_rec, *, cell, anchors) -> bool` (True only when a static health-cost anchor reads `0xFFFFFFFE`); `three_part_budget(*, serialized_bytes, peak_rss_mb, elapsed_s, ceilings) -> dict` (`within_budget` requires **all three** under ceiling). Recon proposes a `proposed_policy_delta`; it never writes the policy.

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


def test_joined_pair_discovers_both_cells_uniquely():
    # index FK in spell-cell 2, side value in side-cell 1; decoy spell-cell 1 also holds ids but resolves
    # to the WRONG values, so only the (2, 1) pair satisfies every anchor.
    spell = _spell([[133, 3, 2], [116, 2, 3], [400, 0, 0]], field_count=3)
    id_to_rec = {r.u32(0): r for r in spell.records()}
    side = _side([(2, 1500), (3, 3000)])
    anchors = [{"spell_id": 133, "expected_state": "resolved", "expected_value": 1500},
               {"spell_id": 116, "expected_state": "resolved", "expected_value": 3000},
               {"spell_id": 400, "expected_state": "not_applicable", "expected_value": None}]
    pair, winners = discover_join_pair(spell, id_to_rec, side, side_id_cell=0, side_value_cells=[1],
                                       anchors=anchors)
    assert pair == (2, 1) and winners == [(2, 1)]


def test_resolved_zero_is_distinguished_from_not_applicable():
    # spell 133 -> side id 1 whose value is 0 (a RESOLVED zero); spell 400 has fk 0 (not_applicable).
    spell = _spell([[133, 1], [400, 0]], field_count=2)
    id_to_rec = {r.u32(0): r for r in spell.records()}
    side = _side([(1, 0)])
    correct = [{"spell_id": 133, "expected_state": "resolved", "expected_value": 0},
               {"spell_id": 400, "expected_state": "not_applicable", "expected_value": None}]
    pair, _ = discover_join_pair(spell, id_to_rec, side, side_id_cell=0, side_value_cells=[1], anchors=correct)
    assert pair == (1, 1)
    # Mislabelling the resolved-zero as not_applicable must FAIL to match (its fk is non-zero).
    mislabelled = [{"spell_id": 133, "expected_state": "not_applicable", "expected_value": None},
                   {"spell_id": 400, "expected_state": "not_applicable", "expected_value": None}]
    pair2, _ = discover_join_pair(spell, id_to_rec, side, side_id_cell=0, side_value_cells=[1], anchors=mislabelled)
    assert pair2 is None


def test_joined_pair_ambiguous_returns_none():
    spell = _spell([[133, 2, 2], [116, 3, 3], [400, 0, 0]], field_count=3)  # spell-cells 1 and 2 identical
    id_to_rec = {r.u32(0): r for r in spell.records()}
    side = _side([(2, 1500), (3, 3000)])
    anchors = [{"spell_id": 133, "expected_state": "resolved", "expected_value": 1500},
               {"spell_id": 116, "expected_state": "resolved", "expected_value": 3000}]
    pair, winners = discover_join_pair(spell, id_to_rec, side, side_id_cell=0, side_value_cells=[1],
                                       anchors=anchors)
    assert pair is None and winners == [(1, 1), (2, 1)]


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


def _anchor_holds(a, id_to_rec, side_by_id, index_cell, value_cell, kind) -> bool:
    """A STATE-BEARING anchor holds when the (index_cell -> side row -> value_cell) resolution matches its
    declared state AND value. not_applicable requires fk == 0; resolved requires a non-zero fk pointing at
    a present side row whose value_cell equals expected_value (expected_value may itself be 0 — a resolved
    zero, which is why the state, not the value, decides applicability)."""
    rec = id_to_rec.get(a["spell_id"])
    if rec is None:
        return False
    fk = rec.u32(index_cell)
    if a["expected_state"] == "not_applicable":
        return fk == 0
    if a["expected_state"] != "resolved":
        return False
    side = side_by_id.get(fk)
    return fk != 0 and side is not None and _read_side(side, value_cell, kind) == a["expected_value"]


def discover_join_pair(view, id_to_rec, side_view, *, side_id_cell, side_value_cells, anchors,
                       side_value_kind="int32"):
    """Discover BOTH the Spell index cell and the side value cell of a join as a jointly-unique pair.
    For each candidate index cell (whose non-zero values are ~all valid side ids) and each candidate
    side value cell, every state-bearing anchor must resolve THROUGH the pair. A bare FK-validity scan is
    ambiguous (dozens of small-int columns fall in a side id range) and knowing the value cell a priori is
    cheating; requiring the pair to be jointly unique over the state-bearing anchors breaks both."""
    side_by_id = {r.u32(side_id_cell): r for r in side_view.records()}
    side_ids = set(side_by_id)
    winners: list[tuple[int, int]] = []
    for ic in range(view.cell_count):
        nonzero = [r.u32(ic) for r in view.records() if r.u32(ic) != 0]
        if len(nonzero) < _MIN_SUPPORT or sum(1 for v in nonzero if v in side_ids) / len(nonzero) < 0.99:
            continue
        for vc in side_value_cells:
            if all(_anchor_holds(a, id_to_rec, side_by_id, ic, vc, side_value_kind) for a in anchors):
                winners.append((ic, vc))
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

`discover_join_pair` passes `side_value_cells` as the candidate set (not a single known cell): for `SpellRange` that set is both value cells under the one shared `range_index`; a `(index_cell, side_value_cell)` pair wins only when it is **jointly unique** over the state-bearing anchors. `SpellIcon.path` is discovered by a sibling `discover_string_join_pair` that resolves candidate side cells through the string block (`try_string`) and matches the anchors' expected icon names (the numeric `_read_side`/`expected_value` comparison is replaced by string equality); floats compare by expected raw bits or a stated tolerance. The `power_type` verdict emits and binds the **static tooltip evidence** for the negative anchor (the health-cost `description`), not merely an input flag.

Then integrate into `recon_spell_mechanics`: replace the ambiguous single-cell `_discover_index_cell` call with `discover_join_pair`/`discover_string_join_pair` for each of cast/duration/range/icon (using the frozen state-bearing anchor set), add the `power_type` negative-anchor scan, call `verify_source_topology` for the topology section (replacing the `has_file`-only loop), and compute `budget` via `three_part_budget` from the **serialized** projection estimate + subprocess `ru_maxrss` + elapsed. The `proposed_policy_delta` names the four discovered `(index, side_value)` pairs, the `SpellIcon.path` string cell, and the `power_type` signedness verdict + its bound evidence. Recon still writes no policy.

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
- Produces: `iter_spell_records(spell_view, side_views, *, policy, provenance) -> Iterator[dict]` streaming compact `coa-client-spell-v3` rows (identity + normalized `mechanics` + attribution + a `raw` compact block; each field carries a `policy_ref`, no evidence text); `eligible_from_row(obs, pol, policy_doc) -> bool` (the serialized-form eligibility mirror shared with Node, exercised by the Task 7 golden fixtures); the four-part join promotion gate; `iter_icon_catalog(spell_view, side_views, *, policy, asset_resolver) -> Iterator[dict]` (`coa-client-spell-icons-v1`, full-table domain, dedup asset entries) where `asset_resolver(client_path) -> {bytes, archive, member, patch_chain} | None` reads the effective client BLP member so `source_asset_sha256` hashes the **actual BLP bytes** (never the path). The concrete resolver (MPQ-chain reader) is wired in `regenerate` (Task 10); `iter_icon_catalog` only consumes the callable.

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
import hashlib
from coa_client_extract.spell_icons import iter_icon_catalog
from tests._spell_fixtures import v2_icon_policy, spell_dbc, icon_side_views


def _resolver(path):
    # returns BLP bytes distinct from the path string, so a path-hash would NOT match a bytes-hash
    return {"bytes": b"BLP:" + path.encode(), "archive": "patch-T.MPQ", "member": path, "patch_chain": []}


def test_icon_catalog_hashes_blp_bytes_and_dedups():
    rows = list(iter_icon_catalog(spell_dbc(), icon_side_views(), policy=v2_icon_policy(), asset_resolver=_resolver))
    by_id = {r["spell_id"]: r for r in rows}
    r = by_id[805775]
    assert r["client_path"].endswith(".blp") and r["asset_status"] == "source_only"
    # the hash is over the BLP BYTES the resolver returned, not the client_path string
    assert r["source_asset_sha256"] == hashlib.sha256(b"BLP:" + r["client_path"].encode()).hexdigest()
    assert r["source_archive"] == "patch-T.MPQ"
    # two spells sharing one icon path produce one deduplicated source asset hash
    assert r["source_asset_sha256"] == by_id[133]["source_asset_sha256"]


def test_icon_catalog_missing_member_is_missing_status():
    rows = list(iter_icon_catalog(spell_dbc(), icon_side_views(), policy=v2_icon_policy(),
                                  asset_resolver=lambda p: None))     # no client member for any path
    assert all(r["asset_status"] == "missing" and r["source_asset_sha256"] is None for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_spell_record.py tests/test_spell_icons.py -v`
Expected: FAIL with `ModuleNotFoundError` (module renamed / not yet created).

- [ ] **Step 3: Port `spell_v2.py` to a streaming `spell_record.py` + add `spell_icons.py`**

```python
# coa_client_extract/spell_record.py  (key changes vs the ported spell_v2.py)
from .contracts import policy_ref, policy_ref_component, resolve_policy_ref

SCHEMA = "coa-client-spell-v3"


def _compact(obs_dict: dict, *, policy_ref_str: str) -> dict:
    """A compact raw cell: retain enough raw to reconstruct eligibility + a policy_ref, DROP the per-row
    proof/evidence text (Node re-derives proof/promotion from the policy via policy_ref). A string
    observation keeps `raw_offset` + `resolved` (a string cannot be re-decoded from an offset, so Node
    verifies equality against `resolved`); a numeric cell keeps `raw_u32`."""
    out = {"state": obs_dict["state"], "decoded_reason": obs_dict["decoded_reason"],
           "policy_ref": policy_ref_str}
    if "raw_offset" in obs_dict:                       # StringObservation
        out["raw_offset"] = obs_dict["raw_offset"]; out["resolved"] = obs_dict.get("resolved")
    else:                                             # numeric Envelope
        out["raw_u32"] = obs_dict.get("raw_u32")
    return out


def _join_spec(join) -> dict:
    return {"index_field": join.index_field, "side_table": join.side_table,
            "side_value_field": join.side_value_field}


def _join_normalized(join, idx_fp, id_fp, val_fp, jo) -> bool:
    """The exact four-part predicate (design A1)."""
    return (join.promotion == "normalized"
            and idx_fp.promotion == "normalized" and id_fp.promotion == "normalized"
            and val_fp.promotion == "normalized"
            and semantic_promotion_eligible(jo.composed_proof) and jo.state == "resolved")


def eligible_from_row(obs: dict, pol: dict, policy_doc: dict) -> bool:
    """Recompute a field's promotion eligibility from the SERIALIZED compact form (the exact shape Node
    consumes), so the golden fixtures pin producer and Node to one rule. A scalar is eligible iff its
    policy is fully verified+normalized and its observation decoded; a join is eligible iff its own
    `promotion` is normalized (looked up in `policy_doc['joins']`), it resolved, and every component's
    policy is verified+normalized."""
    if obs.get("components"):
        join = policy_doc.get("joins", {}).get(obs["join_name"], {})
        if join.get("promotion") != "normalized" or obs.get("state") != "resolved":
            return False
        for _, c in obs["components"].items():
            cp = resolve_policy_ref(policy_doc, c["policy_ref"])
            if not (cp.get("promotion") == "normalized" and cp.get("layout") == "verified"
                    and cp.get("interpretation") == "verified"):
                return False
        return True
    return (pol.get("promotion") == "normalized" and pol.get("layout") == "verified"
            and pol.get("interpretation") == "verified"
            and obs.get("state") in ("present", "resolved") and obs.get("decoded_reason") == "decoded")


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
            raw[jname] = {"join_name": jname, "state": jo_dict["state"],
                          "decoded_reason": jo_dict["decoded_reason"],
                          "components": {k: _compact(v, policy_ref_str=policy_ref_component(_join_spec(join), k))
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


def iter_icon_catalog(spell_view, side_views, *, policy, asset_resolver):
    """coa-client-spell-icons-v1 over the FULL-table domain (every spell whose icon join resolves),
    dedup asset entries by client_path. `asset_resolver(client_path) -> {bytes, archive, member,
    patch_chain} | None` reads the effective client BLP member; source_asset_sha256 hashes those ACTUAL
    BLP bytes (never the path string), and `missing` means the resolver found no client member. Emits
    {spell_id, spell_icon_id, client_path, source_asset_sha256, source_archive, asset_status, readiness}."""
    join = policy.joins["spell_icon_id"]
    icon_view = side_views.get(join.side_table)
    id_cell = policy.tables[join.side_table]["fields"]["id"].cell
    path_cell = policy.tables[join.side_table]["fields"][join.side_value_field].cell
    by_id = {r.u32(id_cell): r for r in icon_view.records()} if icon_view else {}
    asset_cache: dict[str, dict] = {}                     # client_path -> resolved asset facts (dedup)
    idx_cell = policy.tables["Spell"]["fields"][join.index_field].cell
    spell_id_cell = policy.tables["Spell"]["fields"]["id"].cell
    for rec in spell_view.records():
        spell_id = rec.u32(spell_id_cell)
        fk = rec.u32(idx_cell) if idx_cell is not None else 0
        side = by_id.get(fk)
        client_path = icon_view.read_string(side.u32(path_cell)) if side else None
        if not client_path:
            yield {"schema_version": SCHEMA, "spell_id": spell_id, "spell_icon_id": fk,
                   "client_path": None, "source_asset_sha256": None, "source_archive": None,
                   "asset_status": "missing", "readiness": "unavailable"}
            continue
        if client_path not in asset_cache:
            resolved = asset_resolver(client_path)          # reads the effective BLP member once per path
            if resolved is None:
                asset_cache[client_path] = {"sha256": None, "archive": None, "status": "missing"}
            else:
                asset_cache[client_path] = {"sha256": hashlib.sha256(resolved["bytes"]).hexdigest(),
                                            "archive": resolved["archive"], "status": "source_only"}
        a = asset_cache[client_path]
        yield {"schema_version": SCHEMA, "spell_id": spell_id, "spell_icon_id": fk,
               "client_path": client_path, "source_asset_sha256": a["sha256"], "source_archive": a["archive"],
               "asset_status": a["status"],
               "readiness": "available" if a["status"] == "source_only" else "unavailable"}
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
- Modify: `coa_scraper/scripts/lib/mechanics-projection.mjs`; `coa_client_extract/spell_record.py` (append the symmetric Python verifier `verify_row_against_policy`)
- Create: `tests/golden/e0r_policy.json`, `tests/golden/e0r_projection_rows.jsonl` (cross-language golden fixtures — the identical bytes drive both a Node and a Python assertion)
- Test: `coa_scraper/tests/mechanics-projection-e0r.test.mjs`, `coa_scraper/tests/golden-projection.test.mjs`, `tests/test_golden_projection.py`
- **No lock file here.** The canonical `coa_scraper/config/spell_layout.lock.json` is authored **only** at Task 8b; Task 7's tests build a lock object inline, committing no placeholder.

**Interfaces:**
- Produces: `verifyRowAgainstPolicy(row, policyDoc)` — resolves each field's `policy_ref`, re-decodes numeric `raw_u32` (`Int32`/`Uint32`/`Float32`), verifies string `resolved` equality, recomputes the **full** join predicate (including the join's own `promotion` from `policyDoc.joins[...]`), and throws unless the producer's normalized value agrees under the biconditional; `assertPolicyLock(policyDoc, lock)` — recomputes the canonical hash and rejects a policy whose recomputed `sha256` ≠ the committed lock; `eligibleFromPolicy(field, obs, policyDoc)` mirrors Python `eligible_from_row` (verified by the shared golden).

- [ ] **Step 1: Write the failing test**

```javascript
// coa_scraper/tests/mechanics-projection-e0r.test.mjs
import { test } from "node:test";
import assert from "node:assert";
import { verifyRowAgainstPolicy, assertPolicyLock } from "../scripts/lib/mechanics-projection.mjs";

const policy = { sha256: "abc", tables: { Spell: { fields: {
  power_type: { kind: "int32", layout: "verified", interpretation: "verified", promotion: "normalized" } } } } };

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

// Recompute the policy hash with the SAME canonical algorithm as Python compute_policy_sha256
// (json.dumps(sort_keys=True, separators=(",",":")) over the doc MINUS its own "sha256"), so Node does
// not trust the policy's self-declared field, and compare to the committed lock.
function canonicalSha256(doc) {
  const { sha256: _omit, ...rest } = doc;
  const canon = JSON.stringify(sortDeep(rest));            // sortDeep: recursively key-sorted, no spaces
  return crypto.createHash("sha256").update(canon).digest("hex");
}

export function assertPolicyLock(policyDoc, lock) {
  const actual = canonicalSha256(policyDoc);
  if (!lock || actual !== lock.sha256) {
    throw new MechanicsBuildError(`policy lock mismatch: recomputed ${actual} != lock ${lock?.sha256}`);
  }
  if (policyDoc.sha256 && policyDoc.sha256 !== actual) {
    throw new MechanicsBuildError(`policy self-declared sha256 ${policyDoc.sha256} != recomputed ${actual}`);
  }
}

// Biconditional: for EVERY field observation, recompute eligibility from (policy, obs). Eligible =>
// the normalized value MUST be present and agree; ineligible => it MUST be null. (The shipped/earlier
// code only checked "populated => eligible", skipping nulls — half the biconditional.) A join's OWN
// promotion is consulted via policyDoc.joins[...], not just its components' — otherwise a normalized
// component set with a raw_only join would wrongly read as eligible.
export function eligibleFromPolicy(field, obs, policyDoc) {
  if (obs.components) {                                    // a join observation — recompute the FULL A1 predicate
    const join = (policyDoc.joins || {})[obs.join_name || field] || {};
    if (join.promotion !== "normalized" || obs.state !== "resolved") return false;
    return Object.entries(obs.components).every(([, c]) => {
      const cp = resolvePolicyRef(policyDoc, c.policy_ref);
      return cp.promotion === "normalized" && cp.layout === "verified" && cp.interpretation === "verified";
    });
  }
  const pol = resolvePolicyRef(policyDoc, obs.policy_ref);
  return pol.promotion === "normalized" && pol.layout === "verified" && pol.interpretation === "verified"
         && (obs.state === "present" || obs.state === "resolved") && obs.decoded_reason === "decoded";
}

export function verifyRowAgainstPolicy(row, policyDoc) {
  const mech = row.mechanics || {};
  for (const [field, obs] of Object.entries(row.raw || {})) {
    const value = mech[field];
    const pol = obs.components
      ? resolvePolicyRef(policyDoc, obs.components.side_value.policy_ref)
      : resolvePolicyRef(policyDoc, obs.policy_ref);
    const eligible = eligibleFromPolicy(field, obs, policyDoc);
    const populated = value !== null && value !== undefined;
    if (eligible !== populated) {
      throw new MechanicsBuildError(`projection ${row.spell_id}: ${field} eligible=${eligible} but populated=${populated} (biconditional violation)`);
    }
    if (!populated) continue;
    if (pol.kind === "string") {
      const resolved = obs.components ? obs.components.side_value.resolved : obs.resolved;
      if (value !== resolved) throw new MechanicsBuildError(`projection ${row.spell_id}: ${field} != resolved`);
    } else {
      const raw = obs.components ? obs.components.side_value.raw_u32 : obs.raw_u32;
      if (redecode(raw, pol.kind) !== value) throw new MechanicsBuildError(`projection ${row.spell_id}: ${field} re-decode disagrees`);
    }
  }
}
```

Wire `verifyRowAgainstPolicy` + `assertPolicyLock` into `loadAndValidateProjection` (load the policy child + the committed lock; call per row), and reject a manifest lacking the policy child (pre-E0R).

- [ ] **Step 3b: Author the cross-language golden fixtures**

The golden pins the biconditional to identical bytes across both languages. `tests/golden/e0r_policy.json` is a minimal policy doc; `tests/golden/e0r_projection_rows.jsonl` is one row per accept/reject case, each tagged `golden_accept`.

```json
// tests/golden/e0r_policy.json
{
  "schema_version": "coa-spell-layout-v2",
  "tables": {
    "Spell": {"fields": {
      "power_type": {"kind": "int32", "layout": "verified", "interpretation": "verified", "promotion": "normalized"},
      "school_mask": {"kind": "uint32", "layout": "verified", "interpretation": "reference", "promotion": "raw_only"},
      "casting_time_index": {"kind": "uint32", "layout": "verified", "interpretation": "verified", "promotion": "normalized"}}},
    "SpellCastTimes": {"fields": {
      "id": {"kind": "uint32", "layout": "verified", "interpretation": "verified", "promotion": "normalized"},
      "base_ms": {"kind": "int32", "layout": "verified", "interpretation": "verified", "promotion": "normalized"}}}
  },
  "joins": {"cast_time_ms": {"index_field": "casting_time_index", "side_table": "SpellCastTimes",
                             "side_value_field": "base_ms", "promotion": "normalized"}}
}
```

```jsonc
// tests/golden/e0r_projection_rows.jsonl  (one JSON object per line)
{"golden_accept": true,  "spell_id": 1, "mechanics": {"power_type": 3}, "raw": {"power_type": {"state": "present", "raw_u32": 3, "decoded_reason": "decoded", "policy_ref": "/tables/Spell/fields/power_type"}}}
{"golden_accept": false, "spell_id": 2, "mechanics": {"power_type": 5}, "raw": {"power_type": {"state": "present", "raw_u32": 3, "decoded_reason": "decoded", "policy_ref": "/tables/Spell/fields/power_type"}}}
{"golden_accept": true,  "spell_id": 3, "mechanics": {"school_mask": null}, "raw": {"school_mask": {"state": "present", "raw_u32": 4, "decoded_reason": "decoded", "policy_ref": "/tables/Spell/fields/school_mask"}}}
{"golden_accept": false, "spell_id": 4, "mechanics": {"school_mask": 4}, "raw": {"school_mask": {"state": "present", "raw_u32": 4, "decoded_reason": "decoded", "policy_ref": "/tables/Spell/fields/school_mask"}}}
{"golden_accept": true,  "spell_id": 5, "mechanics": {"cast_time_ms": 1500}, "raw": {"cast_time_ms": {"join_name": "cast_time_ms", "state": "resolved", "decoded_reason": "decoded", "components": {"index": {"state": "present", "raw_u32": 7, "decoded_reason": "decoded", "policy_ref": "/tables/Spell/fields/casting_time_index"}, "side_id": {"state": "present", "raw_u32": 7, "decoded_reason": "decoded", "policy_ref": "/tables/SpellCastTimes/fields/id"}, "side_value": {"state": "present", "raw_u32": 1500, "resolved": null, "decoded_reason": "decoded", "policy_ref": "/tables/SpellCastTimes/fields/base_ms"}}}}}
```

The `school_mask` rows prove the **null half** of the biconditional: a `raw_only` field must be `null` (accept) and is rejected if populated. The `cast_time_ms` row exercises the join-promotion path.

```javascript
// coa_scraper/tests/golden-projection.test.mjs
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import { verifyRowAgainstPolicy } from "../scripts/lib/mechanics-projection.mjs";

const policy = JSON.parse(fs.readFileSync(new URL("../../tests/golden/e0r_policy.json", import.meta.url)));
const rows = fs.readFileSync(new URL("../../tests/golden/e0r_projection_rows.jsonl", import.meta.url), "utf8")
  .split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));

test("Node agrees with the golden verdict for every row", () => {
  for (const row of rows) {
    if (row.golden_accept) assert.doesNotThrow(() => verifyRowAgainstPolicy(row, policy), `row ${row.spell_id}`);
    else assert.throws(() => verifyRowAgainstPolicy(row, policy), `row ${row.spell_id} should reject`);
  }
});
```

The Python side needs a verifier symmetric to Node's `verifyRowAgainstPolicy` (biconditional **and** value agreement), added to `spell_record.py`:

```python
# coa_client_extract/spell_record.py  (append — the symmetric Python verifier)
import struct as _struct


def _redecode(raw_u32: int, kind: str):
    b = _struct.pack("<I", raw_u32 & 0xFFFFFFFF)
    if kind == "int32":
        return _struct.unpack("<i", b)[0]
    if kind == "float":
        return _struct.unpack("<f", b)[0]
    return _struct.unpack("<I", b)[0]


def verify_row_against_policy(row: dict, policy_doc: dict) -> None:
    """Independent Python mirror of Node's verifyRowAgainstPolicy: for every field the biconditional
    (eligible iff populated) must hold, and a populated value must agree with a re-decode of raw_u32
    (numeric) or the resolved string (string). Raises ValueError on any mismatch."""
    mech = row.get("mechanics", {})
    for field, obs in (row.get("raw") or {}).items():
        pol = (resolve_policy_ref(policy_doc, obs["components"]["side_value"]["policy_ref"])
               if obs.get("components") else resolve_policy_ref(policy_doc, obs["policy_ref"]))
        eligible = eligible_from_row(obs, pol, policy_doc)
        value = mech.get(field)
        populated = value is not None
        if eligible != populated:
            raise ValueError(f"{row.get('spell_id')}:{field} eligible={eligible} populated={populated}")
        if not populated:
            continue
        if pol.get("kind") == "string":
            resolved = obs["components"]["side_value"]["resolved"] if obs.get("components") else obs.get("resolved")
            if value != resolved:
                raise ValueError(f"{row.get('spell_id')}:{field} string != resolved")
        else:
            raw = obs["components"]["side_value"]["raw_u32"] if obs.get("components") else obs["raw_u32"]
            if _redecode(raw, pol.get("kind")) != value:
                raise ValueError(f"{row.get('spell_id')}:{field} re-decode disagrees")
```

```python
# tests/test_golden_projection.py
import json
import pytest
from pathlib import Path
from coa_client_extract.spell_record import verify_row_against_policy

GOLDEN = Path("tests/golden")


def test_python_verifier_agrees_with_golden_verdict():
    policy = json.loads((GOLDEN / "e0r_policy.json").read_text())
    rows = [json.loads(l) for l in (GOLDEN / "e0r_projection_rows.jsonl").read_text().splitlines() if l.strip()]
    for row in rows:
        if row["golden_accept"]:
            verify_row_against_policy(row, policy)                 # must not raise
        else:
            with pytest.raises(ValueError):
                verify_row_against_policy(row, policy)
```

Both languages read the **same two files** and run their **own** full verifier; if the Python and Node implementations ever diverge on the rule (biconditional or value agreement), one of these fails.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test coa_scraper/tests/mechanics-projection-e0r.test.mjs coa_scraper/tests/golden-projection.test.mjs coa_scraper/tests/mechanics-projection.test.mjs`; `pytest tests/test_golden_projection.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add coa_scraper/scripts/lib/mechanics-projection.mjs coa_client_extract/spell_record.py \
        coa_scraper/tests/mechanics-projection-e0r.test.mjs coa_scraper/tests/golden-projection.test.mjs \
        tests/golden/e0r_policy.json tests/golden/e0r_projection_rows.jsonl tests/test_golden_projection.py
git commit -m "M1.14E0R Task 7: Node projection-v3 independent verify (numeric re-decode + string resolved + join promotion + policy lock) + cross-language golden"
```

---

## Task 8: Recon CLI + the recon-adjudication artifacts (HARD HOLD — agent adjudication follows in Task 8b)

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

### Task 8b: Recon adjudication (agent-executable; authors the reviewed policy from the delta)

**Not a human gate.** An agent runs recon against the real client and authors the frozen, client-bound
data from `proposed_policy_delta`. It needs the local Ascension client + a built StormLib; if neither is
available in this environment, hand this one task to a maintainer, but it is an ordinary task otherwise.
Recon still only *proposes* — authoring the policy is a separate reviewable commit.

- [ ] **Step 1: Run recon against the real client**
  ```bash
  export COA_CLIENT_ROOT=/path/to/ascension-live/Data      # export first — a VAR=x prefix is not visible to "$VAR" on the same line
  python -m coa_client_extract mechanics-recon --client-root "$COA_CLIENT_ROOT" --out reports/client_extract
  ```
- [ ] **Step 2: Author `coa_client_extract/data/spell_layout_v2.json` from the delta** — fill the four
  join index cells + the icon path cell; set each join's `promotion` (`normalized` only when uniquely
  value-anchor-proven; ambiguous → `cell: null`, `unresolved`); author the structured `bound` for every
  required table (each table's sha256 + full 5-field header + logical member/archive + patch chain, with
  `bound.tables` exactly equal to `required_tables`); set `power_type` `promotion: normalized` **only**
  if the static negative anchor held (else `raw_only`); set `reviewed: true`; recompute `sha256`.
- [ ] **Step 3: Author `coa_scraper/config/spell_layout.lock.json`** — `{schema_version, client_build,
  sha256}` pinning the reviewed policy's recomputed hash (this replaces the Task 7 test fixture; the
  canonical lock exists only from here on).
- [ ] **Step 4: Re-run recon → `verified` (exit 0)** to confirm the authored policy matches its delta.
- [ ] **Step 5: Commit (no push)**
  ```bash
  git add coa_client_extract/data/spell_layout_v2.json coa_scraper/config/spell_layout.lock.json
  git commit -m "M1.14E0R Task 8b: author reviewed client-bound spell-layout-v2 + policy lock from recon delta"
  ```

---

## Task 9: Transactional publication — registry, candidate/final trust digest, cross-child, icon bundle, lock

**Files:**
- Modify: `coa_client_extract/publish.py`, `coa_client_extract/manifest.py`
- Test: `tests/test_publish_e0r.py`

**Interfaces:**
- Consumes: `contracts.CANDIDATE_MUTABLE_KEYS`, `contracts.CROSS_CHILD_CHECKS`, `contracts.ICON_ASSET_STATUSES`.
- Produces: `candidate_trust_sha256(manifest) -> str` (complete manifest minus `CANDIDATE_MUTABLE_KEYS`); `validate_candidate_generation(gen_dir) -> dict` (per-child + **streaming** cross-child merge-join incl. `identity_agrees` + `compact_raw_expands_to_envelope` + bidirectional icon coverage + `sorted_unique_ids` across all three children + icon-bundle internal-manifest enforcement; raises `ResolveError` on any failure); `finalize_and_publish(writer, *, base_manifest, binding, validation, budget) -> dict` (final manifest differs from the candidate ONLY in `CANDIDATE_MUTABLE_KEYS` and must reproduce the candidate digest; process file lock over predecessor-read → pointer replace; pointer last; a `publication_state == "candidate"` manifest is never pointer-resolvable); `build_manifest_v3(...)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_publish_e0r.py
import json
import pytest
from pathlib import Path
from coa_client_extract.publish import (
    GenerationWriter, candidate_trust_sha256, validate_candidate_generation, ResolveError,
)


def _row(schema, sid, **extra):
    return {"schema_version": schema, "spell_id": sid, "coa_attribution": {"is_coa": True},
            "mechanics": {}, "raw": {}, **extra}


def _stage(root: Path, *, full=None, proj=None, icons=None):
    """Stage ALL 11 required children so per-child hashes match; inconsistencies are injected at
    stage-time via `full`/`proj`/`icons` (NEVER by mutating a file after its hash is registered)."""
    full = full if full is not None else [_row("coa-client-spell-v3", 1)]
    proj = proj if proj is not None else [_row("coa-client-spell-projection-v3", 1)]
    icons = icons if icons is not None else [{"schema_version": "coa-client-spell-icons-v1",
                                              "spell_id": 1, "asset_status": "source_only"}]
    gw = GenerationWriter(root)
    gw.add_jsonl("coa_client_spell.jsonl", full, schema_version="coa-client-spell-v3")
    gw.add_jsonl("coa_client_spell_coa.jsonl", proj, schema_version="coa-client-spell-projection-v3")
    gw.add_jsonl("coa_client_spell_icons.jsonl", icons, schema_version="coa-client-spell-icons-v1")
    gw.add_json("coa_client_spell_projection.manifest.json", {"schema_version": "coa-client-spell-projection-manifest-v3"},
                schema_version="coa-client-spell-projection-manifest-v3")
    for name in ("coa_client_content.jsonl", "coa_client_advancement.jsonl", "coa_client_class_types.jsonl",
                 "coa_client_tab_types.jsonl", "coa_client_essence.jsonl"):
        gw.add_jsonl(name, [], schema_version="coa-client-misc-v1")
    gw.add_json("coa_client_archive_plan.json", {"schema_version": "coa-client-archive-plan-v1"},
                schema_version="coa-client-archive-plan-v1")
    gw.add_json("spell_layout_v2.json", {"schema_version": "coa-spell-layout-v2"}, schema_version="coa-spell-layout-v2")
    gw.publish_candidate(base_manifest={}, binding={})
    return gw


def test_trust_digest_ignores_only_validation_and_budget(tmp_path):
    base = {"schema_version": "coa-client-extract-manifest-v3", "generation_id": "g", "children": {},
            "binding": {}, "outputs": {}, "unknown_symbol_inventory": {}, "predecessor_generation_id": None}
    d1 = candidate_trust_sha256({**base, "publication_state": "candidate", "validation": {"ok": True}, "budget": {"a": 1}})
    d2 = candidate_trust_sha256({**base, "publication_state": "published", "validation": {"ok": False}, "budget": {"a": 2}})
    assert d1 == d2                                            # only publication_state/validation/budget move
    assert candidate_trust_sha256({**base, "binding": {"x": 1}}) != d1
    assert candidate_trust_sha256({**base, "a_new_field": 1}) != d1   # a NEW top-level field is not ignored


def test_cross_child_rejects_is_coa_row_absent_from_projection(tmp_path):
    gw = _stage(tmp_path, full=[_row("coa-client-spell-v3", 1), _row("coa-client-spell-v3", 2)],
                proj=[_row("coa-client-spell-projection-v3", 1)])   # spell 2 is_coa but not projected
    with pytest.raises(ResolveError, match="projection_is_coa_subset"):
        validate_candidate_generation(gw.gen_dir)


def test_cross_child_rejects_identity_mismatch(tmp_path):
    gw = _stage(tmp_path, full=[_row("coa-client-spell-v3", 1, name="Fireball")],
                proj=[_row("coa-client-spell-projection-v3", 1, name="Frostbolt")])  # same id, different name
    with pytest.raises(ResolveError, match="identity_agrees"):
        validate_candidate_generation(gw.gen_dir)


def test_cross_child_rejects_compact_raw_without_raw(tmp_path):
    bad = _row("coa-client-spell-v3", 1, name="Fireball",
               raw={"power_type": {"state": "present", "policy_ref": "/tables/Spell/fields/power_type"}})  # no raw_u32
    gw = _stage(tmp_path, full=[bad], proj=[_row("coa-client-spell-projection-v3", 1, name="Fireball")])
    with pytest.raises(ResolveError, match="compact_raw_expands_to_envelope"):
        validate_candidate_generation(gw.gen_dir)


def test_icon_bundle_required_when_any_converted(tmp_path):
    gw = _stage(tmp_path, icons=[{"schema_version": "coa-client-spell-icons-v1", "spell_id": 1,
                                  "asset_status": "converted", "converted_ref": "icons.tar#a.png"}])
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
from .contracts import CANDIDATE_MUTABLE_KEYS, ICON_ASSET_STATUSES

REQUIRED_CHILDREN = ("coa_client_spell.jsonl", "coa_client_spell_coa.jsonl",
                     "coa_client_spell_projection.manifest.json", "coa_client_spell_icons.jsonl",
                     "coa_client_content.jsonl", "coa_client_archive_plan.json",
                     "coa_client_advancement.jsonl", "coa_client_class_types.jsonl",
                     "coa_client_tab_types.jsonl", "coa_client_essence.jsonl", "spell_layout_v2.json")


def candidate_trust_sha256(manifest: dict) -> str:
    """Digest the COMPLETE manifest minus ONLY the explicitly-mutable keys (publication_state,
    validation, budget) and the digest field itself — a strict complete view, so an unknown/new
    top-level field is never silently ignored, and only publication_state (candidate->published),
    /validation, and /budget may move candidate->final."""
    trust = {k: v for k, v in manifest.items()
             if k not in CANDIDATE_MUTABLE_KEYS and k != "candidate_trust_sha256"}
    return _sha256(json.dumps(trust, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def _read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


class _Cursor:
    """A forward, ascending-by-spell_id cursor that enforces sorted-unique order as it advances — no
    set/list materialization of the children."""
    def __init__(self, it, label):
        self._it, self._label, self._prev = iter(it), label, None
        self.row = None
        self.advance()

    def advance(self):
        self.row = next(self._it, None)
        if self.row is not None:
            sid = self.row["spell_id"]
            if self._prev is not None and sid <= self._prev:
                raise ResolveError(f"sorted_unique_ids: {self._label} duplicate/out-of-order spell_id {sid}")
            self._prev = sid
        return self.row


def _expand_compact(sid, field, cell) -> None:
    """compact_raw_expands_to_envelope: a compact raw cell must re-expand to a well-formed envelope — a
    resolvable state, a policy_ref, and enough raw (raw_u32 for numeric; raw_offset+resolved for string;
    components for a join) to reconstruct the value."""
    if "state" not in cell or ("policy_ref" not in cell and "components" not in cell):
        raise ResolveError(f"compact_raw_expands_to_envelope: {sid}:{field} missing state/policy_ref")
    if not ("raw_u32" in cell or "raw_offset" in cell or "components" in cell):
        raise ResolveError(f"compact_raw_expands_to_envelope: {sid}:{field} carries no raw to reconstruct")


def _identity_agrees(frow, prow) -> None:
    """identity_agrees: the full-table row and its projection must agree on identity + normalized
    mechanics (the projection is a re-view of the same spell, never a divergent one)."""
    if frow.get("name") != prow.get("name"):
        raise ResolveError(f"identity_agrees: spell {frow['spell_id']} name differs full vs projection")
    if frow.get("mechanics") != prow.get("mechanics"):
        raise ResolveError(f"identity_agrees: spell {frow['spell_id']} mechanics differ full vs projection")


def _cross_child(gen_dir: Path) -> None:
    """Streaming merge-join over ascending spell_id across the three spell children (design A5) — cursors
    only, no set/list materialization. Enforces projection⊆is_coa, projection-within-domain,
    identity_agrees, compact_raw_expands_to_envelope, icon coverage, and sorted-unique ids."""
    full = _Cursor(_read_jsonl(gen_dir / "coa_client_spell.jsonl"), "full")
    proj = _Cursor(_read_jsonl(gen_dir / "coa_client_spell_coa.jsonl"), "projection")
    icons = _Cursor(_read_jsonl(gen_dir / "coa_client_spell_icons.jsonl"), "icons")
    while full.row is not None:
        sid = full.row["spell_id"]
        while icons.row is not None and icons.row["spell_id"] < sid:
            icons.advance()
        if icons.row is None or icons.row["spell_id"] != sid:
            raise ResolveError(f"icons_agree: spell {sid} lacks an icon-catalog row")
        # a projection id strictly below the current is_coa cursor is outside the is_coa domain
        if proj.row is not None and proj.row["spell_id"] < sid:
            raise ResolveError(f"projection_within_domain: {proj.row['spell_id']} outside is_coa domain")
        is_coa = full.row.get("coa_attribution", {}).get("is_coa") is True
        if is_coa:
            if proj.row is None or proj.row["spell_id"] != sid:
                raise ResolveError(f"projection_is_coa_subset: {sid} missing from projection")
            _identity_agrees(full.row, proj.row)
            for field, cell in (proj.row.get("raw") or {}).items():
                _expand_compact(sid, field, cell)
            proj.advance()
        for field, cell in (full.row.get("raw") or {}).items():
            _expand_compact(sid, field, cell)
        full.advance()
    if proj.row is not None:                       # projection rows with no is_coa full row are out of domain
        raise ResolveError(f"projection_within_domain: {proj.row['spell_id']} outside is_coa domain")


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

`GenerationWriter.publish_candidate` writes the candidate manifest (`publication_state: "candidate"`, `candidate_trust_sha256`) **without** touching the pointer. `finalize_and_publish` reopens under an `fcntl.flock` on a `root/.publish.lock`, asserts `candidate_trust_sha256(final) == candidate digest` (the final differs only in the `CANDIDATE_MUTABLE_KEYS` — `publication_state` flips candidate→published, and `/validation`+`/budget` are added — all three excluded from the digest), writes the final manifest, revalidates the predecessor, then `os.replace`s the pointer last. `resolve_active_generation` refuses any manifest whose `publication_state == "candidate"`.

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

## Task 11: Remove AscensionDB integration entirely + network-trap negative gate

**Files:**
- Delete: `coa_scraper/scripts/enrich-ascensiondb.mjs`, `enrich-ascensiondb-assets.mjs`, `enrich-linked-items.mjs`, `apply-db-enrichment.mjs`, and the AscensionDB portions of `enrich-ascensiondb.mjs`'s helpers.
- Modify: `coa_scraper/scripts/lib/mechanics-reconcile.mjs`, `build-mechanics-artifacts.mjs`, `coa_meta/guide_tooltips.py` (drop `DB_HOST`/`db.ascension.gg`), `coa_scraper/package.json`, root `package.json`
- Create: `coa_scraper/scripts/lib/jsonl.mjs` (generic `readJsonl`, off `ascensiondb.mjs`); `coa_scraper/scripts/download-spell-icons.mjs` (opt-in, image-download-only utility — the *only* surviving `db.ascension.gg` touch, writing local files, no runtime URLs)
- Test: `coa_scraper/tests/no-ascensiondb.test.mjs`

**Interfaces:**
- Produces: `TIERS = ["client_dbc", "verified_builder", "inferred"]` (no `ascension_db`); `buildCanonicalMechanics({ entries, spellRows, projection })` — **no** `dbRows` parameter; `readJsonl` in `jsonl.mjs`. The `enrich-db`/`apply-db-enrichment`/`enrich-items`/`build-items`/`pipeline:m1.9` scripts are **removed** from both `package.json`s (not renamed); a `download-spell-icons` script is added.

- [ ] **Step 1: Write the failing test (network trap + provenance inspection)**

```javascript
// coa_scraper/tests/no-ascensiondb.test.mjs
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import http from "node:http";
import https from "node:https";
import { TIERS } from "../scripts/lib/mechanics-reconcile.mjs";
import { buildCanonicalMechanics } from "../scripts/build-mechanics-artifacts.mjs";

test("ascension_db is not a canonical reconciliation tier", () => {
  assert.ok(!TIERS.includes("ascension_db"));
});

test("no canonical AscensionDB command survives in either package.json", () => {
  for (const url of ["../package.json", "../../package.json"]) {
    const pkg = JSON.parse(fs.readFileSync(new URL(url, import.meta.url)));
    const joined = JSON.stringify(pkg.scripts);
    assert.ok(!/--db-spells|enrich-db|apply-db-enrichment|pipeline:m1\.9/.test(joined));
  }
  const scraper = JSON.parse(fs.readFileSync(new URL("../package.json", import.meta.url)));
  assert.ok(scraper.scripts["build-mechanics"].includes("--client-extract-pointer"));
});

test("canonical build makes NO network request and emits no ascension_db provenance", () => {
  const trap = () => { throw new Error("network access is forbidden in a canonical build"); };
  const origHttp = http.request, origHttps = https.request;
  http.request = trap; https.request = trap;                       // network trap
  try {
    const rows = buildCanonicalMechanics({ entries: [{ spell_id: 1, name: "X" }],
      spellRows: [], projection: [{ spell_id: 1, name: "X", mechanics: {}, raw: {} }] });
    const blob = JSON.stringify(rows);
    assert.ok(!/ascension_db|db\.ascension\.gg/.test(blob));
    assert.ok(!rows.some((r) => Object.values(r.field_provenance || {}).some(
      (p) => p.selected_tier === "ascension_db")));
  } finally { http.request = origHttp; https.request = origHttps; }
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test coa_scraper/tests/no-ascensiondb.test.mjs`
Expected: FAIL — `ascension_db` is still in `TIERS`, the scripts still exist, and `buildCanonicalMechanics` is not exported.

- [ ] **Step 3: Remove the integration**

- Drop `ascension_db` from `TIERS` in `mechanics-reconcile.mjs`; delete the `dbIdentityReference`/`applyDbIdentityGate`/DB-only-field code paths.
- Add `buildCanonicalMechanics({ entries, spellRows, projection })` (no `dbRows`); delete the `--db-spells` flag and the `--projection` legacy path from `build-mechanics-artifacts.mjs` (pointer-only).
- Create `jsonl.mjs` with `readJsonl` and re-point `build-mechanics-artifacts.mjs`'s import off `ascensiondb.mjs`.
- `git rm` `enrich-ascensiondb.mjs`, `enrich-ascensiondb-assets.mjs`, `enrich-linked-items.mjs`, `apply-db-enrichment.mjs`; remove `enrich-db`/`apply-db-enrichment`/`enrich-items`/`build-items`/`pipeline:m1.9`/`pipeline:m1.8`'s DB steps from both `package.json`s.
- Remove `DB_HOST`/`db.ascension.gg` from `guide_tooltips.py`.
- Add `download-spell-icons.mjs` — an opt-in CLI that, given a list of missing icon slugs, downloads **only** the image files to a local directory (writes files, prints a summary; never invoked by a canonical build).

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test coa_scraper/tests/no-ascensiondb.test.mjs`; `npm run build-mechanics` (pointer-only, green)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add coa_scraper/scripts/lib/mechanics-reconcile.mjs coa_scraper/scripts/lib/jsonl.mjs \
        coa_scraper/scripts/build-mechanics-artifacts.mjs coa_scraper/scripts/download-spell-icons.mjs \
        coa_meta/guide_tooltips.py coa_scraper/package.json package.json coa_scraper/tests/no-ascensiondb.test.mjs
git rm coa_scraper/scripts/enrich-ascensiondb.mjs coa_scraper/scripts/enrich-ascensiondb-assets.mjs \
       coa_scraper/scripts/enrich-linked-items.mjs coa_scraper/scripts/apply-db-enrichment.mjs
git commit -m "M1.14E0R Task 11: remove AscensionDB integration entirely; network-trap negative gate; image-only download utility"
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
                          "reason_code": "proven_empty"}}))
    assert r.costs == {} and r.field_readiness["costs"]["status"] == "verified_empty"


def test_contradictory_readiness_is_rejected():
    # verified_empty must carry an empty value + a "proven" reason; `not_extracted` contradicts it.
    with pytest.raises(MechanicsLoadError, match="readiness invariant"):
        mechanic_from_raw(_rec(costs=None, field_readiness={"costs": {"status": "verified_empty",
                          "reason_code": "not_extracted"}}))


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
- Modify: `coa_meta/action_catalog.py` (nullable fields + `quantitative_readiness` + null-safe serialization), `coa_meta/rotation_simulation.py` (**`simulate_apl` lives here**, still `gcd_ms or 1500`), `coa_meta/combat/state.py` + `coa_meta/combat/engine.py` (`CombatAction` defaults), `coa_meta/reporting.py` (label the heuristic path)
- Test: `tests/test_action_catalog_interlock.py`, `tests/test_simulation_interlock.py`

**Interfaces:**
- Produces: `CatalogAction.cooldown_ms: int | None`, `gcd_ms: int | None`, `costs: dict | None`; `ActionCatalog.quantitative_readiness -> {ready: bool, blocking: list[{action_key, field, status, reason_code}]}` propagated from `MechanicRecord.field_readiness` (not inferred from nullness); `simulate_apl` (in `rotation_simulation.py`) and combat conversion (`combat/engine.py`) raise `QuantitativeScopeUnready` when `not ready`; `heuristic_combat_action(node, category)` is the **only** place invented `1500`/`45_000`/estimated costs live (default-off; tagged `source: "heuristic"`).

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
# ActionCatalog gains readiness (design B5) — driven by MechanicRecord.field_readiness, not nullness.
_LOAD_BEARING = ("gcd_ms", "cooldown_ms", "costs")
_BLOCKING_STATUSES = {"unavailable", "ambiguous"}     # per contracts.READINESS_INVARIANTS


@property
def quantitative_readiness(self) -> dict:
    blocking = []
    for a in self.actions:
        for field in _LOAD_BEARING:
            fr = (a.field_readiness or {}).get(field, {})
            status = fr.get("status") or ("available" if getattr(a, field) is not None else "unavailable")
            if status in _BLOCKING_STATUSES:
                blocking.append({"action_key": a.action_key, "field": field, "status": status,
                                 "reason_code": fr.get("reason_code", "pending_e1_operand")})
    return {"ready": not blocking, "blocking": blocking}


def assert_quantitative_ready(self) -> None:
    rd = self.quantitative_readiness
    if not rd["ready"]:
        raise QuantitativeScopeUnready(f"{len(rd['blocking'])} action(s) lack load-bearing data")
```

`CatalogAction` carries `field_readiness: dict | None` (from `MechanicRecord.field_readiness`), and its `to_dict` serializes nullable `cooldown_ms`/`gcd_ms`/`costs` without coercion. In **`rotation_simulation.py`** (where `simulate_apl` lives — it still uses `gcd_ms or 1500`) and **`combat/engine.py`**, move the invented `gcd_ms=1500`/`cooldown_ms=45_000`/`_estimated_costs` into `heuristic_combat_action(node, category)` in `combat/state.py` (tagged `source="heuristic"`), keep it **off** unless an explicit `mode="heuristic"` is passed, and call `catalog.assert_quantitative_ready()` before any quantitative loop. `reporting.py` labels the tooltip-inference path `heuristic` and surfaces an explicit blocked result in canonical mode.

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
- Modify: `coa_meta/guide_assets.py`, `coa_meta/guide_builder.py` (and its callers that pass DB icon names/cached paths), `coa_scraper/scripts/lib/icon-assets.mjs`
- Test: `tests/test_guide_icons.py`, `coa_scraper/tests/icon-assets-e0r.test.mjs`

**Interfaces:**
- Produces: `GuideAssetCatalog(icon_catalog=<coa-client-spell-icons-v1 map>)` — resolves icons **only** from the client catalog: a `converted` row (with a bundle asset) renders it; a `source_only`/`missing` row (a verified BLP that is not itself browser-renderable, or no client member) renders a `source="placeholder"`; it **never** returns an `ascension_db_remote` asset and **never** falls through to a generic `asset_root` search that could resurrect a cached AscensionDB image. `ASCENSIONDB_ICON_URL_TEMPLATE` and the three `icon-assets.mjs` URL templates are deleted. (The BLP-bytes asset resolver that populates the catalog lives in `spell_icons.py`, Task 6.)

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


def test_source_only_renders_placeholder_and_converted_renders_asset():
    # source_only (BLP verified but not browser-renderable) -> placeholder, NOT an asset_root fallthrough
    src = GuideAssetCatalog(icon_catalog={133: {"client_path": "Interface/Icons/Spell_Fire_Fireball.blp",
                                                "asset_status": "source_only"}})
    a1 = src.icon_for(icon=None, label="Fireball", spell_id=133)
    assert a1.source == "placeholder" and "db.ascension.gg" not in str(a1.href or "")
    # converted -> the bundle asset is rendered from the client catalog
    conv = GuideAssetCatalog(icon_catalog={133: {"client_path": "Interface/Icons/Spell_Fire_Fireball.blp",
                                                 "asset_status": "converted", "converted_ref": "icons.tar#fireball.png"}})
    a2 = conv.icon_for(icon=None, label="Fireball", spell_id=133)
    assert a2.source == "client_icon" and "db.ascension.gg" not in str(a2.href or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_guide_icons.py -v`
Expected: FAIL — `ASCENSIONDB_ICON_URL_TEMPLATE` still exists and `icon_for` has no `spell_id`/client-catalog path.

- [ ] **Step 3: Implement client-native icons**

- Delete `ASCENSIONDB_ICON_URL_TEMPLATE` and the `ascension_db_remote` branch in `guide_assets.py`; add an `icon_catalog` constructor arg; in `icon_for(..., spell_id=None)`, look up the client catalog by `spell_id`: a `converted` row → `source="client_icon"` (href = the bundle asset); a `source_only`/`missing`/absent row → `source="placeholder"`. **Do not** fall through to the generic `asset_root` search (which could resurrect a cached AscensionDB image), and never construct a `db.ascension.gg` URL.
- Update `guide_builder.py` and its callers to pass `spell_id` + the client `icon_catalog` instead of DB icon names/cached paths.
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
- Produces: a CI workflow running the synthetic Python + Node suites on push/PR; `write_acceptance_summary(...)` emitting the schema-stable curated run record (`client_build`, `generation_id`, `manifest_sha256`, policy `sha256`, `extractor_commit`, `benchmark_env_id`, per-child `{sha256, byte_length, records}`, three-part regenerate `budget`, the canonical `build_mechanics` measurement `{elapsed_s, peak_rss_mb, pointer_only: true}`, recon `status`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r_acceptance_summary.py
from coa_client_extract.cli import write_acceptance_summary   # or wherever it lands


def test_acceptance_summary_has_stable_fields(tmp_path):
    summary = write_acceptance_summary(tmp_path, _fake_manifest(), recon_status="verified",
                                       benchmark_env_id="local-x86-64",
                                       build_mechanics={"elapsed_s": 4.2, "peak_rss_mb": 210, "pointer_only": True})
    assert set(summary) >= {"client_build", "generation_id", "manifest_sha256", "policy_sha256",
                            "extractor_commit", "benchmark_env_id", "children", "budget", "recon_status",
                            "build_mechanics"}
    assert summary["recon_status"] == "verified"
    assert summary["build_mechanics"]["pointer_only"] is True
```

- [ ] **Step 2–3:** red → implement `write_acceptance_summary(dist, manifest, *, recon_status, benchmark_env_id, build_mechanics)` and an `acceptance-summary` CLI subcommand that parses the `/usr/bin/time -v` output for elapsed + peak RSS and asserts `pointer_only` (the build-mechanics command carried no `--db-spells`); `.github/workflows/ci.yml` (checkout → `pip install -e .` → `pytest -q` → `npm --prefix coa_scraper ci` → `npm --prefix coa_scraper test`; the `client`/`stormlib` markers are excluded in CI and kept local); write the schema docs (client-spell v3, mechanics v2, generation v3, recon topology + negative anchor, the new field-readiness doc) and `DECISIONS.md` entries (evidence ≠ authorization; the generation manifest is authoritative, not a child, + candidate trust digest; full-topology hard hold; AscensionDB not a canonical source; missing ≠ default; client-native icons; explicit versioning); update `client-dbc-reference.md` confidence labels + `ROADMAP.md` (E0R inserted before E1) → green.

- [ ] **Step 4: Commit the code + CI + docs FIRST (a clean commit, no acceptance artifact yet)**

The acceptance summary is a *record of running the clean commit*, so it must not be part of the commit it attests to. Commit code/CI/docs first:

```bash
git add .github/workflows/ci.yml docs/ tests/test_e0r_acceptance_summary.py \
        coa_client_extract/cli.py
git commit -m "M1.14E0R Task 16: CI + schema/decision docs + acceptance-summary writer"
```

- [ ] **Step 5: From that clean commit, run every suite + the real-client regenerate AND the canonical build-mechanics; measure the budget**

```bash
pytest -q                                   # synthetic (all Python)
pytest -m client -q                         # real client (local only)
node --test coa_scraper/tests/*.test.mjs    # all Node
export COA_CLIENT_ROOT=/path/to/ascension-live/Data   # export FIRST — a `VAR=x cmd "$VAR"` prefix is not visible to "$VAR" on the same line
# (a) Full real-client regenerate (not just recon) — MUST be within the three-part budget:
python -m coa_client_extract mechanics --client-root "$COA_CLIENT_ROOT" --out coa_scraper/dist
# (b) The CANONICAL, pointer-only, network-free Node consumer build — measured end-to-end:
/usr/bin/time -v npm --prefix coa_scraper run build-mechanics 2>&1 | tee reports/client_extract/build_mechanics_time.txt
python -m coa_client_extract acceptance-summary --dist coa_scraper/dist --recon-status verified \
       --build-mechanics-time reports/client_extract/build_mechanics_time.txt \
       --out reports/client_extract/coa_e0r_acceptance_summary.json
```

Confirm the regenerate manifest's `budget["within_budget"] is True` **and** that `npm run build-mechanics` is pointer-only (no `--db-spells`, no network) and completes; the acceptance summary records both the regenerate budget and the canonical build-mechanics elapsed/peak-RSS.

- [ ] **Step 6: Commit the acceptance summary separately (attesting to the Step 4 commit)**

```bash
git add reports/client_extract/coa_e0r_acceptance_summary.json reports/client_extract/build_mechanics_time.txt
git commit -m "M1.14E0R Task 16: recorded full real-client regenerate + canonical build-mechanics within budget"
```

> ### ⛔ HUMAN CHECK-IN — end of E0R (the single human gate; performed on the pushed WIP branch)
> Now — and **only** now — push the branch for review:
> ```bash
> git push -u origin m1-14-e0r     # the one and only push in the milestone
> ```
> The human reviews `m1-14-e0r` on the remote against the [design](../specs/2026-07-19-m1-14-e0r-correctness-sunset-remediation-design.md) **Exit criteria**: canonical build pointer-only + fully AscensionDB-free (integration deleted, only the opt-in image-download utility remains); full-topology hard hold in recon **and** regenerate; `raw_only` never populates normalized + Node independent (biconditional) verification; transactional candidate→pointer with the trust digest + streaming cross-child; streaming within the three-part budget with a recorded real-client regenerate; missing ≠ default with the consumer interlock; client-native icons; clean tree; CI green. On approval, E0R ff-merges and M1.14E1 planning begins against the realized interfaces.

---

## Self-Review

**Spec coverage:** design-lock invariants (T1, also the plan's Global Constraints); A1 promotion + string join (T2, T3, T6); A2 shared topology + structured bound (T2, T4, and the hard hold in T10); A3 Node boundary numeric/string via `policy_ref` + lock (T7, wired in T10); A4 streaming compact-raw + hoisted provenance + three-part budget (T5 budget, T6 producer, T10 regenerate); A5 registry + candidate/final trust digest + cross-child + icon bundle + process lock + manifest-not-a-child (T9, T10); A6 `power_type` static negative anchor (T5, authored at the agent-run T8b adjudication); A7 hygiene (T15); B1/B2 total AscensionDB removal + network-trap negative gate + download-only image utility (T11); B3 `coa-mechanics-v2` (T12); B4 icons (T6 catalog + asset resolver, T14 guide/guide_builder); B5 interlock (T13); B6 item/asset AscensionDB code removed (T11); CI + docs + real-client regenerate (T16). One human check-in (the end-of-E0R review on the pushed branch); the recon adjudication (T8b) is agent-executable.

**Placeholder scan:** none — `spell_layout_v2.json` join cells and `spell_layout.lock.json` are honestly authored at the **agent-executable** T8b recon adjudication (code-gated: recon must return `verified`), not stubbed, and the canonical lock file is created **only** there (T7 uses an inline test lock, committing no placeholder); every code task carries full test + implementation code and a named commit; the prose-summarized steps (T8 Step 2–4, T10/T11/T12/T15/T16 Step 2–4) each name the exact functions/files and the green command.

**Type consistency:** `contracts.policy_ref`/`policy_ref_component`/enums/`TRUST_CRITICAL_MANIFEST_KEYS`/`CROSS_CHILD_CHECKS` (T1) are consumed by T2/T6/T7/T9/T12; `JoinPolicy.promotion` + structured `bound` (T2) by T6's four-part gate and T4/T10's hard hold; `make_string_join` (T3) by T6/T14; `verify_source_topology`/`topology_matches_bound` (T4) by T5/T10; `iter_spell_records`/`iter_icon_catalog` (T6) by T9's cross-child + T14; `candidate_trust_sha256`/`validate_candidate_generation`/`REQUIRED_CHILDREN` (T9) by T10; `verifyRowAgainstPolicy`/`assertPolicyLock` (T7) by T10's Node validation; `MECHANICS_SCHEMA_VERSION = "coa-mechanics-v2"` + `field_readiness` (T12) by T13's readiness gate; the `spell_v2.py` → `spell_record.py` rename is applied from T6 onward.

