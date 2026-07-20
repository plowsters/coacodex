from __future__ import annotations

from pathlib import Path

from .guide_models import GuideAsset


class GuideAssetCatalog:
    """Resolves spell icons ONLY from the client-native coa-client-spell-icons-v1 catalog (keyed by
    spell_id). A `converted` row — a client BLP converted to a browser-renderable bundle asset — renders
    that asset (`source="client_icon"`); a `source_only`/`missing`/absent row renders a placeholder. It
    NEVER constructs a db.ascension.gg URL and NEVER falls through to a generic asset_root search that
    could resurrect a cached AscensionDB image (E0R AscensionDB sunset)."""

    def __init__(self, icon_catalog: dict | None = None, asset_root: Path | str | None = None):
        self.icon_catalog = {int(k): v for k, v in (icon_catalog or {}).items()}
        self.asset_root = Path(asset_root) if asset_root else None
        self._assets: dict[str, GuideAsset] = {}

    @property
    def assets(self) -> dict[str, GuideAsset]:
        return dict(self._assets)

    def icon_for(self, icon: str | None = None, label: str = "", *, spell_id: int | None = None,
                 local_path: str | None = None) -> GuideAsset:
        row = self.icon_catalog.get(int(spell_id)) if spell_id is not None else None
        slug = _asset_slug((icon or label or "").split("\\")[-1])
        asset_id = f"icon:{slug or _asset_slug(label) or 'missing'}"
        if asset_id in self._assets:
            return self._assets[asset_id]

        if row and row.get("asset_status") == "converted" and row.get("converted_ref"):
            asset = GuideAsset(
                asset_id=asset_id, kind="icon", label=label,
                href=row["converted_ref"], source="client_icon", missing=False,
                source_path=row.get("client_path"),
            )
        else:
            # source_only (a verified client BLP that is not itself browser-renderable), missing, or no
            # client row at all -> a placeholder, NEVER a remote/cached-DB image.
            asset = GuideAsset(
                asset_id=asset_id, kind="icon", label=label,
                href=None, source="placeholder", missing=True,
            )
        self._assets[asset_id] = asset
        return asset


def _asset_slug(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())
