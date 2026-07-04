from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .domain import TalentNode

SCHEMA_VERSION = "coa-normalized-v1"


class RepositoryLoadError(ValueError):
    pass


def _as_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _int_tuple(values: list[Any] | None) -> tuple[int, ...]:
    out: list[int] = []
    for value in values or []:
        parsed = _as_int(value)
        if parsed:
            out.append(parsed)
    return tuple(out)


def node_from_raw(raw: dict[str, Any], source: str) -> TalentNode:
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise RepositoryLoadError(f"{source} has unsupported schema_version {raw.get('schema_version')!r}")
    entry_id = _as_int(raw.get("entry_id"))
    if not entry_id:
        raise RepositoryLoadError(f"{source} missing numeric entry_id")
    return TalentNode(
        entry_id=entry_id,
        spell_id=_as_int(raw.get("spell_id")) or None,
        name=raw.get("name") or "",
        class_id=_as_int(raw.get("class_id")),
        class_name=raw.get("class_name") or "",
        tab_id=_as_int(raw.get("tab_id")),
        tab_name=raw.get("tab_name") or "",
        entry_type=raw.get("entry_type") or "",
        essence_kind=raw.get("essence_kind") or "unknown",
        ae_cost=_as_int(raw.get("ae_cost")),
        te_cost=_as_int(raw.get("te_cost")),
        required_tab_ae=_as_int(raw.get("required_tab_ae")),
        required_tab_te=_as_int(raw.get("required_tab_te")),
        required_level=_as_int(raw.get("required_level")),
        max_rank=max(1, _as_int(raw.get("max_rank"), 1)),
        row=_as_int(raw.get("row")),
        col=_as_int(raw.get("col")),
        node_type=raw.get("node_type") or "",
        is_passive=bool(raw.get("is_passive")),
        is_starting_node=bool(raw.get("is_starting_node")),
        required_ids=_int_tuple(raw.get("required_ids")),
        connected_node_ids=_int_tuple(raw.get("connected_node_ids")),
        tags=tuple(raw.get("tags") or []),
        damage_schools=tuple(raw.get("damage_schools") or []),
        resources=tuple(raw.get("resources") or []),
        description_text=raw.get("description_text") or "",
        source_category=raw.get("source_category") or "",
        availability=dict(raw.get("availability") or {}),
        raw=raw,
    )


class TalentRepository:
    def __init__(self, nodes: list[TalentNode]):
        self._nodes = list(nodes)
        self._by_id = {node.entry_id: node for node in nodes}
        self._by_class: dict[str, list[TalentNode]] = {}
        self._by_name: dict[tuple[str, str], TalentNode] = {}
        for node in nodes:
            self._by_class.setdefault(node.class_name, []).append(node)
            self._by_name[(node.class_name, node.name.casefold())] = node

    @classmethod
    def from_entries(cls, entries_path: Path | str) -> "TalentRepository":
        path = Path(entries_path)
        nodes: list[TalentNode] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RepositoryLoadError(f"{path}:{line_no} invalid JSON: {exc}") from exc
                nodes.append(node_from_raw(raw, f"{path}:{line_no}"))
        return cls(nodes)

    def node_by_id(self, node_id: int) -> TalentNode:
        return self._by_id[node_id]

    def get_node(self, node_id: int) -> TalentNode | None:
        return self._by_id.get(node_id)

    def node_by_name(self, class_name: str, name: str) -> TalentNode:
        return self._by_name[(class_name, name.casefold())]

    def nodes_for_class(self, class_name: str) -> list[TalentNode]:
        return list(self._by_class.get(class_name, []))

    def class_names(self) -> list[str]:
        return sorted(self._by_class)
