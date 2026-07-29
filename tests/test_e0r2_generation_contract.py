"""E0R.2 T1.1: the generation contract is ONE versioned, SELF-VALIDATED document.

A name list cannot express cardinality, row schema, or shape — which is how a complete-but-EMPTY
generation passed both validators at 02e0b7c. The loader validates the contract itself: a malformed
contract is a broken gate, and a broken gate that loads is worse than no gate.

Contracts are IMMUTABLE, versioned registry files. A revision is written once and never edited; a change
means a new file. That is what keeps a generation published under an older revision independently
resolvable after WS6 moves `current` — including the predecessor the publish transaction chains to.
"""
from __future__ import annotations

import copy
import json
import re
import subprocess

import pytest

from coa_client_extract.contracts import (CONTRACTS_DIR, ContractError,
                                          GENERATION_CONTRACT_CHILD, GENERATION_CONTRACT_SCHEMA,
                                          generation_contract_sha256, load_contract_registry,
                                          load_current_contract, load_observation_wire_schema,
                                          load_supported_contract, validate_contract_registry,
                                          validate_generation_contract)
from coa_client_extract.publish import (CURRENT_REQUIRED_CHILDREN, REQUIRED_CHILDREN, ResolveError,
                                        required_children_for, validate_candidate_generation)

from tests._e0r2_fixtures import stage_minimal_generation

_DIR_REL = "coa_client_extract/data/generation_contracts"
_REGISTRY_REL = f"{_DIR_REL}/index.json"


def _all_supported_contracts():
    registry = load_contract_registry()
    return [(revision, load_supported_contract(revision, entry["sha256"]))
            for revision, entry in registry["supported"].items()]


def _paths_supported_before(base: str) -> set[str]:
    """The revision files that were already PUBLISHED at the merge base. A revision file added on this
    branch may still be edited; one that existed upstream may not."""
    proc = subprocess.run(["git", "show", f"{base}:{_REGISTRY_REL}"], capture_output=True, text=True)
    if proc.returncode != 0:
        return set()          # no registry upstream yet — nothing had been published to freeze
    return {f"{_DIR_REL}/{entry['path']}" for entry in json.loads(proc.stdout)["supported"].values()}


# --- the contract document itself ---

def test_contract_covers_exactly_the_required_children():
    revision, contract = load_current_contract()
    assert contract["schema_version"] == GENERATION_CONTRACT_SCHEMA
    assert contract["revision"] == revision
    assert set(contract["children"]) == set(REQUIRED_CHILDREN)


def test_the_contract_is_itself_a_child_of_the_generation():
    """The twelfth child. A contract that is not staged alongside the generation it governs cannot be
    re-checked by a consumer, which is the whole point of binding it."""
    _, contract = load_current_contract()
    assert GENERATION_CONTRACT_CHILD in contract["children"]
    spec = contract["children"][GENERATION_CONTRACT_CHILD]
    assert spec["kind"] == "json"
    assert spec["child_schema_version"] == GENERATION_CONTRACT_SCHEMA
    assert spec["optional"] is False


def test_every_child_declares_kind_schema_cardinality_and_shape():
    for name, spec in load_current_contract()[1]["children"].items():
        assert spec["kind"] in ("jsonl", "json"), name
        assert spec["child_schema_version"], name
        assert spec["shape"], name
        assert spec["cardinality"]["rule"], name
        if spec["kind"] == "jsonl":
            assert spec["row_schema_version"], name
        else:
            assert spec["row_schema_version"] is None, name


def test_no_child_uses_a_bare_floor_where_a_source_count_exists():
    """A floor of 1 admits a one-spell generation — and equally a one-class-type generation, which is
    useless for a class guide. Every child whose source-domain count is derivable must derive it."""
    children = load_current_contract()[1]["children"]
    assert children["coa_client_spell.jsonl"]["cardinality"]["rule"] == "reviewed_bound_record_count"
    assert children["coa_client_spell_icons.jsonl"]["cardinality"]["rule"] == "equals_full_spell_records"
    assert children["coa_client_spell_coa.jsonl"]["cardinality"]["rule"] == "equals_is_coa_full_records"
    for name in ("coa_client_class_types.jsonl", "coa_client_tab_types.jsonl",
                 "coa_client_essence.jsonl"):
        assert children[name]["cardinality"]["rule"] == "derived_from_source_topology", name
    assert children["coa_client_advancement.jsonl"]["cardinality"]["rule"] == "declared_derivation"
    # Content has no WDBC source at all — five JSON files, bound by T0.2's content_sources block.
    assert children["coa_client_content.jsonl"]["cardinality"]["rule"] == "declared_content_derivation"
    assert not any(spec["cardinality"]["rule"] == "min" for spec in children.values())


