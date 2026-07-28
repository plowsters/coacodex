# M1.14 E0R.2 — close the E0R.1 review blockers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) or
> superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox
> (`- [ ]`) syntax for tracking. **This file is the canonical task tracker** (the MCP tracker is offline).

**Goal:** Make every guarantee E0R.1 *documented* impossible to violate, so PR #1 can merge on evidence
rather than on description.

**Architecture:** Seven review blockers, closed in dependency order. A single versioned JSON
**generation contract** replaces the name-only child registry and is read by both trust boundaries. The
acceptance record becomes one internally-executed, generation-bound command. Recon re-probes the
ambiguous joins live on every run and stops making artifact-size claims it cannot support. The canonical
Node build streams end to end. The generation sheds ~225 MB of provably-redundant bytes so E1 has real
headroom. `converted` icon assets are prohibited until a bundle validator exists.

**Tech Stack:** Python 3.11 (`coa_client_extract/`, `coa_meta/`), Node 20 ESM
(`coa_scraper/scripts/`), pytest, `node --test`.

## Global Constraints

- **Branch:** `m1-14-e0r`. No history rewrite. **Do NOT merge PR #1. Do NOT start E1.**
- **Commits:** explicit file paths only — **NEVER `git add -A`**. One contract-focused commit per task.
- **Method:** probe-first TDD. Every adversarial case is a failing test *before* its fix.
- **Push:** once, at the end (WS8), after the full local suite is green. Never claim a remote green
  before the push.
- **Anchor-evidence precedence (verbatim, unchanged from E0R):** 1. Hash-bound client-static evidence
  (client strings, known BLP paths). 2. Verified Builder payload fields
  (`coa_scraper/dist/coa_entries.jsonl`) that explicitly encode the value. 3. Stock 3.3.5 data ONLY as
  corroboration for demonstrably-unchanged stock spells. Do not use AscensionDB, remembered values,
  runtime behavior, or values inferred from the candidate DBC column being tested.
- **Client:** `COA_CLIENT_ROOT=/home/archbug/Games/ascension-wow/drive_c/Program Files/Ascension Launcher/resources/ascension-live/Data`
- **Suites:** `pytest -q` from the repo root (CI runs **bare** `pytest`); `npm --prefix coa_scraper test`.
- **Baseline at plan time:** branch head `02e0b7c`, 625 Python + 121 Node green, generation
  `a9663d1b410841dd8284cb7538c61185` at 523,026,495 bytes (97.42% of ceiling).

---

## Execution status

| Task | Status | Commit |
|---|---|---|
| T1.1 Generation contract document + loader | pending | |
| T1.2 Python candidate validator enforces the contract | pending | |
| T1.3 Node candidate validator reads the same contract | pending | |
| T1.4 Production policy gains `required_scalar_fields` | pending | |
| T1.5 Publication requires both validations + budget | pending | |
| T2.1 `converted` prohibited until a bundle validator exists | pending | |
| T3.1 Live FK candidate scan on every recon | pending | |
| T3.2 Recon state machine requires surviving ambiguity | pending | |
| T3.3 Recon stops claiming artifact size; policy-bound rss/elapsed | pending | |
| T4.1 Readiness + source coverage producers | pending | |
| T4.2 One internally-executed acceptance command | pending | |
| T4.3 Acceptance binds recon + mechanics to the generation | pending | |
| T5.1 Streaming projection consumption | pending | |
| T5.2 Generator mechanics rows + incremental statistics | pending | |
| T5.3 RSS test through the real canonical build | pending | |
| T6.1 Field-descriptor hoist (`policy_ref`, `join_name`) | pending | |
| T6.2 Enum interning (`state`, `decoded_reason`) | pending | |
| T6.3 Icon asset normalization | pending | |
| T6.4 Budget target ≤75% asserted on real measurement | pending | |
| T7.1 CI runs `npm test`; path hygiene | pending | |
| T7.2 Documentation corrections | pending | |
| T8.1 Real-client re-run: recon, regenerate, build, acceptance | pending | |
| T8.2 Push, PR update, CI green | pending | |

---

# Workstream 1 — one shared child-contract registry (blocker 1)

**Blocker:** both validators accept a candidate carrying every required child *name* with zero
spell/projection/icon rows, arbitrary child `schema_version` strings, and (in production) no
`required_scalar_fields`, so a full row may omit its entire expected field domain. Reproduced:

```
=== PYTHON validate_candidate_generation ===  ACCEPTED
=== NODE  validateCandidateByPath        ===  ACCEPTED
```

### Task 1.1: The generation contract document and its loader

**Files:**
- Create: `coa_client_extract/data/generation_contract.json`
- Modify: `coa_client_extract/contracts.py`
- Test: `tests/test_e0r2_generation_contract.py`

**Interfaces:**
- Produces: `load_generation_contract() -> dict`, `GENERATION_CONTRACT_SCHEMA = "coa-generation-contract-v1"`.
  Contract shape per child: `{kind, child_schema_version, row_schema_version, min_records,
  max_records, requires}`. `kind` ∈ `{"jsonl", "json"}`. `row_schema_version` is `null` for
  `kind: "json"` children.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_generation_contract.py
"""E0R.2 T1.1: the generation contract is ONE versioned document both trust boundaries read. A name
list cannot express cardinality, row schema, or domain — which is how a complete-but-empty generation
passed both validators at 02e0b7c."""
import json
from pathlib import Path

from coa_client_extract.contracts import GENERATION_CONTRACT_SCHEMA, load_generation_contract
from coa_client_extract.publish import REQUIRED_CHILDREN

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "coa_client_extract/data/generation_contract.json"


def test_contract_covers_exactly_the_required_children():
    contract = load_generation_contract()
    assert contract["schema_version"] == GENERATION_CONTRACT_SCHEMA
    assert set(contract["children"]) == set(REQUIRED_CHILDREN)


def test_every_child_declares_kind_schema_and_cardinality():
    for name, spec in load_generation_contract()["children"].items():
        assert spec["kind"] in ("jsonl", "json"), name
        assert spec["child_schema_version"], name
        assert isinstance(spec["min_records"], int) and spec["min_records"] >= 1, name
        if spec["kind"] == "jsonl":
            assert spec["row_schema_version"], name
        else:
            assert spec["row_schema_version"] is None, name


def test_the_spell_domain_children_require_a_nonempty_domain():
    """A zero-row spell/icon child is not a small generation, it is not a generation."""
    children = load_generation_contract()["children"]
    for name in ("coa_client_spell.jsonl", "coa_client_spell_icons.jsonl", "coa_client_spell_coa.jsonl"):
        assert children[name]["min_records"] >= 1, name


def test_the_contract_file_is_the_only_source_node_reads():
    """Node must load THIS file, not a hand-mirrored copy — the mirror is what drifts."""
    generation_mjs = (Path(__file__).resolve().parents[1]
                      / "coa_scraper/scripts/lib/generation.mjs").read_text(encoding="utf-8")
    assert "generation_contract.json" in generation_mjs
    assert "REQUIRED_CHILDREN = [" not in generation_mjs      # the retired hand-mirrored name list
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python -m pytest tests/test_e0r2_generation_contract.py -q`
Expected: FAIL — `ImportError: cannot import name 'GENERATION_CONTRACT_SCHEMA'`.

- [ ] **Step 3: Author the contract document**

Cardinalities come from the real generation `a9663d1b` (advancement 3,614; class_types 46;
tab_types 94; essence 5,600; content 52,744). `min_records` is a floor that a *degenerate* generation
fails, not a regression detector — set it to 1 for domain children and to a conservative fraction for
the reference tables, so a client patch that legitimately shrinks a table does not fail the gate.

```json
{
  "schema_version": "coa-generation-contract-v1",
  "note": "The E0R child contract read by BOTH trust boundaries (coa_client_extract.publish and coa_scraper/scripts/lib/generation.mjs). A name list cannot express cardinality or row schema; this can.",
  "children": {
    "coa_client_spell.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-spell-v4",
      "row_schema_version": "coa-client-spell-v4", "min_records": 1, "max_records": null,
      "requires": ["spell_id", "name", "mechanics", "raw", "coa_attribution"]
    },
    "coa_client_spell_coa.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-spell-projection-v3",
      "row_schema_version": "coa-client-spell-projection-v3", "min_records": 1, "max_records": null,
      "requires": ["spell_id", "name", "mechanics", "field_observations", "coa_attribution"]
    },
    "coa_client_spell_icons.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-spell-icons-v2",
      "row_schema_version": "coa-client-spell-icons-v2", "min_records": 1, "max_records": null,
      "requires": ["spell_id", "spell_icon_id", "asset_status", "readiness"]
    },
    "coa_client_icon_assets.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-icon-assets-v1",
      "row_schema_version": "coa-client-icon-assets-v1", "min_records": 1, "max_records": null,
      "requires": ["asset_id", "client_path"]
    },
    "coa_client_spell_fields.json": {
      "kind": "json", "child_schema_version": "coa-client-spell-fields-v1",
      "row_schema_version": null, "min_records": 1, "max_records": 1, "requires": []
    },
    "coa_client_spell_projection.manifest.json": {
      "kind": "json", "child_schema_version": "coa-client-spell-projection-manifest-v3",
      "row_schema_version": null, "min_records": 1, "max_records": 1, "requires": []
    },
    "coa_client_content.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-content-v1",
      "row_schema_version": "coa-client-content-v1", "min_records": 1000, "max_records": null,
      "requires": ["content_kind", "values", "provenance"]
    },
    "coa_client_archive_plan.json": {
      "kind": "json", "child_schema_version": "coa-client-archive-plan-v1",
      "row_schema_version": null, "min_records": 1, "max_records": 1, "requires": []
    },
    "coa_client_advancement.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-advancement-v1",
      "row_schema_version": "coa-client-advancement-v1", "min_records": 100, "max_records": null,
      "requires": ["node_id", "name", "class", "entry_type", "provenance"]
    },
    "coa_client_class_types.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-class-types-v1",
      "row_schema_version": "coa-client-class-types-v1", "min_records": 1, "max_records": null,
      "requires": []
    },
    "coa_client_tab_types.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-tab-types-v1",
      "row_schema_version": "coa-client-tab-types-v1", "min_records": 1, "max_records": null,
      "requires": []
    },
    "coa_client_essence.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-essence-v1",
      "row_schema_version": "coa-client-essence-v1", "min_records": 1, "max_records": null,
      "requires": []
    },
    "spell_layout_v2.json": {
      "kind": "json", "child_schema_version": "coa-spell-layout-v2",
      "row_schema_version": null, "min_records": 1, "max_records": 1, "requires": []
    }
  }
}
```

> **Note on the two new children and the two bumped schema versions:** `coa_client_spell_fields.json`,
> `coa_client_icon_assets.jsonl`, `coa-client-spell-v4` and `coa-client-spell-icons-v2` are introduced by
> Workstream 6. Authoring them here keeps the contract a single document; T6.x makes the producer emit
> them. Between T1.1 and T6.3 the Python/Node candidate validators will reject the *old* generation
> shape — that is expected and is why WS6 precedes the real re-run in WS8. The synthetic test corpus is
> migrated in T6.1–T6.3 alongside the producer.

- [ ] **Step 4: Add the loader to `contracts.py`**

```python
GENERATION_CONTRACT_SCHEMA = "coa-generation-contract-v1"
_CONTRACT_CACHE: dict | None = None


