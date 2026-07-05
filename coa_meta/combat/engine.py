from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from .events import CombatEvent
from .rng import SeededRng
from .state import ActionEffect, ActorState, CombatAction, TargetState


@dataclass(frozen=True)
class CombatEngineConfig:
    duration_ms: int = 60_000
    seed: int = 1
    target_count: int = 1


@dataclass(frozen=True)
class CombatResult:
    events: tuple[CombatEvent, ...]
    total_damage: float
    total_healing: float
    casts_by_spell: dict[int, int]
    final_resources: dict[str, float]
    warnings: tuple[str, ...] = tuple()

    def to_dict(self) -> dict:
        return {
            "events": [event.to_dict() for event in self.events],
            "total_damage": self.total_damage,
            "total_healing": self.total_healing,
            "casts_by_spell": self.casts_by_spell,
            "final_resources": self.final_resources,
            "warnings": list(self.warnings),
        }


@dataclass(order=True)
class _ScheduledEffect:
    time_ms: int
    sequence: int
    spell_id: int = field(compare=False)
    effect: ActionEffect = field(compare=False)


class CombatEngine:
    def __init__(
        self,
        *,
        actions: tuple[CombatAction, ...],
        actor: ActorState | None = None,
        target: TargetState | None = None,
        config: CombatEngineConfig | None = None,
    ):
        self.actions = actions
        self.actor = actor or ActorState()
        self.target = target or TargetState()
        self.config = config or CombatEngineConfig()
        self.rng = SeededRng(self.config.seed)

    def run(self) -> CombatResult:
        time_ms = 0
        gcd_ready_ms = 0
        sequence = 0
        cooldown_ready: dict[int, int] = {}
        resources = dict(self.actor.resources)
        events: list[CombatEvent] = []
        scheduled: list[_ScheduledEffect] = []
        casts_by_spell: dict[int, int] = {}
        total_damage = 0.0
        total_healing = 0.0
        warnings: list[str] = []

        while time_ms <= self.config.duration_ms:
            while scheduled and scheduled[0].time_ms <= time_ms:
                scheduled_effect = heapq.heappop(scheduled)
                event = self._event_from_effect(
                    scheduled_effect.time_ms,
                    scheduled_effect.spell_id,
                    scheduled_effect.effect,
                    periodic=True,
                )
                events.append(event)
                if event.event_type.endswith("damage"):
                    total_damage += event.amount
                elif event.event_type.endswith("heal"):
                    total_healing += event.amount

            if time_ms >= gcd_ready_ms:
                action = self._first_available_action(time_ms, cooldown_ready, resources)
                if action is not None:
                    events.append(CombatEvent(time_ms=time_ms, event_type="cast", spell_id=action.spell_id))
                    casts_by_spell[action.spell_id] = casts_by_spell.get(action.spell_id, 0) + 1
                    self._spend_resources(resources, action)
                    cooldown_ready[action.spell_id] = time_ms + action.cooldown_ms
                    gcd_ready_ms = time_ms + action.gcd_ms
                    for effect in action.effects:
                        if effect.duration_ms and effect.tick_interval_ms:
                            sequence = self._schedule_periodic_effects(
                                scheduled,
                                sequence,
                                time_ms,
                                action.spell_id,
                                effect,
                            )
                        else:
                            event = self._event_from_effect(time_ms, action.spell_id, effect, periodic=False)
                            events.append(event)
                            if event.event_type == "damage":
                                total_damage += event.amount
                            elif event.event_type == "heal":
                                total_healing += event.amount

            next_time = self._next_time(time_ms, gcd_ready_ms, cooldown_ready, scheduled)
            if next_time is None or next_time > self.config.duration_ms:
                break
            time_ms = next_time

        return CombatResult(
            events=tuple(events),
            total_damage=total_damage,
            total_healing=total_healing,
            casts_by_spell=casts_by_spell,
            final_resources=resources,
            warnings=tuple(warnings),
        )

    def _first_available_action(
        self,
        time_ms: int,
        cooldown_ready: dict[int, int],
        resources: dict[str, float],
    ) -> CombatAction | None:
        for action in self.actions:
            if cooldown_ready.get(action.spell_id, 0) > time_ms:
                continue
            if any(resources.get(resource, 0.0) < cost for resource, cost in action.costs.items()):
                continue
            return action
        return None

    def _spend_resources(self, resources: dict[str, float], action: CombatAction) -> None:
        for resource, cost in action.costs.items():
            resources[resource] = resources.get(resource, 0.0) - cost

    def _schedule_periodic_effects(
        self,
        scheduled: list[_ScheduledEffect],
        sequence: int,
        time_ms: int,
        spell_id: int,
        effect: ActionEffect,
    ) -> int:
        assert effect.duration_ms is not None
        assert effect.tick_interval_ms is not None
        tick_time = time_ms + effect.tick_interval_ms
        end_time = time_ms + effect.duration_ms
        while tick_time <= end_time and tick_time <= self.config.duration_ms:
            sequence += 1
            heapq.heappush(scheduled, _ScheduledEffect(tick_time, sequence, spell_id, effect))
            tick_time += effect.tick_interval_ms
        return sequence

    def _event_from_effect(
        self,
        time_ms: int,
        spell_id: int,
        effect: ActionEffect,
        *,
        periodic: bool,
    ) -> CombatEvent:
        event_type = effect.effect_type
        if periodic and effect.effect_type == "damage":
            event_type = "periodic_damage"
        elif periodic and effect.effect_type == "heal":
            event_type = "periodic_heal"
        return CombatEvent(
            time_ms=time_ms,
            event_type=event_type,
            spell_id=spell_id,
            amount=effect.amount * min(effect.max_targets or 1, self.config.target_count),
            school=effect.school,
            target=effect.target,
        )

    def _next_time(
        self,
        time_ms: int,
        gcd_ready_ms: int,
        cooldown_ready: dict[int, int],
        scheduled: list[_ScheduledEffect],
    ) -> int | None:
        candidates = []
        if gcd_ready_ms > time_ms:
            candidates.append(gcd_ready_ms)
        candidates.extend(ready for ready in cooldown_ready.values() if ready > time_ms)
        if scheduled:
            candidates.append(scheduled[0].time_ms)
        future = [candidate for candidate in candidates if candidate > time_ms]
        return min(future) if future else None
