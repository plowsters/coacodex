from __future__ import annotations

from coa_meta.apl import APLAction, APLDocument
from coa_meta.apl_interpreter import APLInterpreter, APLRuntimeState
from coa_meta.combat.state import ActionEffect, CombatAction


def _document(*actions: APLAction) -> APLDocument:
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


def _action(action_key: str, condition: str, priority: float) -> APLAction:
    return APLAction(
        action_key=action_key,
        action_name=action_key.replace("_", " ").title(),
        node_id=None,
        spell_id=1000 + int(priority),
        category="test",
        condition=condition,
        priority=priority,
        confidence="medium",
        notes=tuple(),
        evidence=tuple(),
    )


def test_interpreter_selects_first_usable_action_by_condition_and_priority():
    spender = CombatAction(
        spell_id=1001,
        name="Spend",
        costs={"energy": 80},
        effects=(ActionEffect(effect_type="damage", amount=100),),
    )
    builder = CombatAction(
        spell_id=1002,
        name="Build",
        effects=(ActionEffect(effect_type="damage", amount=20),),
    )
    interpreter = APLInterpreter(
        _document(
            _action("spend", "energy>=80", 10),
            _action("build", "energy.deficit>0", 20),
        ),
        action_catalog={"spend": spender, "build": builder},
    )

    decision = interpreter.choose_action(
        APLRuntimeState(resources={"energy": 90}, max_resources={"energy": 100})
    )

    assert decision.action == spender
    assert decision.apl_action is not None
    assert decision.apl_action.action_key == "spend"


def test_interpreter_understands_dot_cooldown_execute_and_aoe_conditions():
    dot = CombatAction(spell_id=1003, name="Dot")
    interpreter = APLInterpreter(
        _document(
            _action("dot", "dot.dot.remains<gcd", 10),
            _action("execute", "target.health.pct<35", 20),
            _action("aoe", "active_enemies>=3", 30),
            _action("cooldown", "cooldown.cooldown.ready", 40),
        ),
        action_catalog={
            "dot": dot,
            "execute": CombatAction(spell_id=1004, name="Execute"),
            "aoe": CombatAction(spell_id=1005, name="Aoe"),
            "cooldown": CombatAction(spell_id=1006, name="Cooldown"),
        },
    )

    decision = interpreter.choose_action(
        APLRuntimeState(
            time_ms=5000,
            debuffs={"dot": 1000},
            active_enemies=5,
            target_health_pct=20,
            cooldown_ready={"cooldown": 0},
            gcd_ms=1500,
        )
    )

    assert decision.action == dot


def test_interpreter_returns_no_action_for_unsupported_or_unusable_conditions():
    interpreter = APLInterpreter(
        _document(_action("mystery", "unknown.condition", 10)),
        action_catalog={"mystery": CombatAction(spell_id=1007, name="Mystery")},
    )

    decision = interpreter.choose_action(APLRuntimeState())

    assert decision.action is None
    assert decision.reason == "no_usable_action"
    assert "unsupported_condition:unknown.condition" in decision.warnings
