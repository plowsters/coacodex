# M1.14 E0R.2 — close the E0R.1 review blockers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) or
> superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox
> (`- [ ]`) syntax for tracking. **This file is the canonical task tracker** (the MCP tracker is offline).

**Goal:** Make every guarantee E0R.1 *documented* impossible to violate, so PR #1 can merge on evidence
rather than on description.

**Architecture:** Seven review blockers, closed in dependency order. A **cryptographically bound**
generation contract — staged as a generation child, hashed into `manifest.binding`, covered by candidate
trust, and independently re-derived by both languages — replaces the name-only child registry, and
expresses *relational* cardinalities against the client topology rather than conservative floors. The
acceptance record becomes one internally-executed command whose every claim is bound to a single
generation id **and** manifest hash. Recon re-probes the ambiguous joins against a hash-bound baseline.
The canonical Node build streams end to end. A v4 schema migration sheds ~225 MB of measured redundancy.

**Tech Stack:** Python 3.11 (`coa_client_extract/`, `coa_meta/`), Node 20 ESM
(`coa_scraper/scripts/`), pytest, `node --test`.

## Global Constraints

- **Branch:** `m1-14-e0r`. No history rewrite. **Do NOT merge PR #1. Do NOT start E1.**
- **Commits:** explicit file paths only — **NEVER `git add -A`**. One contract-focused commit per task.
- **Method:** probe-first TDD. Every adversarial case is a failing test *before* its fix.
- **EVERY COMMIT LEAVES THE FULL SYNTHETIC SUITE GREEN.** No task may end with a knowingly-red test.
  Schema changes land as expand → migrate → contract, with each step independently valid. A gate that
  can only pass after a real-client run (the headroom assertion) is committed **together with** the
  artifact that satisfies it, never earlier.
- **Push:** once, at the end (WS8), after the full local suite is green. Never claim a remote green
  before the push.
- **Anchor-evidence precedence (verbatim, unchanged from E0R):** 1. Hash-bound client-static evidence
  (client strings, known BLP paths). 2. Verified Builder payload fields
  (`coa_scraper/dist/coa_entries.jsonl`) that explicitly encode the value. 3. Stock 3.3.5 data ONLY as
  corroboration for demonstrably-unchanged stock spells. Do not use AscensionDB, remembered values,
  runtime behavior, or values inferred from the candidate DBC column being tested.
- **Client root:** always referenced as `$COA_CLIENT_ROOT`, never as a literal path — including in this
  document, which T7.1's hygiene test scans.
- **Suites:** `pytest -q` from the repo root (CI runs **bare** `pytest`); `npm --prefix coa_scraper test`.
- **Baseline at plan time:** branch head `d69b5d3`, 625 Python + 121 Node green, generation
  `a9663d1b410841dd8284cb7538c61185` at 523,026,495 bytes (97.42% of ceiling).

## Verified schema facts this plan depends on

Established by probe against the tree at `02e0b7c` — do not re-derive, do not assume otherwise:

| Fact | Value |
|---|---|
| Recon client build | `recon.source_pins.client_build` |
| Recon per-table capture hash | `recon.source_pins.dbc.<Table>.sha256` |
| Recon topology | `recon.topology.tables.<Table>` (`.header.record_count`, `.sha256`, `.member`, …) |
| Manifest policy hash | `manifest.binding.policy_sha256` |
| Manifest topology | `manifest.binding.topology.tables.<Table>` — **not** `manifest.binding.tables` |
| Spell header record_count | 208,447 — **equals** the full child's record count exactly |
| Full-child raw cell shapes | `scalar` (1 `policy_ref`) or `join-absent` (1 `policy_ref`); **zero** resolved joins today |
| Resolved join shape | `_compact_join` emits `components.{index,side_id,side_value}`, each with its **own** `policy_ref` |
| `state` vocabulary | `present`, `unresolved`, `resolved`, `candidate`, `absent` — **no closed set is declared anywhere** |
| `decoded_reason` vocabulary | `decoded`, `not_present`, `proof_withheld`, `value_out_of_domain`, `index_zero`, `side_row_missing`, `non_finite`, `unknown_symbol` — **no closed set is declared anywhere** |
| Policy rehash | `load_spell_policy` raises `policy sha256 mismatch` on an edited doc; only `compute_policy_sha256(json.load(...))` yields a new hash |

---

## Execution status

| Task | Status | Commit |
|---|---|---|
| T0.1 Closed observation vocabularies as schema constants | pending | |
| T1.1 Contract document describing the **current** schema + validated loader | pending | |
| T1.2 Contract staged, hashed into `binding`, covered by candidate trust | pending | |
| T1.3 Node re-derives and compares the bound contract | pending | |
| T2.1 Relational cardinalities + unregistered children rejected | pending | |
| T2.2 Per-child shape validation (both languages) | pending | |
| T2.3 Full observation domain in the policy, validated at load | pending | |
| T2.4 Publication requires both validations and a clean budget | pending | |
| T2.5 `converted` prohibited until a bundle validator exists | pending | |
| T3.1 Live FK candidate scan on every recon | pending | |
| T3.2 Hash-bound ambiguity baseline; exact agreement required | pending | |
| T3.3 Recon stops claiming artifact size; policy-bound rss/elapsed | pending | |
| T4.1 `observation_coverage` + `field_readiness_coverage` producers | pending | |
| T4.2 One internally-executed acceptance command | pending | |
| T4.3 Acceptance binds recon + mechanics to one generation (real schemas) | pending | |
| T5.1 Streaming projection consumption | pending | |
| T5.2 Generator mechanics rows + incremental statistics | pending | |
| T5.3 Bounded-retention RSS gate through the real canonical build | pending | |
| T6.1 Kind-aware field descriptors (expand) | pending | |
| T6.2 v4 spell rows: hoist + intern (migrate + contract, atomic) | pending | |
| T6.3 Icon v2: normalized assets (migrate + contract, atomic) | pending | |
| T7.1 CI runs `npm test`; path hygiene over tracked text | pending | |
| T7.2 Documentation + ROADMAP corrections | pending | |
| T8.1 Real-client re-run: recon, regenerate, build, acceptance | pending | |
| T8.2 Headroom gate committed with the record | pending | |
| T8.3 Push, PR update, CI green | pending | |

---

# Workstream 0 — prerequisite: closed vocabularies

### Task 0.1: The observation vocabularies become schema-owned constants

**Files:**
- Modify: `coa_client_extract/contracts.py`
- Test: `tests/test_e0r2_vocabularies.py`

**Why first:** T6.2 interns `state` and `decoded_reason` as integer codes. Interning a vocabulary that
exists only as scattered string literals is unsound — a value with no code silently breaks
round-tripping, and a code assignment read from a staged data file lets an attacker relabel meanings
while keeping compact→rich expansion internally consistent. The codes must be **owned by the schema**,
not by the generation.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_vocabularies.py
"""E0R.2 T0.1: `state` and `decoded_reason` are closed vocabularies that existed only as scattered
string literals. T6.2 assigns them integer codes, so the vocabularies AND their code assignments must
be schema-owned constants — a code table read from the staged generation would let a tampered
descriptor relabel meanings while compact->rich expansion stayed self-consistent."""
import re
from pathlib import Path

from coa_client_extract.contracts import (DECODED_REASONS, DECODED_REASON_CODES, OBSERVATION_STATES,
                                          OBSERVATION_STATE_CODES)

SRC = Path(__file__).resolve().parents[1] / "coa_client_extract"


def test_the_vocabularies_are_closed_and_complete():
    assert OBSERVATION_STATES == ("absent", "candidate", "present", "resolved", "unresolved")
    assert DECODED_REASONS == (
        "decoded", "index_zero", "non_finite", "not_present", "proof_withheld",
        "side_row_missing", "unknown_symbol", "value_out_of_domain")


def test_codes_are_dense_stable_and_derived_from_the_tuple_order():
    """Dense 0..n-1 so an out-of-range index is detectable; tuple order is the wire format, so
    REORDERING THE TUPLE IS A SCHEMA BREAK — append only."""
    assert OBSERVATION_STATE_CODES == {s: i for i, s in enumerate(OBSERVATION_STATES)}
    assert DECODED_REASON_CODES == {r: i for i, r in enumerate(DECODED_REASONS)}


def test_no_producer_emits_a_value_outside_the_vocabulary():
    """The real defect this guards: a new literal added in spell_record.py with no code assignment."""
    literals = set()
    for path in SRC.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'"(?:state|decoded_reason)":\s*"([a-z_]+)"', text):
            literals.add(match.group(1))
    unknown = literals - set(OBSERVATION_STATES) - set(DECODED_REASONS)
    assert unknown == set(), f"producer emits values with no schema code: {sorted(unknown)}"
```

- [ ] **Step 2: Run and confirm failure** — `ImportError: cannot import name 'DECODED_REASONS'`.

- [ ] **Step 3: Add the constants to `contracts.py`**

```python
# The closed observation vocabularies (E0R.2 T0.1). Order IS the wire format: T6.2 serializes the index,
# so entries may be APPENDED but never reordered or removed without a schema version bump. Sourced by
# enumerating every literal the producer emits (`spell_record.py`, `observations.py`) — before this,
# no closed set existed anywhere in the package.
OBSERVATION_STATES = ("absent", "candidate", "present", "resolved", "unresolved")
DECODED_REASONS = ("decoded", "index_zero", "non_finite", "not_present", "proof_withheld",
                   "side_row_missing", "unknown_symbol", "value_out_of_domain")
