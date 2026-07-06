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

    def icon_for(self, icon: str | None, label: str, *, local_path: str | None = None) -> GuideAsset:
        if local_path:
            return self._asset_from_local_path(icon, label, local_path)

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

    def _asset_from_local_path(self, icon: str | None, label: str, local_path: str) -> GuideAsset:
        href = _asset_href(local_path, self.asset_root)
        slug = _asset_slug(Path(href).stem or (icon or label).split("\\")[-1])
        asset_id = f"icon:{slug or _asset_slug(label) or 'missing'}"
        if asset_id in self._assets:
            return self._assets[asset_id]

        asset = GuideAsset(
            asset_id=asset_id,
            kind="icon",
            label=label,
            href=href,
            source="ascension_db_asset",
            missing=False,
            source_path=str(local_path),
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


def _asset_href(local_path: str, asset_root: Path | None) -> str:
    path = Path(local_path)
    if asset_root:
        try:
            return path.relative_to(asset_root).as_posix()
        except ValueError:
            pass
    parts = path.as_posix().split("/")
    if "assets" in parts:
        index = len(parts) - 1 - parts[::-1].index("assets")
        return "/".join(parts[index + 1 :])
    return path.name