def load_generation_contract() -> dict:
    """The ONE child contract both trust boundaries read (E0R.2 T1.1). Cached: it is a frozen data file,
    and the candidate validator consults it per child."""
    global _CONTRACT_CACHE
    if _CONTRACT_CACHE is None:
        import json
        from pathlib import Path
        path = Path(__file__).resolve().parent / "data" / "generation_contract.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("schema_version") != GENERATION_CONTRACT_SCHEMA:
            raise ValueError(f"generation contract bad schema_version {doc.get('schema_version')!r}")
        _CONTRACT_CACHE = doc
    return _CONTRACT_CACHE
```

- [ ] **Step 5: Run the test — two assertions stay red until T1.2 and T1.3**

Run: `python -m pytest tests/test_e0r2_generation_contract.py -q`
Expected: 2 pass, 2 FAIL. `test_contract_covers_exactly_the_required_children` fails because
`publish.REQUIRED_CHILDREN` is still the hand-written 11-name tuple and the contract names 13 children
(the two WS6 additions) — T1.2 makes it contract-derived. `test_the_contract_file_is_the_only_source_node_reads`
fails until T1.3. Both are expected red; do not soften the contract to make them pass early.

- [ ] **Step 6: Commit**

```bash
git add coa_client_extract/data/generation_contract.json coa_client_extract/contracts.py \
        tests/test_e0r2_generation_contract.py
git commit -m "feat(e0r2): T1.1 — one versioned generation contract read by both boundaries"
```

### Task 1.2: The Python candidate validator enforces the contract

**Files:**
- Modify: `coa_client_extract/publish.py` (`REQUIRED_CHILDREN`, `_validate_children_by_path`,
  `validate_candidate_generation`)
- Test: `tests/test_e0r2_empty_generation_rejected.py`

**Interfaces:**
- Consumes: `load_generation_contract()` from T1.1.
- Produces: `REQUIRED_CHILDREN` derived from the contract (kept as a name tuple for existing importers).

- [ ] **Step 1: Write the failing probe — this is the exact reproduction from the review**

```python
# tests/test_e0r2_empty_generation_rejected.py
"""E0R.2 T1.2: a candidate carrying every required child NAME but no spell/projection/icon domain is
not a small generation — it is a hole in the trust boundary. At 02e0b7c both validators ACCEPTED it."""
import hashlib
import json

import pytest

from coa_client_extract.publish import (REQUIRED_CHILDREN, ResolveError, candidate_trust_sha256,
                                        validate_candidate_generation)
from tests._e0r2_fixtures import POLICY_TEXT, stage_candidate


def test_a_complete_but_empty_candidate_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, rows={})          # every child present, every JSONL child empty
    with pytest.raises(ResolveError, match="min_records|empty"):
        validate_candidate_generation(gen)


def test_an_arbitrary_child_schema_version_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, child_schema_overrides={
        "coa_client_spell.jsonl": "totally-made-up-schema-v99"})
    with pytest.raises(ResolveError, match="schema_version"):
        validate_candidate_generation(gen)


def test_a_row_missing_its_schema_version_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, drop_row_keys={"coa_client_spell.jsonl": ["schema_version"]})
    with pytest.raises(ResolveError, match="row schema_version"):
        validate_candidate_generation(gen)


def test_a_row_missing_a_required_key_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, drop_row_keys={"coa_client_spell.jsonl": ["coa_attribution"]})
    with pytest.raises(ResolveError, match="coa_attribution"):
        validate_candidate_generation(gen)


def test_a_wellformed_candidate_still_validates(tmp_path):
    """The gate must not be a wall: the golden-shaped generation passes unchanged."""
    validate_candidate_generation(stage_candidate(tmp_path))
```

`tests/_e0r2_fixtures.py` builds a minimal *valid* generation (three spells, one is_coa, one icon
asset) and lets each probe degrade exactly one property. Model it on
`tests/golden/e0r1_corpus/` — reuse that corpus's rows rather than inventing new ones, so the golden
corpus stays the single source of row shape.

- [ ] **Step 2: Run it and confirm every probe but the last fails**

Run: `python -m pytest tests/test_e0r2_empty_generation_rejected.py -q`
Expected: 4 FAIL (no exception raised), 1 PASS.

- [ ] **Step 3: Enforce the contract in `_validate_children_by_path` and `validate_candidate_generation`**

Replace the literal `REQUIRED_CHILDREN` tuple with a contract-derived one, add the per-child
cardinality/schema checks, and add a streaming per-row check:

```python
from .contracts import load_generation_contract

REQUIRED_CHILDREN = tuple(sorted(load_generation_contract()["children"]))


def _verify_child_against_contract(name: str, meta: dict, path: Path, spec: dict) -> None:
    """Cardinality, child schema, and (for JSONL) per-row schema + required keys. A generation whose
    children are all present but all empty carries no domain and is rejected here (E0R.2 T1.2)."""
    if meta.get("schema_version") != spec["child_schema_version"]:
        raise ResolveError(
            f"child {name!r} schema_version {meta.get('schema_version')!r} != contract "
            f"{spec['child_schema_version']!r}")
    records = meta.get("records")
    if records < spec["min_records"]:
        raise ResolveError(f"child {name!r} min_records: {records} < {spec['min_records']}")
    if spec["max_records"] is not None and records > spec["max_records"]:
        raise ResolveError(f"child {name!r} max_records: {records} > {spec['max_records']}")
    if spec["kind"] != "jsonl":
        return
    row_schema, required = spec["row_schema_version"], spec["requires"]
    for index, row in enumerate(_read_jsonl(path)):        # streaming; never a row list
        if row.get("schema_version") != row_schema:
            raise ResolveError(
                f"child {name!r} row {index} schema_version {row.get('schema_version')!r} != {row_schema!r}")
        for key in required:
            if key not in row:
                raise ResolveError(f"child {name!r} row {index} missing required key {key!r}")
```

Call it from `_validate_children_by_path` for every child the contract names, after the existing
hash/bytes/records scan. Leave unknown children alone — the contract governs *required* children, and
an extra child is already caught by `candidate_trust_sha256`.

- [ ] **Step 4: Run the probes and the full suite**

Run: `python -m pytest tests/test_e0r2_empty_generation_rejected.py -q && python -m pytest -q`
Expected: probes PASS. The full suite will show failures in existing tests whose synthetic generations
predate the contract — migrate those fixtures (they are the same class of omission the contract now
catches). Do not weaken the contract to accommodate a fixture.

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/publish.py tests/test_e0r2_empty_generation_rejected.py tests/_e0r2_fixtures.py
git commit -m "fix(e0r2): T1.2 — the Python candidate validator enforces cardinality and row schema"
```

### Task 1.3: The Node candidate validator reads the same contract

**Files:**
- Modify: `coa_scraper/scripts/lib/generation.mjs:19-25` (delete the mirrored `REQUIRED_CHILDREN`),
  `validateChildrenByPath`, `validateCandidateByPath`
- Test: `coa_scraper/tests/generation-contract.test.mjs`

**Interfaces:**
- Consumes: `coa_client_extract/data/generation_contract.json` — the same file Python reads, resolved
  via `new URL("../../../coa_client_extract/data/generation_contract.json", import.meta.url)`.
- Produces: `loadGenerationContract()`, `REQUIRED_CHILDREN` (derived, kept as a named export for
  existing importers).

- [ ] **Step 1: Write the failing test**

```javascript
// coa_scraper/tests/generation-contract.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { loadGenerationContract, validateCandidateByPath, GenerationResolveError } from "../scripts/lib/generation.mjs";
import { stageCandidate } from "./_e0r2-fixtures.mjs";

test("the Node boundary reads the same contract document Python reads", () => {
  const contract = loadGenerationContract();
  assert.equal(contract.schema_version, "coa-generation-contract-v1");
  assert.ok(contract.children["coa_client_spell.jsonl"].min_records >= 1);
});

test("a complete-but-empty candidate is rejected", (t) => {
  const dir = stageCandidate(t, { rows: {} });
  assert.throws(() => validateCandidateByPath(dir), GenerationResolveError, /min_records|empty/);
});

test("an arbitrary child schema_version is rejected", (t) => {
  const dir = stageCandidate(t, { childSchemaOverrides: { "coa_client_spell.jsonl": "made-up-v99" } });
  assert.throws(() => validateCandidateByPath(dir), GenerationResolveError, /schema_version/);
});

test("a row missing its schema_version is rejected", (t) => {
  const dir = stageCandidate(t, { dropRowKeys: { "coa_client_spell.jsonl": ["schema_version"] } });
  assert.throws(() => validateCandidateByPath(dir), GenerationResolveError, /row schema_version/);
});

test("a well-formed candidate still validates", (t) => {
  validateCandidateByPath(stageCandidate(t, {}));
});
```

- [ ] **Step 2: Run and confirm failure**

Run: `cd coa_scraper && node --test tests/generation-contract.test.mjs`
Expected: FAIL — `loadGenerationContract is not exported`.

- [ ] **Step 3: Implement, reusing the existing `readJsonlLines` generator so the row check streams**