OBSERVATION_STATE_CODES = {s: i for i, s in enumerate(OBSERVATION_STATES)}
DECODED_REASON_CODES = {r: i for i, r in enumerate(DECODED_REASONS)}
```

- [ ] **Step 4: Run the full suite; commit**

```bash
git add coa_client_extract/contracts.py tests/test_e0r2_vocabularies.py
git commit -m "feat(e0r2): T0.1 — closed observation vocabularies as schema-owned constants"
```

---

# Workstream 1 — a cryptographically bound generation contract (blocker 1, part 1)

**Blocker:** both validators accept a candidate carrying every required child *name* with zero
spell/projection/icon rows and arbitrary child `schema_version` strings. Reproduced at `02e0b7c`:

```
=== PYTHON validate_candidate_generation ===  ACCEPTED
=== NODE  validateCandidateByPath        ===  ACCEPTED
```

**Correction carried from review round 2:** a contract read from the working tree is not bound to the
generation. A generation produced under contract A could later be validated under contract B. The
contract must be staged as a child, hashed into `manifest.binding`, and covered by candidate trust —
and **both languages must compare the staged contract against their own trusted supported contract**,
so a tampered staged copy is rejected rather than obeyed.

**This workstream describes the CURRENT schema** (`coa-client-spell-v3`, `coa-client-spell-icons-v1`,
11 children). WS6 migrates to v4 and updates the contract atomically. Every commit here is green.

### Task 1.1: The contract document and a self-validating loader

**Files:**
- Create: `coa_client_extract/data/generation_contract.json`
- Modify: `coa_client_extract/contracts.py`
- Test: `tests/test_e0r2_generation_contract.py`

**Interfaces:**
- Produces: `GENERATION_CONTRACT_SCHEMA = "coa-generation-contract-v1"`,
  `load_generation_contract() -> dict`, `validate_generation_contract(doc) -> dict` (raises
  `ContractError`), `generation_contract_sha256(doc) -> str` (canonical JSON: sorted keys, no
  whitespace variance).

Per-child shape:

```json
{
  "kind": "jsonl" | "json",
  "child_schema_version": "<exact string>",
  "row_schema_version": "<exact string>" | null,
  "optional": false,
  "cardinality": {"rule": "<named relational rule>" | "min", "min": <int>},
  "shape": "<named semantic validator>"
}
```

`cardinality.rule` names a **relational** rule resolved at validation time (see T2.1); `"min"` with an
explicit floor is permitted **only** for ancillary datasets whose exact source-domain count cannot be
derived. `shape` names a validator implemented independently in both languages (see T2.2) — top-level
key presence is not a shape.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_generation_contract.py
"""E0R.2 T1.1: the generation contract is ONE versioned, SELF-VALIDATED document. A name list cannot
express cardinality, row schema, or shape — which is how a complete-but-empty generation passed both
validators at 02e0b7c. The loader validates the contract itself: a malformed contract is a broken gate,
and a broken gate that loads is worse than no gate."""
import copy

import pytest

from coa_client_extract.contracts import (ContractError, GENERATION_CONTRACT_SCHEMA,
                                          generation_contract_sha256, load_generation_contract,
                                          validate_generation_contract)
from coa_client_extract.publish import REQUIRED_CHILDREN


def test_contract_covers_exactly_the_required_children():
    contract = load_generation_contract()
    assert contract["schema_version"] == GENERATION_CONTRACT_SCHEMA
    assert set(contract["children"]) == set(REQUIRED_CHILDREN)


def test_every_child_declares_kind_schema_cardinality_and_shape():
    for name, spec in load_generation_contract()["children"].items():
        assert spec["kind"] in ("jsonl", "json"), name
        assert spec["child_schema_version"], name
        assert spec["shape"], name
        assert spec["cardinality"]["rule"], name
        if spec["kind"] == "jsonl":
            assert spec["row_schema_version"], name
        else:
            assert spec["row_schema_version"] is None, name


def test_the_spell_domain_children_use_relational_cardinality_not_a_floor():
    """A floor of 1 admits a one-spell generation. The domain count is derivable from the client
    topology, so it must be derived."""
    children = load_generation_contract()["children"]
    assert children["coa_client_spell.jsonl"]["cardinality"]["rule"] == "spell_topology_record_count"
    assert children["coa_client_spell_icons.jsonl"]["cardinality"]["rule"] == "equals_full_spell_records"
    assert children["coa_client_spell_coa.jsonl"]["cardinality"]["rule"] == "equals_is_coa_full_records"


@pytest.mark.parametrize("mutate, match", [
    (lambda d: d.update(schema_version="nope"), "schema_version"),
    (lambda d: d["children"]["spell_layout_v2.json"].update(kind="parquet"), "kind"),
    (lambda d: d["children"]["spell_layout_v2.json"].update(shape=""), "shape"),
    (lambda d: d["children"]["spell_layout_v2.json"].update(unexpected_key=1), "unexpected_key"),
    (lambda d: d["children"]["coa_client_spell.jsonl"].update(row_schema_version=None), "row_schema_version"),
    (lambda d: d["children"].update(dupe=copy.deepcopy(d["children"]["spell_layout_v2.json"])), "shape"),
])
def test_the_loader_rejects_a_malformed_contract(mutate, match):
    doc = copy.deepcopy(load_generation_contract())
    mutate(doc)
    with pytest.raises(ContractError, match=match):
        validate_generation_contract(doc)


def test_the_contract_hash_is_canonical_and_stable():
    doc = load_generation_contract()
    reordered = {"children": doc["children"], "schema_version": doc["schema_version"],
                 **{k: v for k, v in doc.items() if k not in ("children", "schema_version")}}
    assert generation_contract_sha256(doc) == generation_contract_sha256(reordered)
    assert len(generation_contract_sha256(doc)) == 64
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Author the contract for the CURRENT schema**

Eleven children, matching what `regenerate` emits today. Relational rules for the three spell-domain
children and the two derived-count JSON children; explicit `min` floors **only** for the five ancillary
DBC-derived tables, whose source-domain counts are not recorded in the topology binding.

```json
{
  "schema_version": "coa-generation-contract-v1",
  "note": "The E0R child contract. STAGED as a generation child and hashed into manifest.binding, so a generation is always interpreted under the contract it was produced with. Both languages re-derive their own trusted copy and compare.",
  "children": {
    "coa_client_spell.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-spell-v3",
      "row_schema_version": "coa-client-spell-v3", "optional": false,
      "cardinality": {"rule": "spell_topology_record_count"}, "shape": "full_spell_row_v3"
    },
    "coa_client_spell_coa.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-spell-projection-v3",
      "row_schema_version": "coa-client-spell-projection-v3", "optional": false,
      "cardinality": {"rule": "equals_is_coa_full_records"}, "shape": "projection_row_v3"
    },
    "coa_client_spell_icons.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-spell-icons-v1",
      "row_schema_version": "coa-client-spell-icons-v1", "optional": false,
      "cardinality": {"rule": "equals_full_spell_records"}, "shape": "icon_row_v1"
    },
    "coa_client_spell_projection.manifest.json": {
      "kind": "json", "child_schema_version": "coa-client-spell-projection-manifest-v3",
      "row_schema_version": null, "optional": false,
      "cardinality": {"rule": "single_document"}, "shape": "projection_manifest_v3"
    },
    "spell_layout_v2.json": {
      "kind": "json", "child_schema_version": "coa-spell-layout-v2",
      "row_schema_version": null, "optional": false,
      "cardinality": {"rule": "single_document"}, "shape": "spell_policy_v2"
    },
    "coa_client_archive_plan.json": {
      "kind": "json", "child_schema_version": "coa-client-archive-plan-v1",
      "row_schema_version": null, "optional": false,
      "cardinality": {"rule": "single_document"}, "shape": "archive_plan_v1"
    },
    "coa_client_content.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-content-v1",
      "row_schema_version": "coa-client-content-v1", "optional": false,
      "cardinality": {"rule": "min", "min": 1000}, "shape": "content_row_v1"
    },
    "coa_client_advancement.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-advancement-v1",
      "row_schema_version": "coa-client-advancement-v1", "optional": false,
      "cardinality": {"rule": "min", "min": 100}, "shape": "advancement_row_v1"
    },
    "coa_client_class_types.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-class-types-v1",
      "row_schema_version": "coa-client-class-types-v1", "optional": false,
      "cardinality": {"rule": "min", "min": 1}, "shape": "class_type_row_v1"
    },
    "coa_client_tab_types.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-tab-types-v1",
      "row_schema_version": "coa-client-tab-types-v1", "optional": false,
      "cardinality": {"rule": "min", "min": 1}, "shape": "tab_type_row_v1"
    },
    "coa_client_essence.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-essence-v1",
      "row_schema_version": "coa-client-essence-v1", "optional": false,
      "cardinality": {"rule": "min", "min": 1}, "shape": "essence_row_v1"
    }
  }
}
```

- [ ] **Step 4: Implement the loader with full self-validation**

```python
class ContractError(Exception):
    """The generation contract itself is malformed. A broken gate that loads is worse than no gate."""


_CHILD_KEYS = {"kind", "child_schema_version", "row_schema_version", "optional", "cardinality", "shape"}
_CARDINALITY_RULES = frozenset({
    "spell_topology_record_count", "equals_full_spell_records", "equals_is_coa_full_records",
    "single_document", "min"})


def validate_generation_contract(doc: dict) -> dict:
    if doc.get("schema_version") != GENERATION_CONTRACT_SCHEMA:
        raise ContractError(f"contract schema_version {doc.get('schema_version')!r}")
    children = doc.get("children")
    if not isinstance(children, dict) or not children:
        raise ContractError("contract declares no children")
    seen_shapes = set()
    for name, spec in children.items():
        extra = set(spec) - _CHILD_KEYS
        if extra:
            raise ContractError(f"child {name!r} has unexpected_key(s) {sorted(extra)}")
        missing = _CHILD_KEYS - set(spec)
        if missing:
            raise ContractError(f"child {name!r} missing {sorted(missing)}")
        if spec["kind"] not in ("jsonl", "json"):
            raise ContractError(f"child {name!r} kind {spec['kind']!r}")
        if not spec["child_schema_version"] or not isinstance(spec["child_schema_version"], str):
            raise ContractError(f"child {name!r} child_schema_version")
        if spec["kind"] == "jsonl":
            if not spec["row_schema_version"]:
                raise ContractError(f"child {name!r} jsonl child needs a row_schema_version")
        elif spec["row_schema_version"] is not None:
            raise ContractError(f"child {name!r} json child must have row_schema_version null")
        if not isinstance(spec["shape"], str) or not spec["shape"]:
            raise ContractError(f"child {name!r} shape must name a validator")
        if spec["shape"] in seen_shapes:
            raise ContractError(f"shape {spec['shape']!r} is reused; each child needs its own shape")
        seen_shapes.add(spec["shape"])
        rule = (spec["cardinality"] or {}).get("rule")
        if rule not in _CARDINALITY_RULES:
            raise ContractError(f"child {name!r} cardinality rule {rule!r}")
        if rule == "min" and not isinstance(spec["cardinality"].get("min"), int):
            raise ContractError(f"child {name!r} min cardinality needs an integer floor")
    return doc


def generation_contract_sha256(doc: dict) -> str:
    """Canonical digest: sorted keys, no whitespace variance — key order must not change the hash."""
    import hashlib
    import json
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
```

- [ ] **Step 5: Derive `REQUIRED_CHILDREN` from the contract in `publish.py`** so the first test passes:
  `REQUIRED_CHILDREN = tuple(sorted(load_generation_contract()["children"]))`. Because this workstream
  describes the *current* schema, the derived tuple equals the existing literal and nothing else moves.

- [ ] **Step 6: Run the full suite (must be fully green); commit**

```bash
python -m pytest -q
git add coa_client_extract/data/generation_contract.json coa_client_extract/contracts.py \
        coa_client_extract/publish.py tests/test_e0r2_generation_contract.py
