from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GuideMetricDefinition:
    metric_id: str
    label: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class GuideAsset:
    asset_id: str
    kind: str
    label: str
    href: str | None
    source: str
    missing: bool = False
    source_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class GuideTooltip:
    tooltip_id: str
    entry_id: int
    spell_id: int | None
    name: str
    html: str
    text: str
    db_url: str | None
    source: str
    source_confidence: str
    warnings: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "coa-guide-tooltip-v1",
            "tooltip_id": self.tooltip_id,
            "entry_id": self.entry_id,
            "spell_id": self.spell_id,
            "name": self.name,
            "html": self.html,
            "text": self.text,
            "db_url": self.db_url,
            "source": self.source,
            "source_confidence": self.source_confidence,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class GuideNode:
    entry_id: int
    spell_id: int | None
    name: str
    class_name: str
    tab_name: str
    essence_kind: str
    required_level: int
    ae_cost: int
    te_cost: int
    tags: tuple[str, ...]
    active: bool
    db_url: str | None
    tooltip_id: str
    asset: GuideAsset

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["tags"] = list(self.tags)
        data["asset"] = self.asset.to_dict()
        return data


@dataclass(frozen=True)
class GuideBuildCard:
    rank: int
    label: str
    confidence_label: str
    projected_dps_index: float
    node_ids: tuple[int, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "label": self.label,
            "confidence_label": self.confidence_label,
            "projected_dps_index": self.projected_dps_index,
            "node_ids": list(self.node_ids),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class GuideSpec:
    slug: str
    href: str
    class_name: str
    spec_name: str
    role: str
    confidence_label: str
    warning_count: int
    summary: str
    sections: tuple[str, ...]
    builds: tuple[GuideBuildCard, ...]
    nodes: tuple[GuideNode, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "href": self.href,
            "class_name": self.class_name,
            "spec_name": self.spec_name,
            "role": self.role,
            "confidence_label": self.confidence_label,
            "warning_count": self.warning_count,
            "summary": self.summary,
            "sections": list(self.sections),
            "builds": [build.to_dict() for build in self.builds],
            "nodes": [node.to_dict() for node in self.nodes],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class GuideSite:
    schema_version: str
    generated_at: str
    index_path: str
    legacy_index_path: str
    specs: tuple[GuideSpec, ...]
    metric_definitions: dict[str, GuideMetricDefinition]
    tooltips: dict[str, GuideTooltip]
    assets: dict[str, GuideAsset]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "index_path": self.index_path,
            "legacy_index_path": self.legacy_index_path,
            "specs": [spec.to_dict() for spec in self.specs],
            "metric_definitions": {
                key: value.to_dict() for key, value in self.metric_definitions.items()
            },
            "tooltips": {key: value.to_dict() for key, value in self.tooltips.items()},
            "assets": {key: value.to_dict() for key, value in self.assets.items()},
            "warnings": list(self.warnings),
        }
