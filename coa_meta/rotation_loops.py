from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Sequence

from .apl import APLAction, APLDocument
from .domain import TalentNode


@dataclass(frozen=True)
class RotationLoop:
    schema_version: str
    objective: str
    opener: tuple[str, ...]
    core_loop: tuple[str, ...]
    cooldowns: tuple[str, ...]
    defensive_or_support: tuple[str, ...]
    resource_rule: str | None
    maintenance_rule: str | None
    reliability_label: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "objective": self.objective,
            "opener": list(self.opener),
            "core_loop": list(self.core_loop),
            "cooldowns": list(self.cooldowns),
            "defensive_or_support": list(self.defensive_or_support),
            "resource_rule": self.resource_rule,
            "maintenance_rule": self.maintenance_rule,
            "reliability_label": self.reliability_label,
            "warnings": list(self.warnings),
        }


def build_rotation_loop(
    *,
    apl: APLDocument,
    selected_nodes: Sequence[TalentNode],
    role: str,
    encounter: str,
) -> RotationLoop:
    actions_by_category = _group_actions(apl.actions)
    warnings = list(apl.warnings)
    objective = _role_objective(role, encounter)

    maintenance_actions = actions_by_category.get("maintenance", tuple())
    cooldown_actions = actions_by_category.get("cooldown", tuple())
    builder_actions = actions_by_category.get("builder", tuple())
    spender_actions = actions_by_category.get("spender", tuple())
    filler_actions = actions_by_category.get("filler", tuple())

    core_loop: list[str] = []
    if maintenance_actions:
        core_loop.append(f"Keep {_names(maintenance_actions)} active before moving into your damage loop.")
    if builder_actions and spender_actions:
        core_loop.append(f"Build with {_names(builder_actions)} until your spender window is ready.")
        core_loop.append(f"Spend with {_names(spender_actions)} before you overcap or during burst windows.")
    elif spender_actions:
        core_loop.append(f"Use {_names(spender_actions)} whenever the condition is met.")
    elif builder_actions:
        core_loop.append(f"Use {_names(builder_actions)} as your repeatable builder or main filler.")
    if filler_actions:
        core_loop.append(f"Fill empty globals with {_names(filler_actions)}.")

    defensive_or_support = _role_specific_steps(actions_by_category, role)
    if not core_loop and defensive_or_support:
        core_loop.extend(defensive_or_support[:2])
    if not core_loop:
        core_loop.extend(f"Use {action.action_name} when available." for action in tuple(apl.actions)[:3])
        warnings.append("inferred_loop_low_confidence")

    opener = tuple(f"Open with {action.action_name} to set up the pull." for action in cooldown_actions[:2])
    cooldowns = tuple(f"Use {action.action_name} during your main damage or recovery window." for action in cooldown_actions)
    resource_rule = _resource_rule(builder_actions, spender_actions)
    maintenance_rule = (
        f"Refresh {_names(maintenance_actions)} before it falls off."
        if maintenance_actions
        else None
    )
    reliability = _loop_reliability(apl.actions, core_loop, warnings)

    return RotationLoop(
        schema_version="coa-rotation-loop-v1",
        objective=objective,
        opener=opener,
        core_loop=tuple(core_loop[:6]),
        cooldowns=cooldowns,
        defensive_or_support=defensive_or_support,
        resource_rule=resource_rule,
        maintenance_rule=maintenance_rule,
        reliability_label=reliability,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _group_actions(actions: Sequence[APLAction]) -> dict[str, tuple[APLAction, ...]]:
    grouped: dict[str, list[APLAction]] = defaultdict(list)
    for action in sorted(actions, key=lambda item: item.priority):
        grouped[action.category].append(action)
    return {category: tuple(values) for category, values in grouped.items()}


def _role_objective(role: str, encounter: str) -> str:
    target_note = "single target" if encounter == "single_target" else encounter.replace("_", " ")
    if role == "tank":
        return f"Keep yourself stable while maintaining threat and damage in {target_note}."
    if role == "healer":
        return f"Keep allies alive with steady healing and timely recovery buttons in {target_note}."
    if role == "support":
        return f"Maintain group buffs, debuffs, and useful filler actions in {target_note}."
    if role == "caster_dps":
        return f"Maintain uptime on casts, effects, and spender windows in {target_note}."
    if role == "ranged_dps":
        return f"Maintain range, keep effects rolling, and spend during strong damage windows in {target_note}."
    return f"Maintain uptime, build cleanly, and spend inside strong windows in {target_note}."


def _role_specific_steps(actions_by_category: dict[str, tuple[APLAction, ...]], role: str) -> tuple[str, ...]:
    steps: list[str] = []
    if role == "healer":
        heal_actions = actions_by_category.get("heal", tuple()) or actions_by_category.get("utility", tuple())
        steps.extend(f"Use {action.action_name} when allies need healing." for action in heal_actions)
    elif role == "tank":
        defensive_actions = (
            actions_by_category.get("defensive", tuple())
            or actions_by_category.get("cooldown", tuple())
            or actions_by_category.get("utility", tuple())
        )
        steps.extend(f"Use {action.action_name} to smooth incoming damage." for action in defensive_actions)
    elif role == "support":
        support_actions = actions_by_category.get("support", tuple()) or actions_by_category.get("utility", tuple())
        steps.extend(f"Keep {action.action_name} contributing to group uptime." for action in support_actions)
    return tuple(steps)


def _resource_rule(builder_actions: tuple[APLAction, ...], spender_actions: tuple[APLAction, ...]) -> str | None:
    if builder_actions and spender_actions:
        return f"Build with {_names(builder_actions)} and spend with {_names(spender_actions)} before overcapping."
    if spender_actions:
        return f"Spend with {_names(spender_actions)} whenever its condition is ready."
    if builder_actions:
        return f"Use {_names(builder_actions)} as your stable repeatable action."
    return None


def _loop_reliability(actions: Sequence[APLAction], core_loop: Sequence[str], warnings: Sequence[str]) -> str:
    if not actions or "inferred_loop_low_confidence" in warnings:
        return "low"
    low_confidence = sum(1 for action in actions if action.confidence == "low")
    if low_confidence > len(actions) / 2:
        return "low"
    if len(core_loop) >= 2 and not warnings:
        return "high"
    return "medium"


def _names(actions: Sequence[APLAction]) -> str:
    names = [action.action_name for action in actions[:3]]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"
