"""E0R.2 T1.2: a contract read from the working tree is not BOUND to the generation.

Without a binding, a generation produced under contract A could later be validated under contract B —
whichever happened to be checked out. So the contract is staged as a child, hashed into
`manifest.binding.generation_contract`, and covered by `candidate_trust_sha256` (`binding` is already
inside TRUST_CRITICAL_MANIFEST_KEYS, so the digest definition needs no change).

Validation compares THREE things, and all three must agree:

  1. the STAGED child's canonical digest,
  2. the digest and revision the manifest BINDING names,
  3. a revision in the validator's OWN supported registry.

The third is set MEMBERSHIP, not equality with `current`. That distinction is what keeps a generation
published under an older revision resolvable after WS6 adds `e0r-v2` and moves `current` — without it,
rollback and the predecessor chain the publish transaction reads both break the moment a revision ships.

T1.1 landed legs 1 and 3 (registry dispatch, so the required-child set is never derived from unverified
staged bytes). This module adds leg 2 and the systematic rejection matrix.
"""
from __future__ import annotations

import copy
import json

import pytest

from coa_client_extract import contracts as contracts_mod
from coa_client_extract.contracts import (GENERATION_CONTRACT_CHILD, GENERATION_CONTRACT_SCHEMA,
                                          generation_contract_sha256, load_current_contract)
from coa_client_extract.publish import (MANIFEST_NAME, ResolveError, candidate_trust_sha256,
                                        validate_candidate_generation)

from tests._e0r2_fixtures import stage_minimal_generation


@pytest.fixture(autouse=True)
def _isolate_registry_cache():
    """The registry and contract docs are cached module globals (they are frozen data files read per
    publish/resolve). A test that repoints CONTRACTS_DIR must not leak into the next one."""
    yield
    contracts_mod._REGISTRY_CACHE = None
    contracts_mod._CONTRACT_CACHE.clear()


def _manifest(gen_dir):
    return json.loads((gen_dir / MANIFEST_NAME).read_text(encoding="utf-8"))


