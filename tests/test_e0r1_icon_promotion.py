# tests/test_e0r1_icon_promotion.py
"""E0R.1 T2.3 — the icon catalog routes resolution through make_string_join + promotion. An UNRESOLVED icon
join (fk 0 / no side row) is `asset_status: "placeholder"` (readiness unavailable), NOT `"missing"`; `"missing"`
is reserved for a PROVEN path whose client asset is absent. When WS1 adjudicated the icon index, real paths
resolve and the manifest records honest resolved-icon coverage; when the icon probe stayed ambiguous, every
row is a placeholder and coverage is zero."""
import hashlib

from coa_client_extract.spell_icons import iter_icon_catalog, icon_coverage
from tests._spell_fixtures import (
    v2_icon_policy, v2_icon_policy_ambiguous, spell_dbc_icon_edges, icon_side_views)


def _bytes_resolver(path):
    return {"bytes": b"BLP:" + path.encode(), "archive": "patch-T.MPQ", "member": path, "patch_chain": []}


def _rows(policy, resolver):
    return {r["spell_id"]: r for r in iter_icon_catalog(
        spell_dbc_icon_edges(), icon_side_views(), policy=policy, asset_resolver=resolver)}


def test_index_zero_fk_is_placeholder_not_missing():
    r = _rows(v2_icon_policy(), _bytes_resolver)[300]
    assert r["asset_status"] == "placeholder"          # NOT "missing": there is no proven path to resolve
    assert r["readiness"] == "unavailable"
    assert r["client_path"] is None and r["source_asset_sha256"] is None


def test_side_row_missing_fk_is_placeholder():
    r = _rows(v2_icon_policy(), _bytes_resolver)[400]   # fk 999 -> no SpellIcon row
    assert r["asset_status"] == "placeholder"
    assert r["client_path"] is None


def test_resolved_path_with_present_asset_is_source_only():
    r = _rows(v2_icon_policy(), _bytes_resolver)[133]
    assert r["asset_status"] == "source_only" and r["readiness"] == "available"
    assert r["client_path"].endswith("Ability_Fireball.blp")
    assert r["source_asset_sha256"] == hashlib.sha256(b"BLP:" + r["client_path"].encode()).hexdigest()


def test_resolved_path_with_absent_asset_is_missing_not_placeholder():
    # A PROVEN client path whose BLP member is absent from the chain is `missing` (the path resolved); this
    # is the case the placeholder status must NOT swallow.
    r = _rows(v2_icon_policy(), lambda p: None)[133]
    assert r["asset_status"] == "missing" and r["readiness"] == "unavailable"
    assert r["client_path"].endswith("Ability_Fireball.blp")   # path is known; only the asset is absent
    assert r["source_asset_sha256"] is None


def test_coverage_counts_are_honest():
    rows = list(iter_icon_catalog(spell_dbc_icon_edges(), icon_side_views(),
                                  policy=v2_icon_policy(), asset_resolver=_bytes_resolver))
    cov = icon_coverage(rows)
    assert cov["spells"] == 4
    assert cov["resolved_paths"] == 2                  # 133 + 500 resolve to real paths
    assert cov["placeholders"] == 2                    # 300 (fk0) + 400 (no side row)
    assert cov["assets_present"] == 2 and cov["assets_missing"] == 0
    assert cov["resolved_paths"] == cov["assets_present"] + cov["assets_missing"]
    assert cov["spells"] == cov["resolved_paths"] + cov["placeholders"]


def test_absent_assets_count_as_missing_coverage():
    rows = list(iter_icon_catalog(spell_dbc_icon_edges(), icon_side_views(),
                                  policy=v2_icon_policy(), asset_resolver=lambda p: None))
    cov = icon_coverage(rows)
    assert cov["resolved_paths"] == 2                  # the paths still resolved
    assert cov["assets_present"] == 0 and cov["assets_missing"] == 2
    assert cov["placeholders"] == 2


def test_unadjudicated_icon_index_is_all_placeholders_zero_coverage():
    # When the WS1 icon probe genuinely stayed ambiguous (null FK cell), no path can resolve.
    rows = list(iter_icon_catalog(spell_dbc_icon_edges(), icon_side_views(),
                                  policy=v2_icon_policy_ambiguous(), asset_resolver=_bytes_resolver))
    assert all(r["asset_status"] == "placeholder" for r in rows)
    cov = icon_coverage(rows)
    assert cov["resolved_paths"] == 0 and cov["placeholders"] == 4
