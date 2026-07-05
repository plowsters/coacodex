from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .stats import ROLE_STAT_WEIGHTS, StatProfile

ITEM_SCHEMA_VERSION = "coa-item-v1"


class GearLoadError(ValueError):
    pass


@dataclass(frozen=True)
class ItemRecord:
    item_id: int
    name: str
    slot: str = ""
    item_class: str = ""
    subclass: str = ""
    weapon_type: str = ""
    armor_type: str = ""
    stats: dict[str, float] = field(default_factory=dict)
    ratings: dict[str, float] = field(default_factory=dict)
    speed: float | None = None
    min_damage: float | None = None
    max_damage: float | None = None
    spell_power: float = 0.0
    attack_power: float = 0.0
    required_level: int | None = None
    confidence: str = "low"
    raw: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "ItemRecord":
        if raw.get("schema_version") != ITEM_SCHEMA_VERSION:
            raise GearLoadError(f"Unsupported item schema_version {raw.get('schema_version')!r}")
        item_id = _as_int(raw.get("item_id"))
        if not item_id:
            raise GearLoadError("Item record missing numeric item_id")
        return cls(
            item_id=item_id,
            name=str(raw.get("name") or ""),
            slot=str(raw.get("slot") or ""),
            item_class=str(raw.get("item_class") or ""),
            subclass=str(raw.get("subclass") or ""),
            weapon_type=str(raw.get("weapon_type") or ""),
            armor_type=str(raw.get("armor_type") or ""),
            stats=_number_map(raw.get("stats")),
            ratings=_number_map(raw.get("ratings")),
            speed=_as_float_or_none(raw.get("speed")),
            min_damage=_as_float_or_none(raw.get("min_damage")),
            max_damage=_as_float_or_none(raw.get("max_damage")),
            spell_power=_as_float(raw.get("spell_power")),
            attack_power=_as_float(raw.get("attack_power")),
            required_level=_as_int_or_none(raw.get("required_level")),
            confidence=str(raw.get("confidence") or "low"),
            raw=dict(raw),
        )

    def stat_profile(self) -> StatProfile:
        values = {**self.stats, **self.ratings}
        values["spell_power"] = values.get("spell_power", 0.0) + self.spell_power
        values["attack_power"] = values.get("attack_power", 0.0) + self.attack_power
        return StatProfile.from_mapping(values)


@dataclass(frozen=True)
class GearProfile:
    items: tuple[ItemRecord, ...] = tuple()

    def total_stats(self) -> StatProfile:
        total = StatProfile()
        for item in self.items:
            total += item.stat_profile()
        return total


@dataclass(frozen=True)
class ItemScore:
    item_id: int
    name: str
    role: str
    score: float
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "role": self.role,
            "score": self.score,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class GearRecommendationReport:
    role: str
    engine_role: str
    best_weapon_types: tuple[str, ...]
    best_armor_types: tuple[str, ...]
    available_weapon_types: tuple[str, ...]
    available_armor_types: tuple[str, ...]
    item_scores: tuple[ItemScore, ...]
    source: str
    confidence: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "coa-gear-recommendation-v2",
            "role": self.role,
            "engine_role": self.engine_role,
            "best_weapon_types": list(self.best_weapon_types),
            "best_armor_types": list(self.best_armor_types),
            "available_weapon_types": list(self.available_weapon_types),
            "available_armor_types": list(self.available_armor_types),
            "item_scores": [score.to_dict() for score in self.item_scores],
            "source": self.source,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
        }


GUIDE_ROLE_GEAR_DEFAULTS: dict[str, dict[str, tuple[str, ...]]] = {
    "melee_dps": {
        "best_weapon_types": ("sword", "axe", "dagger", "mace"),
        "best_armor_types": ("leather", "mail"),
        "available_weapon_types": ("sword", "axe", "dagger", "mace", "staff"),
        "available_armor_types": ("cloth", "leather", "mail", "plate"),
    },
    "caster_dps": {
        "best_weapon_types": ("staff", "dagger", "mace"),
        "best_armor_types": ("cloth", "leather"),
        "available_weapon_types": ("staff", "dagger", "mace", "sword"),
        "available_armor_types": ("cloth", "leather", "mail"),
    },
    "tank": {
        "best_weapon_types": ("shield", "sword", "mace", "axe"),
        "best_armor_types": ("plate", "mail"),
        "available_weapon_types": ("shield", "sword", "mace", "axe"),
        "available_armor_types": ("plate", "mail", "leather"),
    },
    "healer": {
        "best_weapon_types": ("staff", "mace", "dagger"),
        "best_armor_types": ("cloth", "leather", "mail"),
        "available_weapon_types": ("staff", "mace", "dagger", "sword"),
        "available_armor_types": ("cloth", "leather", "mail"),
    },
    "support": {
        "best_weapon_types": ("staff", "mace", "dagger", "sword"),
        "best_armor_types": ("cloth", "leather", "mail"),
        "available_weapon_types": ("staff", "mace", "dagger", "sword", "axe"),
        "available_armor_types": ("cloth", "leather", "mail", "plate"),
    },
}


