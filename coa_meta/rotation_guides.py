from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .action_catalog import ActionCatalog, CatalogAction
from .apl import APLAction, APLDocument
from .rotation_scoring import RotationSelection
from .rotation_simulation import RotationSimulationResult


ROTATION_GUIDE_SCHEMA_VERSION = "coa-rotation-guide-v1"
VALID_RELIABILITY = {"high", "medium", "low"}
VALID_SOURCES = {"theorycraft", "simulated", "empirical", "blended"}


@dataclass(frozen=True)
class RotationGuideRule:
    rule_id: str
    section: str
    text: str
    ability_name: str
    spell_id: int | None = None
    entry_id: int | None = None
    icon: str | None = None
    db_url: str | None = None
    condition: str = ""
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "section": self.section,
            "text": self.text,
            "ability_name": self.ability_name,
            "spell_id": self.spell_id,
            "entry_id": self.entry_id,
            "icon": self.icon,
            "db_url": self.db_url,
            "condition": self.condition,
            "priority": self.priority,
        }


@dataclass(frozen=True)
class ActionUsageSummary:
    action_key: str
    ability_name: str
    count: int
    first_used_ms: int | None = None
    last_used_ms: int | None = None
    uptime_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_key": self.action_key,
            "ability_name": self.ability_name,
            "count": self.count,
            "first_used_ms": self.first_used_ms,
            "last_used_ms": self.last_used_ms,
            "uptime_pct": self.uptime_pct,
        }


@dataclass(frozen=True)
class RotationSimulationSummary:
    source: str
    role: str
    encounter: str
    duration_ms: int
    objective_score: float
    reliability: str
    action_count: int
    unsupported_condition_count: int
    unsupported_effect_count: int
    warnings: tuple[str, ...] = tuple()

    def __post_init__(self) -> None:
        _validate_reliability(self.reliability)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "role": self.role,
            "encounter": self.encounter,
            "duration_ms": self.duration_ms,
            "objective_score": self.objective_score,
            "reliability": self.reliability,
            "action_count": self.action_count,
            "unsupported_condition_count": self.unsupported_condition_count,
            "unsupported_effect_count": self.unsupported_effect_count,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class RotationGuide:
    source: str
    role: str
    encounter: str
    build_id: str
    simulation_summary: RotationSimulationSummary
    opener: tuple[RotationGuideRule, ...] = tuple()
    core_loop: tuple[RotationGuideRule, ...] = tuple()
    priority_rules: tuple[RotationGuideRule, ...] = tuple()
    cooldown_rules: tuple[RotationGuideRule, ...] = tuple()
    proc_rules: tuple[RotationGuideRule, ...] = tuple()
    defensive_rules: tuple[RotationGuideRule, ...] = tuple()
    healing_rules: tuple[RotationGuideRule, ...] = tuple()
    support_rules: tuple[RotationGuideRule, ...] = tuple()
    aoe_adjustments: tuple[RotationGuideRule, ...] = tuple()
    movement_notes: tuple[str, ...] = tuple()
    ability_sequence: tuple[str, ...] = tuple()
    action_usage: tuple[ActionUsageSummary, ...] = tuple()
    reliability: str = "medium"
    warnings: tuple[str, ...] = tuple()

    def __post_init__(self) -> None:
        _validate_reliability(self.reliability)
        if self.source not in VALID_SOURCES:
            raise ValueError(f"Invalid rotation guide source: {self.source}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ROTATION_GUIDE_SCHEMA_VERSION,
            "source": self.source,
            "role": self.role,
            "encounter": self.encounter,
            "build_id": self.build_id,
            "simulation_summary": self.simulation_summary.to_dict(),
            "opener": _rule_list(self.opener),
            "core_loop": _rule_list(self.core_loop),
            "priority_rules": _rule_list(self.priority_rules),
            "cooldown_rules": _rule_list(self.cooldown_rules),
            "proc_rules": _rule_list(self.proc_rules),
            "defensive_rules": _rule_list(self.defensive_rules),
            "healing_rules": _rule_list(self.healing_rules),
            "support_rules": _rule_list(self.support_rules),
            "aoe_adjustments": _rule_list(self.aoe_adjustments),
            "movement_notes": list(self.movement_notes),
            "ability_sequence": list(self.ability_sequence),
            "action_usage": [item.to_dict() for item in self.action_usage],
            "reliability": self.reliability,
            "warnings": list(self.warnings),
        }