```javascript
const CONTRACT_URL = new URL("../../../coa_client_extract/data/generation_contract.json", import.meta.url);
let _contract = null;

export function loadGenerationContract() {
  if (_contract === null) {
    _contract = JSON.parse(fs.readFileSync(CONTRACT_URL, "utf8"));
    if (_contract.schema_version !== "coa-generation-contract-v1") {
      throw new GenerationResolveError(`generation contract bad schema_version ${_contract.schema_version}`);
    }
  }
  return _contract;
}

export const REQUIRED_CHILDREN = Object.keys(loadGenerationContract().children).sort();

function verifyChildAgainstContract(name, meta, childPath, spec) {
  if (meta.schema_version !== spec.child_schema_version) {
    throw new GenerationResolveError(`child ${name} schema_version ${meta.schema_version} != contract ${spec.child_schema_version}`);
  }
  if (meta.records < spec.min_records) throw new GenerationResolveError(`child ${name} min_records: ${meta.records} < ${spec.min_records}`);
  if (spec.max_records !== null && meta.records > spec.max_records) {
    throw new GenerationResolveError(`child ${name} max_records: ${meta.records} > ${spec.max_records}`);
  }
  if (spec.kind !== "jsonl") return;
  let index = 0;
  for (const row of readJsonlLines(childPath)) {          // streaming; never a row array
    if (row.schema_version !== spec.row_schema_version) {
      throw new GenerationResolveError(`child ${name} row ${index} schema_version ${row.schema_version} != ${spec.row_schema_version}`);
    }
    for (const key of spec.requires) {
      if (!(key in row)) throw new GenerationResolveError(`child ${name} row ${index} missing required key ${key}`);
    }
    index += 1;
  }
}
```

- [ ] **Step 4: Run both suites**

Run: `cd coa_scraper && node --test tests/*.test.mjs`
Expected: PASS. Then re-run `python -m pytest tests/test_e0r2_generation_contract.py -q` — the
`test_the_contract_file_is_the_only_source_node_reads` assertion now passes.

- [ ] **Step 5: Commit**

```bash
git add coa_scraper/scripts/lib/generation.mjs coa_scraper/tests/generation-contract.test.mjs \
        coa_scraper/tests/_e0r2-fixtures.mjs
git commit -m "fix(e0r2): T1.3 — Node reads the shared contract; the mirrored name list is deleted"
```

### Task 1.4: The production policy declares `required_scalar_fields`

**Files:**
- Modify: `coa_client_extract/data/spell_layout_v2.json` (add `required_scalar_fields`, bump `sha256`),
  `coa_scraper/config/spell_layout.lock.json`
- Test: `tests/test_e0r2_required_scalar_fields.py`

**Context:** `mechanics-projection.mjs:326` reads `policyDoc.required_scalar_fields || []`. The key
exists only in `tests/golden/e0r1_corpus/policy.json:199`, so in production the required-field domain
check is vacuous — a full row may omit its entire expected field domain and pass.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_required_scalar_fields.py
"""E0R.2 T1.4: the PRODUCTION policy must name the scalars a full row is required to carry. The
golden fixture declared them; the shipped policy did not, so the check ran against an empty list."""
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_the_production_policy_declares_required_scalar_fields():
    policy = json.loads((REPO / "coa_client_extract/data/spell_layout_v2.json").read_text(encoding="utf-8"))
    assert set(policy["required_scalar_fields"]) >= {"id", "name", "power_type", "school_mask"}


def test_a_full_row_omitting_a_required_scalar_is_rejected_under_the_production_policy():
    """Drive the real Node verifier with the real policy — a unit assertion on the JSON would not
    prove the verifier consumes it."""
    script = """
    import { verifyFullRowAgainstPolicy, MechanicsBuildError } from "./scripts/lib/mechanics-projection.mjs";
    import fs from "node:fs";
    const policy = JSON.parse(fs.readFileSync("../coa_client_extract/data/spell_layout_v2.json", "utf8"));
    const row = { spell_id: 1, schema_version: "coa-client-spell-v4", mechanics: {}, raw: { id: {} } };
    try { verifyFullRowAgainstPolicy(row, policy); console.log("ACCEPTED"); }
    catch (e) { console.log("REJECTED:" + e.message); }
    """
    probe = REPO / "coa_scraper/_t14_probe.mjs"
    probe.write_text(script)
    try:
        out = subprocess.run(["node", "_t14_probe.mjs"], cwd=REPO / "coa_scraper",
                             capture_output=True, text=True).stdout
    finally:
        probe.unlink(missing_ok=True)
    assert out.startswith("REJECTED"), out
    assert "name" in out
```

- [ ] **Step 2: Run and confirm failure** — `KeyError: 'required_scalar_fields'`, and the Node probe
  prints `ACCEPTED`.

- [ ] **Step 3: Add the key to the production policy**

The value is the set of normalized Spell scalars every full row carries today, read off the real
generation's `mechanics` + `raw` keys: `["id", "name", "power_type", "school_mask"]`. Do **not**
include the four join-derived fields (`cast_time_ms`, `duration_ms`, `range_min_yd`, `range_max_yd`):
they are `raw_only` with null cells by reviewed adjudication, so requiring them would make every real
row fail.

- [ ] **Step 4: Recompute the policy `sha256` and the Node lock in lockstep**

The policy carries its own digest and `coa_scraper/config/spell_layout.lock.json` pins it. Use the
existing helper rather than hand-editing:

```bash
python -c "
from coa_client_extract.spell_layout import load_default_policy
print(load_default_policy().sha256)"
```

Write the value into both files. Run `python -m pytest tests/ -q -k 'policy_lock or layout'` to confirm
the lock tests agree.

- [ ] **Step 5: Run the tests; commit**

```bash
git add coa_client_extract/data/spell_layout_v2.json coa_scraper/config/spell_layout.lock.json \
        tests/test_e0r2_required_scalar_fields.py
git commit -m "fix(e0r2): T1.4 — the production policy declares required_scalar_fields"
```

### Task 1.5: Publication itself requires both validations and a passing budget

**Files:**
- Modify: `coa_client_extract/publish.py:171-204` (`finalize_and_publish`)
- Test: `tests/test_e0r2_publish_requires_validation.py`

**Context:** `finalize_and_publish` writes caller-supplied `validation`/`budget` verbatim. Strict
consumers reject the resulting pointer afterwards, but the publisher should never create it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_publish_requires_validation.py
"""E0R.2 T1.5: a generation that failed a trust boundary or its budget must never become the pointer's
target. Consumer-side strictness is a second line of defence, not the gate."""
import pytest

from coa_client_extract.publish import PublishError, POINTER_NAME
from tests._e0r2_fixtures import staged_writer


def test_publishing_with_a_failed_node_validation_is_refused(tmp_path):
    gw, candidate = staged_writer(tmp_path)
    with pytest.raises(PublishError, match="validation"):
        gw.finalize_and_publish(candidate_manifest=candidate,
                                validation={"python": True, "node": False},
                                budget={"within_budget": True, "breach": []})
    assert not (tmp_path / POINTER_NAME).exists()      # pointer untouched


def test_publishing_over_budget_is_refused(tmp_path):
    gw, candidate = staged_writer(tmp_path)
    with pytest.raises(PublishError, match="budget"):
        gw.finalize_and_publish(candidate_manifest=candidate,
                                validation={"python": True, "node": True},
                                budget={"within_budget": False, "breach": ["whole_generation bytes ..."]})
    assert not (tmp_path / POINTER_NAME).exists()


def test_a_fully_validated_within_budget_generation_publishes(tmp_path):
    gw, candidate = staged_writer(tmp_path)
    final = gw.finalize_and_publish(candidate_manifest=candidate,
                                    validation={"python": True, "node": True},
                                    budget={"within_budget": True, "breach": []})
    assert final["publication_state"] == "published"
    assert (tmp_path / POINTER_NAME).is_file()
```

- [ ] **Step 2: Run and confirm the first two fail (no exception, pointer written).**

- [ ] **Step 3: Add the gate as the first statement inside `finalize_and_publish`'s `try:`**

```python
            if not (validation.get("python") and validation.get("node")):
                raise PublishError(
                    f"refusing to publish: validation {validation!r} — a generation must pass BOTH "
                    "trust boundaries before the pointer may name it")
            if not budget.get("within_budget"):
                raise PublishError(f"refusing to publish: budget breach {budget.get('breach')!r}")
```

Placing it inside the existing `try:` keeps `finally: self._release_publish_lock()` covering the refusal
path, so a refused publication still releases the lock.

- [ ] **Step 4: Run the full Python suite**

Run: `python -m pytest -q`
Expected: PASS. Any test that published with `node: False` was asserting the old permissiveness —
update it to assert the refusal.

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/publish.py tests/test_e0r2_publish_requires_validation.py
git commit -m "fix(e0r2): T1.5 — finalize refuses to publish an unvalidated or over-budget generation"
```

---

# Workstream 2 — prohibit `converted` until a bundle validator exists (blocker 7)

**Blocker:** both validators only check that a bundle child *exists* if any row is `converted` —
no tar path containment, no internal manifest, no content hashes. No code path produces `converted`
(grep over `coa_client_extract/` finds only validation reads), so the honest resolution is to reject
the status in this schema and reintroduce it with its validator.

### Task 2.1: `converted` is not a valid icon asset status in this schema

**Files:**
- Modify: `coa_client_extract/contracts.py:16` (`ICON_ASSET_STATUSES`), `coa_client_extract/publish.py`
  (`_verify_icon_row`, `_cross_child` bundle branch), `coa_scraper/scripts/lib/generation.mjs:10,128-144,198-200`
- Test: `tests/test_e0r2_converted_prohibited.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_converted_prohibited.py
"""E0R.2 T2.1: `converted` promised tar containment, bundle-manifest and content-hash verification that
were never implemented, and nothing produces the status. An unverifiable status that no producer emits
is not a feature — reject it here and reintroduce it WITH its validator."""
import pytest

from coa_client_extract.contracts import ICON_ASSET_STATUSES
from coa_client_extract.publish import ResolveError, _verify_icon_row


def test_converted_is_not_an_admissible_status():
    assert "converted" not in ICON_ASSET_STATUSES
    assert ICON_ASSET_STATUSES == frozenset({"source_only", "missing", "placeholder"})


def test_a_converted_row_is_rejected():
    with pytest.raises(ResolveError, match="converted"):
        _verify_icon_row({"spell_id": 1, "asset_status": "converted", "client_path": "Interface\\Icons\\x",
                          "converted_ref": "bundle:1"})


