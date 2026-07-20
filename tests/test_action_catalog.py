from __future__ import annotations

from pathlib import Path

from coa_meta.action_catalog import build_action_catalog, classify_action_role
from coa_meta.domain import TalentNode
from coa_meta.mechanics_repository import MechanicsRepository

FIXTURES = Path(__file__).parent / "fixtures"
MECHANICS = FIXTURES / "mechanics_fixture.jsonl"


def _node(
    entry_id: int,
    spell_id: int,
    name: str,
    *,
    is_passive: bool = False,
    tags: tuple[str, ...] = tuple(),
) -> TalentNode:
    return TalentNode(
        entry_id=entry_id,
        spell_id=spell_id,
        name=name,
        class_id=1,
        class_name="Venomancer",
        tab_id=1,
        tab_name="Stalking",
        entry_type="Talent" if is_passive else "Ability",
        essence_kind="talent",
        ae_cost=0,
        te_cost=1,
        required_tab_ae=0,
        required_tab_te=0,
        required_level=10,
        max_rank=1,
        row=0,
        col=0,
        node_type="SpendCircle",
        is_passive=is_passive,
        is_starting_node=False,
        required_ids=tuple(),
        connected_node_ids=tuple(),
        tags=tags,
        damage_schools=tuple(),
        resources=tuple(),
        description_text="",
    )


def test_action_catalog_maps_selected_active_mechanics_and_excludes_passives():
    mechanics = MechanicsRepository.from_jsonl(MECHANICS)
    selected = (
        _node(201, 2001, "Venom Burst", tags=("spender",)),
        _node(202, 2002, "Lingering Toxin", tags=("dot",)),
        _node(203, 2003, "Toxic Readiness", tags=("cooldown",)),
        _node(204, 2004, "Venom Training", is_passive=True, tags=("passive",)),
        _node(206, 2006, "Restorative Spores", tags=("heal", "support")),
    )

    catalog = build_action_catalog(selected, mechanics, role="melee_dps", encounter="single_target")

    assert set(catalog.actions_by_spell_id) == {2001, 2002, 2003, 2006}
    assert 2004 not in catalog.actions_by_spell_id

    venom = catalog.actions_by_spell_id[2001]
    assert venom.action_key == "venom_burst"
    assert venom.entry_id == 201
    assert venom.spell_id == 2001
    assert venom.costs == {"Energy": 35.0}
    assert venom.spends == {"Energy": 35.0}
    assert venom.cooldown_ms == 6000
    assert venom.gcd_ms == 1500
    assert venom.range_yards == 30
    assert venom.confidence == "high"
    assert venom.role_classification == "damage"
    assert venom.effects[0].effect_type == "damage"

    toxin = catalog.actions_by_spell_id[2002]
    assert toxin.duration_ms == 12000
    assert toxin.tick_interval_ms == 2000

    assert catalog.coverage_summary["selected_node_count"] == 5
    assert catalog.coverage_summary["executable_action_count"] == 4
    assert catalog.coverage_summary["passive_skipped_count"] == 1
    assert catalog.coverage_summary["missing_mechanics_count"] == 0
    assert catalog.warnings == tuple()


def test_action_catalog_missing_mechanics_emit_warning_and_null_timing():
    catalog = build_action_catalog(
        (_node(999, 2999, "Unknown Strike", tags=("builder",)),),
        MechanicsRepository.from_jsonl(MECHANICS),
        role="melee_dps",
        encounter="single_target",
    )

    action = catalog.actions_by_spell_id[2999]

    assert action.name == "Unknown Strike"
    # E0R B5: a missing mechanic yields UNKNOWN (null) timing/costs, never invented 0/1500/{} defaults —
    # and it blocks the quantitative scope with an explicit readiness reason.
    assert action.cooldown_ms is None
    assert action.gcd_ms is None
    assert action.costs is None
    assert action.field_readiness["gcd_ms"] == {"status": "unavailable", "reason_code": "not_extracted"}
    assert action.effects == tuple()
    assert action.confidence == "low"
    assert action.role_classification == "unknown"
    assert "missing_mechanics:2999" in catalog.warnings
    assert catalog.coverage_summary["mechanics_coverage_pct"] == 0.0
    assert catalog.quantitative_readiness["ready"] is False


def test_action_role_classification_is_role_aware():
    mechanics = MechanicsRepository.from_jsonl(MECHANICS)

    assert classify_action_role(mechanics.by_spell_id(2001), role="melee_dps") == "damage"
    assert classify_action_role(mechanics.by_spell_id(2006), role="healer") == "heal"
    assert classify_action_role(mechanics.by_spell_id(2006), role="support") == "support"
    assert classify_action_role(mechanics.by_spell_id(2005), role="melee_dps") == "utility"