def load_items_jsonl(path: Path | str) -> tuple[ItemRecord, ...]:
    source = Path(path)
    items: list[ItemRecord] = []
    if not source.exists():
        return tuple()
    with source.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise GearLoadError(f"{source}:{line_no} invalid JSON: {exc}") from exc
            items.append(ItemRecord.from_raw(raw))
    return tuple(items)


def rank_items_for_role(role: str, items: tuple[ItemRecord, ...]) -> tuple[ItemScore, ...]:
    weights = ROLE_STAT_WEIGHTS.get(role)
    if not weights:
        raise GearLoadError(f"Unsupported role {role!r}")
    scores = []
    for item in items:
        profile = item.stat_profile()
        score = sum(getattr(profile, stat, 0.0) * weight for stat, weight in weights.items())
        scores.append(ItemScore(item_id=item.item_id, name=item.name, role=role, score=round(score, 3), confidence=item.confidence))
    return tuple(sorted(scores, key=lambda item: (item.score, item.item_id), reverse=True))


def recommend_weapon_and_armor(role: str, items: tuple[ItemRecord, ...]) -> dict[str, Any]:
    defaults = {
        "dps": {
            "weapon_types": ["sword", "axe", "dagger", "bow", "gun", "staff"],
            "armor_types": ["leather", "mail", "plate", "cloth"],
        },
        "tank": {
            "weapon_types": ["shield", "sword", "mace", "axe"],
            "armor_types": ["plate", "mail"],
        },
        "healer_support": {
            "weapon_types": ["staff", "mace", "dagger"],
            "armor_types": ["cloth", "leather", "mail"],
        },
    }
    if role not in defaults:
        raise GearLoadError(f"Unsupported role {role!r}")

    warnings: list[str] = []
    if not items:
        warnings.append("item_data_missing")
        return {"role": role, **defaults[role], "warnings": warnings}

    weapon_types = sorted({item.weapon_type for item in items if item.weapon_type}) or defaults[role]["weapon_types"]
    armor_types = sorted({item.armor_type for item in items if item.armor_type}) or defaults[role]["armor_types"]
    if any(item.confidence == "low" for item in items):
        warnings.append("item_data_low_confidence")
    return {
        "role": role,
        "weapon_types": weapon_types,
        "armor_types": armor_types,
        "warnings": warnings,
    }


def recommend_gear_for_guide_role(
    role: str,
    *,
    engine_role: str,
    items: tuple[ItemRecord, ...],
) -> GearRecommendationReport:
    defaults = GUIDE_ROLE_GEAR_DEFAULTS.get(role)
    if defaults is None:
        raise GearLoadError(f"Unsupported guide role {role!r}")
    warnings: list[str] = []
    scores: tuple[ItemScore, ...] = tuple()
    source = "defaults"
    confidence = "low"
    if items:
        scores = rank_items_for_role(engine_role, items)
        source = "mixed"
        confidence = "medium"
        if any(item.confidence == "low" for item in items):
            warnings.append("item_data_low_confidence")
    else:
        warnings.extend(("item_data_missing", "gear_targets_from_role_defaults"))
    available_weapon_types = (
        tuple(sorted({item.weapon_type for item in items if item.weapon_type}))
        or defaults["available_weapon_types"]
    )
    available_armor_types = (
        tuple(sorted({item.armor_type for item in items if item.armor_type}))
        or defaults["available_armor_types"]
    )
    return GearRecommendationReport(
        role=role,
        engine_role=engine_role,
        best_weapon_types=defaults["best_weapon_types"],
        best_armor_types=defaults["best_armor_types"],
        available_weapon_types=available_weapon_types,
        available_armor_types=available_armor_types,
        item_scores=scores[:10],
        source=source,
        confidence=confidence,
        warnings=tuple(warnings),
    )


def _as_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _number_map(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for key, amount in value.items():
        parsed = _as_float_or_none(amount)
        if parsed is not None:
            out[str(key)] = parsed
    return out
