from __future__ import annotations

from pathlib import Path

from .guide_models import GuideAsset


class GuideAssetCatalog:
    def __init__(self, asset_root: Path | str | None = None):
        self.asset_root = Path(asset_root) if asset_root else None
        self._assets: dict[str, GuideAsset] = {}

    @property
    def assets(self) -> dict[str, GuideAsset]:
        return dict(self._assets)

    def icon_for(self, icon: str | None, label: str) -> GuideAsset:
        slug = _asset_slug((icon or label).split("\\")[-1])
        asset_id = f"icon:{slug or _asset_slug(label) or 'missing'}"
        if asset_id in self._assets:
            return self._assets[asset_id]

        path = self._find_local_icon(slug)
        if path is None:
            asset = GuideAsset(
                asset_id=asset_id,
                kind="icon",
                label=label,
                href=None,
                source="placeholder",
                missing=True,
            )
        else:
            asset = GuideAsset(
                asset_id=asset_id,
                kind="icon",
                label=label,
                href=path.name,
                source="asset_root",
                missing=False,
                source_path=str(path),
            )
        self._assets[asset_id] = asset
        return asset

    def _find_local_icon(self, slug: str) -> Path | None:
        if not slug or self.asset_root is None or not self.asset_root.exists():
            return None
        for path in self.asset_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            if slug in _asset_slug(path.stem):
                return path
        return None


def _asset_slug(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())
