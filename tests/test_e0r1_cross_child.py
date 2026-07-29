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

from tests._e0r2_fixtures import stage_candidate, validate_staged

CORPUS = Path(__file__).resolve().parent / "golden" / "e0r1_corpus"
CORPUS_V4 = Path(__file__).resolve().parent / "golden" / "e0r2_corpus_v4"


def _rows(name):
    # E0R.2 T6.3: the icon baselines are the NORMALIZED v2 ones; the v3 corpus keeps the rest.
    corpus = CORPUS_V4 if name in ("icons.jsonl", "icon_assets.jsonl") else CORPUS
    return [json.loads(l) for l in (corpus / name).read_text().splitlines() if l.strip()]


def _pick(name, case):
    return [{k: v for k, v in r.items() if k not in ("case", "golden_accept")}
            for r in _rows(name) if r["case"] == case]


def _candidate(root, *, full=None, proj=None, icons=None, icon_assets=None):
    """Assemble a COMPLETE staged candidate from the corpus baselines (mirrors the Node helper
    coa_scraper/tests/helpers/candidate.mjs); a single full/proj/icons override injects one failure.

    E0R.2 T2.1: the shared fixture also sizes the staged policy's reviewed `bound` and writes the lock,
    so a cross-child case reaches the merge-join rather than the cardinality gate."""
    return stage_candidate(root, full=full, proj=proj, icons=icons, icon_assets=icon_assets)


def test_valid_corpus_baseline_passes_cross_child(tmp_path):
    active = validate_staged(_candidate(tmp_path))
    assert "coa_client_spell_icons.jsonl" in active["children"]


# --- icon id/path agreement (corpus reject rows, domain preserved) ---

# E0R.2 T6.3 replaced the id/path agreement rules with RELATIONAL ones. The v1 cases these tests were
# written for (`placeholder_with_path`, the two `converted` ones) describe a dialect that no longer
# exists; the corpus carries their v2 successors, each breaking one relation between the two children.

def test_a_null_reference_claiming_available_fails(tmp_path):
    icons = _pick("icons.jsonl", "valid_icon")
    icons[1] = _pick("icons.jsonl", "null_ref_claims_available")[0]     # spell 2
    with pytest.raises(ResolveError, match="readiness"):
        validate_staged(_candidate(tmp_path, icons=icons))


def test_a_dangling_reference_fails(tmp_path):
    icons = _pick("icons.jsonl", "valid_icon")
    icons[0] = _pick("icons.jsonl", "dangling_asset_ref")[0]
    with pytest.raises(ResolveError, match="dangling asset_ref"):
        validate_staged(_candidate(tmp_path, icons=icons))


def test_a_reference_whose_reason_is_not_decoded_fails(tmp_path):
    icons = _pick("icons.jsonl", "valid_icon")
    icons[0] = _pick("icons.jsonl", "ref_with_undecoded_reason")[0]
    with pytest.raises(ResolveError, match="only a decoded join yields a path"):
        validate_staged(_candidate(tmp_path, icons=icons))


def test_an_orphan_asset_row_fails(tmp_path):
    assets = _pick("icon_assets.jsonl", "valid_asset") + _pick("icon_assets.jsonl", "orphan_asset")
    with pytest.raises(ResolveError, match="referenced by no spell"):
        validate_staged(_candidate(tmp_path, icon_assets=sorted(assets, key=lambda a: a["asset_id"])))


# --- exact icon domain: catalog == full table, 1:1 in lockstep ---

def test_trailing_icon_beyond_domain_fails(tmp_path):
    icons = _pick("icons.jsonl", "valid_icon") + _pick("icons.jsonl", "trailing_icon_beyond_domain")
    with pytest.raises(ResolveError, match="icons_agree"):
        validate_staged(_candidate(tmp_path, icons=icons))


def test_orphan_icon_below_domain_fails(tmp_path):
    # an icon row for a spell ABSENT from the full table, sorted before it — the pre-T3.3 merge-join
    # silently skipped these instead of rejecting.
    orphan = dict(_pick("icons.jsonl", "valid_icon")[0])
    orphan["spell_id"] = 0
    icons = [orphan] + _pick("icons.jsonl", "valid_icon")
    with pytest.raises(ResolveError, match="icons_agree"):
        validate_staged(_candidate(tmp_path, icons=icons))


def test_missing_icon_row_fails(tmp_path):
    icons = _pick("icons.jsonl", "valid_icon")[:2]                     # drop spell 3's icon
    with pytest.raises(ResolveError, match="icons_agree"):
        validate_staged(_candidate(tmp_path, icons=icons))
