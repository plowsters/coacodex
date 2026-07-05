from __future__ import annotations

from coa_meta.combat.engine import CombatEngine, CombatEngineConfig
from coa_meta.combat.state import ActionEffect, ActorState, CombatAction


def test_engine_casts_first_available_action_and_tracks_damage_resources_and_cooldowns():
    strike = CombatAction(
        spell_id=4001,
        name="Venom Strike",
        gcd_ms=1000,
        cooldown_ms=2000,
        costs={"Energy": 20},
        effects=(ActionEffect(effect_type="damage", amount=100, school="nature"),),
    )
    actor = ActorState(resources={"Energy": 100}, max_resources={"Energy": 100})

    result = CombatEngine(
        actions=(strike,),
        actor=actor,
        config=CombatEngineConfig(duration_ms=5000, seed=7),
    ).run()

    assert result.total_damage == 300
    assert result.casts_by_spell[4001] == 3
    assert result.final_resources["Energy"] == 40
    assert [event.event_type for event in result.events if event.spell_id == 4001].count("cast") == 3
    assert [event.time_ms for event in result.events if event.event_type == "damage"] == [0, 2000, 4000]


def test_engine_schedules_periodic_damage_ticks():
    toxin = CombatAction(
        spell_id=4002,
        name="Lingering Toxin",
        gcd_ms=1500,
        cooldown_ms=10000,
        effects=(
            ActionEffect(
                effect_type="damage",
                amount=25,
                school="nature",
                duration_ms=6000,
                tick_interval_ms=2000,
            ),
        ),
    )

    result = CombatEngine(
        actions=(toxin,),
        actor=ActorState(),
        config=CombatEngineConfig(duration_ms=7000, seed=7),
    ).run()

    tick_events = [event for event in result.events if event.event_type == "periodic_damage"]

    assert result.total_damage == 75
    assert [event.time_ms for event in tick_events] == [2000, 4000, 6000]
    assert all(event.amount == 25 for event in tick_events)
