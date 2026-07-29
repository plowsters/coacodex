"""Shared E0R.2 generation-fixture helpers.

Every synthetic generation now carries a TWELFTH child — `generation_contract.json`, the immutable
registry revision the generation was produced under — plus the `binding.generation_contract` that
identifies it by revision and canonical digest. Seven test modules build candidates; keeping the staging
in one place is what stops them drifting apart as WS6 adds revisions (T1.1).
"""
from __future__ import annotations

import copy
import json

from coa_client_extract.contracts import (GENERATION_CONTRACT_CHILD, GENERATION_CONTRACT_SCHEMA,
                                          generation_contract_sha256, load_current_contract)
from coa_client_extract.publish import GenerationWriter

from tests._spell_fixtures import v2_policy


def generation_contract_binding(contract=None) -> dict:
    """The `binding` fragment identifying the staged contract. A producer records it so a consumer can
    tell WHICH revision governed the generation without trusting the staged bytes.

    `contract` is a (revision, doc) pair; it defaults to the current revision. It describes whatever was
    actually STAGED — binding a document other than the staged one is a desynchronization a test opts
    into explicitly (`bind_override`), never a fixture default. Keeping the two in step by default is
    what lets the binding leg and the registry leg be exercised one at a time."""
    revision, doc = contract if contract is not None else load_current_contract()
    return {"generation_contract": {"schema_version": GENERATION_CONTRACT_SCHEMA,
                                    "revision": revision,
                                    "sha256": generation_contract_sha256(doc)}}


def staged_contract_doc(*, contract=None, mutate=None) -> tuple[str, dict]:
    """The (revision, doc) a fixture will stage. `mutate` (tests only) alters the copy so the validator
    can be exercised against a tampered, structurally broken, or unsupported document."""
    revision, doc = contract if contract is not None else load_current_contract()
    doc = copy.deepcopy(doc)
    if mutate is not None:
        mutate(doc)
    return (doc.get("revision", revision) if isinstance(doc, dict) else revision), doc


def stage_generation_contract(gw: GenerationWriter, *, mutate=None, contract=None) -> tuple[str, dict]:
    """Stage the contract child; returns the (revision, doc) actually written."""
    revision, doc = staged_contract_doc(contract=contract, mutate=mutate)
    gw.add_json(GENERATION_CONTRACT_CHILD, doc, schema_version=GENERATION_CONTRACT_SCHEMA)
    return revision, doc


def stage_minimal_generation(root, *, drop_contract: bool = False, contract_mutate=None,
                             contract=None, bind_override=None, drop_binding: bool = False):
    """A complete-but-empty staged CANDIDATE: every required child present, the three spell children
    empty so the cross-child merge-join is trivially satisfied, and a real policy child so `_cross_child`
    can load it. Returns the generation directory.

    This shape is exactly the one that passed both validators at 02e0b7c while carrying zero spells —
    it stays useful here precisely because WS2 is what makes it stop passing.

    Contract knobs, each isolating ONE leg of the three-way check (T1.2):
      * `contract`      — stage and bind an explicit (revision, doc) instead of `current`
      * `contract_mutate` — tamper the STAGED copy; the binding follows it, so the registry leg fires
      * `bind_override` — desynchronize the binding from the staged copy, so the binding leg fires
      * `drop_binding` / `drop_contract` — omit the binding block / the child entirely
    """
    gw = GenerationWriter(root)
    gw.add_jsonl("coa_client_spell.jsonl", [], schema_version="coa-client-spell-v3")
    gw.add_jsonl("coa_client_spell_coa.jsonl", [], schema_version="coa-client-spell-projection-v3")
    gw.add_jsonl("coa_client_spell_icons.jsonl", [], schema_version="coa-client-spell-icons-v1")
    gw.add_json("coa_client_spell_projection.manifest.json",
                {"schema_version": "coa-client-spell-projection-manifest-v3"},
                schema_version="coa-client-spell-projection-manifest-v3")
    for name in ("coa_client_content.jsonl", "coa_client_advancement.jsonl",
                 "coa_client_class_types.jsonl", "coa_client_tab_types.jsonl",
                 "coa_client_essence.jsonl"):
        gw.add_jsonl(name, [], schema_version="coa-client-misc-v1")
    gw.add_json("coa_client_archive_plan.json", {"schema_version": "coa-client-archive-plan-v1"},
                schema_version="coa-client-archive-plan-v1")
    gw.add_json("spell_layout_v2.json", json.loads(json.dumps(v2_policy().doc)),
                schema_version="coa-spell-layout-v2")
    binding: dict = {}
    if not drop_contract:
        staged = stage_generation_contract(gw, mutate=contract_mutate, contract=contract)
        binding = generation_contract_binding(staged)
    elif contract is not None:
        binding = generation_contract_binding(contract)
    if bind_override is not None:
        binding = {"generation_contract": bind_override}
    if drop_binding:
        binding = {}
    gw.publish_candidate(base_manifest={}, binding=binding)
    return gw.gen_dir
