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


def test_source_only_renders_placeholder_and_converted_renders_asset():
    # source_only (BLP verified but not browser-renderable) -> placeholder, NOT an asset_root fallthrough
    src = GuideAssetCatalog(icon_catalog={133: {"client_path": "Interface/Icons/Spell_Fire_Fireball.blp",
                                                "asset_status": "source_only"}})
    a1 = src.icon_for(icon=None, label="Fireball", spell_id=133)
    assert a1.source == "placeholder" and "db.ascension.gg" not in str(a1.href or "")
    # converted -> the bundle asset is rendered from the client catalog
    conv = GuideAssetCatalog(icon_catalog={133: {"client_path": "Interface/Icons/Spell_Fire_Fireball.blp",
                                                 "asset_status": "converted", "converted_ref": "icons.tar#fireball.png"}})
    a2 = conv.icon_for(icon=None, label="Fireball", spell_id=133)
    assert a2.source == "client_icon" and a2.href == "icons.tar#fireball.png"
    assert "db.ascension.gg" not in str(a2.href or "")


def test_missing_client_row_never_constructs_a_remote_url():
    cat = GuideAssetCatalog(icon_catalog={999: {"client_path": None, "asset_status": "missing"}})
    asset = cat.icon_for(icon="Interface\\Icons\\Whatever", label="Whatever", spell_id=999)
    assert asset.source == "placeholder" and asset.href is None


def test_no_client_catalog_yields_placeholders_not_remote():
    cat = GuideAssetCatalog()                            # no catalog at all
    asset = cat.icon_for(icon="Interface\\Icons\\Shared_Strike", label="Shared Strike", spell_id=5)
    assert asset.source == "placeholder" and asset.missing is True
