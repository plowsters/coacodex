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


def generation_contract_binding() -> dict:
    """The `binding` fragment identifying the staged contract. A producer records it so a consumer can
    tell WHICH revision governed the generation without trusting the staged bytes."""
    revision, contract = load_current_contract()
    return {"generation_contract": {"schema_version": GENERATION_CONTRACT_SCHEMA,
                                    "revision": revision,
                                    "sha256": generation_contract_sha256(contract)}}


def stage_generation_contract(gw: GenerationWriter, *, mutate=None) -> None:
    """Stage the contract child. `mutate` (tests only) alters the staged copy so the validator's
    registry dispatch can be exercised against a tampered or unsupported document."""
    contract = copy.deepcopy(load_current_contract()[1])
    if mutate is not None:
        mutate(contract)
    gw.add_json(GENERATION_CONTRACT_CHILD, contract, schema_version=GENERATION_CONTRACT_SCHEMA)


def stage_minimal_generation(root, *, drop_contract: bool = False, contract_mutate=None):
    """A complete-but-empty staged CANDIDATE: every required child present, the three spell children
    empty so the cross-child merge-join is trivially satisfied, and a real policy child so `_cross_child`
    can load it. Returns the generation directory.

    This shape is exactly the one that passed both validators at 02e0b7c while carrying zero spells —
    it stays useful here precisely because WS2 is what makes it stop passing."""
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
    if not drop_contract:
        stage_generation_contract(gw, mutate=contract_mutate)
    gw.publish_candidate(base_manifest={}, binding=generation_contract_binding())
    return gw.gen_dir
