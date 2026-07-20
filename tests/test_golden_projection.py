# tests/test_golden_projection.py
import json
import pytest
from pathlib import Path
from coa_client_extract.spell_record import verify_row_against_policy

GOLDEN = Path(__file__).resolve().parent / "golden"


def test_python_verifier_agrees_with_golden_verdict():
    policy = json.loads((GOLDEN / "e0r_policy.json").read_text())
    rows = [json.loads(l) for l in (GOLDEN / "e0r_projection_rows.jsonl").read_text().splitlines() if l.strip()]
    for row in rows:
        if row["golden_accept"]:
            verify_row_against_policy(row, policy)                 # must not raise
        else:
            with pytest.raises(ValueError):
                verify_row_against_policy(row, policy)
