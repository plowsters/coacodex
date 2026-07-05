from __future__ import annotations

from pathlib import Path

from .guide_assets import GuideAssetCatalog
from .guide_models import (
    GuideBuildCard,
    GuideMetricDefinition,
    GuideNode,
    GuideSite,
    GuideSpec,
)
from .guide_tooltips import build_node_tooltip, load_db_tooltip_rows
from .reporting import MetaReport, slugify_key
from .repository import TalentRepository

GUIDE_SITE_SCHEMA_VERSION = "coa-guide-site-v1"
GUIDE_SECTIONS = (
    "Overview",
    "Recommended Builds",
    "Talents",
    "Rotation",
    "Stats",
    "Weapons and Armor",
    "Abilities and Talents",
    "Warnings",
    "Data Notes",
)


def build_guide_site(
    report: MetaReport,
    *,
    entries_path: Path | str,
    db_tooltips_path: Path | str | None = None,
    asset_root: Path | str | None = None,
) -> GuideSite:
    data = report.to_dict()
    repository = TalentRepository.from_entries(entries_path)
    db_rows = load_db_tooltip_rows(db_tooltips_path)
    assets = GuideAssetCatalog(asset_root)
    tooltips = {}
    specs = []

    for result in data["spec_results"]:
        class_name = result["class_name"]
        spec_name = result["spec_name"]
        slug = f"{slugify_key(class_name)}-{slugify_key(spec_name)}"
        relevant_nodes = [
            node for node in repository.nodes_for_class(class_name)
            if node.tab_name in {"Class", spec_name}
        ]
        guide_nodes = []
        for node in sorted(relevant_nodes, key=lambda item: (item.tab_name != "Class", item.row, item.col, item.name)):
            tooltip = build_node_tooltip(node, db_rows)
            tooltips[tooltip.tooltip_id] = tooltip
            asset = assets.icon_for(node.raw.get("icon") or node.raw.get("iconPath") or node.name, node.name)
            guide_nodes.append(
                GuideNode(
                    entry_id=node.entry_id,
                    spell_id=node.spell_id,
                    name=node.name,
                    class_name=node.class_name,
                    tab_name=node.tab_name,
                    essence_kind=node.essence_kind,
                    required_level=node.required_level,
                    ae_cost=node.ae_cost,
                    te_cost=node.te_cost,
                    tags=tuple(node.tags),
                    active=not node.is_passive,
                    db_url=tooltip.db_url,
                    tooltip_id=tooltip.tooltip_id,
                    asset=asset,
                )
            )

        builds = tuple(_build_cards(result))
        warnings = tuple(result.get("warnings", []))
        confidence = builds[0].confidence_label if builds else "low"
        specs.append(
            GuideSpec(
                slug=slug,
                href=f"specs/{slug}.html",
                class_name=class_name,
                spec_name=spec_name,
                role=result["role"],
                confidence_label=confidence,
                warning_count=len(warnings),
                summary=_summary_text(result),
                sections=GUIDE_SECTIONS if warnings else tuple(section for section in GUIDE_SECTIONS if section != "Warnings"),
                builds=builds,
                nodes=tuple(guide_nodes),
                warnings=warnings,
            )
        )

    return GuideSite(
        schema_version=GUIDE_SITE_SCHEMA_VERSION,
        generated_at=data["generated_at"],
        index_path="index.html",
        legacy_index_path="meta-report.html",
        specs=tuple(specs),
        metric_definitions=_metric_definitions(),
        tooltips=tooltips,
        assets=assets.assets,
        warnings=tuple(data.get("warnings", [])),
    )


def _build_cards(result: dict) -> list[GuideBuildCard]:
    cards = []
    for build in result.get("top_builds", []):
        node_ids = tuple(node["node_id"] for node in build.get("selected_nodes", []))
        cards.append(
            GuideBuildCard(
                rank=int(build["rank"]),
                label=f"Build {build['rank']}",
                confidence_label=str(build["confidence_label"]),
                projected_dps_index=float(build["projected_dps_index"]),
                node_ids=node_ids,
                warnings=tuple(build.get("warnings", [])),
            )
        )
    return cards


def _summary_text(result: dict) -> str:
    strengths = result.get("summary", {}).get("strengths") or []
    if strengths:
        return str(strengths[0])
    return "Early theorycraft guide generated from normalized CoA builder data."


def _metric_definitions() -> dict[str, GuideMetricDefinition]:
    return {
        "projected_dps_index": GuideMetricDefinition(
            metric_id="projected_dps_index",
            label="Projected DPS Index",
            description="A relative theorycraft score. It is not observed DPS, simulated DPS, or a log parse.",
        ),
        "confidence": GuideMetricDefinition(
            metric_id="confidence",
            label="Confidence",
            description="How much source data supports this recommendation. Low confidence means the guide is using more tooltip inference.",
        ),
    }