git commit -m "feat(e0r2): T1.1 — a self-validating generation contract for the current schema"
```

### Task 1.2: The contract is staged, hashed into `binding`, and covered by candidate trust

**Files:**
- Modify: `coa_client_extract/cli.py` (`regenerate` — stage the child, extend `binding`),
  `coa_client_extract/publish.py` (`validate_candidate_generation`),
  `coa_client_extract/data/generation_contract.json` (add itself as a child)
- Test: `tests/test_e0r2_contract_binding.py`

**Design:** the contract is staged as `generation_contract.json` (a twelfth child, self-describing) and
`manifest.binding.generation_contract = {"schema_version": ..., "sha256": ...}`. `binding` is already
inside `TRUST_CRITICAL_MANIFEST_KEYS`, so candidate trust covers the hash with no change to the digest
definition. Validation compares three things: the **staged child bytes**, the **bound hash**, and the
validator's **own trusted contract**. All three must agree.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_contract_binding.py
"""E0R.2 T1.2: a contract read from the working tree is not bound to the generation — a generation
produced under contract A could later be validated under contract B. Stage it, hash it into binding,
cover it with candidate trust, and make the validator compare the staged copy against its OWN trusted
contract so a tampered staged copy is rejected rather than obeyed."""
import json

import pytest

from coa_client_extract.contracts import generation_contract_sha256, load_generation_contract
from coa_client_extract.publish import ResolveError, validate_candidate_generation
from tests._e0r2_fixtures import stage_candidate


def test_the_contract_is_staged_as_a_child_and_bound_in_the_manifest(tmp_path):
    gen = stage_candidate(tmp_path)
    manifest = json.loads((gen / "manifest.json").read_text(encoding="utf-8"))
    bound = manifest["binding"]["generation_contract"]
    assert bound["sha256"] == generation_contract_sha256(load_generation_contract())
    assert (gen / "generation_contract.json").is_file()


def test_a_staged_contract_that_differs_from_the_bound_hash_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, tamper_staged_contract={"schema_version": "coa-generation-contract-v1",
                                                            "children": {}})
    with pytest.raises(ResolveError, match="generation_contract"):
        validate_candidate_generation(gen)


def test_a_generation_bound_to_an_unsupported_contract_is_rejected(tmp_path):
    """Both the staged child AND the bound hash say contract B; the validator only supports A."""
    gen = stage_candidate(tmp_path, contract_override={"schema_version": "coa-generation-contract-v1",
                                                        "children": {"only.jsonl": {}}})
    with pytest.raises(ResolveError, match="not the supported contract"):
        validate_candidate_generation(gen)


def test_candidate_trust_covers_the_bound_contract_hash(tmp_path):
    """Rewriting the bound hash without restaging breaks the trust digest."""
    gen = stage_candidate(tmp_path)
    manifest = json.loads((gen / "manifest.json").read_text(encoding="utf-8"))
    manifest["binding"]["generation_contract"]["sha256"] = "0" * 64
    (gen / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ResolveError, match="candidate_trust_sha256"):
        validate_candidate_generation(gen)
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement**

Stage the contract in `regenerate` beside `spell_layout_v2.json`; add
`binding["generation_contract"] = {"schema_version": ..., "sha256": generation_contract_sha256(doc)}`;
add `generation_contract.json` to the contract's own `children` map (kind `json`, shape
`generation_contract_v1`, `single_document`). In `validate_candidate_generation`, before any per-child
work:

```python
    supported = load_generation_contract()
    staged_path = gen_dir / "generation_contract.json"
    if not staged_path.is_file():
        raise ResolveError("generation_contract child missing; the generation is unbound")
    staged = json.loads(staged_path.read_text(encoding="utf-8"))
    staged_sha = generation_contract_sha256(staged)
    bound_sha = ((manifest.get("binding") or {}).get("generation_contract") or {}).get("sha256")
    if staged_sha != bound_sha:
        raise ResolveError(
            f"generation_contract: staged child hashes {staged_sha[:16]} but binding names {str(bound_sha)[:16]}")
    if staged_sha != generation_contract_sha256(supported):
        raise ResolveError(
            "generation_contract: the generation is bound to a contract that is not the supported "
            f"contract ({staged_sha[:16]} != {generation_contract_sha256(supported)[:16]})")
    contract = validate_generation_contract(staged)
```

Use `contract` — the verified staged copy — for all downstream child checks.

- [ ] **Step 4: Run the full suite; commit**

```bash
git add coa_client_extract/cli.py coa_client_extract/publish.py \
        coa_client_extract/data/generation_contract.json tests/test_e0r2_contract_binding.py
git commit -m "feat(e0r2): T1.2 — the contract is staged, bound in the manifest, and trust-covered"
```

### Task 1.3: Node re-derives and compares the bound contract

**Files:**
- Modify: `coa_scraper/scripts/lib/generation.mjs:19-25` (delete the mirrored name list)
- Test: `coa_scraper/tests/generation-contract.test.mjs`

**Design:** Node loads its **own** trusted copy from `coa_client_extract/data/generation_contract.json`
(the same file Python ships, so there is no hand-mirrored constant to drift), validates it with an
independent implementation of `validateGenerationContract`, then performs the same three-way comparison
against the staged child and the bound hash. Node's canonical-JSON hash must agree byte-for-byte with
Python's — that equality is itself a test.

- [ ] **Step 1: Write the failing test**

```javascript
// coa_scraper/tests/generation-contract.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { loadGenerationContract, generationContractSha256, validateCandidateByPath,
         GenerationResolveError } from "../scripts/lib/generation.mjs";
import { stageCandidate } from "./_e0r2-fixtures.mjs";

test("Node and Python compute the same canonical contract hash", () => {
  const fromPython = execFileSync("python3", ["-c",
    "from coa_client_extract.contracts import generation_contract_sha256, load_generation_contract;" +
    "print(generation_contract_sha256(load_generation_contract()))"],
    { cwd: "..", encoding: "utf8", env: { ...process.env, PYTHONPATH: ".." } }).trim();
  assert.equal(generationContractSha256(loadGenerationContract()), fromPython);
});

test("a staged contract that differs from the bound hash is rejected", (t) => {
  const dir = stageCandidate(t, { tamperStagedContract: true });
  assert.throws(() => validateCandidateByPath(dir), /generation_contract/);
});

test("a generation bound to an unsupported contract is rejected", (t) => {
  const dir = stageCandidate(t, { contractOverride: { schema_version: "coa-generation-contract-v1", children: {} } });
  assert.throws(() => validateCandidateByPath(dir), /not the supported contract/);
});

