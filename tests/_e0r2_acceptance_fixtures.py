"""Shared acceptance fixtures for E0R.2 WS4 — a published generation, a recon report bound to it, and a
canonical build that really runs.

Extracted from tests/test_e0r1_acceptance_binding.py when T4.2 folded the build executor inside
`run_acceptance`: both suites stage the same generation and would otherwise drift apart.

T4.3 made the fixture honest twice over. The generation is now a fully BOUND one (a policy sized to what
it stages, a `binding.topology` matching it facet-for-facet), because acceptance now compares a canonical
identity digest computed from the recon report against the same digest computed from `binding` — a
generation bound to `{"policy_sha256": "abc123"}` cannot exercise that at all. And the build is executed
by a stand-in `node` (tests/_fake_node_build.py) rather than a substituted executor, because the checks
T4.3 adds are about the ARTIFACTS the build leaves on disk; an executor that writes nothing can only ever
reach the measurement gate.

Every knob breaks exactly ONE correspondence between the recon, the generation and the build.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

from coa_client_extract.publish import GenerationWriter
from coa_client_extract.spell_mechanics import SCHEMA as RECON_SCHEMA
from tests._e0r2_fixtures import (GENEROUS_CEILINGS, clean_budget, generation_contract_binding,
                                  stage_generation_contract, staged_writer)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Generation-manifest coverage: the two facts that are GENERATION properties (T4.1). Acceptance now fails
# closed on either being absent rather than recording `{}`.
BASE_MANIFEST = {
    "icon_coverage": {"spells": 3, "resolved_paths": 3, "placeholder": 0},
    "observation_coverage": {"schema_version": "coa-client-observation-coverage-v1", "rows": 3,
                             "cells": 12, "states": {"present": 12},
                             "decoded_reasons": {"decoded": 12}, "fields": {}},
}

# 4 entries, 3 unique spell ids — so "record_count == unique builder spell ids" is a real identity here
# rather than one a line count would satisfy by accident.
BUILDER_ENTRIES = [{"entry_id": 1, "spell_id": 101, "name": "Alpha"},
                   {"entry_id": 2, "spell_id": 102, "name": "Beta"},
                   {"entry_id": 3, "spell_id": 102, "name": "Beta (rank 2)"},
                   {"entry_id": 4, "spell_id": 103, "name": "Gamma"}]
BUILDER_UNIQUE_SPELL_IDS = 3


def stage_minimal(root) -> GenerationWriter:
    """A generation with every required child but no bound policy — used only where the test is about
    something upstream of the T4.3 identity check."""
    gw = GenerationWriter(root)
    gw.add_jsonl("coa_client_spell.jsonl", [], schema_version="coa-client-spell-v3")
    gw.add_jsonl("coa_client_spell_coa.jsonl", [], schema_version="coa-client-spell-projection-v3")
    gw.add_json("coa_client_spell_projection.manifest.json",
                {"schema_version": "coa-client-spell-projection-manifest-v3"},
                schema_version="coa-client-spell-projection-manifest-v3")
    gw.add_jsonl("coa_client_spell_icons.jsonl", [], schema_version="coa-client-spell-icons-v1")
    for name in ("coa_client_content.jsonl", "coa_client_advancement.jsonl", "coa_client_class_types.jsonl",
                 "coa_client_tab_types.jsonl", "coa_client_essence.jsonl"):
        gw.add_jsonl(name, [], schema_version="coa-client-misc-v1")
    gw.add_json("coa_client_archive_plan.json", {"schema_version": "coa-client-archive-plan-v1"},
                schema_version="coa-client-archive-plan-v1")
    gw.add_json("spell_layout_v2.json", {"schema_version": "coa-spell-layout-v2"},
                schema_version="coa-spell-layout-v2")
    stage_generation_contract(gw)
    return gw


def publish(root, *, base_manifest=None) -> GenerationWriter:
    gw = stage_minimal(root)
    candidate = gw.publish_candidate(base_manifest=base_manifest or {},
                                     binding={"policy_sha256": "abc123",
                                              **generation_contract_binding()})
    gw.finalize_and_publish(candidate_manifest=candidate,
                            validation={"python": True, "node": True},
                            budget=clean_budget(GENEROUS_CEILINGS))
    return gw


def publish_bound(root, *, base_manifest=None, drop_manifest_keys=()) -> Path:
    """A published generation whose `binding` carries a real policy digest and a real topology."""
    manifest = {k: copy.deepcopy(v) for k, v in {**BASE_MANIFEST, **(base_manifest or {})}.items()
                if k not in set(drop_manifest_keys)}
    gw, candidate, ceilings = staged_writer(root, base_manifest=manifest)
    gw.finalize_and_publish(candidate_manifest=candidate,
                            validation={"python": True, "node": True},
                            budget=clean_budget(ceilings))
    return Path(root)


def published_manifest(dist: Path) -> dict:
    """The manifest of the generation the pointer resolves to, read back off disk."""
    pointer = json.loads((Path(dist) / "coa_client_extract.pointer.json").read_text(encoding="utf-8"))
    gen_dir = Path(dist) / f"gen-{pointer['generation_id']}"
    return json.loads((gen_dir / "manifest.json").read_text(encoding="utf-8"))


def recon_doc_for(binding: dict, *, status="verified", blocking=(), policy_sha256=None,
                  table_sha256=None, expected_absent_ok=None, schema_version=RECON_SCHEMA,
                  candidate_distinct_ids=8) -> dict:
    """The recon report a run against THIS generation's client would have produced."""
    topology = copy.deepcopy(binding["topology"])
    for name, sha in (table_sha256 or {}).items():
        topology["tables"][name]["sha256"] = sha
    if expected_absent_ok is not None:
        topology["expected_absent_ok"] = expected_absent_ok
    return {
        "schema_version": schema_version,
        "status": status,
        "blocking_findings": [dict(b) for b in blocking],
        "source_pins": {"dbc": {n: {"sha256": t["sha256"]} for n, t in topology["tables"].items()},
                        "policy_sha256": policy_sha256 or binding["policy_sha256"],
                        "extractor_commit": "0" * 40,
                        "client_build": topology["client_build"],
                        "effective_archive": "fixture/common.MPQ", "patch_chain": []},
        "topology": topology,
        # Deliberately OUTSIDE the identity digest and inside the report hash: the scan metrics, the
        # budget measurements and the proposed delta are what the record attests to, not what it matches.
        "index_fk": {"icon_index": {"scanned": True, "candidates": [
            {"cell": 133, "distinct_ids": candidate_distinct_ids, "nonzero_count": 12,
             "valid_count": 12}]}},
        "proposed_policy_delta": {},
        "budget": {"within_budget": True, "breach": []},
    }


