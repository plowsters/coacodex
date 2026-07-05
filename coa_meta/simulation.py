from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .apl import APLDocument
from .combat.engine import CombatEngine, CombatEngineConfig
from .combat.state import ActionEffect, ActorState, CombatAction
from .domain import BuildState, TalentNode
from .repository import TalentRepository

SIMULATION_RESULT_SCHEMA_VERSION = "coa-simulation-result-v1"


@dataclass(frozen=True)
class SimulationConfig:
    duration_ms: int = 60_000
    iterations: int = 1
    seed: int = 1
    target_count: int = 1


@dataclass(frozen=True)
class SimulationResult:
    schema_version: str
    source: str
    duration_ms: int
    iterations: int
    seed: int
    role: str
    total_damage: float
    total_healing: float
    dps: float
    hps: float
    spell_breakdown: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "duration_ms": self.duration_ms,
            "iterations": self.iterations,
            "seed": self.seed,
            "role": self.role,
            "total_damage": self.total_damage,
            "total_healing": self.total_healing,
            "dps": self.dps,
            "hps": self.hps,
            "spell_breakdown": list(self.spell_breakdown),
            "warnings": list(self.warnings),
        }


def simulate_build(
    state: BuildState,
    repository: TalentRepository,
    apl: APLDocument,
    config: SimulationConfig | None = None,
) -> SimulationResult:
    config = config or SimulationConfig()
    iterations = max(1, config.iterations)
    actions, warnings = _combat_actions_from_apl(state, repository, apl)
    total_damage = 0.0
    total_healing = 0.0
    spell_totals: dict[int, float] = {}

    for offset in range(iterations):
        result = CombatEngine(
            actions=actions,
            actor=_default_actor(),
            config=CombatEngineConfig(
                duration_ms=config.duration_ms,
                seed=config.seed + offset,
                target_count=config.target_count,
            ),
        ).run()
        total_damage += result.total_damage
        total_healing += result.total_healing
        for event in result.events:
            if event.event_type.endswith("damage") and event.spell_id is not None:
                spell_totals[event.spell_id] = spell_totals.get(event.spell_id, 0.0) + event.amount

    average_damage = total_damage / iterations
    average_healing = total_healing / iterations
    seconds = max(config.duration_ms / 1000, 1)
    return SimulationResult(
        schema_version=SIMULATION_RESULT_SCHEMA_VERSION,
        source="simulated",
        duration_ms=config.duration_ms,
        iterations=iterations,
        seed=config.seed,
        role=apl.role,
        total_damage=round(average_damage, 3),
        total_healing=round(average_healing, 3),
        dps=round(average_damage / seconds, 3),
        hps=round(average_healing / seconds, 3),
        spell_breakdown=tuple(
            {
                "spell_id": spell_id,
                "average_damage": round(amount / iterations, 3),
            }
            for spell_id, amount in sorted(spell_totals.items(), key=lambda item: (-item[1], item[0]))
        ),
        warnings=tuple(warnings),
    )


def _combat_actions_from_apl(
    state: BuildState,
    repository: TalentRepository,
    apl: APLDocument,
) -> tuple[tuple[CombatAction, ...], list[str]]:
    warnings: list[str] = []
    actions: list[CombatAction] = []
    selected = state.selected_ids
    for apl_action in apl.actions:
        if apl_action.node_id is None or apl_action.node_id not in selected:
            continue
        node = repository.get_node(apl_action.node_id)
        if node is None or node.spell_id is None:
            warnings.append(f"missing_node_for_apl_action:{apl_action.action_key}")
            continue
        actions.append(_action_from_node(node, apl_action.category))
    if not actions:
        warnings.append("no_simulatable_apl_actions")
    return tuple(actions), warnings


def _action_from_node(node: TalentNode, category: str) -> CombatAction:
    amount = _estimated_amount(node, category)
    effect_type = "heal" if "heal" in node.tags else "damage"
    duration_ms = 12_000 if "dot" in node.tags and effect_type == "damage" else None
    tick_interval_ms = 3_000 if duration_ms else None
    effects = (
        ActionEffect(
            effect_type=effect_type,
            amount=amount,
            school=next(iter(node.damage_schools), ""),
            duration_ms=duration_ms,
            tick_interval_ms=tick_interval_ms,
            max_targets=5 if category == "aoe" else None,
        ),
    )
    costs = _estimated_costs(node, category)
    cooldown_ms = 45_000 if category == "cooldown" else 0
    return CombatAction(
        spell_id=node.spell_id or node.entry_id,
        name=node.name,
        gcd_ms=1500,
        cooldown_ms=cooldown_ms,
        costs=costs,
        effects=effects,
    )


def _estimated_amount(node: TalentNode, category: str) -> float:
    base = 40.0
    if category == "builder":
        base = 35.0
    elif category == "spender":
        base = 140.0
    elif category == "cooldown":
        base = 90.0
    elif category == "aoe":
        base = 60.0
    elif "dot" in node.tags:
        base = 30.0
    elif "heal" in node.tags:
        base = 100.0
    return base + (len(node.tags) * 2.5)


def _estimated_costs(node: TalentNode, category: str) -> dict[str, float]:
    if category != "spender":
        return {}
    resource = next(iter(node.resources), "Energy")
    return {resource: 40.0}


def _default_actor() -> ActorState:
    return ActorState(
        resources={"Energy": 100.0, "Mana": 1000.0, "Rage": 100.0, "energy": 100.0},
        max_resources={"Energy": 100.0, "Mana": 1000.0, "Rage": 100.0, "energy": 100.0},
    )
