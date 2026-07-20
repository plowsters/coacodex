# tests/test_e0r_end_to_end.py
"""End-to-end transactional v3 path: real producer + icon catalog -> candidate -> validate -> publish,
resolved by BOTH the Python resolver and the Node generation.mjs resolver."""
import json
import subprocess
from pathlib import Path

import pytest

from coa_client_extract.publish import (
    GenerationWriter, validate_candidate_generation, resolve_active_generation, ResolveError,
)
from coa_client_extract.spell_record import iter_spell_records
from coa_client_extract.spell_icons import iter_icon_catalog
from tests._spell_fixtures import v2_policy, v2_icon_policy, spell_dbc, side_views, icon_side_views


def _resolver(path):
    return {"bytes": b"BLP:" + path.encode(), "archive": "patch-T.MPQ", "member": path, "patch_chain": []}


def _stage_full_generation(root: Path) -> GenerationWriter:
    prov = {"effective_archive": "patch-T.MPQ"}
    full = sorted(iter_spell_records(spell_dbc(), side_views(), policy=v2_policy(), provenance=prov),
                  key=lambda r: r["spell_id"])
    proj = [{**r, "schema_version": "coa-client-spell-projection-v3"}
            for r in full if r["coa_attribution"]["is_coa"] is True]
    icons = sorted(iter_icon_catalog(spell_dbc(), icon_side_views(), policy=v2_icon_policy(),
                                     asset_resolver=_resolver), key=lambda r: r["spell_id"])
    gw = GenerationWriter(root)
    gw.add_jsonl("coa_client_spell.jsonl", full, schema_version="coa-client-spell-v3")
    gw.add_jsonl("coa_client_spell_coa.jsonl", proj, schema_version="coa-client-spell-projection-v3")
    gw.add_jsonl("coa_client_spell_icons.jsonl", icons, schema_version="coa-client-spell-icons-v1")
    gw.add_json("coa_client_spell_projection.manifest.json",
                {"schema_version": "coa-client-spell-projection-manifest-v3"},
                schema_version="coa-client-spell-projection-manifest-v3")
    for name in ("coa_client_content.jsonl", "coa_client_advancement.jsonl", "coa_client_class_types.jsonl",
                 "coa_client_tab_types.jsonl", "coa_client_essence.jsonl"):
        gw.add_jsonl(name, [], schema_version="coa-client-misc-v1")
    gw.add_json("coa_client_archive_plan.json", {"schema_version": "coa-client-archive-plan-v1"},
                schema_version="coa-client-archive-plan-v1")
    gw.add_json("spell_layout_v2.json", {"schema_version": "coa-spell-layout-v2"},
                schema_version="coa-spell-layout-v2")
    return gw


def test_transactional_v3_generation_resolves_in_python_and_node(tmp_path):
    dist = tmp_path / "dist"
    gw = _stage_full_generation(dist)
    candidate = gw.publish_candidate(base_manifest={}, binding={})
    validate_candidate_generation(gw.gen_dir)                       # Python candidate validation by path
    final = gw.finalize_and_publish(candidate_manifest=candidate,
                                    validation={"ok": True}, budget={"within_budget": True})
    assert final["publication_state"] == "published"

    active = resolve_active_generation(dist)                        # Python resolver
    assert active["manifest"]["schema_version"] == "coa-client-extract-manifest-v3"
    assert active["manifest"]["publication_state"] == "published"

    # Node resolves + validates the SAME published generation.
    r = subprocess.run(["node", "coa_scraper/scripts/lib/generation.mjs", str(dist)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_node_rejects_a_candidate_generation(tmp_path):
    # A candidate (never finalized) writes NO pointer -> Node has no active generation to resolve.
    dist = tmp_path / "dist"
    gw = _stage_full_generation(dist)
    gw.publish_candidate(base_manifest={}, binding={})
    r = subprocess.run(["node", "coa_scraper/scripts/lib/generation.mjs", str(dist)],
                       capture_output=True, text=True)
    assert r.returncode != 0
