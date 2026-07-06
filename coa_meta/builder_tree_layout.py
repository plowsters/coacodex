from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BUILDER_TREE_LAYOUT_SCHEMA_VERSION = "coa-builder-tree-layout-v1"
BUILDER_TREE_KINDS = ("ability_essence", "talent_essence", "level_passives")


@dataclass(frozen=True)
class BuilderLayoutBounds:
    x: float
    y: float
    width: float
    height: float

    def to_dict(self) -> dict[str, float]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class BuilderLayoutNode:
    entry_id: int
    spell_id: int | None
    name: str
    x: float
    y: float
    width: float
    height: float
    tree_kind: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class BuilderLayoutEdge:
    source_entry_id: int
    target_entry_id: int
    kind: str = "requires"

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class BuilderLayoutTree:
    tree_kind: str
    layout_source: str
    bounds: BuilderLayoutBounds
    nodes: tuple[BuilderLayoutNode, ...]
    edges: tuple[BuilderLayoutEdge, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tree_kind": self.tree_kind,
            "layout_source": self.layout_source,
            "bounds": self.bounds.to_dict(),
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


@dataclass(frozen=True)
class BuilderTreeLayout:
    schema_version: str
    class_name: str
    source_spec_name: str
    display_spec_name: str
    layout_source: str
    trees: tuple[BuilderLayoutTree, ...]
    captured_at: str = ""
    source_url: str = ""
    viewport: dict[str, Any] | None = None
    warnings: tuple[str, ...] = tuple()

    def tree_by_kind(self, tree_kind: str) -> BuilderLayoutTree | None:
        for tree in self.trees:
            if tree.tree_kind == tree_kind:
                return tree
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "class_name": self.class_name,
            "source_spec_name": self.source_spec_name,
            "display_spec_name": self.display_spec_name,
            "captured_at": self.captured_at,
            "source_url": self.source_url,
            "layout_source": self.layout_source,
            "viewport": dict(self.viewport or {}),
            "trees": [tree.to_dict() for tree in self.trees],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class BuilderTreeLayoutCollection:
    layouts: tuple[BuilderTreeLayout, ...]

    def layout_for(self, class_name: str, source_spec_name: str) -> BuilderTreeLayout | None:
        class_key = class_name.casefold()
        spec_key = source_spec_name.casefold()
        for layout in self.layouts:
            if layout.class_name.casefold() == class_key and layout.source_spec_name.casefold() == spec_key:
                return layout
        return None


def load_builder_tree_layout(path: Path | str) -> BuilderTreeLayout:
    source_path = Path(path)
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    return _parse_layout(raw, source_path=source_path)


def load_builder_tree_layouts(root: Path | str) -> BuilderTreeLayoutCollection:
    root_path = Path(root)
    if root_path.is_file():
        return BuilderTreeLayoutCollection((load_builder_tree_layout(root_path),))
    layouts: list[BuilderTreeLayout] = []
    for path in sorted(root_path.glob("*.json")):
        if not path.is_file():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != BUILDER_TREE_LAYOUT_SCHEMA_VERSION:
            continue
        layouts.append(_parse_layout(raw, source_path=path))
    return BuilderTreeLayoutCollection(tuple(layouts))


def _parse_layout(raw: dict[str, Any], *, source_path: Path) -> BuilderTreeLayout:
    schema_version = str(raw.get("schema_version") or "")
    if schema_version != BUILDER_TREE_LAYOUT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported builder tree layout schema {schema_version!r} in {source_path}; "
            f"expected {BUILDER_TREE_LAYOUT_SCHEMA_VERSION!r}"
        )
    trees = tuple(_parse_tree(tree, source_path=source_path) for tree in raw.get("trees", []))
    return BuilderTreeLayout(
        schema_version=schema_version,
        class_name=str(raw.get("class_name") or ""),
        source_spec_name=str(raw.get("source_spec_name") or ""),
        display_spec_name=str(raw.get("display_spec_name") or raw.get("source_spec_name") or ""),
        captured_at=str(raw.get("captured_at") or ""),
        source_url=str(raw.get("source_url") or ""),
        layout_source=str(raw.get("layout_source") or "unknown"),
        viewport=dict(raw.get("viewport") or {}),
        trees=trees,
        warnings=tuple(str(warning) for warning in raw.get("warnings", [])),
    )


def _parse_tree(raw: dict[str, Any], *, source_path: Path) -> BuilderLayoutTree:
    tree_kind = str(raw.get("tree_kind") or "")
    if tree_kind not in BUILDER_TREE_KINDS:
        raise ValueError(
            f"Unsupported builder tree kind {tree_kind!r} in {source_path}; "
            f"expected one of {', '.join(BUILDER_TREE_KINDS)}"
        )
    bounds = _parse_bounds(dict(raw.get("bounds") or {}))
    return BuilderLayoutTree(
        tree_kind=tree_kind,
        layout_source=str(raw.get("layout_source") or "unknown"),
        bounds=bounds,
        nodes=tuple(_parse_node(node, tree_kind=tree_kind) for node in raw.get("nodes", [])),
        edges=tuple(_parse_edge(edge) for edge in raw.get("edges", [])),
    )


def _parse_bounds(raw: dict[str, Any]) -> BuilderLayoutBounds:
    return BuilderLayoutBounds(
        x=float(raw.get("x", 0)),
        y=float(raw.get("y", 0)),
        width=float(raw.get("width", 0)),
        height=float(raw.get("height", 0)),
    )


def _parse_node(raw: dict[str, Any], *, tree_kind: str) -> BuilderLayoutNode:
    spell_id = raw.get("spell_id")
    return BuilderLayoutNode(
        entry_id=int(raw["entry_id"]),
        spell_id=int(spell_id) if spell_id is not None else None,
        name=str(raw.get("name") or ""),
        x=float(raw.get("x", 0)),
        y=float(raw.get("y", 0)),
        width=float(raw.get("width", 0)),
        height=float(raw.get("height", 0)),
        tree_kind=tree_kind,
    )


def _parse_edge(raw: dict[str, Any]) -> BuilderLayoutEdge:
    return BuilderLayoutEdge(
        source_entry_id=int(raw["source_entry_id"]),
        target_entry_id=int(raw["target_entry_id"]),
        kind=str(raw.get("kind") or "requires"),
    )
