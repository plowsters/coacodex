from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .domain import TalentNode
from .mechanics import MechanicEffect, MechanicRecord
from .mechanics_repository import MechanicsRepository


class QuantitativeScopeUnready(RuntimeError):
    """A quantitative consumer (APL sim, combat conversion) was asked to run over actions that lack
    load-bearing timing/cost data. E0R fails CLOSED here rather than silently substituting invented
    defaults (missing != default, design B5). Pass an explicit heuristic mode to opt into estimates."""


# The fields a quantitative loop cannot honestly run without. `costs` unknown (None) is distinct from a
# proven-empty {} — only the former blocks.
_LOAD_BEARING = ("gcd_ms", "cooldown_ms", "costs")
_BLOCKING_STATUSES = {"unavailable", "ambiguous"}


@dataclass(frozen=True)
class CatalogAction:
    action_key: str
    entry_id: int
    spell_id: int
    name: str
    costs: dict[str, float] | None       # None = unknown (blocks quantitative scope); {} = verified empty
    generates: dict[str, float]
    spends: dict[str, float]
    cooldown_ms: int | None              # None = unknown; a proven 0 is preserved (missing != default)
    gcd_ms: int | None                   # None = unknown; a proven 1500 is preserved
    cast_time_ms: int | None
    range_yards: float | None
    duration_ms: int | None
    tick_interval_ms: int | None
    effects: tuple[MechanicEffect, ...]
    tags: tuple[str, ...]
    mechanic_kind: str
    confidence: str
    role_classification: str
    source: str
    warnings: tuple[str, ...] = tuple()
    field_readiness: dict[str, dict] | None = None
    mechanic: MechanicRecord | None = None
    node: TalentNode | None = None

    def readiness_of(self, field_name: str) -> str:
        """The readiness status of a load-bearing field: the MechanicRecord's field_readiness if present,
        else inferred from nullness (a null value is unavailable, a present value is available)."""
        entry = (self.field_readiness or {}).get(field_name)
        if entry and entry.get("status"):
            return entry["status"]
        return "available" if getattr(self, field_name) is not None else "unavailable"

    def to_dict(self) -> dict[str, Any]:
        # Nullable fields serialize WITHOUT coercion — a null cooldown/gcd/costs is a distinct, load-bearing
        # value a downstream consumer must see as unknown (never a defaulted 0/1500/{}).
        return {
            "action_key": self.action_key,
            "entry_id": self.entry_id,
            "spell_id": self.spell_id,
            "name": self.name,
            "costs": dict(self.costs) if self.costs is not None else None,
            "generates": dict(self.generates),
            "spends": dict(self.spends),
            "cooldown_ms": self.cooldown_ms,
            "gcd_ms": self.gcd_ms,
            "cast_time_ms": self.cast_time_ms,
            "range_yards": self.range_yards,
            "duration_ms": self.duration_ms,
            "tick_interval_ms": self.tick_interval_ms,
            "effects": [effect.to_dict() for effect in self.effects],
            "tags": list(self.tags),
            "mechanic_kind": self.mechanic_kind,
            "confidence": self.confidence,
            "role_classification": self.role_classification,
            "source": self.source,
            "warnings": list(self.warnings),
            "field_readiness": dict(self.field_readiness) if self.field_readiness else {},
        }


@dataclass(frozen=True)
class ActionCatalog:
    actions_by_key: dict[str, CatalogAction]
    actions_by_spell_id: dict[int, CatalogAction]
    warnings: tuple[str, ...]
    coverage_summary: dict[str, float | int]

    @property
    def actions(self) -> tuple[CatalogAction, ...]:
        return tuple(self.actions_by_key.values())

    @property
    def quantitative_readiness(self) -> dict[str, Any]:
        """Whether every action carries the load-bearing gcd/cooldown/costs a quantitative scope needs —
        driven by each action's readiness (B5), NOT merely by nullness. `blocking` names every offending
        (action_key, field)."""
        blocking: list[dict[str, Any]] = []
        for action in self.actions:
            for field_name in _LOAD_BEARING:
                status = action.readiness_of(field_name)
                if status in _BLOCKING_STATUSES:
                    entry = (action.field_readiness or {}).get(field_name, {})
                    blocking.append({"action_key": action.action_key, "field": field_name,
                                     "status": status,
                                     "reason_code": entry.get("reason_code", "pending_e1_operand")})
        return {"ready": not blocking, "blocking": blocking}

    def assert_quantitative_ready(self) -> None:
        readiness = self.quantitative_readiness
        if not readiness["ready"]:
            raise QuantitativeScopeUnready(
                f"{len(readiness['blocking'])} action(s) lack load-bearing gcd/cooldown/costs data")


