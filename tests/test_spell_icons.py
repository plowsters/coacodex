# tests/test_spell_icons.py
import hashlib
from coa_client_extract.spell_icons import (canonical_icon_path, icon_asset_table,
                                            iter_icon_catalog)
from tests._spell_fixtures import v2_icon_policy, spell_dbc, icon_side_views


def _resolver(path):
    # returns BLP bytes distinct from the path string, so a path-hash would NOT match a bytes-hash
    return {"bytes": b"BLP:" + canonical_icon_path(path).encode(), "archive": "patch-T.MPQ",
            "member": path, "patch_chain": []}


def _catalog(resolver):
    assets = icon_asset_table()
    rows = list(iter_icon_catalog(spell_dbc(), icon_side_views(), policy=v2_icon_policy(),
                                  asset_resolver=resolver, assets=assets))
    return rows, assets


def test_icon_catalog_hashes_blp_bytes_and_dedups():
    rows, assets = _catalog(_resolver)
    by_id = {r["spell_id"]: r for r in rows}
    asset = assets.get(by_id[805775]["asset_ref"])
    assert asset["client_path"].endswith(".blp") and asset["availability"] == "source_only"
    # the hash is over the BLP BYTES the resolver returned, not the client_path string
    assert asset["source_asset_sha256"] == hashlib.sha256(
        b"BLP:" + asset["client_path"].encode()).hexdigest()
    assert asset["source_archive"] == "patch-T.MPQ"
    # E0R.2 T6.3: two spells sharing one icon path now share one ASSET ROW, not one repeated hash
    assert by_id[805775]["asset_ref"] == by_id[133]["asset_ref"]


def test_icon_catalog_missing_member_is_missing_status():
    rows, assets = _catalog(lambda p: None)               # no client member for any path
    assert all(a["availability"] == "missing" and a["source_asset_sha256"] is None
               for a in assets.rows())
    assert all(r["readiness"] == "unavailable" for r in rows)