test("the hand-mirrored name list is gone", () => {
  const src = fs.readFileSync(new URL("../scripts/lib/generation.mjs", import.meta.url), "utf8");
  assert.ok(!/REQUIRED_CHILDREN = \[/.test(src), "a mirrored constant is what drifts");
});
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement** `loadGenerationContract`, `validateGenerationContract`,
  `generationContractSha256` (canonical JSON: `JSON.stringify` over recursively key-sorted objects with
  no separators — verify against Python by the first test), and the three-way comparison in
  `validateCandidateByPath`. `REQUIRED_CHILDREN` becomes a derived export.

- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_scraper/scripts/lib/generation.mjs coa_scraper/tests/generation-contract.test.mjs \
        coa_scraper/tests/_e0r2-fixtures.mjs
git commit -m "feat(e0r2): T1.3 — Node re-derives and compares the bound contract"
```

---

# Workstream 2 — real domain enforcement (blocker 1, part 2; blocker 7)

### Task 2.1: Relational cardinalities; unregistered children rejected

**Files:**
- Modify: `coa_client_extract/publish.py`, `coa_scraper/scripts/lib/generation.mjs`
- Test: `tests/test_e0r2_cardinality.py`, `coa_scraper/tests/generation-contract.test.mjs`

**Correction carried from review round 2:** a floor of 1 admits a one-spell generation, and my earlier
claim that an unregistered child is "caught by `candidate_trust_sha256`" was **wrong** — the digest
authenticates an intentionally-added child, it does not reject one. Both are fixed here.

**The relational rules** (`binding.topology.tables.Spell.header.record_count` is 208,447 and equals the
full child's record count exactly — verified):

| rule | assertion |
|---|---|
| `spell_topology_record_count` | full-child records **==** `manifest.binding.topology.tables.Spell.header.record_count` |
| `equals_full_spell_records` | icon-child records **==** full-child records |
| `equals_is_coa_full_records` | projection records **==** count of full rows with `coa_attribution.is_coa is True` |
| `single_document` | exactly 1 record |
| `min` | records **>=** floor (ancillary tables only) |

The projection equality is *already* enforced exactly by `_cross_child`'s streaming merge-join
(`projection_is_coa_subset` + `projection_within_domain` compose to an equality). The contract-level
count is a cheap manifest-level pre-check that fails fast with a clearer message — it is not new
coverage, and it must not be treated as replacing the merge-join.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_cardinality.py
"""E0R.2 T2.1: `min_records: 1` is not a domain gate — a one-spell generation passes it. The client
topology records the exact source-domain count, so the contract derives the expectation instead of
guessing a floor."""
import pytest

from coa_client_extract.publish import ResolveError, validate_candidate_generation
from tests._e0r2_fixtures import stage_candidate


def test_a_truncated_full_child_is_rejected(tmp_path):
    """Three spells staged, topology says three; drop one row and restage the manifest honestly."""
    gen = stage_candidate(tmp_path, truncate_full_to=2)
    with pytest.raises(ResolveError, match="spell_topology_record_count|2 != 3"):
        validate_candidate_generation(gen)


def test_an_icon_catalog_shorter_than_the_full_domain_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, truncate_icons_to=2)
    with pytest.raises(ResolveError, match="equals_full_spell_records"):
        validate_candidate_generation(gen)


def test_a_projection_missing_an_is_coa_row_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, drop_projection_rows=1)
    with pytest.raises(ResolveError, match="equals_is_coa_full_records|projection_is_coa_subset"):
        validate_candidate_generation(gen)


def test_a_json_child_with_more_than_one_document_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, duplicate_json_document="coa_client_archive_plan.json")
    with pytest.raises(ResolveError, match="single_document"):
        validate_candidate_generation(gen)


def test_an_unregistered_child_is_rejected(tmp_path):
    """candidate_trust_sha256 AUTHENTICATES an added child; it does not reject one."""
    gen = stage_candidate(tmp_path, extra_child=("smuggled.jsonl", b'{"x":1}\n'))
    with pytest.raises(ResolveError, match="unregistered child"):
        validate_candidate_generation(gen)


def test_a_wellformed_candidate_still_validates(tmp_path):
    validate_candidate_generation(stage_candidate(tmp_path))
```

- [ ] **Step 2: Run and confirm the first five fail.**

- [ ] **Step 3: Implement `_resolve_cardinality(rule, name, meta, manifest, gen_dir, counts)`**

The `is_coa` count is accumulated during the streaming pass `_cross_child` already makes — do not add a
second full read. Reject unregistered children explicitly:

```python
    registered = set(contract["children"])
    for name in children:
        if name not in registered:
            raise ResolveError(
                f"unregistered child {name!r}: the contract is a whitelist, and candidate trust "
                "authenticates an added child rather than rejecting it")
```

- [ ] **Step 4: Mirror in `generation.mjs`; run both suites; commit**

```bash
git add coa_client_extract/publish.py coa_scraper/scripts/lib/generation.mjs \
        tests/test_e0r2_cardinality.py coa_scraper/tests/generation-contract.test.mjs
git commit -m "fix(e0r2): T2.1 — relational cardinalities and a child whitelist"
```

### Task 2.2: Per-child shape validation in both languages

**Files:**
- Create: `coa_client_extract/shapes.py`, `coa_scraper/scripts/lib/shapes.mjs`
- Modify: `coa_client_extract/publish.py`, `coa_scraper/scripts/lib/generation.mjs`
- Test: `tests/test_e0r2_shapes.py`, `coa_scraper/tests/shapes.test.mjs`

**Correction carried from review round 2:** checking `schema_version` plus top-level key presence
establishes neither field types, nullability, nested envelope shape, nor JSON-document semantics —
`{}` would pass as a one-record JSON artifact.

**Design:** each contract `shape` name maps to a validator function implemented **independently** in
both languages (independent implementations are the point — a shared serialization would reproduce a
shared bug). Each validator asserts: exact key set (no unknown keys), per-key type, explicit
nullability, and nested envelope shape. The two implementations are held together by the shared golden
corpus, which every shape validator runs against in both languages.

- [ ] **Step 1: Write the failing test** — for each shape, a positive case from the golden corpus and
  negative cases for: unknown key, wrong scalar type, null in a non-nullable slot, non-null in a
  must-be-null slot, malformed nested envelope, and (for JSON children) `{}`.

```python
# tests/test_e0r2_shapes.py
"""E0R.2 T2.2: a shape is a type contract, not a key list. `{}` passed as a one-record JSON artifact
because `requires: []` asked nothing of it."""
import pytest

from coa_client_extract.shapes import SHAPES, ShapeError
from tests.golden import golden_rows


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_shape_accepts_its_golden_row(shape):
    SHAPES[shape](golden_rows(shape))


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_shape_rejects_an_unknown_key(shape):
    row = dict(golden_rows(shape)); row["smuggled"] = 1
    with pytest.raises(ShapeError, match="smuggled"):
        SHAPES[shape](row)


def test_an_empty_json_document_is_not_a_valid_archive_plan():
    with pytest.raises(ShapeError):
        SHAPES["archive_plan_v1"]({})


def test_a_full_row_with_a_malformed_raw_envelope_is_rejected():
    row = dict(golden_rows("full_spell_row_v3"))
    row["raw"] = {"id": {"state": "present"}}          # no decoded_reason, no substrate
    with pytest.raises(ShapeError, match="raw.id"):
        SHAPES["full_spell_row_v3"](row)


def test_mechanics_values_may_be_null_but_the_keys_may_not_be_absent():
    row = dict(golden_rows("full_spell_row_v3"))
    row["mechanics"] = {k: None for k in row["mechanics"]}
    SHAPES["full_spell_row_v3"](row)                    # nullable values: fine
    row["mechanics"].pop("school_mask")
    with pytest.raises(ShapeError, match="school_mask"):
        SHAPES["full_spell_row_v3"](row)
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `SHAPES` in Python and `shapes.mjs` in Node**, wired into the streaming row
  loop from T2.1 (one pass, shape-checked per row).
- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_client_extract/shapes.py coa_scraper/scripts/lib/shapes.mjs \
        coa_client_extract/publish.py coa_scraper/scripts/lib/generation.mjs \
        tests/test_e0r2_shapes.py coa_scraper/tests/shapes.test.mjs
git commit -m "fix(e0r2): T2.2 — per-child shape validators in both languages"
```

### Task 2.3: The full observation domain lives in the policy and is validated at load

**Files:**
- Modify: `coa_client_extract/data/spell_layout_v2.json`, `coa_client_extract/spell_layout.py`
  (`load_spell_policy`), `coa_scraper/config/spell_layout.lock.json`
- Test: `tests/test_e0r2_observation_domain.py`

**Correction carried from review round 2:** `required_scalar_fields = ["id","name","power_type",
"school_mask"]` still permits omitting `description`, `cast_time_ms`, `duration_ms`, `range_min_yd`
and `range_max_yd` entirely. **Required means the observation envelope exists, not that a normalized
value exists** — and the real rows already satisfy that: every one of the 208,447 rows carries all nine
raw cells, the join-derived ones in `state: "unresolved"` form. My earlier exclusion of them conflated
"normalized value is null" with "cell absent" and was wrong.

**Design:** replace the single flat list with an explicit three-part `artifact_contract`, validated in
`load_spell_policy()` rather than left as an unchecked JSON property that only Node consumes:

```json
"artifact_contract": {
  "required_raw_observations": ["cast_time_ms", "description", "duration_ms", "id", "name",
                                "power_type", "range_max_yd", "range_min_yd", "school_mask"],
  "required_mechanics_keys": ["cast_time_ms", "duration_ms", "power_type", "range_max_yd",
                              "range_min_yd", "school_mask"],
  "nullable_mechanics_keys": ["cast_time_ms", "duration_ms", "power_type", "range_max_yd",
                              "range_min_yd"],
  "icon_observation_domain": ["spell_icon_id"]
}
```

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_observation_domain.py
"""E0R.2 T2.3: lossless extraction means every field has an OBSERVATION, even when it has no
normalized value. A raw_only join in `unresolved` state is still a required cell; omitting it is
silent loss, which is exactly what E0R exists to prevent."""
import copy
import json
from pathlib import Path

import pytest

from coa_client_extract.spell_layout import SpellPolicyError, compute_policy_sha256, load_spell_policy

POLICY = Path(__file__).resolve().parents[1] / "coa_client_extract/data/spell_layout_v2.json"


def _policy_doc():
    return json.loads(POLICY.read_text(encoding="utf-8"))


def test_the_production_policy_requires_the_full_raw_domain():
    contract = _policy_doc()["artifact_contract"]
    assert set(contract["required_raw_observations"]) == {
        "cast_time_ms", "description", "duration_ms", "id", "name", "power_type",
        "range_max_yd", "range_min_yd", "school_mask"}


def test_nullable_mechanics_keys_are_a_subset_of_required_mechanics_keys():
    contract = _policy_doc()["artifact_contract"]
    assert set(contract["nullable_mechanics_keys"]) <= set(contract["required_mechanics_keys"])
    assert "school_mask" not in contract["nullable_mechanics_keys"]   # proven, never null


def test_load_spell_policy_rejects_an_incoherent_artifact_contract():
    doc = _policy_doc()
    doc["artifact_contract"]["nullable_mechanics_keys"].append("not_a_field")
    doc["sha256"] = compute_policy_sha256(doc)      # rehash so we test the contract check, not the hash
    with pytest.raises(SpellPolicyError, match="not_a_field"):
        load_spell_policy(doc)


def test_load_spell_policy_rejects_a_missing_artifact_contract():
    doc = _policy_doc()
    del doc["artifact_contract"]
    doc["sha256"] = compute_policy_sha256(doc)
    with pytest.raises(SpellPolicyError, match="artifact_contract"):
        load_spell_policy(doc)
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Add the block, validate it in `load_spell_policy`, and rehash correctly**

`load_spell_policy` raises `policy sha256 mismatch` on an edited document, so
`load_default_policy().sha256` can **never** yield the new hash. Load the JSON directly:

```bash
python -c "
import json, pathlib
from coa_client_extract.spell_layout import compute_policy_sha256
p = pathlib.Path('coa_client_extract/data/spell_layout_v2.json')
doc = json.loads(p.read_text(encoding='utf-8'))
doc.pop('sha256', None)
doc['sha256'] = compute_policy_sha256(doc)
p.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(doc['sha256'])"
```

Write the printed value into `coa_scraper/config/spell_layout.lock.json` in the same commit.

- [ ] **Step 4: Point Node's `verifyFullRowAgainstPolicy` at `artifact_contract` (replacing the
  `policyDoc.required_scalar_fields || []` read at `mechanics-projection.mjs:326`), asserting the raw
  domain, the mechanics key set, and the nullability split.**

- [ ] **Step 5: Run both suites; commit**

```bash
git add coa_client_extract/data/spell_layout_v2.json coa_client_extract/spell_layout.py \
        coa_scraper/config/spell_layout.lock.json coa_scraper/scripts/lib/mechanics-projection.mjs \
        tests/test_e0r2_observation_domain.py
git commit -m "fix(e0r2): T2.3 — the full observation domain is policy-declared and load-validated"
```

### Task 2.4: Publication requires both validations and a clean budget

**Files:**
- Modify: `coa_client_extract/publish.py:171-204` (`finalize_and_publish`),
  `coa_client_extract/cli.py:329-346`
- Test: `tests/test_e0r2_publish_requires_validation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_publish_requires_validation.py
"""E0R.2 T2.4: a generation that failed a trust boundary or its budget must never become the pointer's
target. Consumer-side strictness is a second line of defence, not the gate."""
import pytest

from coa_client_extract.publish import POINTER_NAME, PublishError
from tests._e0r2_fixtures import staged_writer


@pytest.mark.parametrize("validation", [
    {"python": True, "node": False},
    {"python": True, "node": "yes"},       # truthy but not True
    {"python": True},                      # absent
])
def test_publishing_without_both_validations_is_refused(tmp_path, validation):
    gw, candidate = staged_writer(tmp_path)
    with pytest.raises(PublishError, match="validation"):
        gw.finalize_and_publish(candidate_manifest=candidate, validation=validation,
                                budget={"within_budget": True, "breach": []})
    assert not (tmp_path / POINTER_NAME).exists()


@pytest.mark.parametrize("budget", [
    {"within_budget": False, "breach": ["whole_generation bytes ..."]},
    {"within_budget": "ok", "breach": []},               # truthy but not True
    {"within_budget": True, "breach": ["a breach nobody acted on"]},
])
def test_publishing_with_an_unclean_budget_is_refused(tmp_path, budget):
    gw, candidate = staged_writer(tmp_path)
    with pytest.raises(PublishError, match="budget"):
        gw.finalize_and_publish(candidate_manifest=candidate,
                                validation={"python": True, "node": True}, budget=budget)
    assert not (tmp_path / POINTER_NAME).exists()


def test_the_budget_is_recomputed_from_staged_child_metadata(tmp_path):
    """A caller-supplied within_budget must not outrank the staged bytes."""
    gw, candidate = staged_writer(tmp_path, oversized=True)
    with pytest.raises(PublishError, match="budget"):
        gw.finalize_and_publish(candidate_manifest=candidate,
                                validation={"python": True, "node": True},
                                budget={"within_budget": True, "breach": []})


def test_a_fully_validated_within_budget_generation_publishes(tmp_path):
    gw, candidate = staged_writer(tmp_path)
    final = gw.finalize_and_publish(candidate_manifest=candidate,
                                    validation={"python": True, "node": True},
                                    budget={"within_budget": True, "breach": []})
    assert final["publication_state"] == "published"
    assert (tmp_path / POINTER_NAME).is_file()
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement** — `is True` identity checks (not truthiness), `breach == []`, and a
  recomputation of the byte ceilings from `self._children` inside `finalize_and_publish` so the
  caller's verdict cannot outrank the staged metadata. Keep it inside the existing `try:` so the
  `finally: self._release_publish_lock()` still covers the refusal path. Also delete the
  `three_part_budget` escape hatch at `cli.py:341-344`: a policy with no reviewed budget block raises
  `PublishError`, and synthetic test policies get explicit synthetic reviewed budgets.

- [ ] **Step 4: Run the full suite; commit**

```bash
git add coa_client_extract/publish.py coa_client_extract/cli.py \
        tests/test_e0r2_publish_requires_validation.py
