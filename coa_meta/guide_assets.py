from __future__ import annotations

from pathlib import Path

from .guide_models import GuideAsset


class GuideAssetCatalog:
    """Resolves spell icons ONLY from the client-native icon catalog (keyed by spell_id). Every row
    renders a PLACEHOLDER: a client BLP is not browser-renderable, and nothing may construct a remote DB
    URL or fall through to a generic asset_root search that could resurrect a cached AscensionDB image
    (E0R AscensionDB sunset).

    E0R.2 T2.5 prohibited the one status that rendered anything else (`converted`), leaving that branch
    dead; T6.3 then normalized the catalog into an association row plus an asset table, and the
    association carries no `asset_status` at all. So the branch is gone rather than kept as a
    now-unreachable special case — the readiness of a client asset is recorded, and rendering it is a
    separate capability that does not exist yet.

    `icon_assets` (optional) is the asset child keyed by `asset_id`; it is what a future renderer would
    resolve a reference through, and holding it here is what makes that a wiring change rather than a
    redesign."""

    def __init__(self, icon_catalog: dict | None = None, asset_root: Path | str | None = None,
                 icon_assets: dict | None = None):
        self.icon_catalog = {int(k): v for k, v in (icon_catalog or {}).items()}
        self.icon_assets = dict(icon_assets or {})
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

        # A verified client BLP is not browser-renderable, and neither a missing asset nor an absent row
        # is renderable either -> a placeholder, NEVER a remote/cached-DB image. `row` is consulted so a
        # caller passing the catalog gets the same answer as one that does not, which is what makes the
        # AscensionDB sunset a property of this class rather than of its inputs.
        _ = row
        asset = GuideAsset(
            asset_id=asset_id, kind="icon", label=label,
            href=None, source="placeholder", missing=True,
        )
        self._assets[asset_id] = asset
        return asset


def _asset_slug(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())