def build_action_catalog(
    selected_nodes: tuple[TalentNode, ...] | list[TalentNode],
    mechanics_repo: MechanicsRepository,
    *,
    role: str,
    encounter: str,
) -> ActionCatalog:
    actions: list[CatalogAction] = []
    warnings: list[str] = []
    passive_skipped = 0
    missing_mechanics = 0

    for node in selected_nodes:
        mechanic = mechanics_repo.get_spell_id(int(node.spell_id or 0)) if node.spell_id else None
        if node.is_passive or mechanic and mechanic.kind == "passive":
            passive_skipped += 1
            continue

        if mechanic is None:
            missing_mechanics += 1
            warnings.append(f"missing_mechanics:{node.spell_id}")
            actions.append(_fallback_action(node, role))
            continue

        actions.append(_action_from_mechanic(node, mechanic, role))

    actions_by_key = {action.action_key: action for action in actions}
    actions_by_spell_id = {action.spell_id: action for action in actions}
    selected_count = len(tuple(selected_nodes))
    coverage = (
        round((selected_count - passive_skipped - missing_mechanics) / max(selected_count - passive_skipped, 1) * 100, 2)
        if selected_count
        else 0.0
    )

    return ActionCatalog(
        actions_by_key=actions_by_key,
        actions_by_spell_id=actions_by_spell_id,
        warnings=tuple(warnings),
        coverage_summary={
            "selected_node_count": selected_count,
            "executable_action_count": len(actions),
            "passive_skipped_count": passive_skipped,
            "missing_mechanics_count": missing_mechanics,
            "mechanics_coverage_pct": coverage,
        },
    )


def classify_action_role(mechanic: MechanicRecord, *, role: str) -> str:
    effect_types = {effect.effect_type for effect in mechanic.effects}
    effect_tags = {tag for effect in mechanic.effects for tag in effect.tags}
    mechanic_tags = effect_tags | {mechanic.kind}

    if role == "support" and ("support" in effect_tags or "aura_apply" in effect_types):
        return "support"
    if "heal" in effect_types:
        return "heal"
    if effect_types & {"damage_reduction", "shield", "absorb"} or mechanic_tags & {"tank", "mitigation"}:
        return "mitigation"
    if effect_types & {"damage"} or mechanic.kind == "debuff":
        return "damage"
    if effect_types & {"summon", "aura_apply", "stat_modify"} or mechanic.kind in {"pet_action", "cooldown"}:
        return "utility"
    return "unknown"


def _action_from_mechanic(node: TalentNode, mechanic: MechanicRecord, role: str) -> CatalogAction:
    return CatalogAction(
        action_key=_action_key(mechanic.name or node.name),
        entry_id=node.entry_id,
        spell_id=int(node.spell_id or mechanic.spell_id),
        name=mechanic.name or node.name,
        # Nullable passthrough — NO invented defaults. A missing cooldown/gcd/costs stays None (unknown)
        # and blocks the quantitative scope via quantitative_readiness; a proven 0/1500/{} is preserved.
        costs=dict(mechanic.costs) if mechanic.costs is not None else None,
        generates=dict(mechanic.generates),
        spends=dict(mechanic.spends),
        cooldown_ms=mechanic.cooldown_ms,
        gcd_ms=mechanic.gcd_ms,
        cast_time_ms=mechanic.cast_time_ms,
        range_yards=mechanic.range_yards,
        duration_ms=mechanic.duration_ms,
        tick_interval_ms=mechanic.tick_interval_ms or _first_tick_interval(mechanic.effects),
        effects=mechanic.effects,
        tags=tuple(dict.fromkeys((*node.tags, *(tag for effect in mechanic.effects for tag in effect.tags)))),
        mechanic_kind=mechanic.kind,
        confidence=mechanic.confidence,
        role_classification=classify_action_role(mechanic, role=role),
        source="mechanics",
        warnings=tuple(),
        field_readiness=dict(mechanic.field_readiness) if mechanic.field_readiness else None,
        mechanic=mechanic,
        node=node,
    )


def _fallback_action(node: TalentNode, role: str) -> CatalogAction:
    return CatalogAction(
        action_key=_action_key(node.name),
        entry_id=node.entry_id,
        spell_id=int(node.spell_id or 0),
        name=node.name,
        # No mechanic at all -> every load-bearing field is unknown (blocks the quantitative scope).
        costs=None,
        generates={},
        spends={},
        cooldown_ms=None,
        gcd_ms=None,
        cast_time_ms=None,
        range_yards=None,
        duration_ms=None,
        tick_interval_ms=None,
        effects=tuple(),
        tags=node.tags,
        mechanic_kind="unknown",
        confidence="low",
        role_classification="unknown",
        source="fallback",
        warnings=(f"missing_mechanics:{node.spell_id}",),
        field_readiness={f: {"status": "unavailable", "reason_code": "not_extracted"}
                         for f in ("gcd_ms", "cooldown_ms", "costs")},
        mechanic=None,
        node=node,
    )


def _first_tick_interval(effects: tuple[MechanicEffect, ...]) -> int | None:
    for effect in effects:
        if effect.tick_interval_ms is not None:
            return effect.tick_interval_ms
    return None


def _action_key(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    return value or "action"
