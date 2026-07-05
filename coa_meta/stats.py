from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StatProfile:
    strength: float = 0.0
    agility: float = 0.0
    stamina: float = 0.0
    intellect: float = 0.0
    spirit: float = 0.0
    attack_power: float = 0.0
    ranged_attack_power: float = 0.0
    spell_power: float = 0.0
    crit_rating: float = 0.0
    haste_rating: float = 0.0
    hit_rating: float = 0.0
    expertise_rating: float = 0.0
    armor: float = 0.0

    def __add__(self, other: "StatProfile") -> "StatProfile":
        return StatProfile(
            **{field: getattr(self, field) + getattr(other, field) for field in STAT_FIELDS}
        )

    @classmethod
    def from_mapping(cls, values: dict[str, Any] | None) -> "StatProfile":
        values = values or {}
        return cls(**{field: _as_float(values.get(field)) for field in STAT_FIELDS})

    def to_dict(self) -> dict[str, float]:
        return {field: getattr(self, field) for field in STAT_FIELDS if getattr(self, field)}


@dataclass(frozen=True)
class StatPriority:
    stat: str
    weight: float
    confidence: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "stat": self.stat,
            "weight": self.weight,
            "confidence": self.confidence,
            "reason": self.reason,
        }


STAT_FIELDS = tuple(StatProfile.__dataclass_fields__)

ROLE_STAT_WEIGHTS: dict[str, dict[str, float]] = {
    "dps": {
        "attack_power": 3.0,
        "spell_power": 3.0,
        "strength": 2.0,
        "agility": 2.0,
        "crit_rating": 1.5,
        "haste_rating": 1.4,
        "hit_rating": 1.3,
        "expertise_rating": 1.0,
        "intellect": 0.5,
        "stamina": 0.2,
    },
    "tank": {
        "stamina": 3.0,
        "armor": 2.8,
        "strength": 1.8,
        "agility": 1.2,
        "expertise_rating": 1.0,
        "hit_rating": 0.8,
        "attack_power": 0.7,
        "crit_rating": 0.3,
    },
    "healer_support": {
        "spell_power": 3.0,
        "intellect": 2.4,
        "spirit": 1.8,
        "haste_rating": 1.3,
        "crit_rating": 1.0,
        "stamina": 0.4,
    },
}


def stat_priority_for_role(role: str) -> tuple[StatPriority, ...]:
    weights = ROLE_STAT_WEIGHTS.get(role)
    if not weights:
        raise ValueError(f"Unsupported role {role!r}")
    return tuple(
        StatPriority(
            stat=stat,
            weight=weight,
            confidence="medium",
            reason=f"Generic {role} stat weight pending simulator/log calibration.",
        )
        for stat, weight in sorted(weights.items(), key=lambda item: (-item[1], item[0]))
    )


def _as_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
