from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .action_catalog import ActionCatalog, CatalogAction
from .objectives import OBJECTIVE_LABELS
from .rotation_simulation import RotationSimulationResult


@dataclass(frozen=True)
class RotationScore:
    candidate_id: str
    role: str
    objective_id: str
    objective_label: str
    objective_score: float
    adjusted_score: float
    reliability: str
    breakdown: dict[str, float]
    warnings: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "role": self.role,
            "objective_id": self.objective_id,
            "objective_label": self.objective_label,
            "objective_score": self.objective_score,
            "adjusted_score": self.adjusted_score,
            "reliability": self.reliability,
            "breakdown": dict(self.breakdown),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class RotationSelection:
    role: str
    best: RotationScore
    ranked: tuple[RotationScore, ...]
    warnings: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "best": self.best.to_dict(),
            "ranked": [score.to_dict() for score in self.ranked],
            "warnings": list(self.warnings),
        }


def score_rotation_result(
    result: RotationSimulationResult,
    role_objective: str,
    action_catalog: ActionCatalog,
) -> RotationScore:
    role = role_objective
    objective_id, objective_label = OBJECTIVE_LABELS.get(role, OBJECTIVE_LABELS["melee_dps"])
    breakdown = _breakdown_for_role(result, role, action_catalog)
    objective_score = round(sum(breakdown.values()), 2)
    reliability = _reliability(result, action_catalog)
    warnings = list(result.warnings)
    penalty = _reliability_factor(reliability)
    if penalty < 1.0:
        warnings.append("reliability_penalty_applied")
    return RotationScore(
        candidate_id=result.source,
        role=role,
        objective_id=objective_id,
        objective_label=objective_label,
        objective_score=objective_score,
        adjusted_score=round(objective_score * penalty, 2),
        reliability=reliability,
        breakdown=breakdown,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def select_best_rotation_candidate(
    results: Sequence[RotationScore],
    role_objective: str,
) -> RotationSelection:
    if not results:
        raise ValueError("select_best_rotation_candidate requires at least one score")
    ranked = tuple(
        sorted(
            results,
            key=lambda score: (
                score.adjusted_score,
                _reliability_rank(score.reliability),
                score.objective_score,
                score.candidate_id,
            ),
            reverse=True,
        )
    )
    warnings: list[str] = []
    if ranked[0].reliability == "low":
        warnings.append("selected_rotation_low_reliability")
    return RotationSelection(role=role_objective, best=ranked[0], ranked=ranked, warnings=tuple(warnings))


def _breakdown_for_role(
    result: RotationSimulationResult,
    role: str,
    action_catalog: ActionCatalog,
) -> dict[str, float]:
    damage = _per_minute(result.total_damage, result.duration_ms)
    healing = _per_minute(result.total_healing, result.duration_ms)
    resource_efficiency = _resource_efficiency(result, action_catalog)
    action_uptime = _duration_coverage(result, action_catalog, {"damage", "utility"})
    mitigation_coverage = _duration_coverage(result, action_catalog, {"mitigation"})
    support_coverage = _duration_coverage(result, action_catalog, {"support"})
    heal_events = _role_action_count(result, action_catalog, {"heal"})
    mitigation_events = result.mitigation_events + _role_action_count(result, action_catalog, {"mitigation"})
    support_events = result.support_events + _role_action_count(result, action_catalog, {"support"})

    if role == "tank":
        return _rounded_breakdown(
            {
                "mitigation_coverage": mitigation_coverage * 8.0,
                "survivability": healing * 0.4 + mitigation_events * 25.0,
                "threat_proxy": damage * 0.15 + mitigation_events * 12.0,
                "damage_contribution": damage * 0.1,
            }
        )
    if role == "healer":
        return _rounded_breakdown(
            {
                "healing_throughput": healing,
                "mana_efficiency": _mana_efficiency(result, action_catalog) * 10.0,
                "emergency_response": heal_events * 20.0,
                "safe_damage": damage * 0.2,
            }
        )
    if role == "support":
        return _rounded_breakdown(
            {
                "support_coverage": support_coverage * 8.0,
                "utility_events": support_events * 25.0,
                "buff_alignment": support_events * 10.0,
                "contribution": damage * 0.15,
            }
        )

    return _rounded_breakdown(
        {
            "damage_throughput": damage,
            "uptime_proxy": action_uptime * 0.5,
            "resource_efficiency": resource_efficiency * 50.0,
            "cooldown_usage": _cooldown_usage(result, action_catalog) * 10.0,
        }
    )


def _reliability(result: RotationSimulationResult, action_catalog: ActionCatalog) -> str:
    coverage = float(action_catalog.coverage_summary.get("mechanics_coverage_pct", 100.0) or 0.0)
    warnings = set(result.warnings) | set(action_catalog.warnings)
    major_warning = any(
        warning.startswith(("unsupported_condition:", "missing_action:", "no_simulatable", "missing_mechanics:"))
        for warning in warnings
    )
    if result.unsupported_condition_count > 0 or coverage < 50.0 or major_warning:
        return "low"
    if result.unsupported_effect_count > 0 or coverage < 80.0 or warnings:
        return "medium"
    return "high"


def _reliability_factor(reliability: str) -> float:
    return {"high": 1.0, "medium": 0.85, "low": 0.55}.get(reliability, 0.55)


def _reliability_rank(reliability: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(reliability, 0)


def _per_minute(value: float, duration_ms: int) -> float:
    if duration_ms <= 0:
        return 0.0
    return float(value) / (duration_ms / 60_000)


def _duration_coverage(
    result: RotationSimulationResult,
    action_catalog: ActionCatalog,
    classifications: set[str],
) -> float:
    total_ms = 0.0
    for action_key, usage in result.action_usage.items():
        action = action_catalog.actions_by_key.get(action_key)
        if action is None or action.role_classification not in classifications:
            continue
        duration_ms = action.duration_ms or _first_effect_duration(action) or 0
        total_ms += duration_ms * usage.count
    if result.duration_ms <= 0:
        return 0.0
    return min(100.0, total_ms / result.duration_ms * 100.0)


def _first_effect_duration(action: CatalogAction) -> int | None:
    for effect in action.effects:
        if effect.duration_ms:
            return effect.duration_ms
    return None


def _role_action_count(
    result: RotationSimulationResult,
    action_catalog: ActionCatalog,
    classifications: set[str],
) -> int:
    total = 0
    for action_key, usage in result.action_usage.items():
        action = action_catalog.actions_by_key.get(action_key)
        if action and action.role_classification in classifications:
            total += usage.count
    return total


def _resource_efficiency(result: RotationSimulationResult, action_catalog: ActionCatalog) -> float:
    generated = 0.0
    spent = 0.0
    for action_key, usage in result.action_usage.items():
        action = action_catalog.actions_by_key.get(action_key)
        if action is None:
            continue
        generated += sum(float(value) for value in action.generates.values()) * usage.count
        spent += sum(float(value) for value in action.costs.values()) * usage.count
    if generated <= 0:
        return 0.0
    return min(1.0, spent / generated)


def _mana_efficiency(result: RotationSimulationResult, action_catalog: ActionCatalog) -> float:
    mana_spent = 0.0
    for action_key, usage in result.action_usage.items():
        action = action_catalog.actions_by_key.get(action_key)
        if action is None:
            continue
        for resource, cost in action.costs.items():
            if resource.casefold() == "mana":
                mana_spent += float(cost) * usage.count
    if mana_spent <= 0:
        return 0.0
    return result.total_healing / mana_spent


def _cooldown_usage(result: RotationSimulationResult, action_catalog: ActionCatalog) -> int:
    total = 0
    for action_key, usage in result.action_usage.items():
        action = action_catalog.actions_by_key.get(action_key)
        if action and action.cooldown_ms > 0:
            total += usage.count
    return total


def _rounded_breakdown(values: dict[str, float]) -> dict[str, float]:
    return {key: round(value, 2) for key, value in values.items()}
