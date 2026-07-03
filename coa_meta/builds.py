from __future__ import annotations

from dataclasses import dataclass

from .domain import BuildState, BuildValidationResult, SelectedRank, TalentNode, ValidationIssue
from .repository import TalentRepository


@dataclass(frozen=True)
class BuildConfig:
    class_name: str
    level: int = 60
    max_ae: int = 26
    max_te: int = 25


class BuildRules:
    def __init__(self, repository: TalentRepository, config: BuildConfig):
        self.repository = repository
        self.config = config
        self.nodes = {node.entry_id: node for node in repository.nodes_for_class(config.class_name)}

    def initial_state(self) -> BuildState:
        selected: set[int] = set()
        changed = True
        while changed:
            changed = False
            for node in self.nodes.values():
                if node.entry_id in selected or node.paid or node.required_level > self.config.level:
                    continue
                if all(required_id in selected or required_id not in self.nodes for required_id in node.required_ids):
                    selected.add(node.entry_id)
                    changed = True
        return BuildState(
            class_name=self.config.class_name,
            selected_ranks=tuple(),
            free_node_ids=tuple(sorted(selected)),
            ae_spent=0,
            te_spent=0,
            tab_ae=tuple(),
            tab_te=tuple(),
        )

    def validate(self, selected: list[SelectedRank]) -> BuildValidationResult:
        issues: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        by_id: dict[int, int] = {}

        for item in selected:
            if item.node_id in by_id:
                issues.append(ValidationIssue("duplicate_node", f"Node {item.node_id} selected more than once", item.node_id))
            by_id[item.node_id] = item.rank

        free_ids = set(self.initial_state().free_node_ids)
        selected_ids = set(by_id) | free_ids
        ae_spent = 0
        te_spent = 0
        tab_ae: dict[int, int] = {}
        tab_te: dict[int, int] = {}

        for node_id, rank in by_id.items():
            node = self.repository.get_node(node_id)
            if node is None:
                issues.append(ValidationIssue("unknown_node", f"Unknown node {node_id}", node_id))
                continue
            if node.class_name != self.config.class_name:
                issues.append(ValidationIssue("wrong_class", f"{node.name} belongs to {node.class_name}", node_id))
                continue
            if rank < 1:
                issues.append(
                    ValidationIssue("rank_below_minimum", f"{node.name} rank must be at least 1", node_id, {"rank": rank})
                )
            if rank > node.max_rank:
                issues.append(
                    ValidationIssue(
                        "rank_above_maximum",
                        f"{node.name} rank {rank} exceeds max rank {node.max_rank}",
                        node_id,
                        {"rank": rank, "max_rank": node.max_rank},
                    )
                )
            paid_rank = max(rank, 1)
            ae_spent += node.ae_cost * paid_rank
            te_spent += node.te_cost * paid_rank
            tab_ae[node.tab_id] = tab_ae.get(node.tab_id, 0) + node.ae_cost * paid_rank
            tab_te[node.tab_id] = tab_te.get(node.tab_id, 0) + node.te_cost * paid_rank

        if ae_spent > self.config.max_ae:
            issues.append(
                ValidationIssue(
                    "ae_budget_exceeded",
                    "Ability Essence budget exceeded",
                    None,
                    {"spent": ae_spent, "max": self.config.max_ae},
                )
            )
        if te_spent > self.config.max_te:
            issues.append(
                ValidationIssue(
                    "te_budget_exceeded",
                    "Talent Essence budget exceeded",
                    None,
                    {"spent": te_spent, "max": self.config.max_te},
                )
            )

        for node_id, rank in by_id.items():
            node = self.nodes.get(node_id)
            if node is None:
                continue
            self._validate_node_requirements(node, rank, selected_ids, tab_ae, tab_te, issues)

        state = BuildState(
            class_name=self.config.class_name,
            selected_ranks=tuple(SelectedRank(node_id, by_id[node_id]) for node_id in sorted(by_id)),
            free_node_ids=tuple(sorted(free_ids)),
            ae_spent=ae_spent,
            te_spent=te_spent,
            tab_ae=tuple(sorted(tab_ae.items())),
            tab_te=tuple(sorted(tab_te.items())),
        )
        return BuildValidationResult(valid=not issues, state=state, issues=tuple(issues), warnings=tuple(warnings))

    def can_add(self, state: BuildState, node: TalentNode, rank: int = 1) -> BuildValidationResult:
        selected = list(state.selected_ranks) + [SelectedRank(node.entry_id, rank)]
        return self.validate(selected)

    def add(self, state: BuildState, node: TalentNode, rank: int = 1) -> BuildState:
        result = self.can_add(state, node, rank)
        if not result.valid or result.state is None:
            codes = ", ".join(result.issue_codes())
            raise ValueError(f"Cannot add {node.name}: {codes}")
        return result.state

    def _validate_node_requirements(
        self,
        node: TalentNode,
        rank: int,
        selected_ids: set[int],
        tab_ae: dict[int, int],
        tab_te: dict[int, int],
        issues: list[ValidationIssue],
    ) -> None:
        if node.required_level > self.config.level:
            issues.append(
                ValidationIssue(
                    "level_required",
                    f"{node.name} requires level {node.required_level}",
                    node.entry_id,
                    {"required_level": node.required_level},
                )
            )
        paid_rank = max(rank, 1)
        available_tab_ae = tab_ae.get(node.tab_id, 0) - node.ae_cost * paid_rank
        available_tab_te = tab_te.get(node.tab_id, 0) - node.te_cost * paid_rank
        if available_tab_ae < node.required_tab_ae:
            issues.append(
                ValidationIssue(
                    "tab_ae_gate_unmet",
                    f"{node.name} requires {node.required_tab_ae} AE in {node.tab_name}",
                    node.entry_id,
                    {"available": available_tab_ae, "required": node.required_tab_ae},
                )
            )
        if available_tab_te < node.required_tab_te:
            issues.append(
                ValidationIssue(
                    "tab_te_gate_unmet",
                    f"{node.name} requires {node.required_tab_te} TE in {node.tab_name}",
                    node.entry_id,
                    {"available": available_tab_te, "required": node.required_tab_te},
                )
            )
        for required_id in node.required_ids:
            if required_id in self.nodes and required_id not in selected_ids:
                issues.append(
                    ValidationIssue(
                        "required_node_missing",
                        f"{node.name} requires node {required_id}",
                        node.entry_id,
                        {"required_id": required_id},
                    )
                )