def test_every_source_table_the_contract_cites_is_bound_by_the_policy():
    """T0.2 exists so this holds with NO placeholder: a cardinality rule that names a table the reviewed
    policy does not bind is a rule that can never be evaluated."""
    from coa_client_extract.spell_layout import load_default_policy

    bound = set(load_default_policy().doc["bound"]["tables"])
    for name, spec in load_current_contract()[1]["children"].items():
        table = spec["cardinality"].get("source_table")
        if table is not None:
            assert table in bound, f"{name} cites unbound source table {table!r}"


def test_the_contract_pins_the_observation_wire_schema_in_use():
    """T0.1's wire codes are serialized by T6.2. Pinning the wire schema by canonical digest makes an
    edit to it break every published contract — which is what IMMUTABLE has to mean operationally."""
    for revision, doc in _all_supported_contracts():
        wire = doc["observation_wire_schema"]
        assert wire["schema_version"] == "coa-observation-wire-v1", revision
        assert wire["sha256"] == generation_contract_sha256(load_observation_wire_schema()), revision


def test_no_contract_revision_contains_a_placeholder():
    """An immutable file with a TODO in it is a file that will be edited."""
    for revision, doc in _all_supported_contracts():
        blob = json.dumps(doc)
        assert not re.search(r"<[^>]*(from|TODO|captured|placeholder)[^>]*>", blob), revision


@pytest.mark.parametrize("mutate, match", [
    (lambda d: d.update(schema_version="nope"), "schema_version"),
    (lambda d: d.update(smuggled_top_level=1), "smuggled_top_level"),
    (lambda d: d.update(revision=""), "revision"),
    (lambda d: d.update(observation_wire_schema={}), "observation wire schema"),
    (lambda d: d.update(children={}), "no children"),
    (lambda d: d["children"]["spell_layout_v2.json"].update(kind="parquet"), "kind"),
    (lambda d: d["children"]["spell_layout_v2.json"].update(shape=""), "shape"),
    (lambda d: d["children"]["spell_layout_v2.json"].update(unexpected_key=1), "unexpected_key"),
    (lambda d: d["children"]["spell_layout_v2.json"].pop("optional"), "missing"),
    (lambda d: d["children"]["spell_layout_v2.json"].update(optional="yes"), "optional"),
    (lambda d: d["children"]["coa_client_spell.jsonl"].update(row_schema_version=None),
     "row_schema_version"),
    (lambda d: d["children"]["spell_layout_v2.json"].update(row_schema_version="x"),
     "row_schema_version"),
    (lambda d: d["children"].update(dupe=copy.deepcopy(d["children"]["spell_layout_v2.json"])), "shape"),
    (lambda d: d["children"].update(**{"../escape.json": d["children"]["spell_layout_v2.json"]}),
     "child name"),
    (lambda d: d["children"].update(**{"sub/dir.json": d["children"]["spell_layout_v2.json"]}),
     "child name"),
    (lambda d: d["children"]["coa_client_content.jsonl"]["cardinality"].update(min=True), "min"),
    (lambda d: d["children"]["coa_client_content.jsonl"]["cardinality"].update(min=-1), "min"),
    (lambda d: d["children"]["coa_client_content.jsonl"]["cardinality"].update(unexpected=1),
     "cardinality"),
    (lambda d: d["children"]["coa_client_content.jsonl"]["cardinality"].update(rule="invented"), "rule"),
    (lambda d: d["children"]["spell_layout_v2.json"].update(cardinality={"rule": "single_document",
                                                                        "source_table": "Spell"}),
     "cardinality"),
    (lambda d: d["children"]["coa_client_advancement.jsonl"]["cardinality"].update(source_table=""),
     "source_table"),
])
def test_the_loader_rejects_a_malformed_contract(mutate, match):
    doc = copy.deepcopy(load_current_contract()[1])
    mutate(doc)
    with pytest.raises(ContractError, match=match):
        validate_generation_contract(doc)