git commit -m "fix(e0r2): T2.4 — publication requires both validations and a recomputed clean budget"
```

### Task 2.5: `converted` is prohibited until a bundle validator exists

**Files:**
- Modify: `coa_client_extract/contracts.py:16`, `coa_client_extract/publish.py` (`_verify_icon_row`,
  `_cross_child`), `coa_scraper/scripts/lib/generation.mjs:10,128-144,198-200`
- Test: `tests/test_e0r2_converted_prohibited.py`

**Context:** both validators only check that a bundle child *exists* if any row is `converted` — no tar
path containment, no internal manifest, no content hashes. No code path produces `converted`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_converted_prohibited.py
"""E0R.2 T2.5: `converted` promised tar containment, bundle-manifest and content-hash verification that
were never implemented, and nothing produces the status. An unverifiable status with no producer is not
a feature — reject it and reintroduce it WITH its validator."""
import pytest

from coa_client_extract.contracts import ICON_ASSET_STATUSES
from coa_client_extract.publish import ResolveError, _verify_icon_row


def test_converted_is_not_an_admissible_status():
    assert ICON_ASSET_STATUSES == frozenset({"source_only", "missing", "placeholder"})


def test_a_converted_row_is_rejected():
    with pytest.raises(ResolveError, match="converted"):
        _verify_icon_row({"spell_id": 1, "asset_status": "converted",
                          "client_path": "Interface\\Icons\\x", "converted_ref": "bundle:1"})


def test_no_producer_emits_converted():
    """If a converter lands, this test is the reminder to bring its validator with it."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "coa_client_extract"
    offenders = [p.name for p in src.glob("*.py")
                 if '"converted"' in p.read_text(encoding="utf-8")
                 and p.name not in ("contracts.py", "publish.py")]
    assert offenders == []
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement**, leaving the reintroduction requirements as a comment at the deleted check:

```python
# E0R.2 T2.5: `converted` (and its icon bundle) is PROHIBITED in this schema. Reintroducing it requires,
# in the same change: tar path containment, per-entry bundle-manifest verification, and per-asset content
# hashes checked against the catalog — the checks the E0R design specified and E0R.1 reduced to an
# existence test. Until then no producer may emit it and no validator may accept it.
```

- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_client_extract/contracts.py coa_client_extract/publish.py \
        coa_scraper/scripts/lib/generation.mjs tests/test_e0r2_converted_prohibited.py
git commit -m "fix(e0r2): T2.5 — prohibit converted icon assets until the bundle validator exists"
```

---

# Workstream 3 — live join recon and an honest recon budget (blockers 3, 4)

**Blocker 3:** for `reviewed_ambiguous` joins `probe_joins` copies authored evidence *without reading
the side table or scanning the client* (`spell_mechanics.py:147-150`), and `_recon_status` accepts
`pair: null` unconditionally (`:194-196`).

**Blocker 4:** recon estimates `record_count * record_size` (raw DBC bytes) against the retired
`DEFAULT_BUDGET = {512, 4096, 600}`, reporting 186.07 MiB for a 523,026,495-byte generation.

### Task 3.1: A live FK candidate scan runs for every ambiguous join on every recon

**Files:**
- Modify: `coa_client_extract/spell_mechanics.py` (`probe_joins`, new `scan_index_candidates`)
- Test: `tests/test_e0r2_recon_live_joins.py`

**Interfaces:**
- Produces: `scan_index_candidates(view, side_view, *, side_id_cell=0) -> list[dict]` — one entry per
  surviving candidate cell: `{"cell": int, "nonzero": int, "valid_fraction": float, "distinct_ids": int}`.
  Metrics ride along because T3.2 compares them against a reviewed baseline.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_recon_live_joins.py
"""E0R.2 T3.1: an adjudicated-ambiguous join is still PROBED on every run. Copying the authored verdict
forward means recon cannot notice the day the client makes the join unique — the one thing the hold
exists to catch."""
from coa_client_extract.spell_mechanics import probe_joins, scan_index_candidates
from tests._e0r2_recon_fixtures import ambiguous_backend, unique_backend


def test_an_ambiguous_join_is_scanned_not_asserted():
    probes = probe_joins(*ambiguous_backend())
    cast = probes["casting_time_index"]
    assert cast["scanned"] is True
    assert cast["pair"] is None
    assert len(cast["candidates"]) >= 2
    assert [c["cell"] for c in cast["candidates"]] == sorted(c["cell"] for c in cast["candidates"])
    assert all({"cell", "nonzero", "valid_fraction", "distinct_ids"} <= set(c) for c in cast["candidates"])


def test_a_join_that_became_unique_is_recorded_as_unique():
    probes = probe_joins(*unique_backend())
    assert len(probes["casting_time_index"]["candidates"]) == 1


def test_a_missing_side_table_is_distinguishable_from_an_ambiguous_one():
    """Regression: the old path returned before read_effective_file, so the two were identical."""
    backend, root, attach, view, id_to_rec, policy, anchors = ambiguous_backend()
    backend.forget("DBFilesClient\\SpellCastTimes.dbc")
    probe = probe_joins(backend, root, attach, view, id_to_rec, policy, anchors)["casting_time_index"]
    assert probe["scanned"] is False
    assert probe["side_table_missing"] is True
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `scan_index_candidates` and rewire the `reviewed_ambiguous` branch** so it
  opens the side table first (recording `side_table_missing`/`scanned: False` when absent, rather than
  the old silent `continue`) and then scans.
- [ ] **Step 4: Run; commit**

```bash
git add coa_client_extract/spell_mechanics.py tests/test_e0r2_recon_live_joins.py \
        tests/_e0r2_recon_fixtures.py
git commit -m "fix(e0r2): T3.1 — ambiguous joins are re-scanned live on every recon"
```

### Task 3.2: The reviewed ambiguity is a hash-bound baseline, not a count

**Files:**
- Modify: `coa_client_extract/data/spell_layout_v2.json` (per-join `ambiguity_baseline`),
  `coa_client_extract/spell_mechanics.py:176-202` (`_recon_status`),
  `coa_scraper/config/spell_layout.lock.json`
- Test: `tests/test_e0r2_recon_live_joins.py` (extend)

**Correction carried from review round 2:** accepting "any candidate set of size ≥2" means a change
from candidate cells `{10,11}` to `{90,91}` still verifies. The reviewed policy must hash-bind the scan
**algorithm version and thresholds**, the **expected candidate-cell set**, and the **per-candidate
metrics**; recon requires exact agreement, and any addition, removal, or metric drift is
`review_required`.

```json
"ambiguity_baseline": {
  "scan_algorithm": "fk_validity_v1",
  "thresholds": {"min_support": 2, "min_distinct": 2, "valid_fraction": 0.99},
  "joins": {
    "casting_time_index": {
      "candidates": [{"cell": 10, "nonzero": 190123, "valid_fraction": 1.0, "distinct_ids": 41}, "..."],
      "digest": "<sha256 of the canonical candidate list>"
    }
  }
}
```

- [ ] **Step 1: Write the failing test**

```python
def test_a_join_whose_candidate_SET_changed_forces_review():
    """Same count, different cells — the ambiguity did not survive, it was replaced."""
    baseline = _baseline(cells=[10, 11])
    status = _recon_status(**_args(baseline=baseline, scanned={"casting_time_index": [90, 91]}))
    assert status == "review_required"


def test_a_join_whose_metrics_drifted_forces_review():
    status = _recon_status(**_args(baseline=_baseline(cells=[10, 11], distinct_ids=41),
                                   scanned_metrics={"distinct_ids": 12}))
    assert status == "review_required"


def test_a_join_that_collapsed_to_one_candidate_forces_review():
    status = _recon_status(**_args(baseline=_baseline(cells=[10, 11]),
                                   scanned={"casting_time_index": [10]}))
    assert status == "review_required"


def test_an_unscanned_ambiguous_join_forces_review():
    """The exact 02e0b7c behaviour: pair=None with no machine evidence read as verified."""
    status = _recon_status(**_args(join_pairs={"casting_time_index": {
        "pair": None, "adjudication": "reviewed_ambiguous"}}))
    assert status == "review_required"


def test_a_scan_run_under_different_thresholds_forces_review():
    status = _recon_status(**_args(baseline=_baseline(min_distinct=2), scan_thresholds={"min_distinct": 5}))
    assert status == "review_required"


def test_an_exactly_matching_baseline_verifies():
    status = _recon_status(**_args(baseline=_baseline(cells=[10, 11]),
                                   scanned={"casting_time_index": [10, 11]}))
    assert status == "verified"
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Author the baseline from a real recon run** (run T3.1's scan against the live client,
  record the observed candidates verbatim), add it to the policy, rehash with `compute_policy_sha256`
  per T2.3's recipe, update the Node lock, and implement the exact-agreement check in `_recon_status`.
- [ ] **Step 4: Run; commit**

```bash
git add coa_client_extract/spell_mechanics.py coa_client_extract/data/spell_layout_v2.json \
        coa_scraper/config/spell_layout.lock.json tests/test_e0r2_recon_live_joins.py
