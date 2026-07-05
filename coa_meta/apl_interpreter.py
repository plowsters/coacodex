from __future__ import annotations

import re
from dataclasses import dataclass, field

from .apl import APLAction, APLDocument
from .combat.state import CombatAction


@dataclass(frozen=True)
class APLRuntimeState:
    time_ms: int = 0
    resources: dict[str, float] = field(default_factory=dict)
    max_resources: dict[str, float] = field(default_factory=dict)
    cooldown_ready: dict[str, int] = field(default_factory=dict)
    buffs: dict[str, int] = field(default_factory=dict)
    debuffs: dict[str, int] = field(default_factory=dict)
    active_enemies: int = 1
    target_health_pct: float = 100.0
    gcd_ms: int = 1500


@dataclass(frozen=True)
class APLDecision:
    action: CombatAction | None
    apl_action: APLAction | None
    reason: str
    warnings: tuple[str, ...] = tuple()


class APLInterpreter:
    def __init__(self, document: APLDocument, action_catalog: dict[str, CombatAction]):
        self.document = document
        self.action_catalog = dict(action_catalog)

    def choose_action(self, state: APLRuntimeState) -> APLDecision:
        warnings: list[str] = []
        for apl_action in sorted(self.document.actions, key=lambda action: (action.priority, action.action_key)):
            passes, warning = self._condition_passes(apl_action.condition, apl_action.action_key, state)
            if warning:
                warnings.append(warning)
            if not passes:
                continue
            action = self.action_catalog.get(apl_action.action_key)
            if action is None:
                warnings.append(f"missing_action:{apl_action.action_key}")
                continue
            if not self._action_is_usable(apl_action.action_key, action, state):
                continue
            return APLDecision(action=action, apl_action=apl_action, reason="selected", warnings=tuple(warnings))
        return APLDecision(action=None, apl_action=None, reason="no_usable_action", warnings=tuple(warnings))

    def _condition_passes(
        self,
        condition: str,
        action_key: str,
        state: APLRuntimeState,
    ) -> tuple[bool, str | None]:
        condition = condition.strip()
        if not condition:
            return True, None

        match = re.fullmatch(r"dot\.([a-z0-9_]+)\.remains<gcd", condition)
        if match:
            remains = state.debuffs.get(match.group(1), 0)
            return remains < state.gcd_ms, None

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
            return state.target_health_pct < float(match.group(1)), None

        match = re.fullmatch(r"active_enemies>=(\d+)", condition)
        if match:
            return state.active_enemies >= int(match.group(1)), None

        return False, f"unsupported_condition:{condition}"

    def _action_is_usable(self, action_key: str, action: CombatAction, state: APLRuntimeState) -> bool:
        if state.cooldown_ready.get(action_key, 0) > state.time_ms:
            return False
        for resource, cost in action.costs.items():
            if _resource_value(state.resources, resource) < cost:
                return False
        return True


def _resource_value(resources: dict[str, float], resource: str) -> float:
    wanted = resource.casefold()
    for key, value in resources.items():
        if key.casefold() == wanted:
            return float(value)
    return 0.0
