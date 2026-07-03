from __future__ import annotations

from dataclasses import dataclass

from .builds import BuildRules
from .domain import BuildValidationResult
from .repository import TalentRepository


@dataclass(frozen=True)
class BuildSearchConfig:
    top: int = 10
    beam_width: int = 10
    branch_width: int = 40
    require_budget_fraction: float = 0.0


class BuildSearcher:
    def __init__(self, repository: TalentRepository, rules: BuildRules):
        self.repository = repository
        self.rules = rules

    def search(self, config: BuildSearchConfig) -> list[BuildValidationResult]:
        start = self.rules.initial_state()
        paid_nodes = [node for node in self.rules.nodes.values() if node.paid]
        beam = [start]
        seen = {tuple()}
        results: list[BuildValidationResult] = [BuildValidationResult(True, start, tuple())]
        max_steps = max(1, self.rules.config.max_ae + self.rules.config.max_te)

        for _ in range(max_steps):
            candidates: list[BuildValidationResult] = []
            for state in beam:
                legal_added: list[BuildValidationResult] = []
                for node in paid_nodes:
                    if node.entry_id in state.selected_ids:
                        continue
                    result = self.rules.can_add(state, node, 1)
                    if result.valid and result.state is not None:
                        key = tuple(sorted((rank.node_id, rank.rank) for rank in result.state.selected_ranks))
                        if key in seen:
                            continue
                        seen.add(key)
                        legal_added.append(result)
                legal_added.sort(key=self._search_score, reverse=True)
                candidates.extend(legal_added[: config.branch_width])
            if not candidates:
                break
            candidates.sort(key=self._search_score, reverse=True)
            beam = [item.state for item in candidates[: config.beam_width] if item.state is not None]
            results.extend(candidates)

        max_budget = self.rules.config.max_ae + self.rules.config.max_te
        min_spend = max_budget * config.require_budget_fraction
        filtered = [item for item in results if item.state and item.state.ae_spent + item.state.te_spent >= min_spend]
        filtered.sort(key=self._search_score, reverse=True)
        return filtered[: config.top]

    def _search_score(self, result: BuildValidationResult) -> float:
        if result.state is None:
            return -1.0
        return result.state.ae_spent + result.state.te_spent + len(result.state.selected_ranks) * 0.01
