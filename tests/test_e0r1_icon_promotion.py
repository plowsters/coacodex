# tests/test_e0r1_icon_promotion.py
"""E0R.1 T2.3 — the icon catalog routes resolution through make_string_join + promotion. An UNRESOLVED
icon join (fk 0 / no side row) yields NO asset reference, and `missing` stays reserved for a PROVEN path
whose client asset is absent. When WS1 adjudicated the icon index, real paths resolve and the manifest
records honest resolved-icon coverage; when the probe stayed ambiguous, nothing resolves and coverage is
zero.

E0R.2 T6.3 normalized the dialect: `asset_status` on every row became an ASSET row's `availability` plus
an association's reference, and the four causes of a null reference became distinguishable instead of one
`placeholder`. The RULES here are unchanged — only where each fact lives."""
import hashlib

from coa_client_extract.contracts import decoded_reason_name
from coa_client_extract.spell_icons import (canonical_icon_path, icon_asset_table, icon_coverage,
                                            iter_icon_catalog)
from tests._spell_fixtures import (
    v2_icon_policy, v2_icon_policy_ambiguous, spell_dbc_icon_edges, icon_side_views)


def _bytes_resolver(path):
    return {"bytes": b"BLP:" + canonical_icon_path(path).encode(), "archive": "patch-T.MPQ",
            "member": path, "patch_chain": []}


def _catalog(policy, resolver):
    assets = icon_asset_table()
    rows = list(iter_icon_catalog(spell_dbc_icon_edges(), icon_side_views(), policy=policy,
                                  asset_resolver=resolver, assets=assets))
    return rows, assets


def _rows(policy, resolver):
    rows, assets = _catalog(policy, resolver)
    return {r["spell_id"]: r for r in rows}, assets


def test_index_zero_fk_references_no_asset_and_says_so():
    rows, _ = _rows(v2_icon_policy(), _bytes_resolver)
    r = rows[300]
    assert r["asset_ref"] is None and r["readiness"] == "unavailable"
    # NOT "missing": there is no proven path to resolve, and T6.3 makes that a DIFFERENT value from the
    # no-side-row case rather than the same placeholder.
    assert decoded_reason_name(r["d"]) == "index_zero"


def test_side_row_missing_fk_is_told_apart_from_index_zero():
    rows, _ = _rows(v2_icon_policy(), _bytes_resolver)
    r = rows[400]                                      # fk 999 -> no SpellIcon row
    assert r["asset_ref"] is None
    assert decoded_reason_name(r["d"]) == "side_row_missing"


def test_resolved_path_with_present_asset_is_source_only():
    rows, assets = _rows(v2_icon_policy(), _bytes_resolver)
    r = rows[133]
    asset = assets.get(r["asset_ref"])
    assert asset["availability"] == "source_only" and r["readiness"] == "available"
    assert asset["client_path"].endswith("ability_fireball.blp")
    assert asset["source_asset_sha256"] == hashlib.sha256(
        b"BLP:" + asset["client_path"].encode()).hexdigest()


def test_resolved_path_with_absent_asset_is_missing_not_unreferenced():
    # A PROVEN client path whose BLP member is absent from the chain is `missing` — the path DID resolve,
    # so the association still references the asset. That distinction is what a single null would lose.
    rows, assets = _rows(v2_icon_policy(), lambda p: None)
    r = rows[133]
    asset = assets.get(r["asset_ref"])
    assert asset["availability"] == "missing" and r["readiness"] == "unavailable"
    assert asset["client_path"].endswith("ability_fireball.blp")   # the path is known
    assert asset["source_asset_sha256"] is None


def test_coverage_counts_are_honest():
    rows, assets = _catalog(v2_icon_policy(), _bytes_resolver)
    cov = icon_coverage(rows, assets)
    assert cov["spells"] == 4
    assert cov["resolved_paths"] == 2                  # 133 + 500 resolve to real paths
    assert cov["placeholders"] == 2                    # 300 (fk0) + 400 (no side row)
    assert cov["assets_present"] == 2 and cov["assets_missing"] == 0
    assert cov["resolved_paths"] == cov["assets_present"] + cov["assets_missing"]
    assert cov["spells"] == cov["resolved_paths"] + cov["placeholders"]


def test_absent_assets_count_as_missing_coverage():
    rows, assets = _catalog(v2_icon_policy(), lambda p: None)
    cov = icon_coverage(rows, assets)
    assert cov["resolved_paths"] == 2                  # the paths still resolved
    assert cov["assets_present"] == 0 and cov["assets_missing"] == 2
    assert cov["placeholders"] == 2


def test_unadjudicated_icon_index_is_all_placeholders_zero_coverage():
    # When the WS1 icon probe genuinely stayed ambiguous (null FK cell), no path can resolve.
    rows, assets = _catalog(v2_icon_policy_ambiguous(), _bytes_resolver)
    assert all(r["asset_ref"] is None for r in rows)
    assert all(decoded_reason_name(r["d"]) == "not_present" for r in rows), "an explained null"
    cov = icon_coverage(rows, assets)
    assert cov["resolved_paths"] == 0 and cov["placeholders"] == 4
