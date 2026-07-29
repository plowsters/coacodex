"""Shared acceptance fixtures for E0R.2 WS4 — a published generation, a recon report, and a measurement.

Extracted from tests/test_e0r1_acceptance_binding.py when T4.2 folded the build executor inside
`run_acceptance`: both suites now stage the same generation and monkeypatch the same executor, and two
copies of that setup would drift.
"""
from __future__ import annotations

import json
from pathlib import Path

from coa_client_extract.publish import GenerationWriter
from tests._e0r2_fixtures import (GENEROUS_CEILINGS, clean_budget, generation_contract_binding,
                                  stage_generation_contract)

VERIFIED_RECON = {
    "schema_version": "coa-mechanics-recon-v2",
    "status": "verified",
    "blocking_findings": [],
    "joins": {"cast_time_ms": {"adopted": True}, "duration_ms": {"adopted": True}},
    "power_type": {"interpretation": "raw_only", "no_static_anchor": True},
}


def stage_minimal(root) -> GenerationWriter:
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


def publish_generation(root, *, base_manifest=None) -> Path:
    """Publish and return the dist root a caller hands to `run_acceptance`."""
    publish(root, base_manifest=base_manifest)
    return Path(root)


def recon_report(tmp_path, *, status="verified", payload=None, name="recon.json") -> Path:
    doc = dict(payload or VERIFIED_RECON)
    doc["status"] = status
    path = Path(tmp_path) / name
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def measured(**over) -> dict:
    """A build measurement shaped exactly as `run_measured_build_mechanics` returns one."""
    out = {"executed": True,
           "command": ["node", "scripts/build-mechanics-artifacts.mjs",
                       "--client-extract-pointer", "…/coa_client_extract.pointer.json"],
           "cwd": "coa_scraper", "exit_code": 0, "pointer_only": True, "network_attempts": 0,
           "elapsed_s": 12.5, "peak_rss_mb": 210.0, "stderr_tail": ""}
    out.update(over)
    return out
