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


def _rows(name):
    return [json.loads(l) for l in (CORPUS / name).read_text().splitlines() if l.strip()]


def _pick(name, case):
    return [{k: v for k, v in r.items() if k not in ("case", "golden_accept")}
            for r in _rows(name) if r["case"] == case]


def _candidate(root, *, full=None, proj=None, icons=None):
    """Assemble a COMPLETE staged candidate from the corpus baselines (mirrors the Node helper
    coa_scraper/tests/helpers/candidate.mjs); a single full/proj/icons override injects one failure.

    E0R.2 T2.1: the shared fixture also sizes the staged policy's reviewed `bound` and writes the lock,
    so a cross-child case reaches the merge-join rather than the cardinality gate."""
    return stage_candidate(root, full=full, proj=proj, icons=icons)


def test_valid_corpus_baseline_passes_cross_child(tmp_path):
    active = validate_staged(_candidate(tmp_path))
    assert "coa_client_spell_icons.jsonl" in active["children"]


# --- icon id/path agreement (corpus reject rows, domain preserved) ---

def test_placeholder_icon_with_client_path_fails(tmp_path):
    icons = _pick("icons.jsonl", "valid_icon")
    icons[1] = _pick("icons.jsonl", "placeholder_with_path")[0]        # spell 2
    with pytest.raises(ResolveError, match="placeholder spell 2 carries a client_path"):
        validate_staged(_candidate(tmp_path, icons=icons))


def test_converted_icon_without_converted_ref_fails(tmp_path):
    # E0R.2 T2.5 retired the rule this corpus case was written for (`converted` needs a converted_ref)
    # in favour of a stronger one: `converted` is not an admissible status at all.
    icons = _pick("icons.jsonl", "valid_icon")
    icons[0] = _pick("icons.jsonl", "converted_without_ref")[0]
    with pytest.raises(ResolveError, match="converted"):
        validate_staged(_candidate(tmp_path, icons=icons))


def test_source_only_icon_with_converted_ref_fails(tmp_path):
    # Likewise: a bundle reference is unverifiable on ANY status, so it is rejected structurally (the
    # shape has no such key) before the semantic gate restates it.
    icons = _pick("icons.jsonl", "valid_icon")
    icons[0] = _pick("icons.jsonl", "source_only_with_converted_ref")[0]
    with pytest.raises(ResolveError, match="converted_ref"):
        validate_staged(_candidate(tmp_path, icons=icons))


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
