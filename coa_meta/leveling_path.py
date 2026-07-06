from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .domain import TalentNode

LEVELING_PATH_SCHEMA_VERSION = "coa-leveling-path-v1"


@dataclass(frozen=True)
class EssenceAward:
    level: int
    essence_kind: str
    amount: int = 1

    def to_dict(self) -> dict[str, int | str]:
        return {"level": self.level, "essence_kind": self.essence_kind, "amount": self.amount}


def essence_kind_for_level(level: int) -> str:
    if level < 10 or level > 60:
        raise ValueError("CoA leveling essence awards are defined for levels 10 through 60")
    return "ability" if level % 2 == 0 else "talent"


def essence_awards_for_levels(start_level: int = 10, max_level: int = 60) -> tuple[EssenceAward, ...]:
    if start_level < 10 or max_level > 60 or start_level > max_level:
        raise ValueError("Expected a level range within 10..60")
    return tuple(
        EssenceAward(level=level, essence_kind=essence_kind_for_level(level))
        for level in range(start_level, max_level + 1)
    )


@dataclass(frozen=True)
class LevelingPathStep:
    level: int
    event_type: str
    node_id: int | None
    spell_id: int | None
    name: str
    essence_kind: str
    reason: str
    ae_spent: int
    te_spent: int
    warnings: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "event_type": self.event_type,
            "node_id": self.node_id,
            "spell_id": self.spell_id,
            "name": self.name,
            "essence_kind": self.essence_kind,
            "reason": self.reason,
            "ae_spent": self.ae_spent,
            "te_spent": self.te_spent,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class LevelingPath:
    schema_version: str
    class_name: str
    spec_name: str
    build_id: str
    max_level: int
    steps: tuple[LevelingPathStep, ...]
    warnings: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "class_name": self.class_name,
            "spec_name": self.spec_name,
            "build_id": self.build_id,
            "max_level": self.max_level,
            "steps": [step.to_dict() for step in self.steps],
            "warnings": list(self.warnings),
        }


def effective_level(node: TalentNode) -> int:
    availability = node.availability or node.raw.get("availability") or {}
    level = availability.get("effective_required_level")
    if availability.get("level_confidence") in {"high", "medium"} and type(level) is int:
        return int(level)
    return int(node.required_level)


def automatic_passive_steps(
    nodes: Iterable[TalentNode],
    *,
    selected_ids: set[int],
    level: int,
    already_unlocked: set[int],
) -> tuple[LevelingPathStep, ...]:
    steps: list[LevelingPathStep] = []
    for node in sorted(nodes, key=lambda item: (effective_level(item), item.row, item.col, item.name)):
        if node.entry_id not in selected_ids or node.entry_id in already_unlocked:
            continue
        if node.ae_cost or node.te_cost:
            continue
        if effective_level(node) != level:
            continue
        already_unlocked.add(node.entry_id)
        steps.append(
            LevelingPathStep(
                level=level,
                event_type="automatic_passive",
                node_id=node.entry_id,
                spell_id=node.spell_id,
                name=node.name,
                essence_kind="free",
                reason=f"Unlocks automatically at level {level}.",
                ae_spent=0,
                te_spent=0,
            )
        )
    return tuple(steps)
