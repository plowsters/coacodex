from __future__ import annotations

from coa_meta.action_catalog import ActionCatalog, CatalogAction
from coa_meta.mechanics import MechanicEffect
from coa_meta.rotation_scoring import score_rotation_result, select_best_rotation_candidate
from coa_meta.rotation_simulation import ActionUsage, RotationEvent, RotationSimulationResult


def _catalog_action(
    key: str,
    *,
    role: str = "damage",
    costs: dict[str, float] | None = None,
    generates: dict[str, float] | None = None,
    cooldown_ms: int = 0,
    duration_ms: int | None = None,
    effect_type: str = "damage",
) -> CatalogAction:
    return CatalogAction(
        action_key=key,
        entry_id=1,
        spell_id=1001,
        name=key.replace("_", " ").title(),
        costs=costs or {},
        generates=generates or {},
        spends={},
        cooldown_ms=cooldown_ms,
        gcd_ms=1500,
        cast_time_ms=None,
        range_yards=None,
        duration_ms=duration_ms,
        tick_interval_ms=None,
        effects=(MechanicEffect(effect_type=effect_type, amount=10, duration_ms=duration_ms),),
        tags=tuple(),
        mechanic_kind="active",
        confidence="medium",
        role_classification=role,
        source="test",
    )


def _catalog(*actions: CatalogAction, coverage: float = 100.0) -> ActionCatalog:
    return ActionCatalog(
        actions_by_key={action.action_key: action for action in actions},
        actions_by_spell_id={action.spell_id: action for action in actions},
        warnings=tuple(),
        coverage_summary={"mechanics_coverage_pct": coverage},
    )


def _result(
    *,
    candidate_id: str = "candidate",
    damage: float = 0.0,
    healing: float = 0.0,
    support_events: int = 0,
    mitigation_events: int = 0,
    usage: dict[str, int] | None = None,
    unsupported_conditions: int = 0,
    unsupported_effects: int = 0,
    warnings: tuple[str, ...] = tuple(),
) -> RotationSimulationResult:
    usages = {
        key: ActionUsage(action_key=key, ability_name=key.title(), count=count, first_used_ms=0, last_used_ms=9000)
        for key, count in (usage or {}).items()
    }
    events = tuple(
        RotationEvent(
            time_ms=index * 1500,
            action_key=key,
            ability_name=key.title(),
            category="test",
            condition="",
            role_classification="damage",
        )
        for index, key in enumerate(usages)
    )
    return RotationSimulationResult(
        source=candidate_id,
        duration_ms=60_000,
        events=events,
        resources={},
        cooldown_ready={},
        buffs={},
        debuffs={},
        action_usage=usages,
        total_damage=damage,
        total_healing=healing,
        support_events=support_events,
        mitigation_events=mitigation_events,
        warnings=warnings,
        unsupported_condition_count=unsupported_conditions,
        unsupported_effect_count=unsupported_effects,
    )


def test_dps_roles_prefer_damage_uptime_and_resource_efficiency():
    catalog = _catalog(
        _catalog_action("build", generates={"energy": 40}),
        _catalog_action("spend", costs={"energy": 80}),
    )
    low = score_rotation_result(
        _result(candidate_id="low", damage=500, usage={"build": 4, "spend": 1}),
        "melee_dps",
        catalog,
    )
    high = score_rotation_result(
        _result(candidate_id="high", damage=900, usage={"build": 4, "spend": 2}),
        "melee_dps",
        catalog,
    )

    assert high.objective_score > low.objective_score
    assert high.breakdown["damage_throughput"] > low.breakdown["damage_throughput"]
    assert high.breakdown["resource_efficiency"] > low.breakdown["resource_efficiency"]
    assert high.reliability == "high"


def test_tank_role_values_mitigation_survivability_threat_and_damage_contribution():
    catalog = _catalog(
        _catalog_action("shield_wall", role="mitigation", effect_type="damage_reduction", duration_ms=8000),
        _catalog_action("slam"),
    )

    mitigation = score_rotation_result(
        _result(candidate_id="tank", damage=300, healing=100, mitigation_events=4, usage={"shield_wall": 4}),
        "tank",
        catalog,
    )
    damage_only = score_rotation_result(
        _result(candidate_id="dps", damage=900, usage={"slam": 12}),
        "tank",
        catalog,
    )

    assert mitigation.objective_score > damage_only.objective_score
    assert mitigation.breakdown["mitigation_coverage"] > damage_only.breakdown["mitigation_coverage"]
    assert mitigation.breakdown["survivability"] > 0
    assert mitigation.breakdown["threat_proxy"] > 0


def test_healer_role_values_healing_mana_efficiency_and_safe_damage():
    catalog = _catalog(
        _catalog_action("heal", role="heal", costs={"mana": 20}, effect_type="heal"),
        _catalog_action("smite"),
    )

    healer = score_rotation_result(
        _result(candidate_id="heal", damage=200, healing=1200, usage={"heal": 6, "smite": 2}),
        "healer",
        catalog,
    )
    damage_only = score_rotation_result(
        _result(candidate_id="smite", damage=900, healing=0, usage={"smite": 12}),
        "healer",
        catalog,
    )

    assert healer.objective_score > damage_only.objective_score
    assert healer.breakdown["healing_throughput"] > 0
    assert healer.breakdown["mana_efficiency"] > 0
    assert healer.breakdown["safe_damage"] > 0


def test_support_role_values_buff_utility_and_contribution():
    catalog = _catalog(
        _catalog_action("group_buff", role="support", effect_type="aura_apply", duration_ms=12000),
        _catalog_action("bolt"),
    )

    support = score_rotation_result(
        _result(candidate_id="support", damage=300, support_events=5, usage={"group_buff": 5, "bolt": 4}),
        "support",
        catalog,
    )
    damage_only = score_rotation_result(
        _result(candidate_id="bolt", damage=900, usage={"bolt": 12}),
        "support",
        catalog,
    )

    assert support.objective_score > damage_only.objective_score
    assert support.breakdown["support_coverage"] > damage_only.breakdown["support_coverage"]
    assert support.breakdown["utility_events"] > 0
    assert support.breakdown["contribution"] > 0


def test_reliability_uses_mechanics_coverage_and_unsupported_work():
    catalog = _catalog(_catalog_action("strike"))
    low_coverage_catalog = _catalog(_catalog_action("strike"), coverage=65.0)

    high = score_rotation_result(_result(usage={"strike": 4}), "melee_dps", catalog)
    medium = score_rotation_result(
        _result(usage={"strike": 4}, unsupported_effects=1),
        "melee_dps",
        low_coverage_catalog,
    )
    low = score_rotation_result(
        _result(usage={"strike": 4}, unsupported_conditions=1),
        "melee_dps",
        catalog,
    )

    assert high.reliability == "high"
    assert medium.reliability == "medium"
    assert low.reliability == "low"


def test_selection_can_prefer_reliable_candidate_over_higher_raw_output():
    catalog = _catalog(_catalog_action("strike"))
    risky = score_rotation_result(
        _result(candidate_id="risky", damage=1200, usage={"strike": 12}, unsupported_conditions=2),
        "melee_dps",
        catalog,
    )
    stable = score_rotation_result(
        _result(candidate_id="stable", damage=1100, usage={"strike": 12}),
        "melee_dps",
        catalog,
    )

    selection = select_best_rotation_candidate((risky, stable), "melee_dps")

    assert selection.best.candidate_id == "stable"
    assert selection.ranked[0].candidate_id == "stable"
    assert "reliability_penalty_applied" in risky.warnings
