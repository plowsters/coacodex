from __future__ import annotations

import re
from dataclasses import dataclass, field

from .action_catalog import ActionCatalog, CatalogAction
from .apl import APLDocument


@dataclass(frozen=True)
class RotationSimulationConfig:
    duration_ms: int = 90_000
    target_count: int = 1
    seed: int = 1
    max_events: int = 10_000
    initial_resources: dict[str, float] = field(default_factory=dict)
    max_resources: dict[str, float] = field(default_factory=dict)
    target_health_pct: float = 100.0
    ally_health_pct: float = 100.0
    actor_health_pct: float = 100.0
    damage_window_active: bool = False


@dataclass(frozen=True)
class RotationEvent:
    time_ms: int
    action_key: str
    ability_name: str
    category: str
    condition: str
    role_classification: str


@dataclass(frozen=True)
class ActionUsage:
    action_key: str
    ability_name: str
    count: int
    first_used_ms: int | None = None
    last_used_ms: int | None = None


@dataclass(frozen=True)
class RotationSimulationResult:
    source: str
    duration_ms: int
    events: tuple[RotationEvent, ...]
    resources: dict[str, float]
    cooldown_ready: dict[str, int]
    buffs: dict[str, int]
    debuffs: dict[str, int]
    action_usage: dict[str, ActionUsage]
    total_damage: float
    total_healing: float
    support_events: int
    mitigation_events: int
    warnings: tuple[str, ...]
    unsupported_condition_count: int
    unsupported_effect_count: int


@dataclass
class _MutableState:
    time_ms: int
    resources: dict[str, float]
    max_resources: dict[str, float]
    cooldown_ready: dict[str, int]
    buffs: dict[str, int]
    debuffs: dict[str, int]
    warnings: list[str]
    unsupported_conditions: set[str]


def simulate_apl(
    apl: APLDocument,
    action_catalog: ActionCatalog,
    config: RotationSimulationConfig,
) -> RotationSimulationResult:
    state = _MutableState(
        time_ms=0,
        resources=dict(config.initial_resources),
        max_resources=dict(config.max_resources),
        cooldown_ready={},
        buffs={},
        debuffs={},
        warnings=[],
        unsupported_conditions=set(),
    )
    events: list[RotationEvent] = []
    usage: dict[str, list[int]] = {}
    total_damage = 0.0
    total_healing = 0.0
    support_events = 0
    mitigation_events = 0
    unsupported_effect_count = 0

    while state.time_ms < config.duration_ms and len(events) < config.max_events:
        selected = _select_action(apl, action_catalog, state, config)
        if selected is None:
            state.time_ms += 100
            _tick_state(state, 100)
            continue

        apl_action, action = selected
        event = RotationEvent(
            time_ms=state.time_ms,
            action_key=action.action_key,
            ability_name=action.name,
            category=apl_action.category,
            condition=apl_action.condition,
            role_classification=action.role_classification,
        )
        events.append(event)
        usage.setdefault(action.action_key, []).append(state.time_ms)

        _spend_and_generate(action, state)
        if action.cooldown_ms > 0:
            state.cooldown_ready[action.action_key] = state.time_ms + action.cooldown_ms

        for effect in action.effects:
            if effect.effect_type == "damage":
                total_damage += float(effect.amount or 0)
                if effect.duration_ms:
                    state.debuffs[action.action_key] = int(effect.duration_ms)
            elif effect.effect_type == "heal":
                total_healing += float(effect.amount or 0)
            elif effect.effect_type in {"aura_apply", "stat_modify"}:
                state.buffs[action.action_key] = int(effect.duration_ms or action.duration_ms or 0)
                if action.role_classification == "support":
                    support_events += 1
                if action.role_classification == "mitigation":
                    mitigation_events += 1
            elif effect.effect_type == "summon":
                support_events += 1 if action.role_classification == "support" else 0
            elif effect.effect_type:
                unsupported_effect_count += 1

        if action.role_classification == "support":
            support_events += 1
        if action.role_classification == "mitigation":
            mitigation_events += 1

        elapsed = action.gcd_ms or 1500
        state.time_ms += elapsed
        _tick_state(state, elapsed)

    action_usage = {
        key: ActionUsage(
            action_key=key,
            ability_name=action_catalog.actions_by_key[key].name,
            count=len(times),
            first_used_ms=times[0],
            last_used_ms=times[-1],
        )
        for key, times in usage.items()
    }

    return RotationSimulationResult(
        source="simulated",
        duration_ms=config.duration_ms,
        events=tuple(events),
        resources=dict(state.resources),
        cooldown_ready=dict(state.cooldown_ready),
        buffs=dict(state.buffs),
        debuffs=dict(state.debuffs),
        action_usage=action_usage,
        total_damage=total_damage,
        total_healing=total_healing,
        support_events=support_events,
        mitigation_events=mitigation_events,
        warnings=tuple(dict.fromkeys(state.warnings)),
        unsupported_condition_count=len(state.unsupported_conditions),
        unsupported_effect_count=unsupported_effect_count,
    )


