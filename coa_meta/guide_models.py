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
class GuideNodeGate:
    node_id: int
    state: str
    reasons: tuple[str, ...]
    issue_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "state": self.state,
            "reasons": list(self.reasons),
            "issue_codes": list(self.issue_codes),
        }


@dataclass(frozen=True)
class GuideTreeEdge:
    source_id: int
    target_id: int
    kind: str
    state: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class GuideTreeSnapshot:
    level: int
    max_ae: int
    max_te: int
    ae_spent: int
    te_spent: int
    selected_node_ids: tuple[int, ...]
    free_node_ids: tuple[int, ...]
    available_node_ids: tuple[int, ...]
    gated_nodes: tuple[GuideNodeGate, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "max_ae": self.max_ae,
            "max_te": self.max_te,
            "ae_spent": self.ae_spent,
            "te_spent": self.te_spent,
            "selected_node_ids": list(self.selected_node_ids),
            "free_node_ids": list(self.free_node_ids),
            "available_node_ids": list(self.available_node_ids),
            "gated_nodes": [node.to_dict() for node in self.gated_nodes],
        }


@dataclass(frozen=True)
class GuideTree:
    tree_id: str
    class_name: str
    spec_name: str
    build_rank: int
    build_label: str
    level: int
    max_ae: int
    max_te: int
    ae_spent: int
    te_spent: int
    rows: int
    cols: int
    nodes: tuple["GuideNode", ...]
    edges: tuple[GuideTreeEdge, ...]
    snapshots: tuple[GuideTreeSnapshot, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "coa-guide-tree-v1",
            "tree_id": self.tree_id,
            "class_name": self.class_name,
            "spec_name": self.spec_name,
            "build_rank": self.build_rank,
            "build_label": self.build_label,
            "level": self.level,
            "max_ae": self.max_ae,
            "max_te": self.max_te,
            "ae_spent": self.ae_spent,
            "te_spent": self.te_spent,
            "rows": self.rows,
            "cols": self.cols,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "snapshots": [snapshot.to_dict() for snapshot in self.snapshots],
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
    row: int | None = None
    col: int | None = None
    node_type: str = "SpendCircle"
    max_rank: int = 1
    rank: int = 0
    selected: bool = False
    free: bool = False
    required_ids: tuple[int, ...] = tuple()
    connected_node_ids: tuple[int, ...] = tuple()
    required_tab_ae: int = 0
    required_tab_te: int = 0
    availability_confidence: str = "unknown"
    source_level: int | None = None
    tooltip_required_level: int | None = None
    tree_state: str = "inactive"
    gate_reasons: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["tags"] = list(self.tags)
        data["required_ids"] = list(self.required_ids)
        data["connected_node_ids"] = list(self.connected_node_ids)
        data["gate_reasons"] = list(self.gate_reasons)
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
    playstyle_label: str = ""
    selection_reason: str = ""
    performance_band: str = ""
    reliability_label: str = ""
    rotation_loop: dict[str, Any] | None = None
    stat_priority_report: dict[str, Any] | None = None
    gear_recommendation_report: dict[str, Any] | None = None
    tree: GuideTree | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "label": self.label,
            "confidence_label": self.confidence_label,
            "projected_dps_index": self.projected_dps_index,
            "node_ids": list(self.node_ids),
            "warnings": list(self.warnings),
            "playstyle_label": self.playstyle_label,
            "selection_reason": self.selection_reason,
            "performance_band": self.performance_band,
            "reliability_label": self.reliability_label,
            "rotation_loop": dict(self.rotation_loop or {}),
            "stat_priority_report": dict(self.stat_priority_report or {}),
            "gear_recommendation_report": dict(self.gear_recommendation_report or {}),
            "tree": self.tree.to_dict() if self.tree else None,
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
    role_provenance: dict[str, Any] | None = None

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
            "role_provenance": dict(self.role_provenance or {}),
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
