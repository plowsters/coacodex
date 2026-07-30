# tests/test_guide_icons.py
from coa_meta.guide_assets import GuideAssetCatalog
import coa_meta.guide_assets as ga


def test_no_ascensiondb_icon_url_template():
    assert not hasattr(ga, "ASCENSIONDB_ICON_URL_TEMPLATE")


def test_absent_client_icon_is_placeholder_not_remote():
    cat = GuideAssetCatalog(icon_catalog={})            # empty client catalog
    asset = cat.icon_for(icon="Spell_Fire_Fireball", label="Fireball", spell_id=133)
    assert asset.source == "placeholder" and asset.missing is True
    assert asset.href is None or not str(asset.href).startswith("http")


def test_a_referenced_client_asset_still_renders_a_placeholder():
    """E0R.2 T2.5 prohibited `converted`, and T6.3 normalized the catalog so an association carries no
    status at all. A verified client BLP is not browser-renderable, so every row is a placeholder —
    what must never happen is a fallthrough to a remote or cached-DB image."""
    cat = GuideAssetCatalog(
        icon_catalog={133: {"spell_id": 133, "asset_ref": "a" * 32, "readiness": "available"}},
        icon_assets={"a" * 32: {"asset_id": "a" * 32, "availability": "source_only",
                                "client_path": "interface/icons/spell_fire_fireball.blp"}})
    asset = cat.icon_for(icon=None, label="Fireball", spell_id=133)
    assert asset.source == "placeholder" and asset.href is None
    assert "db.ascension.gg" not in str(asset.href or "")


def test_missing_client_row_never_constructs_a_remote_url():
    cat = GuideAssetCatalog(icon_catalog={999: {"spell_id": 999, "asset_ref": None,
                                                "readiness": "unavailable"}})
    asset = cat.icon_for(icon="Interface\\Icons\\Whatever", label="Whatever", spell_id=999)
    assert asset.source == "placeholder" and asset.href is None


def test_no_client_catalog_yields_placeholders_not_remote():
    cat = GuideAssetCatalog()                            # no catalog at all
    asset = cat.icon_for(icon="Interface\\Icons\\Shared_Strike", label="Shared Strike", spell_id=5)
    assert asset.source == "placeholder" and asset.missing is True