def _rule_list(rules: tuple[RotationGuideRule, ...]) -> list[dict[str, Any]]:
    return [rule.to_dict() for rule in rules]


def _validate_reliability(value: str) -> None:
    if value not in VALID_RELIABILITY:
        raise ValueError(f"Invalid rotation reliability: {value}")


def build_rotation_guide(
    selection: RotationSelection,
    apl: APLDocument,
    action_catalog: ActionCatalog,
    *,
    role: str,
    encounter: str,
    build_id: str = "",
) -> RotationGuide:
    result = selection.best.simulation_result
    warnings = list(selection.warnings) + list(selection.best.warnings)
    if result is None:
        warnings.append("rotation_guide_missing_simulation_result")
        result = _empty_result(selection.best.candidate_id)

    apl_by_key = {action.action_key: action for action in apl.actions}
    action_by_key = action_catalog.actions_by_key
    event_sequence = _event_ability_sequence(result, action_by_key)
    used_keys = _used_keys(result)

    opener = _opener_rules(result, apl_by_key, action_by_key)
    core_loop = _core_loop_rules(result, apl_by_key, action_by_key)
    priority_rules = _priority_rules(result, apl_by_key, action_by_key)
    cooldown_rules = _section_rules(result, apl_by_key, action_by_key, used_keys, "cooldown")
    proc_rules = _proc_rules(result, apl_by_key, action_by_key, used_keys)
    defensive_rules = _role_rules(result, apl_by_key, action_by_key, used_keys, "defensive", {"mitigation"})
    healing_rules = _role_rules(result, apl_by_key, action_by_key, used_keys, "healing", {"heal"})
    support_rules = _role_rules(result, apl_by_key, action_by_key, used_keys, "support", {"support"})
    aoe_adjustments = _section_rules(result, apl_by_key, action_by_key, used_keys, "aoe")

    primary_count = sum(
        len(section)
        for section in (
            core_loop,
            priority_rules,
            cooldown_rules,
            defensive_rules if role == "tank" else tuple(),
            healing_rules if role == "healer" else tuple(),
            support_rules if role == "support" else tuple(),
        )
    )
    if primary_count < 4:
        warnings.append("rotation_guide_sparse_primary_rules")

    action_usage = tuple(
        ActionUsageSummary(
            action_key=usage.action_key,
            ability_name=_ability_name(usage.action_key, action_by_key, apl_by_key),
            count=usage.count,
            first_used_ms=usage.first_used_ms,
            last_used_ms=usage.last_used_ms,
            uptime_pct=_uptime_pct(action_by_key.get(usage.action_key), usage.count, result.duration_ms),
        )
        for usage in sorted(
            result.action_usage.values(),
            key=lambda item: (-item.count, item.first_used_ms if item.first_used_ms is not None else 999_999, item.action_key),
        )
    )

    summary = RotationSimulationSummary(
        source="simulated",
        role=role,
        encounter=encounter,
        duration_ms=result.duration_ms,
        objective_score=selection.best.objective_score,
        reliability=selection.best.reliability,
        action_count=len(result.events),
        unsupported_condition_count=result.unsupported_condition_count,
        unsupported_effect_count=result.unsupported_effect_count,
        warnings=tuple(dict.fromkeys(result.warnings)),
    )

    return RotationGuide(
        source="simulated",
        role=role,
        encounter=encounter,
        build_id=build_id or selection.best.candidate_id,
        simulation_summary=summary,
        opener=opener,
        core_loop=core_loop,
        priority_rules=priority_rules,
        cooldown_rules=cooldown_rules,
        proc_rules=proc_rules,
        defensive_rules=defensive_rules,
        healing_rules=healing_rules,
        support_rules=support_rules,
        aoe_adjustments=aoe_adjustments,
        movement_notes=tuple(),
        ability_sequence=event_sequence,
        action_usage=action_usage,
        reliability=selection.best.reliability,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _empty_result(candidate_id: str) -> RotationSimulationResult:
    from .rotation_simulation import RotationSimulationResult

    return RotationSimulationResult(
        source=candidate_id,
        duration_ms=0,
        events=tuple(),
        resources={},
        cooldown_ready={},
        buffs={},
        debuffs={},
        action_usage={},
        total_damage=0.0,
        total_healing=0.0,
        support_events=0,
        mitigation_events=0,
        warnings=("rotation_guide_missing_simulation_result",),
        unsupported_condition_count=0,
        unsupported_effect_count=0,
    )


def _event_ability_sequence(
    result: RotationSimulationResult,
    action_by_key: dict[str, CatalogAction],
) -> tuple[str, ...]:
    return tuple(
        action_by_key[event.action_key].name if event.action_key in action_by_key else event.ability_name
        for event in result.events[:12]
    )


def _used_keys(result: RotationSimulationResult) -> set[str]:
    return {key for key, usage in result.action_usage.items() if usage.count > 0}


def _opener_rules(
    result: RotationSimulationResult,
    apl_by_key: dict[str, APLAction],
    action_by_key: dict[str, CatalogAction],
) -> tuple[RotationGuideRule, ...]:
    seen: set[str] = set()
    rules: list[RotationGuideRule] = []
    for event in result.events:
        if event.time_ms > 15_000 or event.action_key in seen:
            continue
        seen.add(event.action_key)
        apl_action = apl_by_key.get(event.action_key)
        action = action_by_key.get(event.action_key)
        rules.append(_rule_from_action(event.action_key, "opener", apl_action, action, len(rules) + 1))
        if len(rules) >= 4:
            break
    return tuple(rules)


def _core_loop_rules(
    result: RotationSimulationResult,
    apl_by_key: dict[str, APLAction],
    action_by_key: dict[str, CatalogAction],
) -> tuple[RotationGuideRule, ...]:
    core_categories = {"builder", "spender", "filler", "execute", "aoe"}
    seen: set[str] = set()
    rules: list[RotationGuideRule] = []
    for event in result.events:
        apl_action = apl_by_key.get(event.action_key)
        if apl_action is None or apl_action.category not in core_categories or event.action_key in seen:
            continue
        seen.add(event.action_key)
        rules.append(_rule_from_action(event.action_key, "core_loop", apl_action, action_by_key.get(event.action_key), len(rules) + 1))
        if len(rules) >= 12:
            break
    return tuple(rules)


def _priority_rules(
    result: RotationSimulationResult,
    apl_by_key: dict[str, APLAction],
    action_by_key: dict[str, CatalogAction],
) -> tuple[RotationGuideRule, ...]:
    used = _used_keys(result)
    rules: list[RotationGuideRule] = []
    for apl_action in sorted(apl_by_key.values(), key=lambda item: (item.priority, item.action_key)):
        if apl_action.action_key not in used:
            continue
        if apl_action.category != "maintenance" and not apl_action.condition.startswith("dot."):
            continue
        rules.append(_rule_from_action(apl_action.action_key, "maintenance", apl_action, action_by_key.get(apl_action.action_key), len(rules) + 1))
    return tuple(rules[:12])


def _section_rules(
    result: RotationSimulationResult,
    apl_by_key: dict[str, APLAction],
    action_by_key: dict[str, CatalogAction],
    used_keys: set[str],
    category: str,
) -> tuple[RotationGuideRule, ...]:
    del result
    rules: list[RotationGuideRule] = []
    for apl_action in sorted(apl_by_key.values(), key=lambda item: (item.priority, item.action_key)):
        action = action_by_key.get(apl_action.action_key)
        if apl_action.action_key not in used_keys:
            continue
        if apl_action.category != category and not (category == "cooldown" and action and (action.cooldown_ms or 0) > 0):
            continue
        rules.append(_rule_from_action(apl_action.action_key, category, apl_action, action, len(rules) + 1))
    return tuple(rules[:12])


def _proc_rules(
    result: RotationSimulationResult,
    apl_by_key: dict[str, APLAction],
    action_by_key: dict[str, CatalogAction],
    used_keys: set[str],
) -> tuple[RotationGuideRule, ...]:
    del result
    rules: list[RotationGuideRule] = []
    for apl_action in sorted(apl_by_key.values(), key=lambda item: (item.priority, item.action_key)):
        action = action_by_key.get(apl_action.action_key)
        if apl_action.action_key not in used_keys or action is None:
            continue
        if "proc" not in action.tags and "proc" not in apl_action.category:
            continue
        rules.append(_rule_from_action(apl_action.action_key, "procs", apl_action, action, len(rules) + 1))
    return tuple(rules[:12])


def _role_rules(
    result: RotationSimulationResult,
    apl_by_key: dict[str, APLAction],
    action_by_key: dict[str, CatalogAction],
    used_keys: set[str],
    category: str,
    classifications: set[str],
) -> tuple[RotationGuideRule, ...]:
    del result
    rules: list[RotationGuideRule] = []
    for apl_action in sorted(apl_by_key.values(), key=lambda item: (item.priority, item.action_key)):
        action = action_by_key.get(apl_action.action_key)
        if apl_action.action_key not in used_keys:
            continue
        if apl_action.category != category and not (action and action.role_classification in classifications):
            continue
        rules.append(_rule_from_action(apl_action.action_key, category, apl_action, action, len(rules) + 1))
    return tuple(rules[:12])


def _rule_from_action(
    action_key: str,
    section: str,
    apl_action: APLAction | None,
    action: CatalogAction | None,
    priority: int,
) -> RotationGuideRule:
    ability_name = _ability_name(action_key, {action_key: action} if action else {}, {action_key: apl_action} if apl_action else {})
    return RotationGuideRule(
        rule_id=f"{section}:{action_key}",
        section=section,
        text=_rule_text(section, ability_name, apl_action.condition if apl_action else ""),
        ability_name=ability_name,
        spell_id=action.spell_id if action else apl_action.spell_id if apl_action else None,
        entry_id=action.entry_id if action else apl_action.node_id if apl_action else None,
        icon=_action_icon(action),
        db_url=_db_url(action, apl_action),
        condition=apl_action.condition if apl_action else "",
        priority=priority,
    )


def _rule_text(section: str, ability_name: str, condition: str) -> str:
    if section == "opener":
        return f"Open with {ability_name}."
    if section == "core_loop":
        return f"Use {ability_name} as part of the repeatable core loop."
    if section == "maintenance":
        return f"Keep {ability_name} active." if condition else f"Maintain {ability_name}."
    if section == "cooldown":
        return f"Use {ability_name} during planned burst windows."
    if section == "defensive":
        return f"Use {ability_name} before heavy damage or dangerous pulls."
    if section == "healing":
        return f"Use {ability_name} when allies need recovery."
    if section == "support":
        return f"Keep {ability_name} aligned with group damage windows."
    if section == "aoe":
        return f"Use {ability_name} when fighting multiple targets."
    if section == "procs":
        return f"Use {ability_name} when its proc or status condition is active."
    return f"Use {ability_name} when it is available."


def _ability_name(
    action_key: str,
    action_by_key: dict[str, CatalogAction],
    apl_by_key: dict[str, APLAction],
) -> str:
    action = action_by_key.get(action_key)
    if action:
        return action.name
    apl_action = apl_by_key.get(action_key)
    if apl_action:
        return apl_action.action_name
    return action_key.replace("_", " ").title()


def _action_icon(action: CatalogAction | None) -> str | None:
    if action and action.node:
        value = action.node.raw.get("icon") or action.node.raw.get("iconPath")
        if value:
            return str(value)
    return None


def _db_url(action: CatalogAction | None, apl_action: APLAction | None) -> None:
    # E0R AscensionDB sunset: rotation actions no longer link out to db.ascension.gg.
    return None


def _uptime_pct(action: CatalogAction | None, count: int, duration_ms: int) -> float | None:
    if action is None or duration_ms <= 0:
        return None
    effect_duration = action.duration_ms
    if effect_duration is None:
        for effect in action.effects:
            if effect.duration_ms:
                effect_duration = effect.duration_ms
                break
    if not effect_duration:
        return None
    return round(min(100.0, effect_duration * count / duration_ms * 100.0), 2)