def _select_action(
    apl: APLDocument,
    action_catalog: ActionCatalog,
    state: _MutableState,
    config: RotationSimulationConfig,
) -> tuple | None:
    for apl_action in sorted(apl.actions, key=lambda item: (item.priority, item.action_key)):
        action = action_catalog.actions_by_key.get(apl_action.action_key)
        if action is None:
            _warn_once(state.warnings, f"missing_action:{apl_action.action_key}")
            continue
        passes, warning = _condition_passes(apl_action.condition, action.action_key, state, config)
        if warning:
            state.unsupported_conditions.add(warning)
            _warn_once(state.warnings, warning)
        if not passes:
            continue
        if state.cooldown_ready.get(action.action_key, 0) > state.time_ms:
            continue
        if any(_resource_value(state.resources, resource) < cost for resource, cost in action.costs.items()):
            continue
        return apl_action, action
    return None


def _condition_passes(
    condition: str,
    action_key: str,
    state: _MutableState,
    config: RotationSimulationConfig,
) -> tuple[bool, str | None]:
    condition = condition.strip()
    if not condition:
        return True, None
    if condition == "when allies injured":
        return config.ally_health_pct < 80, None
    if condition == "before heavy damage":
        return config.damage_window_active, None

    match = re.fullmatch(r"dot\.([a-z0-9_]+)\.remains<gcd", condition)
    if match:
        return state.debuffs.get(match.group(1), 0) < 1500, None

    match = re.fullmatch(r"buff\.([a-z0-9_]+)\.down", condition)
    if match:
        return state.buffs.get(match.group(1), 0) <= 0, None

    match = re.fullmatch(r"cooldown\.([a-z0-9_]+)\.ready", condition)
    if match:
        key = match.group(1)
        return state.cooldown_ready.get(key, 0) <= state.time_ms, None

    match = re.fullmatch(r"([a-z0-9_]+)>=(\d+(?:\.\d+)?)", condition)
    if match:
        return _resource_value(state.resources, match.group(1)) >= float(match.group(2)), None

    match = re.fullmatch(r"([a-z0-9_]+)\.deficit>0", condition)
    if match:
        resource = match.group(1)
        return _resource_value(state.max_resources, resource) - _resource_value(state.resources, resource) > 0, None

    match = re.fullmatch(r"target\.health\.pct<(\d+(?:\.\d+)?)", condition)
    if match:
        return config.target_health_pct < float(match.group(1)), None

    match = re.fullmatch(r"active_enemies>=(\d+)", condition)
    if match:
        return config.target_count >= int(match.group(1)), None

    return False, f"unsupported_condition:{condition}"


def _spend_and_generate(action: CatalogAction, state: _MutableState) -> None:
    for resource, amount in action.costs.items():
        current = _resource_value(state.resources, resource)
        state.resources[resource] = max(0.0, current - float(amount))
    for resource, amount in action.generates.items():
        current = _resource_value(state.resources, resource)
        maximum = _resource_value(state.max_resources, resource) or current + float(amount)
        state.resources[resource] = min(maximum, current + float(amount))


def _tick_state(state: _MutableState, elapsed_ms: int) -> None:
    state.buffs = _tick_map(state.buffs, elapsed_ms)
    state.debuffs = _tick_map(state.debuffs, elapsed_ms)


def _tick_map(values: dict[str, int], elapsed_ms: int) -> dict[str, int]:
    return {
        key: max(0, value - elapsed_ms)
        for key, value in values.items()
        if max(0, value - elapsed_ms) > 0
    }


def _resource_value(resources: dict[str, float], resource: str) -> float:
    wanted = resource.casefold()
    for key, value in resources.items():
        if key.casefold() == wanted:
            return float(value)
    return 0.0


def _warn_once(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)
