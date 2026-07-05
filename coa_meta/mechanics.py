from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MECHANICS_SCHEMA_VERSION = "coa-mechanics-v1"


class MechanicsLoadError(ValueError):
    pass


@dataclass(frozen=True)
class ScalingRule:
    coefficient: float | None = None
    weapon_damage_pct: float | None = None
    attack_power_pct: float | None = None
    spell_power_pct: float | None = None
    stat_modifiers: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(
            {
                "coefficient": self.coefficient,
                "weapon_damage_pct": self.weapon_damage_pct,
                "attack_power_pct": self.attack_power_pct,
                "spell_power_pct": self.spell_power_pct,
                "stat_modifiers": self.stat_modifiers,
            }
        )


@dataclass(frozen=True)
class ProcRule:
    chance: float | None = None
    ppm: float | None = None
    internal_cooldown_ms: int | None = None
    trigger_conditions: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(
            {
                "chance": self.chance,
                "ppm": self.ppm,
                "internal_cooldown_ms": self.internal_cooldown_ms,
                "trigger_conditions": list(self.trigger_conditions),
            }
        )


@dataclass(frozen=True)
class MechanicProvenance:
    source: str
    source_id: str = ""
    source_url: str = ""
    parser: str = ""
    confidence: str = "low"
    notes: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(
            {
                "source": self.source,
                "source_id": self.source_id,
                "source_url": self.source_url,
                "parser": self.parser,
                "confidence": self.confidence,
                "notes": list(self.notes),
            },
            drop_empty=True,
        )


@dataclass(frozen=True)
class MechanicEffect:
    effect_type: str
    school: str = ""
    target: str = ""
    amount: float | None = None
    aura: str = ""
    stat: str = ""
    trigger_spell_id: int | None = None
    duration_ms: int | None = None
    tick_interval_ms: int | None = None
    scaling: ScalingRule | None = None
    tags: tuple[str, ...] = tuple()
    raw: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def to_dict(self) -> dict[str, Any]:
        data = _drop_none(
            {
                "effect_type": self.effect_type,
                "school": self.school,
                "target": self.target,
                "amount": self.amount,
                "aura": self.aura,
                "stat": self.stat,
                "trigger_spell_id": self.trigger_spell_id,
                "duration_ms": self.duration_ms,
                "tick_interval_ms": self.tick_interval_ms,
                "scaling": self.scaling.to_dict() if self.scaling else None,
                "tags": list(self.tags),
            },
            drop_empty=True,
        )
        if self.raw:
            data["raw"] = self.raw
        return data


@dataclass(frozen=True)
class MechanicRecord:
    schema_version: str
    spell_id: int
    name: str
    kind: str
    source_node_ids: tuple[int, ...]
    source_urls: tuple[str, ...]
    school: str = ""
    power_type: str = ""
    range_yards: float | None = None
    cast_time_ms: int | None = None
    gcd_ms: int | None = None
    cooldown_ms: int | None = None
    charges: int | None = None
    duration_ms: int | None = None
    tick_interval_ms: int | None = None
    costs: dict[str, float] = field(default_factory=dict)
    generates: dict[str, float] = field(default_factory=dict)
    spends: dict[str, float] = field(default_factory=dict)
    max_targets: int | None = None
    effects: tuple[MechanicEffect, ...] = tuple()
    proc: ProcRule | None = None
    provenance: tuple[MechanicProvenance, ...] = tuple()
    confidence: str = "low"
    raw: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def to_dict(self) -> dict[str, Any]:
        data = _drop_none(
            {
                "schema_version": self.schema_version,
                "spell_id": self.spell_id,
                "name": self.name,
                "kind": self.kind,
                "source_node_ids": list(self.source_node_ids),
                "source_urls": list(self.source_urls),
                "school": self.school,
                "power_type": self.power_type,
                "range_yards": self.range_yards,
                "cast_time_ms": self.cast_time_ms,
                "gcd_ms": self.gcd_ms,
                "cooldown_ms": self.cooldown_ms,
                "charges": self.charges,
                "duration_ms": self.duration_ms,
                "tick_interval_ms": self.tick_interval_ms,
                "costs": self.costs,
                "generates": self.generates,
                "spends": self.spends,
                "max_targets": self.max_targets,
                "effects": [effect.to_dict() for effect in self.effects],
                "proc": self.proc.to_dict() if self.proc else None,
                "provenance": [item.to_dict() for item in self.provenance],
                "confidence": self.confidence,
            },
            drop_empty=True,
        )
        if self.raw:
            data["raw"] = self.raw
        return data