def test_the_current_contract_is_accepted_unmodified():
    """The negative matrix above is only meaningful if the real document passes."""
    _, doc = load_current_contract()
    assert validate_generation_contract(copy.deepcopy(doc))["revision"] == doc["revision"]


@pytest.mark.parametrize("floor, ok", [(1, True), (5, True), (0, False), (-1, False), (True, False),
                                       (1.0, False), ("5", False)])
def test_an_explicit_floor_needs_a_positive_non_boolean_integer(floor, ok):
    """`min` is reserved for a future ancillary dataset with no derivable source count. It is validated
    now because `isinstance(True, int)` is True in Python — a boolean floor must never mean 1."""
    doc = copy.deepcopy(load_current_contract()[1])
    doc["children"]["coa_client_content.jsonl"]["cardinality"] = {"rule": "min", "min": floor}
    if ok:
        assert validate_generation_contract(doc)
    else:
        with pytest.raises(ContractError, match="min"):
            validate_generation_contract(doc)


def test_the_contract_hash_is_canonical_and_stable():
    _, doc = load_current_contract()
    reordered = {"children": doc["children"], "schema_version": doc["schema_version"],
                 **{k: v for k, v in doc.items() if k not in ("children", "schema_version")}}
    assert generation_contract_sha256(doc) == generation_contract_sha256(reordered)
    assert len(generation_contract_sha256(doc)) == 64


# --- the registry ---

def test_the_registry_pins_every_supported_revision_by_hash():
    registry = load_contract_registry()
    for revision, entry in registry["supported"].items():
        doc = load_supported_contract(revision, entry["sha256"])
        assert generation_contract_sha256(doc) == entry["sha256"]


def test_an_unsupported_or_tampered_revision_is_refused():
    with pytest.raises(ContractError, match="unsupported"):
        load_supported_contract("e0r-v99", "0" * 64)
    revision = load_contract_registry()["current"]
    with pytest.raises(ContractError, match="sha256"):
        load_supported_contract(revision, "0" * 64)


def test_the_registry_itself_is_validated():
    registry = load_contract_registry()
    assert registry["current"] in registry["supported"]
    for revision, entry in registry["supported"].items():
        assert set(entry) == {"path", "sha256"}
        assert re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.json", entry["path"]), entry["path"]
        assert len(entry["sha256"]) == 64


@pytest.mark.parametrize("mutate, match", [
    (lambda d: d.update(schema_version="nope"), "schema_version"),
    (lambda d: d.update(current="e0r-v99"), "current"),
    (lambda d: d.update(supported={}), "supported"),
    (lambda d: d.update(smuggled=1), "smuggled"),
    (lambda d: d["supported"]["e0r-v1"].update(extra=1), "extra"),
    (lambda d: d["supported"]["e0r-v1"].update(path="../escape.json"), "path"),
    (lambda d: d["supported"]["e0r-v1"].update(path="sub/dir.json"), "path"),
    (lambda d: d["supported"]["e0r-v1"].update(sha256="short"), "sha256"),
])
def test_a_malformed_registry_is_refused(mutate, match):
    doc = copy.deepcopy(load_contract_registry())
    mutate(doc)
    with pytest.raises(ContractError, match=match):
        validate_contract_registry(doc)


# --- immutability ---

def test_every_revision_file_still_hashes_to_its_pinned_digest():
    """PRIMARY immutability check, and the one that ALWAYS runs. `git log --name-only` was an earlier
    draft's approach; CI checks out at fetch-depth 1, so that command returns almost nothing and the test
    would have passed VACUOUSLY in exactly the environment it was meant to guard. Runtime hash pinning
    needs no history at all."""
    registry = load_contract_registry()
    for revision, entry in registry["supported"].items():
        doc = json.loads((CONTRACTS_DIR / entry["path"]).read_text(encoding="utf-8"))
        assert generation_contract_sha256(doc) == entry["sha256"], (
            f"{revision} was edited in place; add a new revision instead of changing a published one")
        assert doc["revision"] == revision, f"{revision} disagrees with its registry key"


