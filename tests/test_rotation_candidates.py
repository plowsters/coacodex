from __future__ import annotations

from coa_meta.action_catalog import ActionCatalog, CatalogAction
from coa_meta.apl import APLAction, APLDocument
from coa_meta.mechanics import MechanicEffect
from coa_meta.rotation_candidates import RotationCandidateConfig, generate_rotation_candidates


def _apl(*actions: APLAction) -> APLDocument:
    return APLDocument(
        schema_version="coa-apl-v1",
        source="theorycraft",
        profile_id="test",
        class_name="Venomancer",
        spec_key="stalking",
        role="melee_dps",
        encounter="single_target",
        actions=actions,
        assumptions=tuple(),
        warnings=tuple(),
        provenance={"test": "rotation_candidates"},
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
    cost: dict[str, float] | None = None,
    generates: dict[str, float] | None = None,
    cooldown_ms: int = 0,
    effect_type: str = "damage",
) -> CatalogAction:
    return CatalogAction(
        action_key=key,
        entry_id=1,
        spell_id=1001,
        name=key.replace("_", " ").title(),
        costs=cost or {},
        generates=generates or {},
        spends={},
        cooldown_ms=cooldown_ms,
        gcd_ms=1500,
        cast_time_ms=None,
        range_yards=None,
        duration_ms=None,
        tick_interval_ms=None,
        effects=(MechanicEffect(effect_type=effect_type, amount=10),),
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
        coverage_summary={},
    )


def test_candidates_start_with_base_apl_unchanged():
    apl = _apl(
        _apl_action("spend", "spender", 10, "energy>=80"),
        _apl_action("build", "builder", 20, "energy.deficit>0"),
    )
    catalog = _catalog(_catalog_action("spend", cost={"energy": 80}), _catalog_action("build", generates={"energy": 40}))

    candidates = generate_rotation_candidates(apl, catalog, role="melee_dps")

    assert candidates[0].mutation == "base"
    assert candidates[0].apl.actions == apl.actions
    assert candidates[0].candidate_id.startswith("base:")
    assert candidates[0].fingerprint


def test_candidates_only_reorder_actions_inside_compatible_groups():
    apl = _apl(
        _apl_action("cooldown", "cooldown", 10, "cooldown.cooldown.ready"),
        _apl_action("strike_a", "builder", 20, ""),
        _apl_action("strike_b", "builder", 21, ""),
        _apl_action("finish", "spender", 30, "energy>=80"),
    )
    catalog = _catalog(
        _catalog_action("cooldown", cooldown_ms=90000),
        _catalog_action("strike_a", generates={"energy": 30}),
        _catalog_action("strike_b", generates={"energy": 30}),
        _catalog_action("finish", cost={"energy": 80}),
    )

    candidates = generate_rotation_candidates(apl, catalog, role="melee_dps")
    reordered = [candidate for candidate in candidates if candidate.mutation == "reorder_group:builder"]

    assert reordered
    for candidate in reordered:
        keys = [action.action_key for action in candidate.apl.actions]
        assert keys[0] == "cooldown"
        assert keys[-1] == "finish"
        assert set(keys[1:3]) == {"strike_a", "strike_b"}


def test_candidates_preserve_mandatory_role_actions_for_healers_tanks_and_supports():
    apl = _apl(
        _apl_action("heal", "healing", 10, "when allies injured"),
        _apl_action("mitigate", "defensive", 20, "before heavy damage"),
        _apl_action("buff", "support", 30, "buff.buff.down"),
        _apl_action("filler", "filler", 40, ""),
    )
    catalog = _catalog(
        _catalog_action("heal", role="heal", effect_type="heal"),
        _catalog_action("mitigate", role="mitigation", effect_type="damage_reduction"),
        _catalog_action("buff", role="support", effect_type="aura_apply"),
        _catalog_action("filler"),
    )

    for role, required in (("healer", "heal"), ("tank", "mitigate"), ("support", "buff")):
        candidates = generate_rotation_candidates(apl, catalog, role=role)
        assert candidates
        for candidate in candidates:
            assert required in {action.action_key for action in candidate.apl.actions}


def test_candidates_generate_resource_threshold_variants_inside_bounds():
    apl = _apl(
        _apl_action("spend", "spender", 10, "energy>=80"),
        _apl_action("build", "builder", 20, "energy.deficit>0"),
    )
    catalog = _catalog(_catalog_action("spend", cost={"energy": 80}), _catalog_action("build", generates={"energy": 40}))

    candidates = generate_rotation_candidates(
        apl,
        catalog,
        role="melee_dps",
        config=RotationCandidateConfig(threshold_variants=(0.75, 1.0, 1.25)),
    )

    conditions = {
        action.condition
        for candidate in candidates
        for action in candidate.apl.actions
        if action.action_key == "spend"
    }
    assert {"energy>=60", "energy>=80", "energy>=100"}.issubset(conditions)


def test_candidates_are_capped_deterministically_with_stable_ids_and_fingerprints():
    apl = _apl(
        _apl_action("cooldown", "cooldown", 10, "cooldown.cooldown.ready"),
        _apl_action("strike_a", "builder", 20, ""),
        _apl_action("strike_b", "builder", 21, ""),
        _apl_action("strike_c", "builder", 22, ""),
        _apl_action("finish", "spender", 30, "energy>=80"),
        _apl_action("filler", "filler", 40, ""),
    )
    catalog = _catalog(
        _catalog_action("cooldown", cooldown_ms=90000),
        _catalog_action("strike_a", generates={"energy": 30}),
        _catalog_action("strike_b", generates={"energy": 30}),
        _catalog_action("strike_c", generates={"energy": 30}),
        _catalog_action("finish", cost={"energy": 80}),
        _catalog_action("filler"),
    )
    config = RotationCandidateConfig(max_candidates=4)

    first = generate_rotation_candidates(apl, catalog, role="melee_dps", config=config)
    second = generate_rotation_candidates(apl, catalog, role="melee_dps", config=config)

    assert len(first) == 4
    assert [candidate.candidate_id for candidate in first] == [candidate.candidate_id for candidate in second]
    assert [candidate.fingerprint for candidate in first] == [candidate.fingerprint for candidate in second]
    assert len({candidate.fingerprint for candidate in first}) == len(first)


def test_candidates_prune_non_executable_apls_and_role_irrelevant_role_apls():
    non_executable = _apl(_apl_action("passive_only", "utility", 10, ""))
    empty_catalog = _catalog()

    assert generate_rotation_candidates(non_executable, empty_catalog, role="melee_dps") == tuple()

    damage_only = _apl(_apl_action("filler", "filler", 10, ""))
    damage_catalog = _catalog(_catalog_action("filler"))

    assert generate_rotation_candidates(damage_only, damage_catalog, role="healer") == tuple()
