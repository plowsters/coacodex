from __future__ import annotations

import pytest

from coa_meta.action_catalog import ActionCatalog, CatalogAction
from coa_meta.apl import APLAction, APLDocument
from coa_meta.mechanics import MechanicEffect
from coa_meta.rotation_scoring import score_rotation_result, select_best_rotation_candidate
from coa_meta.rotation_guides import (
    ActionUsageSummary,
    RotationGuide,
    RotationGuideRule,
    RotationSimulationSummary,
    build_rotation_guide,
)
from coa_meta.rotation_simulation import ActionUsage, RotationEvent, RotationSimulationResult


def _rule(rule_id: str, section: str, name: str) -> RotationGuideRule:
    return RotationGuideRule(
        rule_id=rule_id,
        section=section,
        text=f"Use {name}.",
        ability_name=name,
        spell_id=1000,
        entry_id=2000,
        icon="ability_test",
        db_url="https://db.ascension.gg/?spell=1000",
        condition="when ready",
        priority=1,
    )


def _apl(*actions: APLAction, role: str = "melee_dps") -> APLDocument:
    return APLDocument(
        schema_version="coa-apl-v1",
        source="theorycraft",
        profile_id="test",
        class_name="Venomancer",
        spec_key="stalking",
        role=role,
        encounter="single_target",
        actions=actions,
        assumptions=tuple(),
        warnings=tuple(),
        provenance={"test": "rotation_guides"},
    )


def _apl_action(key: str, category: str, priority: float, condition: str = "") -> APLAction:
    return APLAction(
        action_key=key,
        action_name=key.replace("_", " ").title(),
        node_id=priority.__int__(),
        spell_id=1000 + priority.__int__(),
        category=category,
        condition=condition,
        priority=priority,
        confidence="medium",
        notes=tuple(),
        evidence=("test",),
    )


