# tests/test_e0r1_cross_child.py
"""E0R.1 T3.3 — Python cross-child + icon parity with Node over the ONE shared golden corpus. The candidate
validator must enforce the icon catalog as EXACTLY the full-table domain (a missing, orphan, or trailing
icon row fails — the old merge-join silently skipped orphans), per-row icon id/path agreement
(placeholder <=> null client_path, converted <=> converted_ref), and reject every corpus icon reject-case
identically to Node (coa_scraper/tests/e0r1-node-cross-child.test.mjs)."""
import json
from pathlib import Path

import pytest

from coa_client_extract.publish import GenerationWriter, ResolveError, validate_candidate_generation

from tests._e0r2_fixtures import generation_contract_binding, stage_generation_contract

CORPUS = Path(__file__).resolve().parent / "golden" / "e0r1_corpus"


def _rows(name):
    return [json.loads(l) for l in (CORPUS / name).read_text().splitlines() if l.strip()]


def _pick(name, case):
    return [{k: v for k, v in r.items() if k not in ("case", "golden_accept")}
            for r in _rows(name) if r["case"] == case]


def _candidate(root, *, full=None, proj=None, icons=None):
    """Assemble a COMPLETE staged candidate from the corpus baselines (mirrors the Node helper
    coa_scraper/tests/helpers/candidate.mjs); a single full/proj/icons override injects one failure."""
    full = full if full is not None else _pick("full_rows.jsonl", "valid_full")
    proj = proj if proj is not None else _pick("projection_rows.jsonl", "valid")
    icons = icons if icons is not None else _pick("icons.jsonl", "valid_icon")
    policy = json.loads((CORPUS / "policy.json").read_text())
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
    gw.add_json("spell_layout_v2.json", policy, schema_version="coa-spell-layout-v2")
    stage_generation_contract(gw)
    gw.publish_candidate(base_manifest={}, binding=generation_contract_binding())
    return gw.gen_dir


def test_valid_corpus_baseline_passes_cross_child(tmp_path):
    active = validate_candidate_generation(_candidate(tmp_path))
    assert "coa_client_spell_icons.jsonl" in active["children"]


# --- icon id/path agreement (corpus reject rows, domain preserved) ---

def test_placeholder_icon_with_client_path_fails(tmp_path):
    icons = _pick("icons.jsonl", "valid_icon")
    icons[1] = _pick("icons.jsonl", "placeholder_with_path")[0]        # spell 2
    with pytest.raises(ResolveError, match="placeholder spell 2 carries a client_path"):
        validate_candidate_generation(_candidate(tmp_path, icons=icons))


def test_converted_icon_without_converted_ref_fails(tmp_path):
    icons = _pick("icons.jsonl", "valid_icon")
    icons[0] = _pick("icons.jsonl", "converted_without_ref")[0]
    # converted also requires the bundle child; either way it must fail.
    with pytest.raises(ResolveError, match="converted"):
        validate_candidate_generation(_candidate(tmp_path, icons=icons))


def test_source_only_icon_with_converted_ref_fails(tmp_path):
    icons = _pick("icons.jsonl", "valid_icon")
    icons[0] = _pick("icons.jsonl", "source_only_with_converted_ref")[0]
    with pytest.raises(ResolveError, match="non-converted row carries a converted_ref"):
        validate_candidate_generation(_candidate(tmp_path, icons=icons))


# --- exact icon domain: catalog == full table, 1:1 in lockstep ---

def test_trailing_icon_beyond_domain_fails(tmp_path):
    icons = _pick("icons.jsonl", "valid_icon") + _pick("icons.jsonl", "trailing_icon_beyond_domain")
    with pytest.raises(ResolveError, match="icons_agree"):
        validate_candidate_generation(_candidate(tmp_path, icons=icons))


def test_orphan_icon_below_domain_fails(tmp_path):
    # an icon row for a spell ABSENT from the full table, sorted before it — the pre-T3.3 merge-join
    # silently skipped these instead of rejecting.
    orphan = dict(_pick("icons.jsonl", "valid_icon")[0])
    orphan["spell_id"] = 0
    icons = [orphan] + _pick("icons.jsonl", "valid_icon")
    with pytest.raises(ResolveError, match="icons_agree"):
        validate_candidate_generation(_candidate(tmp_path, icons=icons))


def test_missing_icon_row_fails(tmp_path):
    icons = _pick("icons.jsonl", "valid_icon")[:2]                     # drop spell 3's icon
    with pytest.raises(ResolveError, match="icons_agree"):
        validate_candidate_generation(_candidate(tmp_path, icons=icons))
