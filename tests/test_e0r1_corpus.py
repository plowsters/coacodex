# tests/test_e0r1_corpus.py
"""E0R.1 T3.0 — guard the ONE shared golden corpus. The Python projection verifier must agree with every
`golden_accept`, and the valid full/projection/icon baselines must be internally consistent (compact-raw
expands to the projection's field_observations). The Node suite pins the SAME corpus (coa_scraper/tests/
e0r1-corpus.test.mjs), so the two verifiers can never silently diverge."""
import json
from pathlib import Path

import pytest

from coa_client_extract.spell_layout import load_spell_policy
from coa_client_extract.spell_record import _expand_compact, verify_row_against_policy

CORPUS = Path(__file__).resolve().parent / "golden" / "e0r1_corpus"


def _rows(name):
    return [json.loads(l) for l in (CORPUS / name).read_text().splitlines() if l.strip()]


def _strip(r):
    return {k: v for k, v in r.items() if k not in ("case", "golden_accept")}


def test_policy_loads():
    load_spell_policy(json.loads((CORPUS / "policy.json").read_text()))


def test_python_verifier_agrees_with_every_projection_label():
    policy = json.loads((CORPUS / "policy.json").read_text())
    for r in _rows("projection_rows.jsonl"):
        row = _strip(r)
        if r["golden_accept"]:
            verify_row_against_policy(row, policy)                 # must not raise
        else:
            with pytest.raises(ValueError):
                verify_row_against_policy(row, policy)


def test_full_and_icon_rows_are_well_formed():
    for r in _rows("full_rows.jsonl"):
        if r["case"] == "valid_full":
            assert "raw" in r and "field_observations" not in r    # compact dialect
    for r in _rows("icons.jsonl"):
        if r["case"] == "valid_icon":
            assert r["asset_status"] in ("source_only", "converted", "missing", "placeholder")
            if r["asset_status"] == "placeholder":
                assert r["client_path"] is None


def test_valid_baselines_are_cross_child_consistent():
    # expand_compact(full.raw) == projection.field_observations for the shared spell ids {1,2,3}.
    policy = load_spell_policy(json.loads((CORPUS / "policy.json").read_text()))
    full = {r["spell_id"]: _strip(r) for r in _rows("full_rows.jsonl") if r["case"] == "valid_full"}
    proj = {r["spell_id"]: _strip(r) for r in _rows("projection_rows.jsonl") if r["case"] == "valid"}
    assert set(full) == set(proj) == {1, 2, 3}
    for sid in full:
        expanded = {f: _expand_compact(cell, policy) for f, cell in full[sid]["raw"].items()}
        assert expanded == proj[sid]["field_observations"], sid
        assert full[sid]["mechanics"] == proj[sid]["mechanics"]