def _catalog_action(
    key: str,
    *,
    role: str = "damage",
    cooldown_ms: int = 0,
    duration_ms: int | None = None,
    effect_type: str = "damage",
) -> CatalogAction:
    return CatalogAction(
        action_key=key,
        entry_id=1,
        spell_id=1001,
        name=key.replace("_", " ").title(),
        costs={},
        generates={},
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


def _catalog(*actions: CatalogAction) -> ActionCatalog:
    return ActionCatalog(
        actions_by_key={action.action_key: action for action in actions},
        actions_by_spell_id={action.spell_id: action for action in actions},
        warnings=tuple(),
        coverage_summary={"mechanics_coverage_pct": 100.0},
    )


def _result(
    keys: tuple[str, ...],
    *,
    role_classification: str = "damage",
    candidate_id: str = "candidate",
    damage: float = 500.0,
    healing: float = 0.0,
    support_events: int = 0,
    mitigation_events: int = 0,
) -> RotationSimulationResult:
    usage_counts: dict[str, int] = {}
    events: list[RotationEvent] = []
    for index, key in enumerate(keys):
        usage_counts[key] = usage_counts.get(key, 0) + 1
        events.append(
            RotationEvent(
                time_ms=index * 1500,
                action_key=key,
                ability_name=key.replace("_", " ").title(),
                category="test",
                condition="",
                role_classification=role_classification,
            )
        )
    return RotationSimulationResult(
        source=candidate_id,
        source_kind="verified",
        duration_ms=max(60_000, len(keys) * 1500),
        events=tuple(events),
        resources={},
        cooldown_ready={},
        buffs={},
        debuffs={},
        action_usage={
            key: ActionUsage(action_key=key, ability_name=key.replace("_", " ").title(), count=count)
            for key, count in usage_counts.items()
        },
        total_damage=damage,
        total_healing=healing,
        support_events=support_events,
        mitigation_events=mitigation_events,
        warnings=tuple(),
        unsupported_condition_count=0,
        unsupported_effect_count=0,
    )


def _selection(result: RotationSimulationResult, role: str, catalog: ActionCatalog):
    score = score_rotation_result(result, role, catalog)
    return select_best_rotation_candidate((score,), role)


def test_rotation_guide_serializes_schema_sections_and_rules():
    summary = RotationSimulationSummary(
        source="simulated",
        role="melee_dps",
        encounter="single_target",
        duration_ms=90000,
        objective_score=123.4,
        reliability="medium",
        action_count=42,
        unsupported_condition_count=1,
        unsupported_effect_count=2,
        warnings=("unsupported_condition:buff.remains",),
    )
    guide = RotationGuide(
        source="simulated",
        role="melee_dps",
        encounter="single_target",
        build_id="test-build",
        simulation_summary=summary,
        opener=(_rule("open", "opener", "Fel Opener"),),
        core_loop=(_rule("core", "core_loop", "Fel Strike"),),
        priority_rules=(_rule("priority", "priority", "Venom Bite"),),
        cooldown_rules=(_rule("cooldown", "cooldowns", "Fel Frenzy"),),
        proc_rules=(_rule("proc", "procs", "Toxic Surge"),),
        defensive_rules=(_rule("defensive", "defensives", "Hardened Skin"),),
        healing_rules=(_rule("heal", "healing", "Renewing Spores"),),
        support_rules=(_rule("support", "support", "Fel Chant"),),
        ability_sequence=("Fel Opener", "Fel Strike", "Venom Bite"),
        action_usage=(ActionUsageSummary(action_key="fel_strike", ability_name="Fel Strike", count=12, first_used_ms=1500),),
        reliability="medium",
        warnings=("mechanics_inferred",),
    )

    payload = guide.to_dict()

    assert payload["schema_version"] == "coa-rotation-guide-v1"
    assert payload["source"] == "simulated"
    assert payload["build_id"] == "test-build"
    assert payload["simulation_summary"]["objective_score"] == 123.4
    assert payload["simulation_summary"]["unsupported_condition_count"] == 1
    assert payload["simulation_summary"]["unsupported_effect_count"] == 2
    assert payload["opener"][0]["ability_name"] == "Fel Opener"
    assert payload["core_loop"][0]["spell_id"] == 1000
    assert payload["cooldown_rules"][0]["db_url"] == "https://db.ascension.gg/?spell=1000"
    assert payload["proc_rules"][0]["entry_id"] == 2000
    assert payload["defensive_rules"][0]["text"] == "Use Hardened Skin."
    assert payload["healing_rules"][0]["ability_name"] == "Renewing Spores"
    assert payload["support_rules"][0]["ability_name"] == "Fel Chant"
    assert payload["ability_sequence"] == ["Fel Opener", "Fel Strike", "Venom Bite"]
    assert payload["action_usage"][0]["count"] == 12
    assert payload["warnings"] == ["mechanics_inferred"]


def test_empty_rotation_guide_sections_serialize_as_lists():
    guide = RotationGuide(
        source="theorycraft",
        role="healer",
        encounter="aoe",
        build_id="empty",
        simulation_summary=RotationSimulationSummary(
            source="theorycraft",
            role="healer",
            encounter="aoe",
            duration_ms=0,
            objective_score=0.0,
            reliability="low",
            action_count=0,
            unsupported_condition_count=0,
            unsupported_effect_count=0,
        ),
        reliability="low",
    )

    payload = guide.to_dict()

    for key in (
        "opener",
        "core_loop",
        "priority_rules",
        "cooldown_rules",
        "proc_rules",
        "defensive_rules",
        "healing_rules",
        "support_rules",
        "aoe_adjustments",
        "movement_notes",
        "ability_sequence",
        "action_usage",
        "warnings",
    ):
        assert payload[key] == []


def test_build_rotation_guide_uses_simulated_builder_spender_sequence_for_core_loop():
    apl = _apl(
        _apl_action("spend", "spender", 10, "energy>=80"),
        _apl_action("build", "builder", 20, "energy.deficit>0"),
    )
    catalog = _catalog(_catalog_action("build"), _catalog_action("spend"))
    result = _result(("build", "build", "spend", "build", "build", "spend"), damage=900)

    guide = build_rotation_guide(_selection(result, "melee_dps", catalog), apl, catalog, role="melee_dps", encounter="single_target")

    assert guide.source == "simulated"
    assert guide.ability_sequence[:3] == ("Build", "Build", "Spend")
    assert [rule.ability_name for rule in guide.core_loop] == ["Build", "Spend"]
    assert guide.simulation_summary.objective_score > 0
    assert "rotation_guide_sparse_primary_rules" in guide.warnings


def test_build_rotation_guide_separates_dot_maintenance_and_cooldowns():
    apl = _apl(
        _apl_action("dot", "maintenance", 10, "dot.dot.remains<gcd"),
        _apl_action("burst", "cooldown", 20, "cooldown.burst.ready"),
        _apl_action("filler", "filler", 30, ""),
    )
    catalog = _catalog(
        _catalog_action("dot", duration_ms=12000),
        _catalog_action("burst", cooldown_ms=90000),
        _catalog_action("filler"),
    )
    result = _result(("dot", "burst", "filler", "filler", "filler", "dot", "filler"), damage=700)

    guide = build_rotation_guide(_selection(result, "caster_dps", catalog), apl, catalog, role="caster_dps", encounter="single_target")

    assert [rule.ability_name for rule in guide.priority_rules] == ["Dot"]
    assert guide.priority_rules[0].section == "maintenance"
    assert [rule.ability_name for rule in guide.cooldown_rules] == ["Burst"]
    assert "Dot" not in [rule.ability_name for rule in guide.core_loop]


def test_build_rotation_guide_populates_role_specific_sections():
    cases = (
        ("tank", "shield_wall", "defensive", "mitigation", "damage_reduction", "defensive_rules"),
        ("healer", "big_heal", "healing", "heal", "heal", "healing_rules"),
        ("support", "group_buff", "support", "support", "aura_apply", "support_rules"),
    )
    for role, key, category, classification, effect_type, section_name in cases:
        apl = _apl(_apl_action(key, category, 10, ""), _apl_action("filler", "filler", 20, ""), role=role)
        catalog = _catalog(
            _catalog_action(key, role=classification, effect_type=effect_type, duration_ms=8000),
            _catalog_action("filler"),
        )
        result = _result((key, "filler", "filler", key), role_classification=classification, healing=500)

        guide = build_rotation_guide(_selection(result, role, catalog), apl, catalog, role=role, encounter="single_target")

        rules = getattr(guide, section_name)
        assert [rule.ability_name for rule in rules] == [key.replace("_", " ").title()]


def test_build_rotation_guide_limits_primary_rules_to_twelve():
    actions = tuple(_apl_action(f"strike_{index}", "builder", index) for index in range(1, 16))
    catalog = _catalog(*(_catalog_action(f"strike_{index}") for index in range(1, 16)))
    keys = tuple(f"strike_{index}" for index in range(1, 16))

    guide = build_rotation_guide(
        _selection(_result(keys, damage=1500), "melee_dps", catalog),
        _apl(*actions),
        catalog,
        role="melee_dps",
        encounter="single_target",
    )

    assert len(guide.core_loop) == 12
    assert guide.warnings == tuple()


def test_rotation_reliability_values_are_validated():
    with pytest.raises(ValueError, match="Invalid rotation reliability"):
        RotationSimulationSummary(
            source="simulated",
            role="tank",
            encounter="single_target",
            duration_ms=90000,
            objective_score=1.0,
            reliability="certain",
            action_count=1,
            unsupported_condition_count=0,
            unsupported_effect_count=0,
        )

    with pytest.raises(ValueError, match="Invalid rotation reliability"):
        RotationGuide(
            source="simulated",
            role="tank",
            encounter="single_target",
            build_id="bad",
            simulation_summary=RotationSimulationSummary(
                source="simulated",
                role="tank",
                encounter="single_target",
                duration_ms=90000,
                objective_score=1.0,
                reliability="medium",
                action_count=1,
                unsupported_condition_count=0,
                unsupported_effect_count=0,
            ),
            reliability="certain",
        )