def _rewrite_manifest(gen_dir, manifest, *, resign: bool = False):
    """Rewrite a candidate manifest. `resign` re-computes the trust digest so a test can reach the
    contract checks instead of tripping the trust digest first."""
    if resign:
        manifest["candidate_trust_sha256"] = candidate_trust_sha256(manifest)
    (gen_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# --- the binding exists and describes the staged child ---

def test_the_contract_is_staged_as_a_child_and_bound_in_the_manifest(tmp_path):
    gen = stage_minimal_generation(tmp_path)
    revision, doc = load_current_contract()
    bound = _manifest(gen)["binding"]["generation_contract"]
    assert bound["schema_version"] == GENERATION_CONTRACT_SCHEMA
    assert bound["revision"] == revision
    assert bound["sha256"] == generation_contract_sha256(doc)
    assert (gen / GENERATION_CONTRACT_CHILD).is_file()


# That the REAL producer binds what it stages is proven end-to-end by the existing regenerate tests
# (tests/test_client_extract_cli.py, tests/test_e0r1_transaction.py): once the binding leg below is
# enforced, a regenerate that staged one contract and bound another could not resolve at all.


def test_a_valid_generation_still_passes(tmp_path):
    """The rejection matrix below is only meaningful if the honest case is accepted."""
    assert validate_candidate_generation(stage_minimal_generation(tmp_path))["manifest"]


# --- leg 2: the staged child must match the binding ---

def test_a_staged_contract_that_differs_from_the_bound_hash_is_rejected(tmp_path):
    """The generation's own claim about which contract governed it must match the bytes it shipped."""
    _, doc = load_current_contract()
    gen = stage_minimal_generation(
        tmp_path,
        bind_override={"schema_version": GENERATION_CONTRACT_SCHEMA, "revision": doc["revision"],
                       "sha256": "0" * 64})
    with pytest.raises(ResolveError, match="generation_contract"):
        validate_candidate_generation(gen)


def test_a_binding_naming_a_different_revision_than_the_staged_child_is_rejected(tmp_path):
    """Digest agreement alone is not enough: a binding that names revision B while shipping revision A
    would let a consumer record the wrong provenance for a generation that otherwise validates."""
    _, doc = load_current_contract()
    gen = stage_minimal_generation(
        tmp_path,
        bind_override={"schema_version": GENERATION_CONTRACT_SCHEMA, "revision": "e0r-v99",
                       "sha256": generation_contract_sha256(doc)})
    with pytest.raises(ResolveError, match="revision"):
        validate_candidate_generation(gen)


def test_a_binding_with_the_wrong_schema_version_is_rejected(tmp_path):
    _, doc = load_current_contract()
    gen = stage_minimal_generation(
        tmp_path,
        bind_override={"schema_version": "coa-generation-contract-v99", "revision": doc["revision"],
                       "sha256": generation_contract_sha256(doc)})
    with pytest.raises(ResolveError, match="schema_version"):
        validate_candidate_generation(gen)


@pytest.mark.parametrize("bound", [
    {},
    {"revision": "e0r-v1"},
    {"schema_version": GENERATION_CONTRACT_SCHEMA, "revision": "e0r-v1"},
    {"schema_version": GENERATION_CONTRACT_SCHEMA, "sha256": "0" * 64},
    "not-an-object",
    [],
])
def test_an_incomplete_binding_is_rejected(tmp_path, bound):
    gen = stage_minimal_generation(tmp_path, bind_override=bound)
    with pytest.raises(ResolveError, match="generation_contract"):
        validate_candidate_generation(gen)


def test_a_generation_with_no_binding_block_at_all_is_rejected(tmp_path):
    gen = stage_minimal_generation(tmp_path, drop_binding=True)
    with pytest.raises(ResolveError, match="generation_contract"):
        validate_candidate_generation(gen)


# --- leg 3: registry membership, dispatched by hash ---

def test_a_generation_bound_to_an_unsupported_contract_is_rejected(tmp_path):
    """Both the staged child AND the binding say revision B; B is not in the supported registry."""
    gen = stage_minimal_generation(tmp_path,
                                   contract_mutate=lambda d: d.update(revision="made-up-v9"))
    with pytest.raises(ResolveError, match="unsupported"):
        validate_candidate_generation(gen)


def test_a_staged_contract_edited_under_a_supported_revision_is_rejected(tmp_path):
    """Same revision, altered body, binding updated to match — only the registry pin catches this."""
    gen = stage_minimal_generation(
        tmp_path, contract_mutate=lambda d: d["children"].pop("coa_client_essence.jsonl"))
    with pytest.raises(ResolveError, match="sha256"):
        validate_candidate_generation(gen)


def test_a_structurally_broken_staged_contract_is_rejected_before_dispatch(tmp_path):
    """A malformed contract must fail as malformed, not as a hash mismatch — the operator needs to know
    which problem they have."""
    gen = stage_minimal_generation(tmp_path,
                                   contract_mutate=lambda d: d["children"].update(bad="nope"))
    with pytest.raises(ResolveError, match="spec must be an object"):
        validate_candidate_generation(gen)


def test_a_staged_contract_that_is_not_json_is_rejected(tmp_path):
    gen = stage_minimal_generation(tmp_path)
    (gen / GENERATION_CONTRACT_CHILD).write_text("{not json", encoding="utf-8")
    with pytest.raises(ResolveError, match="not valid JSON"):
        validate_candidate_generation(gen)


# --- candidate trust covers the binding ---

def test_candidate_trust_covers_the_bound_contract_hash(tmp_path):
    """Rewriting the bound hash without restaging breaks the trust digest — the binding cannot be edited
    after the fact even to a value the staged child would satisfy."""
    gen = stage_minimal_generation(tmp_path)
    manifest = _manifest(gen)
    manifest["binding"]["generation_contract"]["sha256"] = "0" * 64
    _rewrite_manifest(gen, manifest)
    with pytest.raises(ResolveError, match="candidate_trust_sha256"):
        validate_candidate_generation(gen)


# --- the property the whole design exists for: an OLDER supported revision still resolves ---

def _install_two_revision_registry(tmp_path, monkeypatch):
    """A real second revision on disk, with `current` moved to it. Nothing is faked: both files are
    authored, validated and hash-pinned exactly as the shipped registry is."""
    _, v1 = load_current_contract()
    v1 = copy.deepcopy(v1)
    v2 = copy.deepcopy(v1)
    v2["revision"] = "e0r-v2"
    v2["note"] = "IMMUTABLE. Successor revision used to prove an older revision stays resolvable."

    contracts_dir = tmp_path / "generation_contracts"
    contracts_dir.mkdir(parents=True)
    for doc, name in ((v1, "e0r-v1.json"), (v2, "e0r-v2.json")):
        (contracts_dir / name).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    (contracts_dir / "index.json").write_text(json.dumps({
        "schema_version": "coa-generation-contract-index-v1",
        "current": "e0r-v2",
        "supported": {
            "e0r-v1": {"path": "e0r-v1.json", "sha256": generation_contract_sha256(v1)},
            "e0r-v2": {"path": "e0r-v2.json", "sha256": generation_contract_sha256(v2)},
        },
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr(contracts_mod, "CONTRACTS_DIR", contracts_dir)
    contracts_mod._REGISTRY_CACHE = None
    contracts_mod._CONTRACT_CACHE.clear()
    return v1, v2


def test_a_generation_under_a_NON_CURRENT_but_supported_revision_still_validates(tmp_path, monkeypatch):
    """Rollback and predecessor-chain resolution depend on this: WS6 adds e0r-v2 and moves `current`,
    and every generation published under e0r-v1 must remain independently resolvable."""
    v1, _ = _install_two_revision_registry(tmp_path / "registry", monkeypatch)
    assert load_current_contract()[0] == "e0r-v2"          # the generation below is NOT under `current`

    gen = stage_minimal_generation(tmp_path / "dist", contract=("e0r-v1", v1))
    resolved = validate_candidate_generation(gen)
    assert resolved["manifest"]["binding"]["generation_contract"]["revision"] == "e0r-v1"


def test_a_revision_dropped_from_the_registry_stops_resolving(tmp_path, monkeypatch):
    """The converse: membership is what is checked, so removing a revision is a real, visible decision
    rather than a silent one."""
    v1, _ = _install_two_revision_registry(tmp_path / "registry", monkeypatch)
    gen = stage_minimal_generation(tmp_path / "dist", contract=("e0r-v1", v1))

    index_path = contracts_mod.CONTRACTS_DIR / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["supported"].pop("e0r-v1")
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    contracts_mod._REGISTRY_CACHE = None
    contracts_mod._CONTRACT_CACHE.clear()

    with pytest.raises(ResolveError, match="unsupported"):
        validate_candidate_generation(gen)