def test_no_revision_file_is_modified_relative_to_the_merge_base():
    """SECONDARY check: catches an edit-plus-rehash, which the hash pin alone cannot see. Requires
    history, so T7.1 sets fetch-depth: 0 in CI. FAILS (never skips) when the merge base is unavailable —
    a guard that quietly opts out is the defect this replaces."""
    base = subprocess.run(["git", "merge-base", "HEAD", "origin/main"], capture_output=True, text=True)
    assert base.returncode == 0, (
        "merge base unavailable — run with full history (CI: fetch-depth: 0); refusing to pass vacuously")
    base = base.stdout.strip()
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", base, "--", _DIR_REL], text=True).split()
    frozen = _paths_supported_before(base)
    edited = sorted(p for p in changed if p in frozen)
    assert edited == [], f"published contract revision(s) modified: {edited}"


# --- adoption: the registry is operational, not descriptive ---

def test_required_children_is_derived_from_the_current_contract():
    assert REQUIRED_CHILDREN is CURRENT_REQUIRED_CHILDREN
    assert CURRENT_REQUIRED_CHILDREN == tuple(sorted(load_current_contract()[1]["children"]))
    assert GENERATION_CONTRACT_CHILD in CURRENT_REQUIRED_CHILDREN


def test_required_children_for_reads_the_generations_own_contract():
    """A RESOLVER's requirement comes from the generation's own verified staged contract, never from
    `current`. Deriving it from `current` makes every generation published under an older revision
    unresolvable the moment a new revision ships — breaking rollback and the predecessor chain."""
    _, contract = load_current_contract()
    older = copy.deepcopy(contract)
    older["children"] = {k: v for k, v in contract["children"].items()
                         if k in (GENERATION_CONTRACT_CHILD, "spell_layout_v2.json")}
    assert required_children_for(older) == (GENERATION_CONTRACT_CHILD, "spell_layout_v2.json")
    assert required_children_for(contract) == CURRENT_REQUIRED_CHILDREN


def test_an_optional_child_is_not_required():
    _, contract = load_current_contract()
    relaxed = copy.deepcopy(contract)
    relaxed["children"]["coa_client_essence.jsonl"]["optional"] = True
    assert "coa_client_essence.jsonl" not in required_children_for(relaxed)


def test_a_candidate_without_the_staged_contract_is_rejected(tmp_path):
    gen_dir = stage_minimal_generation(tmp_path, drop_contract=True)
    with pytest.raises(ResolveError, match=GENERATION_CONTRACT_CHILD):
        validate_candidate_generation(gen_dir)


def test_a_complete_candidate_with_the_staged_contract_passes(tmp_path):
    resolved = validate_candidate_generation(stage_minimal_generation(tmp_path))
    assert set(resolved["children"]) == set(CURRENT_REQUIRED_CHILDREN)


def test_a_staged_contract_outside_the_registry_is_rejected(tmp_path):
    """The staged child is UNTRUSTED input. Deriving the required-child set from it without checking it
    against the trusted registry would let a tampered contract declare its own (empty) requirements."""
    gen_dir = stage_minimal_generation(tmp_path, contract_mutate=lambda d: d.update(revision="e0r-v99"))
    with pytest.raises(ResolveError, match="unsupported"):
        validate_candidate_generation(gen_dir)


def test_a_tampered_staged_contract_is_rejected(tmp_path):
    """Same revision, altered body — the canonical digest no longer matches the registry pin."""
    def _drop_a_child(doc):
        doc["children"].pop("coa_client_essence.jsonl")

    gen_dir = stage_minimal_generation(tmp_path, contract_mutate=_drop_a_child)
    with pytest.raises(ResolveError, match="sha256"):
        validate_candidate_generation(gen_dir)


def test_a_structurally_broken_staged_contract_is_rejected(tmp_path):
    gen_dir = stage_minimal_generation(tmp_path, contract_mutate=lambda d: d.update(children="nope"))
    with pytest.raises(ResolveError, match="contract"):
        validate_candidate_generation(gen_dir)
