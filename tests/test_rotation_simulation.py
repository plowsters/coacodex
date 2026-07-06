from __future__ import annotations

from coa_meta.action_catalog import ActionCatalog, CatalogAction
from coa_meta.apl import APLAction, APLDocument
from coa_meta.mechanics import MechanicEffect
from coa_meta.rotation_simulation import RotationSimulationConfig, simulate_apl


def _apl(*actions: APLAction) -> APLDocument:
    return APLDocument(
        schema_version="coa-apl-v1",
        source="theorycraft",
        profile_id="test",
        class_name="Testclass",
        spec_key="test",
        role="dps",
        encounter="single_target",
        actions=actions,
        assumptions=tuple(),
        warnings=tuple(),
        provenance={},
    )


def _apl_action(key: str, condition: str, priority: float, category: str = "test") -> APLAction:
    return APLAction(
        action_key=key,
        action_name=key.replace("_", " ").title(),
        node_id=None,
        spell_id=1000 + int(priority),
        category=category,
        condition=condition,
        priority=priority,
        confidence="medium",
        notes=tuple(),
        evidence=tuple(),
    )


def _catalog(*actions: CatalogAction) -> ActionCatalog:
    return ActionCatalog(
        actions_by_key={action.action_key: action for action in actions},
        actions_by_spell_id={action.spell_id: action for action in actions},
        warnings=tuple(),
        coverage_summary={},
    )


def _action(
    key: str,
    *,
    costs: dict[str, float] | None = None,
    generates: dict[str, float] | None = None,
    cooldown_ms: int = 0,
    gcd_ms: int = 1500,
    effects: tuple[MechanicEffect, ...] = tuple(),
    role_classification: str = "damage",
) -> CatalogAction:
    return CatalogAction(
        action_key=key,
        entry_id=1,
        spell_id=1000,
        name=key.replace("_", " ").title(),
        costs=costs or {},
        generates=generates or {},
        spends=costs or {},
        cooldown_ms=cooldown_ms,
        gcd_ms=gcd_ms,
        cast_time_ms=None,
        range_yards=None,
        duration_ms=None,
        tick_interval_ms=None,
        effects=effects,
        tags=tuple(),
        mechanic_kind="ability",
        confidence="medium",
        role_classification=role_classification,
        source="test",
    )


def test_simulation_executes_builder_spender_loop_without_overcapping():
    result = simulate_apl(
        _apl(
            _apl_action("spend", "energy>=80", 10),
            _apl_action("build", "energy.deficit>0", 20),
        ),
        _catalog(
            _action("build", generates={"energy": 40}),
            _action("spend", costs={"energy": 80}),
        ),
        RotationSimulationConfig(
            duration_ms=7000,
            initial_resources={"energy": 0},
            max_resources={"energy": 100},
        ),
    )

    sequence = [event.action_key for event in result.events[:4]]

    assert sequence == ["build", "build", "spend", "build"]
    assert result.resources["energy"] <= 100
    assert result.action_usage["build"].count >= result.action_usage["spend"].count


def test_simulation_refreshes_dot_near_expiry_not_every_gcd():
    dot_effect = MechanicEffect(
        effect_type="damage",
        target="enemy",
        duration_ms=6000,
        tick_interval_ms=2000,
        tags=("dot",),
    )
    result = simulate_apl(
        _apl(
            _apl_action("dot", "dot.dot.remains<gcd", 10),
            _apl_action("filler", "", 20),
        ),
        _catalog(
            _action("dot", effects=(dot_effect,)),
            _action("filler"),
        ),
        RotationSimulationConfig(duration_ms=15000),
    )

    dot_times = [event.time_ms for event in result.events if event.action_key == "dot"]

    assert len(dot_times) >= 2
    assert all((later - earlier) >= 4500 for earlier, later in zip(dot_times, dot_times[1:]))
    assert result.action_usage["dot"].count < result.action_usage["filler"].count


def test_simulation_respects_cooldown_ready_condition():
    result = simulate_apl(
        _apl(
            _apl_action("burst", "cooldown.burst.ready", 10),
            _apl_action("filler", "", 20),
        ),
        _catalog(
            _action("burst", cooldown_ms=6000),
            _action("filler"),
        ),
        RotationSimulationConfig(duration_ms=10000),
    )

    burst_times = [event.time_ms for event in result.events if event.action_key == "burst"]

    assert burst_times == [0, 6000]


def test_simulation_supports_healer_and_tank_state_conditions():
    healer = simulate_apl(
        _apl(
            _apl_action("heal", "when allies injured", 10),
            _apl_action("filler", "", 20),
        ),
        _catalog(_action("heal", role_classification="heal"), _action("filler")),
        RotationSimulationConfig(duration_ms=2000, ally_health_pct=50),
    )
    tank = simulate_apl(
        _apl(
            _apl_action("mitigate", "before heavy damage", 10),
            _apl_action("filler", "", 20),
        ),
        _catalog(_action("mitigate", role_classification="mitigation"), _action("filler")),
        RotationSimulationConfig(duration_ms=2000, damage_window_active=True),
    )

    assert healer.events[0].action_key == "heal"
    assert tank.events[0].action_key == "mitigate"


def test_simulation_records_unsupported_conditions():
    result = simulate_apl(
        _apl(_apl_action("mystery", "unknown.condition", 10)),
        _catalog(_action("mystery")),
        RotationSimulationConfig(duration_ms=2000),
    )

    assert result.events == tuple()
    assert "unsupported_condition:unknown.condition" in result.warnings
    assert result.unsupported_condition_count == 1