git commit -m "fix(e0r2): T3.2 — verified requires exact agreement with a hash-bound ambiguity baseline"
```

### Task 3.3: Recon stops claiming artifact size

**Files:**
- Modify: `coa_client_extract/spell_mechanics.py` (`three_part_budget` → `recon_budget`, `:358-365`,
  `DEFAULT_BUDGET`), `coa_client_extract/cli.py`
- Test: `tests/test_e0r2_recon_budget.py`

**Design:** recon measures a *recon*. `record_count * record_size` is raw DBC bytes — off by 2.8×
against the real 523 MB. Recon gates its own peak RSS and elapsed against the reviewed policy ceilings
and makes no size claim. A serialized-sample forecast is an explicit **non-goal**: a wrong forecast is
worse than none, and publication measures the real thing exactly.

- [ ] **Step 1: Write the failing test** — `recon_budget` reports no `artifact_size_mb`/
  `serialized_bytes`; it breaches on `python_peak_rss_mb`; `DEFAULT_BUDGET` and `three_part_budget` no
  longer exist; recon reads ceilings from `spell_policy.doc["budget"]`.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `recon_budget(*, peak_rss_mb, elapsed_s, ceilings)`, delete `est_bytes`,
  `DEFAULT_BUDGET` and `three_part_budget`, and thread the policy budget through.**
- [ ] **Step 4: Run the full suite; commit**

```bash
git add coa_client_extract/spell_mechanics.py coa_client_extract/cli.py tests/test_e0r2_recon_budget.py
git commit -m "fix(e0r2): T3.3 — recon gates what it measures; the retired hard-coded budget is deleted"
```

---

# Workstream 4 — one internally-executed, generation-bound acceptance (blocker 2)

**Blocker:** `write_acceptance_summary` trusts a caller-supplied `build_mechanics` dict for `executed`,
`exit_code`, `network_attempts` and `pointer_only`; accepts a recon document containing only
`{"status": "verified"}`; binds no recon or mechanics identity to the generation; and silently
substitutes `{}` for absent coverage. *(Precision: the shipped subcommand does always execute the build
first — `cli.py:833-839` — so the committed record came from the executing path. The fabricable surface
is the function API.)*

**Additional finding:** `readiness_coverage` and `source_coverage` have **no producer anywhere** — only
the two reader lines at `cli.py:555-556`. The `{}` is not a dropped measurement; it was never
implemented, while the E0R.1 tracker's T6.2 checkbox claims it is recorded.

### Task 4.1: `observation_coverage` and `field_readiness_coverage` producers

**Files:**
- Modify: `coa_client_extract/spell_record.py`, `coa_client_extract/cli.py`,
  `coa_scraper/scripts/build-mechanics-artifacts.mjs`
- Test: `tests/test_e0r2_coverage_producers.py`, `coa_scraper/tests/coverage.test.mjs`

**Correction carried from review round 2:** raw extraction states are **observation** coverage, not
final mechanics readiness. Two different denominators, two different layers:

| coverage | layer | denominator |
|---|---|---|
| `observation_coverage` | generation manifest | every raw cell of every full row |
| `icon_coverage` | generation manifest | every spell in the domain (already exists) |
| `field_readiness_coverage` | mechanics manifest | Builder-domain mechanics fields, status/reason counts |
| `source_coverage` | mechanics manifest | `per_field_winner_counts_by_source` (already exists) |

- [ ] **Step 1: Write the failing test** — the accumulator counts states and reasons per field with an
  exact `cells` denominator; `regenerate` hoists `observation_coverage`; the mechanics build emits
  `field_readiness_coverage` with status/reason counts and an exact `fields_considered` denominator.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `observation_accumulator()` (single pass, folded into the existing streaming
  write loop) and the Node-side readiness accumulator (folded into T5.2's incremental statistics).**
- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_client_extract/spell_record.py coa_client_extract/cli.py \
        coa_scraper/scripts/build-mechanics-artifacts.mjs \
        tests/test_e0r2_coverage_producers.py coa_scraper/tests/coverage.test.mjs
git commit -m "feat(e0r2): T4.1 — observation coverage (generation) and readiness coverage (mechanics)"
```

### Task 4.2: One acceptance command that executes what it attests to

**Files:**
- Modify: `coa_client_extract/cli.py:492-567`, `:833-846`
- Test: `tests/test_e0r2_acceptance_executes.py`

**Interfaces:**
- Produces: `run_acceptance(dist, *, recon_report_path, scraper_dir, builder_entries, mechanics_out,
  benchmark_env_id="local", out=None, node="node") -> dict`. `write_acceptance_summary` is **deleted**.
  Record `schema_version` becomes `coa-e0r-acceptance-summary-v3`.

- [ ] **Step 1: Write the failing test** — `cli` has no `write_acceptance_summary`; `run_acceptance`
  has no `build_mechanics` parameter; a monkeypatched executor returning `exit_code: 1` makes
  `run_acceptance` raise and proves the executor was called.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Fold the executor inside** — resolve → validate recon → **execute** → require executed →
  bind (T4.3) → write.
- [ ] **Step 4: Run; commit**

```bash
git add coa_client_extract/cli.py tests/test_e0r2_acceptance_executes.py
git commit -m "fix(e0r2): T4.2 — acceptance executes the build it attests to; the v2 writer is deleted"
```

### Task 4.3: The record binds recon and mechanics to one generation

**Files:**
- Modify: `coa_client_extract/cli.py` (`run_acceptance`),
  `coa_scraper/scripts/build-mechanics-artifacts.mjs` (record input identities)
- Test: `tests/test_e0r2_acceptance_binding.py`

**Correction carried from review round 2 — the field paths in the previous draft did not exist.** Use
the real schemas (verified by probe):

| what | recon | manifest |
|---|---|---|
| policy hash | `source_pins.policy_sha256` | `binding.policy_sha256` |
| client build | `source_pins.client_build` | `binding.topology.client_build` |
| per-table capture hash | `source_pins.dbc.<T>.sha256` | `binding.topology.tables.<T>.sha256` |
| topology | `topology.tables.<T>` | `binding.topology.tables.<T>` |

Compare via a **canonical recon-binding digest** computed identically from both sides, so the check is
one equality rather than a field-by-field walk that silently skips a key it does not know about.

**Mechanics binding, strengthened:**
1. The mechanics manifest records `input_generation_id`, `pointer_manifest_sha256`, `policy_sha256`,
   `projection_child_sha256`, and `builder_entries_sha256`.
2. Acceptance **hashes and counts the emitted mechanics JSONL itself** rather than trusting the
   manifest's claimed output hash.
3. After the build, re-resolve the pointer and compare **both** `generation_id` **and**
   `manifest_sha256`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_acceptance_binding.py
"""E0R.2 T4.3: the record must prove the measurements and the generation are the same run. At 02e0b7c a
recon document containing only {"status": "verified"} was accepted, and a concurrent publish between
resolve and build would have combined two generations' measurements into one attestation."""
import pytest

from coa_client_extract.cli import AcceptanceError, run_acceptance
from tests._e0r2_fixtures import acceptance_env


def test_a_bare_status_only_recon_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="source_pins"):
        run_acceptance(**acceptance_env(tmp_path, recon={"status": "verified"}))


def test_a_recon_bound_to_a_different_policy_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="recon binding digest"):
        run_acceptance(**acceptance_env(tmp_path, recon_policy_sha256="0" * 64))


def test_a_recon_bound_to_a_different_client_capture_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="recon binding digest"):
        run_acceptance(**acceptance_env(tmp_path, recon_table_sha256={"Spell": "f" * 64}))


def test_a_pointer_that_moved_during_the_build_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="pointer moved"):
        run_acceptance(**acceptance_env(tmp_path, republish_during_build=True))


def test_a_pointer_whose_manifest_hash_changed_is_refused(tmp_path):
    """Same generation_id, rewritten manifest — id equality alone would have missed it."""
    with pytest.raises(AcceptanceError, match="manifest_sha256"):
        run_acceptance(**acceptance_env(tmp_path, rewrite_manifest_during_build=True))


def test_a_mechanics_manifest_claiming_a_hash_the_jsonl_does_not_have_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="mechanics jsonl sha256"):
        run_acceptance(**acceptance_env(tmp_path, forge_mechanics_output_hash=True))


def test_a_mechanics_build_bound_to_another_generation_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="input_generation_id"):
        run_acceptance(**acceptance_env(tmp_path, mechanics_input_generation_id="deadbeef"))


@pytest.mark.parametrize("missing", ["observation_coverage", "icon_coverage"])
def test_absent_generation_coverage_fails_instead_of_becoming_an_empty_object(tmp_path, missing):
    with pytest.raises(AcceptanceError, match=missing):
        run_acceptance(**acceptance_env(tmp_path, drop_manifest_keys=[missing]))


@pytest.mark.parametrize("missing", ["field_readiness_coverage", "per_field_winner_counts_by_source"])
def test_absent_mechanics_coverage_fails(tmp_path, missing):
    with pytest.raises(AcceptanceError, match=missing):
        run_acceptance(**acceptance_env(tmp_path, drop_mechanics_keys=[missing]))


def test_the_record_binds_every_identity(tmp_path):
    record = run_acceptance(**acceptance_env(tmp_path))
    assert record["schema_version"] == "coa-e0r-acceptance-summary-v3"
    assert len(record["generation_contract"]["sha256"]) == 64
    assert len(record["mechanics"]["jsonl_sha256"]) == 64
    assert record["mechanics"]["record_count"] > 0
    assert record["coverage"]["observation"]["cells"] > 0
    assert record["coverage"]["readiness"]["fields_considered"] > 0
    assert record["coverage"]["source"]
```

- [ ] **Step 2: Run and confirm every probe fails.**
- [ ] **Step 3: Implement** `recon_binding_digest(source_pins, topology)` (canonical, computed
  identically from the recon report and from `manifest.binding`), the mechanics input-identity block in
  the Node build, independent hashing of the emitted JSONL, the two-field pointer recheck, and
  fail-closed coverage. Record the generation contract schema and hash in the summary.
- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_client_extract/cli.py coa_scraper/scripts/build-mechanics-artifacts.mjs \
        tests/test_e0r2_acceptance_binding.py
git commit -m "fix(e0r2): T4.3 — acceptance binds recon, contract, coverage and mechanics to one generation"
```

---

# Workstream 5 — the canonical build streams end to end (blocker 5)

**Blocker:** the canonical mechanics path does `readFileSync` → `.toString("utf8")` → `.split("\n")` →
accumulate a `projection` array and a `clientById` Map over all of it, then retains the full output
array (`mechanics-projection.mjs:339-385`, `build-mechanics-artifacts.mjs:37-49,102-133,386-423`). The
E0R.1 design named "projection consumption → mechanics serialization" as in scope; the T4.2 RSS test
covers candidate validation instead. Node peaked at 866 MB on the real run.

**Key observation:** `buildCanonicalMechanics` emits one row per **Builder** spell (~3,600), not per
projection row (10,410). The projection is only a lookup, so the streaming pass needs to retain only
rows whose `spell_id` is in `builderSpellIds`.