def test_no_producer_emits_converted():
    """A grep-level guard: if a converter lands, this test is the reminder to bring its validator."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "coa_client_extract"
    offenders = [p.name for p in src.glob("*.py")
                 if '"converted"' in p.read_text(encoding="utf-8") and p.name not in
                 ("contracts.py", "publish.py")]
    assert offenders == [], f"a producer references converted without a bundle validator: {offenders}"
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement**

- `ICON_ASSET_STATUSES = frozenset({"source_only", "missing", "placeholder"})`.
- `_verify_icon_row`: the existing `status not in ICON_ASSET_STATUSES` branch now rejects `converted`
  with the enumeration in the message; delete the two `converted_ref` branches and the
  `status in ("source_only", "converted")` branch becomes `status == "source_only"`.
- `_cross_child`: delete `any_converted` and the bundle-required check; the `children` parameter it was
  the only consumer of goes with it (update the call site in `validate_candidate_generation`).
- `generation.mjs`: the same three edits, plus deleting the `manifest` parameter from `crossChild`.
- Leave a comment at the deleted bundle check naming what reintroduction requires:

```python
# E0R.2 T2.1: `converted` (and its icon bundle) is PROHIBITED in this schema. Reintroducing it requires,
# in the same change: tar path containment, per-entry bundle-manifest verification, and per-asset content
# hashes checked against the catalog — the checks the E0R design specified and E0R.1 deferred to an
# existence test. Until then no producer may emit it and no validator may accept it.
```

- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_client_extract/contracts.py coa_client_extract/publish.py \
        coa_scraper/scripts/lib/generation.mjs tests/test_e0r2_converted_prohibited.py
git commit -m "fix(e0r2): T2.1 — prohibit converted icon assets until the bundle validator exists"
```

---

# Workstream 3 — live join recon and an honest recon budget (blockers 3, 4)

**Blocker 3:** for `reviewed_ambiguous` joins `probe_joins` copies authored evidence *without reading
the side table or scanning the client* (`spell_mechanics.py:147-150`), and `_recon_status` accepts
`pair: null` unconditionally (`:194-196`). Both docstrings claim every required join is probed on every
run. A client patch that made a numeric FK uniquely discoverable would be invisible.

**Blocker 4:** recon estimates `record_count * record_size` (raw DBC bytes) against the retired
`DEFAULT_BUDGET = {512, 4096, 600}` and ignores the reviewed policy budget — reporting 186.07 MiB for a
generation that is actually 523,026,495 bytes.

### Task 3.1: A live FK candidate scan runs for every ambiguous join on every recon

**Files:**
- Modify: `coa_client_extract/spell_mechanics.py` (`probe_joins`, new `scan_index_candidates`)
- Test: `tests/test_e0r2_recon_live_joins.py`

**Interfaces:**
- Produces: `scan_index_candidates(view, side_view, *, side_id_cell=0) -> list[int]` — every Spell cell
  whose non-zero values are ≥99% valid side ids spanning ≥`_MIN_DISTINCT` distinct side rows.
  `probe_joins` records `{"table", "pair": None, "winners": [], "adjudication": "reviewed_ambiguous",
  "evidence", "scanned": True, "candidate_index_cells": [...], "candidate_count": N}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_recon_live_joins.py
"""E0R.2 T3.1: an adjudicated-ambiguous join is still PROBED on every run. Copying the authored verdict
forward means recon cannot notice the day the client makes the join unique — which is the one thing the
hold exists to catch."""
from coa_client_extract.spell_mechanics import probe_joins, scan_index_candidates
from tests._e0r2_recon_fixtures import ambiguous_backend, unique_backend, open_spell_view


def test_an_ambiguous_join_is_scanned_not_asserted():
    probes = probe_joins(*ambiguous_backend())
    cast = probes["casting_time_index"]
    assert cast["scanned"] is True
    assert cast["pair"] is None
    assert cast["candidate_count"] >= 2                  # the ambiguity is re-proven, not remembered
    assert cast["candidate_index_cells"] == sorted(cast["candidate_index_cells"])


def test_a_join_that_became_unique_is_recorded_as_unique():
    """Synthesize a client where exactly one column is FK-valid into SpellCastTimes."""
    probes = probe_joins(*unique_backend())
    assert probes["casting_time_index"]["candidate_count"] == 1


def test_the_scan_reads_the_side_table():
    """Regression: the old path returned before read_effective_file, so a missing side table was
    indistinguishable from an ambiguous one."""
    backend, root, attach, view, id_to_rec, policy, anchors = ambiguous_backend()
    backend.forget("DBFilesClient\\SpellCastTimes.dbc")
    probes = probe_joins(backend, root, attach, view, id_to_rec, policy, anchors)
    assert probes["casting_time_index"]["scanned"] is False
    assert probes["casting_time_index"]["side_table_missing"] is True
```

- [ ] **Step 2: Run and confirm failure** — `ImportError: cannot import name 'scan_index_candidates'`.

- [ ] **Step 3: Implement the scan and rewire the ambiguous branch**

```python
def scan_index_candidates(view, side_view, *, side_id_cell=0) -> list[int]:
    """The bare FK-validity scan: every Spell cell whose non-zero values are ~all valid side ids over
    enough distinct side rows. Deliberately NOT unique on its own — its job is to re-prove, on every
    run, that the ambiguity the review adjudicated is still the client's shape. A collapse to one
    candidate means the client changed and the adjudication must be revisited (E0R.2 T3.1)."""
    side_ids = {r.u32(side_id_cell) for r in side_view.records()}
    candidates = []
    for ic in range(view.cell_count):
        nonzero = [r.u32(ic) for r in view.records() if r.u32(ic) != 0]
        if len(nonzero) < _MIN_SUPPORT:
            continue
        hits = [v for v in nonzero if v in side_ids]
        if len(hits) / len(nonzero) < 0.99 or len(set(hits)) < _MIN_DISTINCT:
            continue
        candidates.append(ic)
    return candidates
```

In `probe_joins`, the `reviewed_ambiguous` branch stops returning early. Open the side table first
(recording `side_table_missing: True` and `scanned: False` when it is absent, instead of the old silent
`continue`), then:

```python
        if spec.get("adjudication") == "reviewed_ambiguous":
            candidates = scan_index_candidates(view, side_view, side_id_cell=spec.get("side_id_cell", 0))
            join_pairs[field] = {
                "table": side_name, "pair": None, "winners": [],
                "adjudication": "reviewed_ambiguous", "evidence": spec.get("evidence"),
                "scanned": True, "candidate_index_cells": candidates,
                "candidate_count": len(candidates)}
            continue
```

- [ ] **Step 4: Run the probes and the recon suite**

Run: `python -m pytest tests/test_e0r2_recon_live_joins.py tests/test_e0r_recon_cli.py tests/test_e0r1_recon_mandatory.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add coa_client_extract/spell_mechanics.py tests/test_e0r2_recon_live_joins.py tests/_e0r2_recon_fixtures.py
git commit -m "fix(e0r2): T3.1 — ambiguous joins are re-scanned live on every recon"
```

### Task 3.2: `verified` requires the reviewed ambiguity to have survived

**Files:**
- Modify: `coa_client_extract/spell_mechanics.py:176-202` (`_recon_status`)
- Test: `tests/test_e0r2_recon_live_joins.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
def test_a_join_that_collapsed_to_one_candidate_forces_review():
    status = _recon_status(**_base_args(join_pairs={
        "casting_time_index": {"pair": None, "scanned": True, "candidate_count": 1,
                               "adjudication": "reviewed_ambiguous"}}))
    assert status == "review_required"


def test_a_join_with_no_surviving_candidate_forces_review():
    status = _recon_status(**_base_args(join_pairs={
        "casting_time_index": {"pair": None, "scanned": True, "candidate_count": 0,
                               "adjudication": "reviewed_ambiguous"}}))
    assert status == "review_required"


def test_an_unscanned_ambiguous_join_forces_review():
    """The exact 02e0b7c behaviour: pair=None with no machine evidence used to read as verified."""
    status = _recon_status(**_base_args(join_pairs={
        "casting_time_index": {"pair": None, "adjudication": "reviewed_ambiguous"}}))
    assert status == "review_required"


def test_a_surviving_ambiguity_still_verifies():
    status = _recon_status(**_base_args(join_pairs={
        "casting_time_index": {"pair": None, "scanned": True, "candidate_count": 30,
                               "adjudication": "reviewed_ambiguous"}}))
    assert status == "verified"
```

- [ ] **Step 2: Run and confirm the first three fail (all return `verified`).**

- [ ] **Step 3: Replace the unconditional `continue` in `_recon_status`**

```python
        pair = probe.get("pair")
        if pair is None:
            # An ambiguous join stays raw_only ONLY while the ambiguity is re-proven by a live scan.
            # >=2 surviving candidates == the reviewed shape. Exactly 1 means the client now pins the
            # join and the adjudication is stale; 0 means the join vanished. Either is a human decision,
            # never a silent `verified` (E0R.2 T3.2).
            if not probe.get("scanned"):
                return "review_required"
            if (probe.get("candidate_count") or 0) < 2:
                return "review_required"
            continue
```

Update the docstring: `verified` now requires *every* required join either uniquely discovered **and**
adopted at the authored cell, or **live-scanned** with ≥2 surviving candidates.

- [ ] **Step 4: Run; commit**

```bash
git add coa_client_extract/spell_mechanics.py tests/test_e0r2_recon_live_joins.py
git commit -m "fix(e0r2): T3.2 — verified requires the reviewed ambiguity to survive a live scan"
```

### Task 3.3: Recon stops claiming artifact size; its own budget is policy-bound

**Files:**
- Modify: `coa_client_extract/spell_mechanics.py:205-218` (`three_part_budget` → `recon_budget`),
  `:358-365` (drop `est_bytes`), `coa_client_extract/cli.py:341-344` (delete the `DEFAULT_BUDGET`
  fallback), `:16` (`DEFAULT_BUDGET`)
- Test: `tests/test_e0r2_recon_budget.py`

**Design:** recon measures a *recon*, not a generation. It has no basis for a generation-size forecast —
`record_count * record_size` is raw DBC bytes, off by 2.8× against the real 523 MB. Recon gates its own
peak RSS and elapsed against the reviewed policy ceilings (`python_peak_rss_mb`, `python_elapsed_s`) and
makes no size claim at all. Generation size stays gated at publication, where it is measured exactly.
A serialized-sample forecast is an explicit **non-goal** here: a wrong forecast is worse than no forecast.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_recon_budget.py
"""E0R.2 T3.3: recon reported 186.07 MiB for a generation that was 523,026,495 bytes, because it
estimated raw DBC bytes against a retired hard-coded ceiling. A number that wrong is worse than no
number — recon now gates only what it actually measures, against the reviewed policy."""
import pytest

from coa_client_extract.spell_mechanics import recon_budget


def test_recon_makes_no_artifact_size_claim():
    report = recon_budget(peak_rss_mb=100.0, elapsed_s=12.0,
                          ceilings={"python_peak_rss_mb": 4096, "python_elapsed_s": 1200})
    assert "artifact_size_mb" not in report
    assert "serialized_bytes" not in report
    assert report["within_budget"] is True


def test_recon_gates_its_own_rss_and_elapsed_against_the_policy():
    report = recon_budget(peak_rss_mb=9000.0, elapsed_s=12.0,
                          ceilings={"python_peak_rss_mb": 4096, "python_elapsed_s": 1200})
    assert report["within_budget"] is False
    assert any("python_peak_rss_mb" in b for b in report["breach"])


def test_the_retired_default_budget_is_gone():
    import coa_client_extract.spell_mechanics as sm
    assert not hasattr(sm, "DEFAULT_BUDGET")
    assert not hasattr(sm, "three_part_budget")


def test_regenerate_refuses_a_policy_without_a_budget_block(tmp_path):
    """The silent DEFAULT_BUDGET fallback meant a policy with no reviewed ceilings still published."""
    from coa_client_extract.cli import regenerate
    from coa_client_extract.publish import PublishError
    from tests._e0r2_fixtures import policy_without_budget, synthetic_client
    with pytest.raises(PublishError, match="budget"):
        regenerate(*synthetic_client(tmp_path), spell_policy=policy_without_budget())
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement**

```python
def recon_budget(*, peak_rss_mb, elapsed_s, ceilings) -> dict:
    """Recon's OWN resource envelope against the reviewed policy ceilings. Recon makes no
    generation-size claim: it reads DBC headers, and record_count*record_size is not a forecast of a
    serialized generation (it was off by 2.8x on the real client). Size is gated at publication, where
    it is measured exactly (E0R.2 T3.3)."""
    breach = []
    for key, value in (("python_peak_rss_mb", peak_rss_mb), ("python_elapsed_s", elapsed_s)):
        ceiling = ceilings.get(key)
        if ceiling is not None and value > ceiling:
            breach.append(f"{key} {value} > {ceiling}")
    return {"measured": {"python_peak_rss_mb": peak_rss_mb, "python_elapsed_s": elapsed_s},
            "ceilings": dict(ceilings), "within_budget": not breach, "breach": breach}
```

`recon_spell_mechanics` takes `budget` from the policy (`spell_policy.doc["budget"]`) rather than the
module default; delete the `est_bytes` line and `DEFAULT_BUDGET`. In `cli.py`, delete the
`three_part_budget` else-branch and raise `PublishError` when `policy.doc.get("budget")` is absent and
no explicit `budget` was passed. Synthetic test policies that relied on the fallback get an explicit
budget block in `tests/_e0r2_fixtures.py`.

- [ ] **Step 4: Run the full Python suite; migrate the fixtures the fallback was propping up; commit**

```bash
git add coa_client_extract/spell_mechanics.py coa_client_extract/cli.py tests/test_e0r2_recon_budget.py
git commit -m "fix(e0r2): T3.3 — recon gates what it measures; the retired hard-coded budget is deleted"
```

---

# Workstream 4 — one internally-executed, generation-bound acceptance (blocker 2)

**Blocker:** `write_acceptance_summary(dist, *, recon_report_path, build_mechanics, ...)` trusts a
caller-supplied `build_mechanics` dict for `executed`, `exit_code`, `network_attempts` and
`pointer_only`. It accepts a recon document containing only `{"status": "verified"}`. It binds no recon
client/policy/topology identity to the resolved generation and no mechanics output hash, and it
silently substitutes `{}` for absent readiness/source coverage. *(Precision: the shipped
`acceptance-summary` subcommand does always execute the build first — `cli.py:833-839` — so the
committed record came from the executing path. The fabricable surface is the function API, which is
what a future caller will reach for.)*

**Additional finding:** `readiness_coverage` and `source_coverage` have **no producer anywhere** —
grep finds only the two reader lines at `cli.py:555-556`. The `{}` is not a dropped measurement; the
measurement was never implemented, while the E0R.1 tracker's T6.2 checkbox claims it is recorded.

### Task 4.1: Real readiness and source coverage producers

**Files:**
- Modify: `coa_client_extract/spell_record.py` or `coa_client_extract/cli.py` (a streaming
  `readiness_coverage` accumulator in `regenerate`), `coa_client_extract/cli.py:280` (manifest hoist)
- Test: `tests/test_e0r2_coverage_producers.py`

**Design:** the two coverages belong to different artifacts and must be sourced accordingly.
- `readiness_coverage` is a **generation** fact: per-field counts of cell `state` and `decoded_reason`
  across the full child, accumulated during the streaming write (single pass, no materialization) and
  hoisted into manifest-v3 next to `icon_coverage`.
- `source_coverage` is a **mechanics-artifact** fact: the canonical build already computes
  `per_field_winner_counts_by_source`. The acceptance record reads it from the mechanics manifest the
  measured build emitted — not from the generation manifest, which has no such concept.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_coverage_producers.py
"""E0R.2 T4.1: the acceptance schema has claimed icon/readiness/source coverage since E0R.1 T6.2, but
readiness_coverage and source_coverage had NO producer — the writer read absent manifest keys and
substituted {}. A coverage claim with no producer is worse than an omitted one."""
from coa_client_extract.spell_record import readiness_accumulator


def test_readiness_coverage_counts_states_and_reasons_per_field():
    acc = readiness_accumulator()
    acc.observe({"id": {"state": "present", "decoded_reason": "decoded"},
                 "power_type": {"state": "present", "decoded_reason": "proof_withheld"}})
    acc.observe({"id": {"state": "present", "decoded_reason": "decoded"},
                 "power_type": {"state": "unresolved", "decoded_reason": "not_present"}})
    cov = acc.result()
    assert cov["fields"]["id"]["state"]["present"] == 2
    assert cov["fields"]["power_type"]["decoded_reason"]["proof_withheld"] == 1
    assert cov["cells"] == 4


def test_regenerate_hoists_readiness_coverage_into_the_manifest(tmp_path):
    from tests._e0r2_fixtures import regenerate_synthetic
    manifest = regenerate_synthetic(tmp_path)
    assert manifest["readiness_coverage"]["cells"] > 0
    assert "power_type" in manifest["readiness_coverage"]["fields"]
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement the accumulator and wire it into the streaming write**

```python
def readiness_accumulator():
    """Single-pass per-field readiness counts over the full child's compact cells — the generation-level
    twin of icon_coverage. Never materializes rows (E0R.2 T4.1)."""
    from collections import Counter, defaultdict

    class _Acc:
        def __init__(self):
            self.fields = defaultdict(lambda: {"state": Counter(), "decoded_reason": Counter()})
            self.cells = 0

        def observe(self, raw_block: dict) -> None:
            for field, cell in raw_block.items():
                bucket = self.fields[field]
                bucket["state"][cell.get("state")] += 1
                bucket["decoded_reason"][cell.get("decoded_reason")] += 1
                self.cells += 1

        def result(self) -> dict:
            return {"cells": self.cells,
                    "fields": {f: {"state": dict(b["state"]), "decoded_reason": dict(b["decoded_reason"])}
                               for f, b in sorted(self.fields.items())}}

    return _Acc()
```

Call `acc.observe(row["raw"])` in the same loop that already writes and hashes the full child, and set
`base_manifest["readiness_coverage"] = acc.result()` beside the existing
`base_manifest["icon_coverage"] = icon_cov` at `cli.py:280`.

- [ ] **Step 4: Run; commit**

```bash
git add coa_client_extract/spell_record.py coa_client_extract/cli.py tests/test_e0r2_coverage_producers.py
git commit -m "feat(e0r2): T4.1 — real readiness coverage producer (source coverage comes from the build)"
```

### Task 4.2: One acceptance command that executes what it attests to

**Files:**
- Modify: `coa_client_extract/cli.py:492-567` (`write_acceptance_summary` → `run_acceptance`),
  `:833-846` (subcommand)
- Test: `tests/test_e0r2_acceptance_executes.py`

**Interfaces:**
- Produces: `run_acceptance(dist, *, recon_report_path, scraper_dir, builder_entries, mechanics_out,
  benchmark_env_id="local", out=None, node="node") -> dict`. `write_acceptance_summary` is **deleted**;
  there is no entry point that accepts a caller-supplied measurement.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_acceptance_executes.py
"""E0R.2 T4.2: acceptance must EXECUTE what it attests to. The v2 writer took a build_mechanics dict
and trusted executed/exit_code/network_attempts/pointer_only, so any caller could hand it a fabricated
successful run."""
import inspect

import pytest

from coa_client_extract import cli


def test_there_is_no_entry_point_that_accepts_a_caller_supplied_measurement():
    assert not hasattr(cli, "write_acceptance_summary")
    assert "build_mechanics" not in inspect.signature(cli.run_acceptance).parameters


def test_a_fabricated_measurement_cannot_reach_the_record(monkeypatch, tmp_path):
    """The only path to build_mechanics is the internal executor."""
    calls = []
    monkeypatch.setattr(cli, "run_measured_build_mechanics",
                        lambda *a, **k: calls.append(a) or {"executed": True, "exit_code": 1})
    from tests._e0r2_fixtures import published_generation, verified_recon
    dist = published_generation(tmp_path)
    with pytest.raises(cli.AcceptanceError, match="exit_code=1"):
        cli.run_acceptance(dist, recon_report_path=verified_recon(tmp_path), scraper_dir=tmp_path,
                           builder_entries=tmp_path / "e.jsonl", mechanics_out=tmp_path / "out")
    assert calls, "the build was not executed"
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Fold the executor inside**

`run_acceptance` performs, in order: resolve the generation → read + validate the recon → **execute**
`run_measured_build_mechanics` → `_require_executed_build_mechanics` → bind (T4.3) → write. Delete
`write_acceptance_summary` and point the subcommand at `run_acceptance`. Bump the record's
`schema_version` to `coa-e0r-acceptance-summary-v3`.

- [ ] **Step 4: Run; commit**

```bash
git add coa_client_extract/cli.py tests/test_e0r2_acceptance_executes.py
git commit -m "fix(e0r2): T4.2 — acceptance executes the build it attests to; the v2 writer is deleted"
```

### Task 4.3: The record binds recon and mechanics to *this* generation

**Files:**
- Modify: `coa_client_extract/cli.py` (`run_acceptance`)
- Test: `tests/test_e0r2_acceptance_binding.py`

**Design — every claim tied to one generation id:**
1. The recon report must carry a full binding, not just `{"status": "verified"}`: its
   `binding.policy_sha256` must equal the manifest's, its `client_build` must match, and its per-table
   `sha256` values must equal the manifest `binding` capture identities.
2. The mechanics manifest's output `sha256` and `record_count` are recorded.
3. `source_coverage` is read from the mechanics manifest's `per_field_winner_counts_by_source`.
4. Missing coverage **fails**; there is no `{}` substitution.
5. After the build, the pointer is re-read and its `generation_id` must still equal the one resolved at
   the start — otherwise a concurrent publish combined measurements from two generations.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_acceptance_binding.py
"""E0R.2 T4.3: the record must prove the measurements and the generation are the same run. At 02e0b7c
a recon document containing only {"status": "verified"} was accepted, and a concurrent pointer change
between resolve and build would have gone unnoticed."""
import pytest

from coa_client_extract.cli import AcceptanceError, run_acceptance
from tests._e0r2_fixtures import acceptance_env


def test_a_bare_status_only_recon_is_refused(tmp_path):
    env = acceptance_env(tmp_path, recon={"status": "verified"})
    with pytest.raises(AcceptanceError, match="binding"):
        run_acceptance(**env)


def test_a_recon_bound_to_a_different_policy_is_refused(tmp_path):
    env = acceptance_env(tmp_path, recon_policy_sha256="0" * 64)
    with pytest.raises(AcceptanceError, match="policy_sha256"):
        run_acceptance(**env)


def test_a_recon_bound_to_a_different_client_capture_is_refused(tmp_path):
    env = acceptance_env(tmp_path, recon_table_sha256={"Spell": "f" * 64})
    with pytest.raises(AcceptanceError, match="Spell"):
        run_acceptance(**env)


def test_a_pointer_that_moved_during_the_build_is_refused(tmp_path):
    env = acceptance_env(tmp_path, republish_during_build=True)
    with pytest.raises(AcceptanceError, match="pointer moved|generation changed"):
        run_acceptance(**env)


def test_absent_coverage_fails_instead_of_becoming_an_empty_object(tmp_path):
    env = acceptance_env(tmp_path, drop_manifest_keys=["readiness_coverage"])
    with pytest.raises(AcceptanceError, match="readiness_coverage"):
        run_acceptance(**env)


def test_the_record_binds_the_mechanics_output_hash(tmp_path):
    record = run_acceptance(**acceptance_env(tmp_path))
    assert len(record["mechanics"]["sha256"]) == 64
    assert record["mechanics"]["record_count"] > 0
    assert record["coverage"]["source"]                       # from the mechanics manifest
    assert record["coverage"]["readiness"]["cells"] > 0
```

- [ ] **Step 2: Run and confirm every probe fails.**

- [ ] **Step 3: Implement the five binding checks in `run_acceptance`**

```python
    # --- the recon must be bound to THIS generation, not merely verified ---
    recon_binding = recon_report.get("binding") or {}
    if not recon_binding:
        raise AcceptanceError("recon report carries no binding block; a status alone binds nothing")
    if recon_binding.get("policy_sha256") != binding.get("policy_sha256"):
        raise AcceptanceError(
            f"recon policy_sha256 {recon_binding.get('policy_sha256')!r} != generation "
            f"{binding.get('policy_sha256')!r}")
    if recon_report.get("client_build") != manifest.get("client_build"):
        raise AcceptanceError(
            f"recon client_build {recon_report.get('client_build')!r} != generation "
            f"{manifest.get('client_build')!r}")
    for table, meta in (binding.get("tables") or {}).items():
        observed = ((recon_binding.get("tables") or {}).get(table) or {}).get("sha256")
        if observed != meta.get("sha256"):
            raise AcceptanceError(
                f"recon bound {table} sha256 {observed!r} != generation {meta.get('sha256')!r}")

    # --- coverage must exist; {} was a claim with no producer (E0R.2 T4.1) ---
    readiness_cov = manifest.get("readiness_coverage")
    if not readiness_cov:
        raise AcceptanceError("generation manifest carries no readiness_coverage")

    # --- the build's own outputs, bound ---
    emitted = json.loads((mechanics_manifest_path).read_text(encoding="utf-8"))
    source_cov = emitted.get("per_field_winner_counts_by_source")
    if not source_cov:
        raise AcceptanceError("mechanics manifest carries no per_field_winner_counts_by_source")
    mechanics = {"sha256": emitted["outputs"]["sha256"],
                 "record_count": emitted["outputs"]["record_count"],
                 "manifest_sha256": _sha256_bytes(mechanics_manifest_path.read_bytes())}

    # --- the pointer must not have moved under us ---
    after = json.loads(pointer.read_text(encoding="utf-8")).get("generation_id")
    if after != manifest.get("generation_id"):
        raise AcceptanceError(
            f"pointer moved during the acceptance run ({manifest.get('generation_id')!r} -> {after!r}); "
            "the measurements would describe two different generations")
```

- [ ] **Step 4: Run; commit**

```bash
git add coa_client_extract/cli.py tests/test_e0r2_acceptance_binding.py
git commit -m "fix(e0r2): T4.3 — acceptance binds recon, coverage and mechanics to one generation"
```

---

# Workstream 5 — the canonical build streams end to end (blocker 5)

**Blocker:** candidate validation streams, but the canonical mechanics path still does
`readFileSync` → `.toString("utf8")` → `.split("\n")` → accumulate a `projection` array and a
`clientById` Map over all of it, then retains the full mechanics output array
(`mechanics-projection.mjs:339-385`, `build-mechanics-artifacts.mjs:37-49,102-133,386-423`). The
E0R.1 design named "projection consumption → mechanics serialization" as in scope for streaming; the
T4.2 RSS test covers candidate validation instead. Node peaked at 866 MB on the real run.

**Key observation that makes this cheap:** `buildCanonicalMechanics` emits one row per **Builder**
spell (~3,600), not per projection row (10,410). The projection is only a lookup. So the streaming pass
needs to retain only the projection rows whose `spell_id` is in `builderSpellIds` — a ~3× smaller map
and no whole-file string.

### Task 5.1: Streaming projection consumption

**Files:**
- Modify: `coa_scraper/scripts/lib/mechanics-projection.mjs:339-385`
  (`loadAndValidateProjectionV3` → `streamAndValidateProjectionV3`)
- Test: `coa_scraper/tests/mechanics-streaming.test.mjs`

**Interfaces:**
- Produces: `streamAndValidateProjectionV3({ projectionPath, manifestBytes, manifest, builderSpellIds,
  policyPath }) -> { absent: false, clientById: Map, coverage, projection_sha256, manifest_sha256,
  client_build }`. The `projection` array is **gone**; callers use `clientById`.

- [ ] **Step 1: Write the failing test**

```javascript
// coa_scraper/tests/mechanics-streaming.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { streamAndValidateProjectionV3 } from "../scripts/lib/mechanics-projection.mjs";
import { syntheticProjection } from "./_e0r2-fixtures.mjs";

test("the projection is never materialized as an array or a whole-file string", () => {
  const src = fs.readFileSync(new URL("../scripts/lib/mechanics-projection.mjs", import.meta.url), "utf8");
  const fn = src.slice(src.indexOf("export function streamAndValidateProjectionV3"));
  assert.ok(!/readFileSync\(projectionPath/.test(fn), "still reads the whole projection");
  assert.ok(!/\.split\("\\n"\)/.test(fn), "still splits the whole projection into strings");
});

test("only builder-domain rows are retained", (t) => {
  const { projectionPath, manifest, manifestBytes, policyPath } = syntheticProjection(t, { rows: 5000 });
  const builderSpellIds = new Set([10, 20, 30]);
  const loaded = streamAndValidateProjectionV3({ projectionPath, manifestBytes, manifest, builderSpellIds, policyPath });
  assert.equal(loaded.clientById.size, 3);
  assert.equal(loaded.coverage.builder_joined_to_projection, 3);
  assert.equal(loaded.coverage.projection_only, 4997);
});

test("every row is still validated, not just the retained ones", (t) => {
  const { projectionPath, manifest, manifestBytes, policyPath } = syntheticProjection(t, { rows: 100, corruptAt: 73 });
  assert.throws(() => streamAndValidateProjectionV3({
    projectionPath, manifestBytes, manifest, builderSpellIds: new Set([1]), policyPath }), /line 73|schema_version/);
});
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement using the existing `readJsonlLines` generator**

Hash incrementally with the same chunked read that yields lines, rather than hashing a whole buffer.
Keep every existing per-row check (`schema_version`, `is_coa`, positive-unique `spell_id`,
`verifyRowAgainstPolicy`) — the point is memory, not fewer checks. Track `seen` as a `Set` of ids (ints,
~10k — that is a counter-scale structure, not a row-scale one) so duplicate detection and the
`unique_spell_ids` cross-check survive.

- [ ] **Step 4: Run; commit**

```bash
git add coa_scraper/scripts/lib/mechanics-projection.mjs coa_scraper/tests/mechanics-streaming.test.mjs
git commit -m "perf(e0r2): T5.1 — the canonical build streams the projection instead of reading it whole"
```

### Task 5.2: Generator mechanics rows and incremental statistics

**Files:**
- Modify: `coa_scraper/scripts/build-mechanics-artifacts.mjs:37-49` (`buildCanonicalMechanics` →
  generator), `:386-423` (`writeArtifact` consumes an iterable), `winnerCounts`/`aggregateCounts` →
  incremental accumulators
- Test: `coa_scraper/tests/mechanics-streaming.test.mjs` (extend)

- [ ] **Step 1: Write the failing test**

```javascript
test("buildCanonicalMechanics yields rows instead of returning an array", () => {
  const gen = buildCanonicalMechanics({ entries: [], clientById: new Map() });
  assert.equal(typeof gen[Symbol.iterator], "function");
  assert.ok(!Array.isArray(gen));
});

test("writeArtifact never holds the row array", (t) => {
  const src = fs.readFileSync(new URL("../scripts/build-mechanics-artifacts.mjs", import.meta.url), "utf8");
  assert.ok(!/rows\.length/.test(src), "record_count still derived from a materialized array");
  assert.ok(!/winnerCounts\(rows\)/.test(src), "statistics still computed over a materialized array");
});

test("the artifact is byte-identical to the pre-streaming implementation", (t) => {
  /* golden: build the fixture corpus and compare sha256 against the recorded value — streaming is a
     memory change, never an output change. */
  const { sha } = buildFixtureArtifact(t);
  assert.equal(sha, GOLDEN_MECHANICS_SHA256);
});
```

The third test is the important one: capture `GOLDEN_MECHANICS_SHA256` from the *current*
implementation before refactoring, so the refactor is provably output-preserving.

- [ ] **Step 2: Record the golden sha, run, confirm failure.**

- [ ] **Step 3: Implement**

`buildCanonicalMechanics` becomes `function*` and `yield`s each row in ascending `spell_id`.
`writeArtifact` keeps its existing `for (const r of rows)` write loop (already streaming) and folds the
statistics into that loop:

```javascript
  let recordCount = 0;
  const stats = statsAccumulator();          // bySource / byTier / aggregate counters
  for (const r of rows) {
    const line = Buffer.from(JSON.stringify(r) + "\n");
    fs.writeSync(outFd, line);
    outHash.update(line);
    stats.observe(r);
    recordCount += 1;
  }
```

- [ ] **Step 4: Run; commit**

```bash
git add coa_scraper/scripts/build-mechanics-artifacts.mjs coa_scraper/tests/mechanics-streaming.test.mjs
git commit -m "perf(e0r2): T5.2 — mechanics rows are generated and counted incrementally"
```

### Task 5.3: The RSS test runs through the real canonical build

**Files:**
- Create: `coa_scraper/tests/_canonical_build_probe.mjs`
- Modify: `coa_scraper/tests/generation-streaming.test.mjs` (or wherever T4.2's RSS test lives)

- [ ] **Step 1: Write the failing test**

```javascript
test("canonical build peak RSS grows sub-linearly with projection size", () => {
  const small = runProbe(10_000);
  const large = runProbe(100_000);
  assert.ok(large.peak_rss_mb - small.peak_rss_mb < 150,
    `RSS delta ${large.peak_rss_mb - small.peak_rss_mb} MB over a 10x projection`);
});
```

`_canonical_build_probe.mjs` stages a synthetic generation of N projection rows, runs the **actual**
`buildMechanicsArtifact` entry point in an isolated subprocess, and prints
`{n, peak_rss_mb}` from `process.resourceUsage().maxRSS`. Mirror `tests/_streaming_probe.py`'s
try/finally temp-dir cleanup — that leak produced a false "memory regression" during E0R.1 when it
filled the tmpfs.

- [ ] **Step 2: Run, confirm the delta exceeds the gate before T5.1/T5.2 (it should already pass after
  them — if so, verify the probe is real by reverting T5.1 locally and watching it fail).**

- [ ] **Step 3: Commit**

```bash
git add coa_scraper/tests/_canonical_build_probe.mjs coa_scraper/tests/generation-streaming.test.mjs
git commit -m "test(e0r2): T5.3 — the RSS gate runs through the real canonical build"
```

---

# Workstream 6 — real E1 headroom (blocker 6)

**Blocker:** the real generation is 523,026,495 of 536,870,912 bytes — **97.42%**, leaving 13.2 MiB.
The design's exit condition is "Re-run the real client with substantial E1 headroom."

**Measured attribution** (20,000-row sample of the full child, extrapolated to 208,447; per-field
constancy verified over 50,000 rows):

| component | share | extrapolated | nature |
|---|---|---|---|
| `policy_ref` | 23.6% | 88.6 MB | **constant per field** (1 distinct value per field over 50k rows) |
| `decoded_reason` | 14.8% | 55.4 MB | closed vocabulary — 3 values observed |
| `state` | 9.7% | 36.3 MB | closed vocabulary — 2 values observed |
| `resolved` | 6.0% | 22.4 MB | descriptions; only 35% dedupable |
| `join_name` | 5.9% | 22.3 MB | **constant per field** |
| icons child | — | 66.1 MB | 14,022 unique paths across 179,774 resolved rows |

The review proposed a description/string dictionary as the strongest opportunity. The measurement says
otherwise: descriptions are mostly unique and dedup to ~8 MB. The dominant redundancy is per-cell
**constant metadata** (111 MB) and **low-cardinality enums** (92 MB). Hoisting and interning those,
plus normalizing icons, projects **~298 MB (55% of ceiling)** without touching descriptions — so
description dedup is left undone as YAGNI and recorded here with its measured value.

**Invariant preserved:** `expand_compact` is exactly the bridge between compact `raw` and rich
`field_observations`, so rehydration keeps
`expand_compact(full.raw) == projection.field_observations` literally true and the projection child
unchanged at `coa-client-spell-projection-v3`.

### Task 6.1: Hoist the per-field constants into a field-descriptor child

**Files:**
- Create: producer for `coa_client_spell_fields.json` in `coa_client_extract/spell_record.py`
- Modify: `coa_client_extract/spell_record.py` (`_compact`, `_expand_compact`),
  `coa_client_extract/cli.py` (stage the new child), `coa_client_extract/publish.py`
  (`_expand_full_raw` and `_cross_child` must load the descriptor child and thread it into
  `_expand_cell` — the signature grows a third argument),
  `coa_scraper/scripts/lib/mechanics-projection.mjs` (`expandCompact`)
- Test: `tests/test_e0r2_field_hoist.py`, `coa_scraper/tests/expand-compact.test.mjs`

**Design:** `coa_client_spell_fields.json` is
`{"schema_version": "coa-client-spell-fields-v1", "fields": {"<raw key>": {"policy_ref": "...",
"join_name": "..."}}}`. Compact cells drop both keys; `expand_compact(cell, policy, fields)` puts them
back. Bump the full child to `coa-client-spell-v4`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_field_hoist.py
"""E0R.2 T6.1: policy_ref and join_name are CONSTANT per field (verified: 1 distinct value per field
over 50,000 real rows) yet were re-serialized on every cell of every row — 111 MB of the 523 MB
generation. Hoist them once; expand_compact puts them back, so the cross-child equality is untouched."""
from coa_client_extract.spell_record import _compact, _expand_compact, build_field_descriptors


def test_compact_cells_carry_no_per_field_constants():
    cell = _compact("cast_time_ms", _sample_observation())
    assert "policy_ref" not in cell
    assert "join_name" not in cell


def test_expansion_restores_them_exactly():
    fields = build_field_descriptors(_policy())
    observation = _sample_observation()
    assert _expand_compact(_compact("cast_time_ms", observation), _policy(), fields) == observation


def test_the_descriptor_child_covers_every_raw_field():
    fields = build_field_descriptors(_policy())
    assert set(fields["fields"]) == set(_expected_raw_fields())
    assert fields["schema_version"] == "coa-client-spell-fields-v1"
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `build_field_descriptors`, drop the two keys in `_compact`, restore them in
  `_expand_compact`, stage the child in `regenerate`, bump the full child schema to
  `coa-client-spell-v4`.**
- [ ] **Step 4: Mirror `expandCompact` in `mechanics-projection.mjs` (it takes the descriptor doc
  alongside the policy doc) and update `crossChild`'s expansion call in `generation.mjs`.**
- [ ] **Step 5: Migrate `tests/golden/e0r1_corpus/` to v4 — the golden corpus is the shared source of
  row shape for both languages, so it changes exactly once here.**
- [ ] **Step 6: Run both suites; commit**

```bash
git add coa_client_extract/spell_record.py coa_client_extract/cli.py \
        coa_scraper/scripts/lib/mechanics-projection.mjs coa_scraper/scripts/lib/generation.mjs \
        tests/golden/e0r1_corpus tests/test_e0r2_field_hoist.py coa_scraper/tests/expand-compact.test.mjs
git commit -m "perf(e0r2): T6.1 — hoist per-field constants out of every cell (-111 MB)"
```

### Task 6.2: Intern the closed-vocabulary enums

**Files:** same as T6.1, plus the `vocabularies` block in `coa_client_spell_fields.json`.

**Design:** the descriptor child gains
`"vocabularies": {"state": ["present", "unresolved"], "decoded_reason": ["decoded", "not_present",
"proof_withheld", ...]}` — the **full closed vocabulary from the policy/contract, not the observed
subset**, so a value that appears for the first time in a later run still has a code. Compact cells
carry `s` and `d` integer indices. An out-of-range index fails closed on expansion.

- [ ] **Step 1: Write the failing test** — round-trip equality per vocabulary member; an out-of-range
  index raises; the vocabulary is the closed set, not the observed set.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement in `_compact`/`_expand_compact` and `expandCompact`.**
- [ ] **Step 4: Run both suites; commit**

```bash
git commit -m "perf(e0r2): T6.2 — intern state/decoded_reason as vocabulary indices (-77 MB)"
```

### Task 6.3: Normalize the icon catalog

**Files:**
- Modify: `coa_client_extract/spell_icons.py` (`iter_icon_catalog`, `icon_coverage`),
  `coa_client_extract/cli.py` (stage `coa_client_icon_assets.jsonl`),
  `coa_client_extract/publish.py` (`_verify_icon_row`, `_cross_child` asset-ref check),
  `coa_scraper/scripts/lib/generation.mjs`, and the icon consumer in `coa_meta/`
- Test: `tests/test_e0r2_icon_normalization.py`

**Design:** `coa_client_icon_assets.jsonl` holds one row per unique client path
(`{asset_id, client_path, source_asset_sha256, source_archive, schema_version}`); the per-spell child
becomes `{spell_id, spell_icon_id, asset_ref, asset_status, readiness, schema_version}` at
`coa-client-spell-icons-v2`. `asset_ref` is null exactly when `asset_status` is `placeholder`. The
cross-child check gains: every non-null `asset_ref` resolves to an asset row, and every asset row is
referenced at least once (no orphans).

- [ ] **Step 1: Write the failing test** — a dangling `asset_ref` is rejected; an orphan asset row is
  rejected; a `placeholder` row with a non-null `asset_ref` is rejected; `icon_coverage` still reports
  the same `resolved_paths`/`unique_paths` totals as the v1 catalog for the same input.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement, keeping the asset table streamed (accumulate `path -> asset_id` during the
  single catalog pass; the map is 14,022 entries, counter-scale).**
- [ ] **Step 4: Update the `coa_meta` icon consumer to resolve through the asset table.**
- [ ] **Step 5: Run both suites; commit**

```bash
git commit -m "perf(e0r2): T6.3 — normalize the icon catalog to unique assets + refs (-37 MB)"
```

### Task 6.4: Assert the headroom on a real measurement

**Files:**
- Modify: `coa_client_extract/data/spell_layout_v2.json` (`budget`), `coa_scraper/config/spell_layout.lock.json`
- Test: `tests/test_e0r2_headroom.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_e0r2_headroom.py
"""E0R.2 T6.4: E0R's exit condition is 'substantial E1 headroom'. 97.42% of ceiling is not headroom,
and raising the ceiling is not reducing the artifact. This asserts against the COMMITTED acceptance
record, so it fails if a future generation regresses."""
import json
from pathlib import Path

RECORD = Path(__file__).resolve().parents[1] / "reports/client_extract/coa_e0r_acceptance_summary.json"
TARGET = 0.75


def test_the_published_generation_leaves_e1_headroom():
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    budget = record["budget"]
    used = budget["whole_generation_bytes"] / budget["ceilings"]["max_whole_generation_bytes"]
    assert used <= TARGET, f"generation uses {used:.1%} of ceiling; E1 needs room below {TARGET:.0%}"
```

- [ ] **Step 2: This test stays RED until T8.1 produces the new record. That is intentional — it is the
  gate on the re-run, not on the refactor.** Note it in the tracker so a red run is not mistaken for a
  regression.
- [ ] **Step 3: Commit the test now; it turns green in WS8.**

```bash
git add tests/test_e0r2_headroom.py
git commit -m "test(e0r2): T6.4 — assert E1 headroom against the committed acceptance record"
```

---

# Workstream 7 — CI, hygiene, documentation

### Task 7.1: CI runs the specified suite; tracked reports carry no machine-local paths

**Files:**
- Modify: `.github/workflows/ci.yml:46-47`
- Create: `tests/test_e0r2_path_hygiene.py`

**Context:** CI runs `npm --prefix coa_scraper run unit-test`, but `npm test` is
`unit-test && validate` — so `validate-normalized.mjs` has never been a merge gate. Eight tracked files
contain `/home/archbug/...`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_path_hygiene.py
"""E0R.2 T7.1: a tracked artifact is a published artifact. Machine-local absolute paths leak the
author's filesystem layout into the repository and make records non-reproducible across machines."""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME_PATH = re.compile(r"/home/[a-z][a-z0-9_-]*/")


