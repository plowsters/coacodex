# tests/test_spell_icons.py
import hashlib
from coa_client_extract.spell_icons import iter_icon_catalog
from tests._spell_fixtures import v2_icon_policy, spell_dbc, icon_side_views


def _resolver(path):
    # returns BLP bytes distinct from the path string, so a path-hash would NOT match a bytes-hash
    return {"bytes": b"BLP:" + path.encode(), "archive": "patch-T.MPQ", "member": path, "patch_chain": []}


def test_icon_catalog_hashes_blp_bytes_and_dedups():
    rows = list(iter_icon_catalog(spell_dbc(), icon_side_views(), policy=v2_icon_policy(), asset_resolver=_resolver))
    by_id = {r["spell_id"]: r for r in rows}
    r = by_id[805775]
    assert r["client_path"].endswith(".blp") and r["asset_status"] == "source_only"
    # the hash is over the BLP BYTES the resolver returned, not the client_path string
    assert r["source_asset_sha256"] == hashlib.sha256(b"BLP:" + r["client_path"].encode()).hexdigest()
    assert r["source_archive"] == "patch-T.MPQ"
    # two spells sharing one icon path produce one deduplicated source asset hash
    assert r["source_asset_sha256"] == by_id[133]["source_asset_sha256"]


def test_icon_catalog_missing_member_is_missing_status():
    rows = list(iter_icon_catalog(spell_dbc(), icon_side_views(), policy=v2_icon_policy(),
                                  asset_resolver=lambda p: None))     # no client member for any path
    assert all(r["asset_status"] == "missing" and r["source_asset_sha256"] is None for r in rows)