def mechanic_from_raw(raw: dict[str, Any], source: str = "<memory>") -> MechanicRecord:
    if raw.get("schema_version") != MECHANICS_SCHEMA_VERSION:
        raise MechanicsLoadError(f"{source} has unsupported schema_version {raw.get('schema_version')!r}")
    spell_id = _as_int(raw.get("spell_id"))
    if not spell_id:
        raise MechanicsLoadError(f"{source} missing numeric spell_id")
    name = str(raw.get("name") or "")
    if not name:
        raise MechanicsLoadError(f"{source} missing name")
    kind = str(raw.get("kind") or "")
    if not kind:
        raise MechanicsLoadError(f"{source} missing kind")
    return MechanicRecord(
        schema_version=MECHANICS_SCHEMA_VERSION,
        spell_id=spell_id,
        name=name,
        kind=kind,
        source_node_ids=_int_tuple(raw.get("source_node_ids")),
        source_urls=tuple(str(item) for item in raw.get("source_urls") or []),
        school=str(raw.get("school") or ""),
        power_type=str(raw.get("power_type") or ""),
        range_yards=_as_float_or_none(raw.get("range_yards")),
        cast_time_ms=_as_int_or_none(raw.get("cast_time_ms")),
        gcd_ms=_as_int_or_none(raw.get("gcd_ms")),
        cooldown_ms=_as_int_or_none(raw.get("cooldown_ms")),
        charges=_as_int_or_none(raw.get("charges")),
        duration_ms=_as_int_or_none(raw.get("duration_ms")),
        tick_interval_ms=_as_int_or_none(raw.get("tick_interval_ms")),
        costs=_number_map(raw.get("costs")),
        generates=_number_map(raw.get("generates")),
        spends=_number_map(raw.get("spends")),
        max_targets=_as_int_or_none(raw.get("max_targets")),
        effects=tuple(_effect_from_raw(item) for item in raw.get("effects") or []),
        proc=_proc_from_raw(raw.get("proc")) if raw.get("proc") else None,
        provenance=tuple(_provenance_from_raw(item) for item in raw.get("provenance") or []),
        confidence=str(raw.get("confidence") or "low"),
        raw=dict(raw.get("raw") or {}),
    )


def _effect_from_raw(raw: dict[str, Any]) -> MechanicEffect:
    return MechanicEffect(
        effect_type=str(raw.get("effect_type") or ""),
        school=str(raw.get("school") or ""),
        target=str(raw.get("target") or ""),
        amount=_as_float_or_none(raw.get("amount")),
        aura=str(raw.get("aura") or ""),
        stat=str(raw.get("stat") or ""),
        trigger_spell_id=_as_int_or_none(raw.get("trigger_spell_id")),
        duration_ms=_as_int_or_none(raw.get("duration_ms")),
        tick_interval_ms=_as_int_or_none(raw.get("tick_interval_ms")),
        scaling=_scaling_from_raw(raw.get("scaling")) if raw.get("scaling") else None,
        tags=tuple(str(item) for item in raw.get("tags") or []),
        raw=dict(raw.get("raw") or {}),
    )


def _scaling_from_raw(raw: dict[str, Any]) -> ScalingRule:
    return ScalingRule(
        coefficient=_as_float_or_none(raw.get("coefficient")),
        weapon_damage_pct=_as_float_or_none(raw.get("weapon_damage_pct")),
        attack_power_pct=_as_float_or_none(raw.get("attack_power_pct")),
        spell_power_pct=_as_float_or_none(raw.get("spell_power_pct")),
        stat_modifiers=_number_map(raw.get("stat_modifiers")),
    )


def _proc_from_raw(raw: dict[str, Any]) -> ProcRule:
    return ProcRule(
        chance=_as_float_or_none(raw.get("chance")),
        ppm=_as_float_or_none(raw.get("ppm")),
        internal_cooldown_ms=_as_int_or_none(raw.get("internal_cooldown_ms")),
        trigger_conditions=tuple(str(item) for item in raw.get("trigger_conditions") or []),
    )


def _provenance_from_raw(raw: dict[str, Any]) -> MechanicProvenance:
    return MechanicProvenance(
        source=str(raw.get("source") or ""),
        source_id=str(raw.get("source_id") or ""),
        source_url=str(raw.get("source_url") or ""),
        parser=str(raw.get("parser") or ""),
        confidence=str(raw.get("confidence") or "low"),
        notes=tuple(str(item) for item in raw.get("notes") or []),
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


def _as_float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_tuple(values: list[Any] | None) -> tuple[int, ...]:
    out: list[int] = []
    for value in values or []:
        parsed = _as_int(value)
        if parsed:
            out.append(parsed)
    return tuple(out)


def _number_map(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for key, raw_amount in value.items():
        parsed = _as_float_or_none(raw_amount)
        if parsed is not None:
            out[str(key)] = parsed
    return out


def _drop_none(data: dict[str, Any], drop_empty: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if drop_empty and value in ("", [], {}, tuple()):
            continue
        out[key] = value
    return out