def _tracked(pattern):
    out = subprocess.check_output(["git", "ls-files", pattern], cwd=REPO, text=True)
    return [REPO / line for line in out.splitlines() if line]


def test_no_tracked_report_carries_a_machine_local_path():
    offenders = []
    for path in _tracked("reports/"):
        if HOME_PATH.search(path.read_text(encoding="utf-8", errors="replace")):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], f"machine-local paths in tracked reports: {offenders}"


def test_ci_runs_the_full_node_suite():
    ci = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "npm --prefix coa_scraper test" in ci
    assert "run unit-test" not in ci      # unit-test alone skips the validator
```

- [ ] **Step 2: Run and confirm both fail.**

- [ ] **Step 3: Fix CI, then make the producers emit repo-relative paths**

- `ci.yml`: `run: npm --prefix coa_scraper test`.
- The acceptance record, recon report, and generation manifests record paths relative to the repo root
  (`client_root`, `recon_report_path`, `effective_archive`, `patch_chain`). The client root lives
  *outside* the repo, so record it as its **basename plus a sha256 of the full path** — the identity is
  what matters for attribution, the absolute path is not. Add a small helper:

```python
def portable_path(path: Path, *, repo_root: Path) -> str:
    """A tracked artifact must not embed the author's filesystem. Inside the repo: a relative path.
    Outside it (the client install): the basename, which is the part that identifies the archive."""
    path = Path(path)
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return path.name
```

- Regenerate the tracked reports in WS8; do not hand-edit them.

- [ ] **Step 4: Run; commit**

```bash
git add .github/workflows/ci.yml coa_client_extract/artifacts.py coa_client_extract/cli.py \
        tests/test_e0r2_path_hygiene.py