def write_recon(path: Path, doc: dict) -> Path:
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def recon_report(tmp_path, *, status="verified", payload=None, name="recon.json") -> Path:
    """A recon report file with no relation to any generation — for tests upstream of the binding."""
    doc = dict(payload or {"schema_version": RECON_SCHEMA, "blocking_findings": []})
    doc["status"] = status
    return write_recon(Path(tmp_path) / name, doc)


def _fake_node(slot: Path, scenario: dict) -> Path:
    """A `node` the real executor spawns. The scenario travels in a file rather than the environment,
    because `run_measured_build_mechanics` owns the env it passes."""
    scenario_path = slot / "build-scenario.json"
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    node = slot / "fake-node"
    node.write_text(f"#!{sys.executable}\n"
                    "import json, sys\n"
                    f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
                    "from tests._fake_node_build import main\n"
                    f"raise SystemExit(main(json.load(open({str(scenario_path)!r})), sys.argv[1:]))\n",
                    encoding="utf-8")
    node.chmod(0o755)
    return node


def _slot(tmp_path: Path) -> Path:
    """A fresh sub-root per call, so a test may build TWO acceptance environments (the report-hash vs
    identity-digest probe needs exactly that) without the second publish landing on the first."""
    slot = Path(tmp_path) / f"acceptance-{len(list(Path(tmp_path).glob('acceptance-*')))}"
    slot.mkdir(parents=True)
    return slot


def acceptance_env(tmp_path, *, out=None,
                   # --- the recon side ---
                   recon=None, recon_status="verified", recon_schema_version=RECON_SCHEMA,
                   recon_policy_sha256=None, recon_table_sha256=None, recon_blocking=(),
                   recon_expected_absent_ok=None, recon_candidate_distinct_ids=8,
                   # --- the generation side ---
                   base_manifest=None, drop_manifest_keys=(),
                   # --- the build side (handed to the stand-in node) ---
                   builder_entries=None, network_attempts=0, build_exit_code=0,
                   republish_during_build=False, rewrite_manifest_during_build=False,
                   forge_mechanics_output_hash=False, forge_mechanics_record_count=None,
                   forge_mechanics_binding=None, drop_mechanics_keys=(), drop_mechanics_rows=0) -> dict:
    """The complete keyword arguments for one `run_acceptance` call, over a generation, a recon and a
    build that agree — unless a knob makes exactly one of them disagree."""
    slot = _slot(tmp_path)
    dist = publish_bound(slot / "dist", base_manifest=base_manifest,
                         drop_manifest_keys=drop_manifest_keys)
    binding = published_manifest(dist)["binding"]

    doc = recon if recon is not None else recon_doc_for(
        binding, status=recon_status, blocking=recon_blocking, policy_sha256=recon_policy_sha256,
        table_sha256=recon_table_sha256, expected_absent_ok=recon_expected_absent_ok,
        schema_version=recon_schema_version, candidate_distinct_ids=recon_candidate_distinct_ids)

    entries = slot / "coa_entries.jsonl"
    entries.write_text("".join(json.dumps(e) + "\n"
                               for e in (BUILDER_ENTRIES if builder_entries is None
                                         else builder_entries)), encoding="utf-8")
    scraper = slot / "coa_scraper"
    scraper.mkdir()
    node = _fake_node(slot, {"network_attempts": network_attempts, "exit_code": build_exit_code,
                             "republish_during_build": republish_during_build,
                             "rewrite_manifest_during_build": rewrite_manifest_during_build,
                             "forge_output_sha256": forge_mechanics_output_hash,
                             "forge_record_count": forge_mechanics_record_count,
                             "forge_binding": forge_mechanics_binding or {},
                             "drop_manifest_keys": list(drop_mechanics_keys),
                             "drop_rows": drop_mechanics_rows})
    env = {"dist": dist, "recon_report_path": write_recon(slot / "recon.json", doc),
           "scraper_dir": scraper, "builder_entries": entries, "mechanics_out": slot / "mech",
           "node": str(node)}
    if out is not None:
        env["out"] = out
    return env


def builder_entries_sha256(env: dict) -> str:
    return hashlib.sha256(Path(env["builder_entries"]).read_bytes()).hexdigest()


def measured(**over) -> dict:
    """A build measurement shaped exactly as `run_measured_build_mechanics` returns one."""
    out = {"executed": True,
           "command": ["node", "scripts/build-mechanics-artifacts.mjs",
                       "--client-extract-pointer", "…/coa_client_extract.pointer.json"],
           "cwd": "coa_scraper", "exit_code": 0, "pointer_only": True, "network_attempts": 0,
           "elapsed_s": 12.5, "peak_rss_mb": 210.0, "stderr_tail": ""}
    out.update(over)
    return out
