from __future__ import annotations

from pathlib import Path

from coa_meta.guide_assets import GuideAssetCatalog


def test_icon_placeholder_is_deterministic_without_asset_root():
    catalog = GuideAssetCatalog()

    asset = catalog.icon_for("Interface\\Icons\\Shared_Strike", "Shared Strike")

    assert asset.asset_id == "icon:sharedstrike"
    assert asset.href is None
    assert asset.missing is True
    assert asset.source == "placeholder"


def test_icon_resolves_matching_local_file(tmp_path: Path):
    icon = tmp_path / "Shared_Strike.png"
    icon.write_bytes(b"fake")
    catalog = GuideAssetCatalog(asset_root=tmp_path)

    asset = catalog.icon_for("Interface\\Icons\\Shared_Strike", "Shared Strike")

    assert asset.asset_id == "icon:sharedstrike"
    assert asset.href == "Shared_Strike.png"
    assert asset.missing is False
    assert asset.source == "asset_root"


def test_icon_prefers_explicit_db_asset_path():
    catalog = GuideAssetCatalog()

    asset = catalog.icon_for(
        "Interface\\Icons\\Fallback",
        "Damage Talent",
        local_path="dist/assets/icons/spell_nature_poison.png",
    )

    assert asset.asset_id == "icon:spellnaturepoison"
    assert asset.href == "icons/spell_nature_poison.png"
    assert asset.missing is False
    assert asset.source == "ascension_db_asset"
    assert asset.source_path == "dist/assets/icons/spell_nature_poison.png"