git commit -m "fix(e0r2): T7.1 — CI runs npm test; tracked reports carry portable paths"
```

### Task 7.2: Documentation corrections

**Files:**
- Modify: `docs/ROADMAP.md` (lines 125, 131, 170, 183, 205, 212, 223, 289, 291),
  `docs/data/mechanics-schema.md` (lines 7, 22, 38, 175),
  `docs/superpowers/plans/2026-07-20-m1-14-e0r1-enforce-contract.md` (the T6.2 checkbox at line 188)

- [ ] **Step 1: `docs/ROADMAP.md`** — the M1.8/M1.10B/M1.11D milestone entries are history and stay,
  but each gains a one-line "superseded by M1.14E0R.1 (AscensionDB runtime deleted)" note. The
  *forward-looking* claims (line 170 "should link to its `db.ascension.gg` spell page", line 205 the
  disclaimer, line 212 "Extend AscensionDB scraping") are no longer true and are rewritten to the
  client-native reality.
- [ ] **Step 2: `docs/data/mechanics-schema.md`** — line 7 ("many fields are inferred from AscensionDB
  tooltips") and line 22 (`source_urls`) describe a retired schema; correct them to the three-tier
  client/Builder/inferred model already documented at line 270. Line 38's audit trio is likewise gone.
- [ ] **Step 3: E0R.1 tracker line 188** — the T6.2 checkbox claims the record "records
  icon/readiness/source coverage counts"; readiness and source had no producer. Correct the line to
  what shipped and point at E0R.2 T4.1.
- [ ] **Step 4: Commit**

```bash
git add docs/ROADMAP.md docs/data/mechanics-schema.md \
        docs/superpowers/plans/2026-07-20-m1-14-e0r1-enforce-contract.md
