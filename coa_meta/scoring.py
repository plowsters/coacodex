from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .domain import BuildState, TalentNode
from .profiles import ScoringProfile
from .repository import TalentRepository


@dataclass(frozen=True)
class ScoreComponent:
    kind: str
    key: str
    value: float
    node_id: int | None = None
    reason: str = ""


@dataclass(frozen=True)
class ScoredBuild:
    source: str
    projected_dps_index: float
    raw_score: float
    confidence: str
    uncertainty: dict[str, float]
    components: tuple[ScoreComponent, ...]
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "projected_dps_index": self.projected_dps_index,
            "raw_score": self.raw_score,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "components": [component.__dict__ for component in self.components],
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
        }


class TheoryScorer:
    def __init__(self, profile: ScoringProfile):
        self.profile = profile
        self._compiled_regex = [
            (re.compile(item["pattern"], flags=re.IGNORECASE), float(item["weight"]), item.get("reason", item["pattern"]))
            for item in profile.regex_boosts
        ]

    def score_build(self, state: BuildState, repository: TalentRepository) -> ScoredBuild:
        components: list[ScoreComponent] = []
        selected_nodes = [repository.get_node(node_id) for node_id in state.selected_ids]
        nodes = [node for node in selected_nodes if node is not None]
        for node in nodes:
            components.extend(self.score_node(node))
        components.extend(self._score_named_sets(nodes, self.profile.synergies, "synergy"))
        components.extend(self._score_named_sets(nodes, self.profile.anti_synergies, "anti_synergy"))
        raw_score = sum(component.value for component in components)
        projected = round(self.profile.baseline_index + raw_score, 2)
        confidence = self._confidence(nodes)
        spread = {"high": 8.0, "medium": 14.0, "low": 22.0}[confidence]
        uncertainty = {
            "low": round(projected * (1.0 - spread / 100.0), 2),
            "mid": projected,
            "high": round(projected * (1.0 + spread / 100.0), 2),
        }
        return ScoredBuild(
            source="theorycraft",
            projected_dps_index=projected,
            raw_score=round(raw_score, 2),
            confidence=confidence,
            uncertainty=uncertainty,
            components=tuple(components),
            assumptions=self.profile.assumptions,
            warnings=tuple(),
        )

    def score_node(self, node: TalentNode) -> list[ScoreComponent]:
        components: list[ScoreComponent] = []
        self._add_weight(
            components,
            "tab",
            node.tab_name,
            self.profile.weights.get("tabs", {}).get(node.tab_name, 0.0),
            node.entry_id,
            f"tab:{node.tab_name}",
        )
        for tag in node.tags:
            self._add_weight(
                components,
                "tag",
                tag,
                self.profile.weights.get("tags", {}).get(tag, 0.0),
                node.entry_id,
                f"tag:{tag}",
            )
        for school in node.damage_schools:
            self._add_weight(
                components,
                "school",
                school,
                self.profile.weights.get("schools", {}).get(school, 0.0),
                node.entry_id,
                f"school:{school}",
            )
        for resource in node.resources:
            self._add_weight(
                components,
                "resource",
                resource,
                self.profile.weights.get("resources", {}).get(resource, 0.0),
                node.entry_id,
                f"resource:{resource}",
            )
        text = f"{node.name}\n{node.description_text}"
        text_lower = text.lower()
        for name, weight in self.profile.named_boosts.items():
            if name.lower() in text_lower:
                self._add_weight(components, "named", name, weight, node.entry_id, f"name/text:{name}")
        for pattern, weight, reason in self._compiled_regex:
            if pattern.search(text):
                self._add_weight(components, "regex", pattern.pattern, weight, node.entry_id, reason)
        return components

    def _score_named_sets(self, nodes: list[TalentNode], sets: tuple[dict[str, Any], ...], kind: str) -> list[ScoreComponent]:
        names = {node.name for node in nodes}
        components: list[ScoreComponent] = []
        for item in sets:
            required = set(item.get("names", []))
            if required and required.issubset(names):
                components.append(
                    ScoreComponent(
                        kind=kind,
                        key="+".join(sorted(required)),
                        value=float(item.get("weight", 0.0)),
                        reason=item.get("reason", ""),
                    )
                )
        return components

    def _confidence(self, nodes: list[TalentNode]) -> str:
        base = self.profile.confidence.get("base", "medium")
        if base == "high" and self.profile.class_name != "*":
            return "high"
        inferred_heavy = sum(1 for node in nodes if not node.tags and not node.damage_schools and not node.resources)
        if inferred_heavy > max(3, len(nodes) // 2):
            return "low"
        return base if base in {"low", "medium", "high"} else "medium"

    @staticmethod
    def _add_weight(
        components: list[ScoreComponent],
        kind: str,
        key: str,
        value: float,
        node_id: int,
        reason: str,
    ) -> None:
        if value:
            components.append(ScoreComponent(kind=kind, key=key, value=float(value), node_id=node_id, reason=reason))
