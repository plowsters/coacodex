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


@dataclass(frozen=True)
class StatPriorityGroup:
    group_id: str
    label: str
    entries: tuple[StatPriority, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "label": self.label,
            "entries": [entry.to_dict() for entry in self.entries],
        }


@dataclass(frozen=True)
class StatPriorityReport:
    role: str
    engine_role: str
    disclaimer: str
    source: str
    confidence: str
    groups: tuple[StatPriorityGroup, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "coa-stat-priority-v2",
            "role": self.role,
            "engine_role": self.engine_role,
            "disclaimer": self.disclaimer,
            "source": self.source,
            "confidence": self.confidence,
            "groups": [group.to_dict() for group in self.groups],
            "warnings": list(self.warnings),
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

GUIDE_ROLE_STAT_WEIGHTS: dict[str, dict[str, float]] = {
    "melee_dps": {
        "attack_power": 3.0,
        "strength": 2.2,
        "agility": 2.0,
        "hit_rating": 1.5,
        "expertise_rating": 1.3,
        "crit_rating": 1.2,
        "haste_rating": 1.0,
        "stamina": 0.2,
    },
    "caster_dps": {
        "spell_power": 3.0,
        "intellect": 2.0,
        "hit_rating": 1.6,
        "haste_rating": 1.3,
        "crit_rating": 1.1,
        "spirit": 0.4,
        "stamina": 0.2,
    },
    "ranged_dps": {
        "ranged_attack_power": 3.0,
        "agility": 2.3,
        "attack_power": 1.8,
        "hit_rating": 1.5,
        "crit_rating": 1.3,
        "haste_rating": 1.1,
        "stamina": 0.2,
    },
    "tank": ROLE_STAT_WEIGHTS["tank"],
    "healer": {
        "spell_power": 3.0,
        "intellect": 2.4,
        "spirit": 1.8,
        "haste_rating": 1.3,
        "crit_rating": 1.0,
        "stamina": 0.4,
    },
    "support": {
        "spell_power": 2.4,
        "intellect": 2.0,
        "spirit": 1.2,
        "haste_rating": 1.2,
        "crit_rating": 0.9,
        "attack_power": 0.8,
        "stamina": 0.4,
    },
}

STAT_DISCLAIMER = "Stat priorities are early theorycraft until simulations or combat logs are available."


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


def stat_priority_report_for_role(role: str, *, engine_role: str) -> StatPriorityReport:
    weights = GUIDE_ROLE_STAT_WEIGHTS.get(role) or ROLE_STAT_WEIGHTS.get(engine_role)
    if not weights:
        raise ValueError(f"Unsupported role {role!r}")
    entries = tuple(
        StatPriority(
            stat=stat,
            weight=weight,
            confidence="medium" if role in GUIDE_ROLE_STAT_WEIGHTS else "low",
            reason=f"Generic {role} priority from role heuristics; pending simulator/log calibration.",
        )
        for stat, weight in sorted(weights.items(), key=lambda item: (-item[1], item[0]))
    )
    return StatPriorityReport(
        role=role,
        engine_role=engine_role,
        disclaimer=STAT_DISCLAIMER,
        source="heuristic",
        confidence="medium" if role in GUIDE_ROLE_STAT_WEIGHTS else "low",
        groups=(
            StatPriorityGroup("primary", "Best stats to target", entries[:3]),
            StatPriorityGroup("secondary", "Good supporting stats", entries[3:7]),
            StatPriorityGroup("situational", "Situational stats", entries[7:]),
        ),
        warnings=("stat_priority_not_simulated",),
    )


def _as_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