git commit -m "docs(e0r2): T7.2 — correct stale AscensionDB claims and the T6.2 coverage checkbox"
```

---

# Workstream 8 — real-client re-run and PR

### Task 8.1: Re-run recon, regenerate, canonical build, acceptance

**Files:** `reports/client_extract/` (regenerated artifacts), tracker

- [ ] **Step 1: Full local suite, both languages**

```bash
cd /home/archbug/projects/coacodex && python -m pytest -q && npm --prefix coa_scraper test
```

Then reproduce CI's packaging conditions — E0R.1 T6.1 found a defect that only bare `pytest` exposes:

```bash
python -P -m pytest -q
```

- [ ] **Step 2: Recon against the real client**

```bash
export COA_CLIENT_ROOT="/home/archbug/Games/ascension-wow/drive_c/Program Files/Ascension Launcher/resources/ascension-live/Data"
python -m coa_client_extract mechanics-recon --client-root "$COA_CLIENT_ROOT" --out reports/client_extract
```

Expect exit 0 (`verified`). **Exit 4 (`review_required`) is a legitimate outcome now that T3.1/T3.2
scan live** — if a numeric join collapsed to one candidate, stop and adjudicate; do not re-bind
mechanically to make the hold pass. If the *capture identity* drifted again (a client patch), follow the
E0R.1 precedent (`d549ac9`): advance only the per-table sha256/header + policy sha256 + Node lock, with
a script asserting the semantic policy view is byte-identical.

- [ ] **Step 3: Regenerate** (~11 min at the previous scale; run in the background and monitor by pid,
  not by `pgrep -f` — the E0R.1 run matched its own shell command line and reported a false "still
  running")

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

- [ ] **Step 5: Verify the headroom gate is now green**

```bash
python -m pytest tests/test_e0r2_headroom.py -q
```

Expected: PASS, with the record showing ≤75% of `max_whole_generation_bytes`. If it is over, the
remaining redundancy must be reduced — **do not raise the ceiling**.

- [ ] **Step 6: Commit the record and the regenerated reports**

```bash
git add reports/client_extract/coa_e0r_acceptance_summary.json \
        reports/client_extract/coa_spell_mechanics_recon.json