### Task 5.1: Streaming projection consumption

**Files:**
- Modify: `coa_scraper/scripts/lib/mechanics-projection.mjs:339-385`
- Test: `coa_scraper/tests/mechanics-streaming.test.mjs`

**Interfaces:**
- Produces: `streamAndValidateProjectionV3({...}) -> { absent: false, clientById: Map, coverage,
  projection_sha256, manifest_sha256, client_build }`. The `projection` array is **gone**.

- [ ] **Step 1: Write the failing test** — the function source contains no `readFileSync(projectionPath`
  and no whole-file `.split`; only builder-domain rows are retained (`clientById.size === 3` over a
  5,000-row projection); **every** row is still validated (a corruption at line 73 throws even though
  only spell 1 is retained); the incremental hash equals the whole-file hash.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement** over the existing `readJsonlLines` generator, hashing incrementally, keeping
  every per-row check and the `seen` id set (counter-scale, ~10k ints).
- [ ] **Step 4: Run; commit**

```bash
git add coa_scraper/scripts/lib/mechanics-projection.mjs coa_scraper/tests/mechanics-streaming.test.mjs
git commit -m "perf(e0r2): T5.1 — the canonical build streams the projection instead of reading it whole"
```

### Task 5.2: Generator mechanics rows and incremental statistics

**Files:**
- Modify: `coa_scraper/scripts/build-mechanics-artifacts.mjs`
- Test: `coa_scraper/tests/mechanics-streaming.test.mjs` (extend)

