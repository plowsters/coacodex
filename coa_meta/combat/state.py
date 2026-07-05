from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ActionEffect:
    effect_type: str
    amount: float = 0.0
    school: str = ""
    target: str = "enemy"
    duration_ms: int | None = None
    tick_interval_ms: int | None = None
    max_targets: int | None = None


@dataclass(frozen=True)
class CombatAction:
    spell_id: int
    name: str
    gcd_ms: int = 1500
    cooldown_ms: int = 0
    costs: dict[str, float] = field(default_factory=dict)
    effects: tuple[ActionEffect, ...] = tuple()


@dataclass(frozen=True)
class ActorState:
    resources: dict[str, float] = field(default_factory=dict)
    max_resources: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TargetState:
    name: str = "target"
    health: float = 1_000_000.0