git commit -m "feat(e0r2): T8.1 — real-client acceptance record (bound, executed, verified)"
```

### Task 8.2: Push, update the PR, require green CI

- [ ] **Step 1: Push** `m1-14-e0r` (including the tracker-docs commit `02e0b7c` held back in E0R.1).
- [ ] **Step 2: Update PR #1's body** with an E0R.2 section: the seven blockers, the reproduction that
  is now red, and the measured size reduction.
- [ ] **Step 3: Wait for CI green on both the push and the pull_request runs.**
- [ ] **Step 4: Report to the user. Do NOT merge; do NOT start E1.**

---

## Out of scope, recorded deliberately

- **Description string dictionary.** Measured at ~8 MB of savings (descriptions are 22.4 MB inline and
  only 35% dedupable). Not worth a string-table child while the other three measures reach 55% of
  ceiling. Revisit if E1's artifacts push past 70%.
- **Recon generation-size forecast.** Recon has no basis for one (T3.3); publication measures the real
  thing exactly.
- **Actually adjudicating the three numeric joins.** The review's own longer-term item: "obtain
  controlled local-client/API anchors and actually adjudicate these joins." T3.1/T3.2 make the standing
  ambiguity *honest and drift-detecting*; they do not resolve it. Resolution needs admissible
  independent evidence that does not exist today under the anchor-evidence precedence — a controlled
  local client where a known spell's cast time can be read back, or a Builder payload field that
  explicitly encodes it. Neither is available, so the joins stay `raw_only` with null cells. This is the
  E1 blocker to schedule next, not an E0R.2 task.
- **The two guide-product findings** — heuristic build rankings presented as recommendations, and
  renderable (vs source) icon coverage. The review states both need not block E0R while the guide is
  unpublished/experimental. They are M1.16 product scope and belong in the ROADMAP, not this plan.