- [ ] **Step 1: Record a golden output hash from the CURRENT implementation first**, so the refactor is
  provably output-preserving; then write the tests: `buildCanonicalMechanics` returns an iterator, not
  an array; no `rows.length` or `winnerCounts(rows)` remains; the artifact sha256 equals the golden.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement** — `function*` yielding ascending rows; `writeArtifact` folds
  `statsAccumulator()` (bySource, byTier, aggregates, and T4.1's `field_readiness_coverage`) into its
  existing write loop with a `recordCount` counter.
- [ ] **Step 4: Run; commit**

```bash
git add coa_scraper/scripts/build-mechanics-artifacts.mjs coa_scraper/tests/mechanics-streaming.test.mjs
git commit -m "perf(e0r2): T5.2 — mechanics rows are generated and counted incrementally"
```

### Task 5.3: A bounded-retention RSS gate through the real canonical build

**Files:**
- Create: `coa_scraper/tests/_canonical_build_probe.mjs`
- Modify: `coa_scraper/tests/generation-streaming.test.mjs`

**Correction carried from review round 2:** the growth is not literally sub-linear — the retained id set
grows with projection size. The property under test is **bounded row retention**: RSS must not grow in
proportion to the *projection row count*, measured as an absolute delta against a pinned threshold.

- [ ] **Step 1: Write the failing test** — run the **actual** `buildMechanicsArtifact` entry point in an
  isolated subprocess at 10k and 100k projection rows with a fixed ~3,600-spell builder domain; assert
  `peak_rss_mb` delta `< 150` and that the 100k peak is under a pinned absolute ceiling. Mirror
  `tests/_streaming_probe.py`'s try/finally temp-dir cleanup — that leak produced a false "memory
  regression" during E0R.1 when it filled the tmpfs.
- [ ] **Step 2: Verify the probe is real** by stashing T5.1 locally and watching it fail.
- [ ] **Step 3: Commit**

```bash
git add coa_scraper/tests/_canonical_build_probe.mjs coa_scraper/tests/generation-streaming.test.mjs
git commit -m "test(e0r2): T5.3 — bounded-retention RSS gate through the real canonical build"
```

---

# Workstream 6 — real E1 headroom (blocker 6)

**Blocker:** the real generation is 523,026,495 of 536,870,912 bytes — **97.42%**, leaving 13.2 MiB
against a design exit condition of "substantial E1 headroom."

**Measured attribution** (20,000-row sample, extrapolated to 208,447; per-field constancy verified over
50,000 rows; cell-shape distribution verified over all 208,447):

| component | share | extrapolated | nature |
|---|---|---|---|
| `policy_ref` | 23.6% | 88.6 MB | **constant per field** (1 distinct value per field) |
| `decoded_reason` | 14.8% | 55.4 MB | closed vocabulary (T0.1) |
| `state` | 9.7% | 36.3 MB | closed vocabulary (T0.1) |
| `resolved` | 6.0% | 22.4 MB | descriptions; only 35% dedupable |
| `join_name` | 5.9% | 22.3 MB | **constant per field** |
| icons child | — | 66.1 MB | 14,022 unique paths across 179,774 resolved rows |

The review's first round proposed a description/string dictionary as the strongest opportunity. The
measurement says otherwise: descriptions are mostly unique and dedup to ~8 MB. The dominant redundancy
is per-cell **constant metadata** (111 MB) and **low-cardinality enums** (92 MB). Hoisting, interning,
and normalizing icons projects **~298 MB (55% of ceiling)** without touching descriptions.

**Sequencing so every commit stays green:** T6.1 *expands* (add descriptors, both encodings supported),
T6.2 and T6.3 *migrate and contract atomically* (producer + both validators + contract + golden corpus
in one commit each).

### Task 6.1: Kind-aware field descriptors (expand)

**Files:**
- Create: descriptor producer in `coa_client_extract/spell_record.py`
- Modify: `coa_client_extract/spell_record.py`, `coa_client_extract/publish.py`,
  `coa_scraper/scripts/lib/mechanics-projection.mjs`, `coa_scraper/scripts/lib/generation.mjs`
- Test: `tests/test_e0r2_field_descriptors.py`, `coa_scraper/tests/descriptors.test.mjs`

**Correction carried from review round 2:** a single `policy_ref` per field **cannot** reconstruct a
resolved join. `_compact_join` emits `components.{index,side_id,side_value}`, each with its own
`policy_ref` (via `policy_ref_component`). Descriptors must be kind-aware:

```json
{
  "schema_version": "coa-client-spell-fields-v1",
  "fields": {
    "school_mask": {"kind": "scalar", "policy_ref": "/tables/Spell/fields/school_mask"},
    "cast_time_ms": {
      "kind": "join",
      "join_name": "cast_time_ms",
      "index_policy_ref": "/tables/Spell/fields/casting_time_index",
      "components": {
        "index":      {"policy_ref": "/tables/Spell/fields/casting_time_index"},
        "side_id":    {"policy_ref": "/tables/SpellCastTimes/fields/id"},
        "side_value": {"policy_ref": "/tables/SpellCastTimes/fields/base_ms"}
      }
    }
  }
}
```

`index_policy_ref` serves the *absent-join* form (null index cell), `components` the *resolved* form.
**Both validators must independently derive the expected descriptor from the policy and reject a staged
descriptor that differs** — otherwise a tampered descriptor could redefine meanings while keeping
compact→rich expansion internally self-consistent.

> Today every cell in all 208,447 rows is `scalar` or `join-absent`, so the resolved-join path is
> unexercised by real data — but it is reachable the moment a join is adopted, which is exactly what E1
> does. The golden corpus must therefore include a resolved-join row.

- [ ] **Step 1: Write the failing test** — descriptors round-trip all three cell shapes (scalar,
  absent join, resolved join with three component refs); the derived descriptor equals the policy-derived
  expectation in **both** languages; a staged descriptor that differs from the policy-derived one is
  rejected; the golden corpus gains a resolved-join row.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `build_field_descriptors(policy)` + `derive_expected_descriptors(policy)` in
  both languages. `_expand_compact` and `expandCompact` gain a descriptors argument.** Both encodings
  (with and without inline `policy_ref`) are accepted at this step — that is what keeps the tree green.
- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_client_extract/spell_record.py coa_client_extract/publish.py \
        coa_scraper/scripts/lib/mechanics-projection.mjs coa_scraper/scripts/lib/generation.mjs \
        tests/golden/e0r1_corpus tests/test_e0r2_field_descriptors.py \
        coa_scraper/tests/descriptors.test.mjs
git commit -m "feat(e0r2): T6.1 — kind-aware field descriptors derived and cross-checked from the policy"
```

### Task 6.2: v4 spell rows — hoist and intern (migrate + contract, atomic)

**Files:** producer, both validators, `generation_contract.json`, golden corpus — **one commit**.

**Design:** compact cells drop `policy_ref`/`join_name` (restored from descriptors) and carry `s`/`d`
integer codes from T0.1's **schema-owned** `OBSERVATION_STATE_CODES`/`DECODED_REASON_CODES` — never
from the staged descriptor. An out-of-range code fails closed. Full child → `coa-client-spell-v4`;
contract updated in the same commit; the projection stays `coa-client-spell-projection-v3` because
`expand_compact` absorbs the change, keeping
`expand_compact(full.raw) == projection.field_observations` literally true.

- [ ] **Step 1: Write the failing test** — round-trip equality per vocabulary member and per cell shape;
  an out-of-range code raises; codes come from `contracts.py` and **not** from the staged descriptor
  (mutate the staged copy's vocabulary and assert the expansion is unaffected or rejected); the
  cross-child equality still holds in both languages; measured bytes for the golden corpus drop.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement in `_compact`/`_compact_join`/`_expand_compact` and `expandCompact`; bump the
  contract's `coa_client_spell.jsonl` entry to v4; migrate the golden corpus; drop the dual-encoding
  support added in T6.1.**
- [ ] **Step 4: Run both suites; commit**

```bash
git commit -m "perf(e0r2): T6.2 — v4 spell rows: hoist per-field constants, intern vocabularies (-188 MB)"
```

### Task 6.3: Icon v2 — normalized assets (migrate + contract, atomic)

**Files:** `coa_client_extract/spell_icons.py`, `cli.py`, `publish.py`, `generation.mjs`, the `coa_meta`
icon consumer, `generation_contract.json`, golden corpus — **one commit**.

**Correction carried from review round 2 — the previous model was internally ambiguous.** It said
`asset_ref` is null only for `placeholder` while requiring every asset row to carry
`source_asset_sha256` and `source_archive`; a `missing` asset (proven path, absent member) has neither.
Explicit model:

- **Asset row** = one normalized client path.
  `{asset_id, client_path, availability: "source_only" | "missing", source_asset_sha256, source_archive, schema_version}`
  Hash and archive are non-null **iff** `availability == "source_only"`, null **iff** `"missing"`.
- **Spell row** = `{spell_id, spell_icon_id, asset_ref, readiness, schema_version}`.
  `asset_ref` is null **iff** the join is unresolved (the old `placeholder`); `readiness` is
  `"available"` iff `asset_ref` resolves to a `source_only` asset, `"unavailable"` otherwise — and the
  cross-child check enforces that derivation rather than trusting the stored value.
- **`asset_id` is deterministic**: `sha256(canonical_path)[:16]` where `canonical_path` is the
  client path lowercased with backslashes normalized to forward slashes. Encounter-order numbering
  would make byte-identical inputs produce different generations.

- [ ] **Step 1: Write the failing test** — a dangling `asset_ref` is rejected; an orphan asset row is
  rejected; a null `asset_ref` with `readiness: "available"` is rejected; a `missing` asset carrying a
  hash is rejected; a `source_only` asset without a hash is rejected; `asset_id` is stable across two
  runs with shuffled input order; `icon_coverage` reports the same `resolved_paths`/`unique_paths`
  totals as the v1 catalog for identical input.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement**, accumulating `canonical_path -> asset_id` during the single existing
  catalog pass (14,022 entries — counter-scale), updating both validators, the contract, the golden
  corpus, and the `coa_meta` consumer to resolve through the asset table.
- [ ] **Step 4: Run both suites; commit**

```bash
git commit -m "perf(e0r2): T6.3 — icon v2: deterministic normalized assets plus refs (-37 MB)"
```

---

# Workstream 7 — CI, hygiene, documentation

### Task 7.1: CI runs `npm test`; path hygiene over tracked text

**Files:**
- Modify: `.github/workflows/ci.yml:46-47`, the artifact producers
- Create: `tests/test_e0r2_path_hygiene.py`

**Context:** CI runs `npm --prefix coa_scraper run unit-test`, but `npm test` is
`unit-test && validate` — so `validate-normalized.mjs` has never been a merge gate. Eight tracked files
contain a machine-local home path, **including this plan's earlier draft**.

**Correction carried from review round 2:** do **not** hash the absolute client-root path — that makes
otherwise identical runs machine-dependent. Omit it, or record a symbolic label; archive names and
content hashes carry the actual identity.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_path_hygiene.py
"""E0R.2 T7.1: a tracked artifact is a published artifact. Machine-local absolute paths leak the
author's filesystem layout and make records non-reproducible across machines."""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME_PATH = re.compile(r"/home/[a-z][a-z0-9_-]*/")
TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".py", ".mjs", ".js", ".yml", ".yaml", ".toml", ".txt"}


def _tracked_text():
    out = subprocess.check_output(["git", "ls-files"], cwd=REPO, text=True)
    return [REPO / line for line in out.splitlines()
            if line and Path(line).suffix in TEXT_SUFFIXES]


def test_no_tracked_text_artifact_carries_a_machine_local_path():
    offenders = []
    for path in _tracked_text():
        if path.name == "test_e0r2_path_hygiene.py":
            continue                                   # this file names the pattern it forbids
        text = path.read_text(encoding="utf-8", errors="replace")
        if HOME_PATH.search(text):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], f"machine-local paths in tracked text: {offenders}"


def test_ci_runs_the_full_node_suite():
    ci = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "npm --prefix coa_scraper test" in ci
    assert "run unit-test" not in ci          # unit-test alone skips the validator
```

- [ ] **Step 2: Run and confirm both fail.**
- [ ] **Step 3: Fix CI; make producers emit repo-relative paths for in-repo files and a **symbolic
  label** (not a hash) for the out-of-tree client root; rewrite every doc to use `$COA_CLIENT_ROOT`.**
  Regenerate the tracked reports in WS8 rather than hand-editing them.
- [ ] **Step 4: Run; commit**

```bash
git add .github/workflows/ci.yml coa_client_extract/artifacts.py coa_client_extract/cli.py \
        docs/ tests/test_e0r2_path_hygiene.py
git commit -m "fix(e0r2): T7.1 — CI runs npm test; tracked text carries no machine-local paths"
```

### Task 7.2: Documentation and ROADMAP corrections

**Files:** `docs/ROADMAP.md`, `docs/data/mechanics-schema.md`,
`docs/superpowers/plans/2026-07-20-m1-14-e0r1-enforce-contract.md`

- [ ] **Step 1: `docs/ROADMAP.md`** — M1.8/M1.10B/M1.11D entries are history and stay, each gaining a
  "superseded by M1.14E0R.1 (AscensionDB runtime deleted)" note. The forward-looking claims (line 170
  `db.ascension.gg` hotlinks, line 205 disclaimer, line 212 "extend AscensionDB scraping") are rewritten
  to the client-native reality.
- [ ] **Step 2: `docs/data/mechanics-schema.md`** — lines 7, 22, 38, 175 describe the retired
  DB-sourced schema; correct them to the three-tier model already documented at line 270.
- [ ] **Step 3: E0R.1 tracker line 188** — the T6.2 checkbox claims the record "records
  icon/readiness/source coverage counts"; readiness and source had no producer. Correct it and point at
  E0R.2 T4.1.
- [ ] **Step 4: Add the two deferred guide-product items as explicit ROADMAP entries** (the out-of-scope
  section says they belong there, so they must actually land there):
  - *M1.16 — label heuristic build rankings as candidates/hypotheses.* `MetaReportRunner` ranks with
    `TheoryScorer` and the guide shows "top theorycraft" language; until client mechanics,
    interpretation, logs, and expert review converge, these are not recommendations.
  - *M1.16 — report renderable icon coverage separately from source coverage.* Acceptance reports
    179,749 **source** BLPs; the guide renders only converted assets, so renderable coverage is
    currently zero. Report source / renderable / CoA-domain / Builder-domain separately, resolve the
    catalog through the published generation, and cache by `spell_id` or asset reference rather than
    label.
- [ ] **Step 5: Commit**

```bash
git add docs/ROADMAP.md docs/data/mechanics-schema.md \
        docs/superpowers/plans/2026-07-20-m1-14-e0r1-enforce-contract.md
git commit -m "docs(e0r2): T7.2 — correct stale AscensionDB claims; schedule the guide-honesty items"
```

---

# Workstream 8 — real-client re-run and PR

### Task 8.1: Re-run recon, regenerate, canonical build, acceptance

- [ ] **Step 1: Full local suite, both languages, then the exact CI command in a clean environment**

```bash
python -m pytest -q && npm --prefix coa_scraper test
python -m venv /tmp/e0r2-clean && /tmp/e0r2-clean/bin/pip install -q -e . pytest
/tmp/e0r2-clean/bin/pytest -q      # from the repo root; BARE pytest, exactly as CI runs it
```

- [ ] **Step 2: Recon**

```bash
export COA_CLIENT_ROOT="<the Ascension Data directory>"
python -m coa_client_extract mechanics-recon --client-root "$COA_CLIENT_ROOT" --out reports/client_extract
```

Expect exit 0. **Exit 4 (`review_required`) is now a legitimate outcome** — T3.2 compares against a
hash-bound baseline, so a changed candidate set or drifted metrics stops the run. Adjudicate; do not
re-bind mechanically to make the hold pass. If only the *capture identity* drifted (a client patch),
follow the E0R.1 precedent (`d549ac9`): advance only the per-table sha256/header + policy sha256 + Node
lock, with a script asserting the semantic policy view is byte-identical.

- [ ] **Step 3: Regenerate** (~11 min at the previous scale; background it and monitor by captured pid —
  `pgrep -f` matched its own shell command line during E0R.1 and reported a false "still running")

```bash
python -m coa_client_extract regenerate --client-root "$COA_CLIENT_ROOT" \
  --out reports/client_extract --builder-entries coa_scraper/dist/coa_entries.jsonl
```

- [ ] **Step 4: Acceptance** (executes the canonical build under the network trap internally)

```bash
python -m coa_client_extract acceptance-summary --dist reports/client_extract \
  --recon-report reports/client_extract/coa_spell_mechanics_recon.json \
  --out reports/client_extract/coa_e0r_acceptance_summary.json
```

- [ ] **Step 5: Read the measured whole-generation bytes out of the record** and confirm ≤75% of
  `max_whole_generation_bytes`. If over, reduce the remaining redundancy — **do not raise the ceiling.**

### Task 8.2: The headroom gate lands with the record

**Files:** `tests/test_e0r2_headroom.py`, `reports/client_extract/*` — **one commit**

Committing the assertion earlier would leave a knowingly-red test in history, which the global
constraints forbid. It lands together with the artifact that satisfies it.

```python
# tests/test_e0r2_headroom.py
"""E0R.2 T8.2: E0R's exit condition is 'substantial E1 headroom'. 97.42% of ceiling is not headroom,
and raising the ceiling is not reducing the artifact."""
import json
from pathlib import Path

RECORD = Path(__file__).resolve().parents[1] / "reports/client_extract/coa_e0r_acceptance_summary.json"
TARGET = 0.75


def test_the_published_generation_leaves_e1_headroom():
    budget = json.loads(RECORD.read_text(encoding="utf-8"))["budget"]
    used = budget["whole_generation_bytes"] / budget["ceilings"]["max_whole_generation_bytes"]
    assert used <= TARGET, f"generation uses {used:.1%} of ceiling; E1 needs room below {TARGET:.0%}"
```

- [ ] **Step 1: Run the full suite one final time (must be entirely green).**
- [ ] **Step 2: Commit**

```bash
git add tests/test_e0r2_headroom.py reports/client_extract/coa_e0r_acceptance_summary.json \
        reports/client_extract/coa_spell_mechanics_recon.json
git commit -m "feat(e0r2): T8.2 — real-client acceptance record and the E1 headroom gate"
```

### Task 8.3: Push, update the PR, require green CI

- [ ] **Step 1: Push** `m1-14-e0r` (including the tracker-docs commit `02e0b7c` held back in E0R.1).
- [ ] **Step 2: Update PR #1's body** with an E0R.2 section: the seven blockers, the reproductions that
  are now red, and the measured size reduction.
- [ ] **Step 3: Wait for CI green on both the push and the pull_request runs.**
- [ ] **Step 4: Report to the user. Do NOT merge; do NOT start E1.**

---

## Out of scope, recorded deliberately

- **Description string dictionary.** Measured at ~8 MB of savings (22.4 MB inline, only 35% dedupable).
  Not worth a string-table child while the other three measures reach 55% of ceiling. Revisit if E1's
  artifacts push past 70%.
- **Recon generation-size forecast.** Recon has no basis for one (T3.3); publication measures exactly.
- **Actually adjudicating the three numeric joins.** T3.1/T3.2 make the standing ambiguity honest and
  drift-detecting; they do not resolve it. Resolution needs admissible independent evidence that does
  not exist today under the anchor-evidence precedence — a controlled local client where a known
  spell's cast time can be read back, or a Builder field that explicitly encodes it. This is the E1
  blocker to schedule next.
- **The two guide-product findings.** Not blockers while the guide is unpublished/experimental, but
  T7.2 lands them as explicit ROADMAP items rather than leaving them in a plan appendix.
