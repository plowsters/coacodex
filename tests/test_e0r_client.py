# tests/test_e0r_client.py
"""Real-client E0R recon acceptance (requires the local Ascension install + StormLib).

Deselected by default; run with `pytest -m client` and COA_CLIENT_ROOT pointing at the client Data dir.
"""
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.client

_CLIENT_ROOT = os.environ.get("COA_CLIENT_ROOT")


@pytest.fixture(scope="module")
def recon_report(tmp_path_factory):
    if not _CLIENT_ROOT or not Path(_CLIENT_ROOT).is_dir():
        pytest.skip("COA_CLIENT_ROOT not set to a client Data dir")
    from coa_client_extract.cli import mechanics_recon_command
    out = tmp_path_factory.mktemp("recon")
    return mechanics_recon_command(Path(_CLIENT_ROOT), out)


def test_real_recon_produces_e0r_report(recon_report):
    # The reviewed v2 default policy is not yet bound (Task 8b authors the bound), so recon is not verified.
    assert recon_report["status"] in ("review_required", "blocked")
    assert recon_report["schema_version"] == "coa-spell-mechanics-recon-v1"


def test_real_recon_topology_is_from_shared_verifier(recon_report):
    topo = recon_report["topology"]
    # every required table opened with a full 5-field header + density from verify_source_topology
    for name in ("Spell", "SpellCastTimes", "SpellDuration", "SpellRange", "SpellIcon"):
        assert name in topo["tables"], name
        h = topo["tables"][name]["header"]
        assert {"magic", "record_count", "field_count", "record_size", "string_block_size"} <= set(h)
        assert topo["tables"][name]["dense"] is True
    # SpellEffect / SpellCooldowns are proven absent (mechanics are inline on this client)
    assert topo["expected_absent_ok"] is True


def test_real_recon_budget_within_ceiling(recon_report):
    b = recon_report["budget"]
    assert {"serialized_mb", "peak_rss_mb", "elapsed_s"} <= set(b)
    assert b["within_budget"] is True, b.get("breach")


def test_real_recon_adjudicates_all_four_joins(recon_report):
    # E0R.1 T1.2: every required join carries a verdict. The icon join is ADOPTED at the cell the Builder
    # icon anchors uniquely pin (133); the three numeric joins are reviewed_ambiguous (recorded, null cell).
    jp = recon_report["join_pairs"]
    assert set(recon_report["required_joins"]) == {
        "casting_time_index", "duration_index", "range_index", "spell_icon_id"}
    assert list(jp["spell_icon_id"]["pair"]) == [133, 0]   # discovered + adopted (tuple in-memory / list via JSON)
    for f in ("casting_time_index", "duration_index", "range_index"):
        assert jp[f]["pair"] is None
        assert jp[f]["adjudication"] == "reviewed_ambiguous"


def test_real_recon_icon_join_not_blocked_by_ambiguous_bare_fk(recon_report):
    # The bare SpellIcon FK-validity scan is deliberately ambiguous (dozens of candidate columns); the
    # adjudicated cell 133 must NOT raise a no_unique_index_cell block.
    assert not any(f.get("field") == "spell_icon_id" and f.get("reason") == "no_unique_index_cell"
                   for f in recon_report["blocking_findings"])
