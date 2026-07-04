from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EssenceKind = Literal["ability", "talent", "unknown"]


@dataclass(frozen=True)
class TalentNode:
    entry_id: int
    spell_id: int | None
    name: str
    class_id: int
    class_name: str
    tab_id: int
    tab_name: str
    entry_type: str
    essence_kind: EssenceKind
    ae_cost: int
    te_cost: int
    required_tab_ae: int
    required_tab_te: int
    required_level: int
    max_rank: int
    row: int
    col: int
    node_type: str
    is_passive: bool
    is_starting_node: bool
    required_ids: tuple[int, ...]
    connected_node_ids: tuple[int, ...]
    tags: tuple[str, ...]
    damage_schools: tuple[str, ...]
    resources: tuple[str, ...]
    description_text: str
    source_category: str = ""
    availability: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)
    raw: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    @property
    def paid(self) -> bool:
        return self.ae_cost > 0 or self.te_cost > 0


@dataclass(frozen=True)
class SelectedRank:
    node_id: int
    rank: int = 1


@dataclass(frozen=True)
class BuildState:
    class_name: str
    selected_ranks: tuple[SelectedRank, ...]
    free_node_ids: tuple[int, ...]
    ae_spent: int
    te_spent: int
    tab_ae: tuple[tuple[int, int], ...]
    tab_te: tuple[tuple[int, int], ...]

    @property
    def selected_ids(self) -> frozenset[int]:
        return frozenset(rank.node_id for rank in self.selected_ranks) | frozenset(self.free_node_ids)

    def rank_for(self, node_id: int) -> int:
        for selected in self.selected_ranks:
            if selected.node_id == node_id:
                return selected.rank
        return 1 if node_id in self.free_node_ids else 0

    def tab_ae_map(self) -> dict[int, int]:
        return dict(self.tab_ae)

    def tab_te_map(self) -> dict[int, int]:
        return dict(self.tab_te)

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_name": self.class_name,
            "selected_ranks": [{"node_id": rank.node_id, "rank": rank.rank} for rank in self.selected_ranks],
            "free_node_ids": list(self.free_node_ids),
            "ae_spent": self.ae_spent,
            "te_spent": self.te_spent,
            "tab_ae": dict(self.tab_ae),
            "tab_te": dict(self.tab_te),
        }


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    node_id: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildValidationResult:
    valid: bool
    state: BuildState | None
    issues: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...] = tuple()

    def issue_codes(self) -> list[str]:
        return [issue.code for issue in self.issues]
