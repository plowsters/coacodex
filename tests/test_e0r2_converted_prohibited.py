"""E0R.2 T2.5: `converted` promised tar containment, bundle-manifest and content-hash verification that
were never implemented, and nothing produces the status. An unverifiable status with no producer is not a
feature — reject it and reintroduce it WITH its validator.

What E0R.1 actually shipped was an existence test: if any icon row said `converted`, a child named
`coa_client_spell_icons.bundle.tar` had to be registered. No path containment, no per-entry manifest, no
content hashes. A check named after a guarantee it does not make is worse than no check, because it reads
like coverage.
"""
import pytest

from coa_client_extract.contracts import ICON_ASSET_STATUSES
from coa_client_extract.publish import ResolveError, _verify_icon_row
from coa_client_extract.shapes import SHAPES, ShapeError
from coa_client_extract.spell_icons import iter_icon_catalog, icon_coverage
from tests._spell_fixtures import icon_side_views, spell_dbc_icon_edges, v2_icon_policy


def _blp(path):
    """A resolver that finds the Fireball asset and not the Frostbolt one, so the same run produces a
    `source_only` row and a `missing` row."""
    if "Fireball" in path:
        return {"bytes": b"BLP:" + path.encode(), "archive": "patch-T.MPQ", "member": path,
                "patch_chain": []}
    return None


def _catalog():
    return list(iter_icon_catalog(spell_dbc_icon_edges(), icon_side_views(),
                                  policy=v2_icon_policy(), asset_resolver=_blp))


def test_converted_is_not_an_admissible_status():
    assert ICON_ASSET_STATUSES == frozenset({"source_only", "missing", "placeholder"})


def test_a_converted_row_is_rejected():
    with pytest.raises(ResolveError, match="converted"):
        _verify_icon_row({"spell_id": 1, "asset_status": "converted",
                          "client_path": "Interface\\Icons\\x", "converted_ref": "bundle:1"})


def test_a_converted_ref_is_rejected_on_any_status():
    # The status is admissible; the reference is not. There is no row shape in which a bundle reference
    # can be verified, so no row may carry one.
    with pytest.raises(ResolveError, match="converted_ref"):
        _verify_icon_row({"spell_id": 1, "asset_status": "source_only",
                          "client_path": "Interface\\Icons\\x", "converted_ref": "bundle:1"})


def test_converted_ref_is_not_even_a_structural_key():
    row = {"schema_version": "coa-client-spell-icons-v1", "spell_id": 1, "spell_icon_id": 1,
           "asset_status": "source_only", "client_path": "Interface/Icons/x.blp",
           "readiness": "available"}
    SHAPES["icon_row_v1"](row)
    with pytest.raises(ShapeError, match="converted_ref"):
        SHAPES["icon_row_v1"]({**row, "converted_ref": "icons.tar#x.png"})


def test_the_catalog_producer_never_emits_converted():
    """Behavioural, not a grep: run the real catalog producer over a client whose icons resolve, are
    missing, and are unjoined, and assert the emitted statuses. A double-quoted-literal scan is brittle
    in both directions — it fires on a comment and misses a computed value."""
    statuses = {row["asset_status"] for row in _catalog()}
    assert statuses <= ICON_ASSET_STATUSES
    assert statuses == {"source_only", "missing", "placeholder"}   # all three paths exercised


def test_every_produced_row_passes_the_prohibition_gate():
    for row in _catalog():
        _verify_icon_row(row)
        assert "converted_ref" not in row


def test_coverage_counts_the_produced_statuses_without_a_converted_branch():
    # icon_coverage counted `converted` as an asset-present status. Nothing produced it, so the branch
    # was unreachable arithmetic; present must equal exactly the source_only rows.
    rows = _catalog()
    cov = icon_coverage(rows)
    assert cov["assets_present"] == sum(1 for r in rows if r["asset_status"] == "source_only")
    assert cov["assets_missing"] == sum(1 for r in rows if r["asset_status"] == "missing")
    assert cov["placeholders"] == sum(1 for r in rows if r["asset_status"] == "placeholder")
    assert cov["spells"] == cov["assets_present"] + cov["assets_missing"] + cov["placeholders"]
