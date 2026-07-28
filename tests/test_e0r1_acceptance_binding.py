# tests/test_e0r1_acceptance_binding.py
"""E0R.1 T6.2 — the acceptance summary is BINDING, not a caller's self-report. It must:

  * commit the NORMALIZED recon report itself (not merely its hash) and bind that report's sha256;
  * assert the recon `status == "verified"` — a `review_required`/`blocked` recon can never be accepted;
  * read strict-V3 / published / validation / budget from the RESOLVED manifest, rejecting any
    caller-supplied publication status or manifest;
  * record real icon / readiness / source COVERAGE counts;
  * derive `pointer_only` and the network-trap result from EXECUTED commands, never caller booleans.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from coa_client_extract.cli import AcceptanceError, write_acceptance_summary
from coa_client_extract.publish import GenerationWriter

VERIFIED_RECON = {
    "schema_version": "coa-mechanics-recon-v2",
    "status": "verified",
    "blocking_findings": [],
    "joins": {"cast_time_ms": {"adopted": True}, "duration_ms": {"adopted": True}},
    "power_type": {"interpretation": "raw_only", "no_static_anchor": True},
}


def _stage_minimal(root):
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
    return gw


def _publish(root, *, base_manifest=None):
    gw = _stage_minimal(root)
    candidate = gw.publish_candidate(base_manifest=base_manifest or {}, binding={"policy_sha256": "abc123"})
    gw.finalize_and_publish(candidate_manifest=candidate,
                            validation={"python": True, "node": True},
                            budget={"within_budget": True})
    return gw


def _recon(tmp_path, payload=VERIFIED_RECON, name="recon.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _build_mechanics(**over):
    measured = {"executed": True, "command": ["node", "scripts/build-mechanics-artifacts.mjs",
                                              "--client-extract-pointer", "…/coa_client_extract.pointer.json"],
                "exit_code": 0, "pointer_only": True, "network_attempts": 0,
                "elapsed_s": 12.5, "peak_rss_mb": 210.0}
    measured.update(over)
    return measured


def test_summary_commits_the_normalized_recon_report_and_binds_its_hash(tmp_path):
    dist = tmp_path / "dist"
    _publish(dist)
    report_path = _recon(tmp_path)

    summary = write_acceptance_summary(dist, recon_report_path=report_path,
                                       build_mechanics=_build_mechanics())

    assert summary["recon_report"] == VERIFIED_RECON, "the report itself must be committed, not just a hash"
    normalized = json.dumps(VERIFIED_RECON, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    assert summary["recon_report_sha256"] == hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    assert summary["recon_status"] == "verified"


def test_a_non_verified_recon_can_never_be_accepted(tmp_path):
    dist = tmp_path / "dist"
    _publish(dist)
    for status in ("review_required", "blocked", "unknown"):
        path = _recon(tmp_path, {**VERIFIED_RECON, "status": status}, name=f"recon-{status}.json")
        with pytest.raises(AcceptanceError, match="recon"):
            write_acceptance_summary(dist, recon_report_path=path, build_mechanics=_build_mechanics())


def test_publication_facts_come_from_the_resolved_manifest_not_the_caller(tmp_path):
    dist = tmp_path / "dist"
    _publish(dist)
    summary = write_acceptance_summary(dist, recon_report_path=_recon(tmp_path),
                                       build_mechanics=_build_mechanics())

    assert summary["manifest_schema_version"] == "coa-client-extract-manifest-v3"
    assert summary["publication_state"] == "published"
    assert summary["validation"] == {"python": True, "node": True}
    assert summary["budget"]["within_budget"] is True
    assert summary["policy_sha256"] == "abc123"
    # every REQUIRED child is pinned with its measured digest/size/record count
    assert summary["children"]["coa_client_spell.jsonl"]["sha256"]
    assert set(summary["children"]) >= {"coa_client_spell.jsonl", "coa_client_spell_coa.jsonl"}


def test_an_unpublished_or_missing_generation_is_refused(tmp_path):
    dist = tmp_path / "empty"
    dist.mkdir()
    with pytest.raises(AcceptanceError):
        write_acceptance_summary(dist, recon_report_path=_recon(tmp_path),
                                 build_mechanics=_build_mechanics())


def test_the_writer_refuses_a_caller_supplied_publication_status(tmp_path):
    # A caller cannot smuggle in its own verdict: there is no status/pointer_only parameter to pass.
    import inspect

    params = set(inspect.signature(write_acceptance_summary).parameters)
    assert not params & {"manifest", "recon_status", "pointer_only", "publication_state", "validation"}


def test_coverage_counts_are_recorded(tmp_path):
    dist = tmp_path / "dist"
    _publish(dist, base_manifest={
        "icon_coverage": {"total": 10, "resolved": 7, "placeholder": 3},
        "readiness_coverage": {"available": 4, "unavailable": 6},
        "source_coverage": {"client_dbc": 8, "verified_builder": 2},
    })
    summary = write_acceptance_summary(dist, recon_report_path=_recon(tmp_path),
                                       build_mechanics=_build_mechanics())

    assert summary["coverage"]["icon"]["resolved"] == 7
    assert summary["coverage"]["readiness"]["unavailable"] == 6
    assert summary["coverage"]["source"]["client_dbc"] == 8


def test_build_mechanics_must_be_an_executed_measurement(tmp_path):
    dist = tmp_path / "dist"
    _publish(dist)
    report_path = _recon(tmp_path)

    # a bare caller boolean is exactly what T6.2 removes
    with pytest.raises(AcceptanceError, match="executed"):
        write_acceptance_summary(dist, recon_report_path=report_path, build_mechanics={"pointer_only": True})
    # a failed build cannot be accepted
    with pytest.raises(AcceptanceError, match="build-mechanics"):
        write_acceptance_summary(dist, recon_report_path=report_path,
                                 build_mechanics=_build_mechanics(exit_code=1))
    # neither can one that reached the network under the trap
    with pytest.raises(AcceptanceError, match="network"):
        write_acceptance_summary(dist, recon_report_path=report_path,
                                 build_mechanics=_build_mechanics(network_attempts=2))
    # nor one that was not pointer-only
    with pytest.raises(AcceptanceError, match="pointer"):
        write_acceptance_summary(dist, recon_report_path=report_path,
                                 build_mechanics=_build_mechanics(pointer_only=False))


def test_summary_round_trips_to_disk(tmp_path):
    dist = tmp_path / "dist"
    _publish(dist)
    out = tmp_path / "acceptance.json"
    summary = write_acceptance_summary(dist, recon_report_path=_recon(tmp_path),
                                       build_mechanics=_build_mechanics(), out=out)
    assert json.loads(out.read_text(encoding="utf-8")) == summary
    assert summary["schema_version"] == "coa-e0r-acceptance-summary-v2"
