from __future__ import annotations

import json
from pathlib import Path

from .guide_builder import build_guide_site
from .guide_rendering import GUIDE_CSS, GUIDE_JS, render_index_html, render_spec_html
from .reporting import MetaReport


def render_guide_index_html(
    report: MetaReport,
    *,
    entries_path: Path | str,
    db_tooltips_path: Path | str | None = None,
    asset_root: Path | str | None = None,
    builder_layout_root: Path | str | None = None,
) -> str:
    site = build_guide_site(
        report,
        entries_path=entries_path,
        db_tooltips_path=db_tooltips_path,
        asset_root=asset_root,
        builder_layout_root=builder_layout_root,
    )
    return render_index_html(site)


def write_guide_site(
    report: MetaReport,
    out_dir: Path | str,
    *,
    entries_path: Path | str,
    db_tooltips_path: Path | str | None = None,
    asset_root: Path | str | None = None,
    builder_layout_root: Path | str | None = None,
) -> tuple[Path, ...]:
    output_dir = Path(out_dir)
    site = build_guide_site(
        report,
        entries_path=entries_path,
        db_tooltips_path=db_tooltips_path,
        asset_root=asset_root,
        builder_layout_root=builder_layout_root,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    asset_dir = output_dir / "assets"
    spec_dir = output_dir / "specs"
    asset_dir.mkdir(parents=True, exist_ok=True)
    spec_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    index_html = render_index_html(site)
    for name in (site.index_path, site.legacy_index_path):
        path = output_dir / name
        path.write_text(index_html, encoding="utf-8")
        written.append(path)

    css_path = asset_dir / "guide.css"
    css_path.write_text(GUIDE_CSS.strip() + "\n", encoding="utf-8")
    written.append(css_path)

    js_path = asset_dir / "guide.js"
    js_path.write_text(GUIDE_JS.strip() + "\n", encoding="utf-8")
    written.append(js_path)

    tooltip_path = asset_dir / "tooltip-catalog.json"
    tooltip_path.write_text(
        json.dumps({key: value.to_dict() for key, value in site.tooltips.items()}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    written.append(tooltip_path)

    manifest_path = asset_dir / "guide-site-manifest.json"
    manifest_path.write_text(json.dumps(site.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    written.append(manifest_path)

    for spec in site.specs:
        path = output_dir / spec.href
        path.write_text(render_spec_html(site, spec), encoding="utf-8")
        written.append(path)

    return tuple(written)
