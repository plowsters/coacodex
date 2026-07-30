# tests/test_action_catalog_interlock.py
import pytest

from coa_meta.action_catalog import CatalogAction, QuantitativeScopeUnready, build_action_catalog
from coa_meta.domain import TalentNode
from coa_meta.mechanics import MechanicRecord
from coa_meta.mechanics_repository import MechanicsRepository


def _node(entry_id, spell_id, name="Node", *, tags=("spender",)):
    return TalentNode(
        entry_id=entry_id, spell_id=spell_id, name=name, class_id=1, class_name="Venomancer",
        tab_id=1, tab_name="Stalking", entry_type="Ability", essence_kind="talent",
        ae_cost=0, te_cost=1, required_tab_ae=0, required_tab_te=0, required_level=10, max_rank=1,
        row=0, col=0, node_type="SpendCircle", is_passive=False, is_starting_node=False,
        required_ids=tuple(), connected_node_ids=tuple(), tags=tags,
        damage_schools=tuple(), resources=tuple(), description_text="")


def _mech(spell_id, *, cooldown_ms, gcd_ms, costs, field_readiness=None):
    return MechanicRecord(
        schema_version="coa-mechanics-v2", spell_id=spell_id, name="X", kind="ability",
        source_node_ids=(), source_urls=(), cooldown_ms=cooldown_ms, gcd_ms=gcd_ms,
        costs=costs, field_readiness=field_readiness or {})


def _catalog_action_for(node, mechanic):
    catalog = build_action_catalog([node], MechanicsRepository([mechanic]),
                                   role="dps", encounter="patchwerk")
    return catalog.actions_by_spell_id[node.spell_id]


def test_unknown_timing_is_null_not_defaulted():
    action = _catalog_action_for(_node(1, 5), _mech(5, cooldown_ms=None, gcd_ms=None, costs=None))
    assert action.cooldown_ms is None and action.gcd_ms is None and action.costs is None  # never 0/1500/{}


def test_verified_zero_and_1500_are_preserved():
    action = _catalog_action_for(_node(1, 6), _mech(6, cooldown_ms=0, gcd_ms=1500, costs={}))
    assert action.cooldown_ms == 0 and action.gcd_ms == 1500 and action.costs == {}
    assert action.to_dict()["costs"] == {} and action.to_dict()["cooldown_ms"] == 0


def test_null_timing_serializes_without_coercion():
    action = _catalog_action_for(_node(1, 5), _mech(5, cooldown_ms=None, gcd_ms=None, costs=None))
    d = action.to_dict()
    assert d["cooldown_ms"] is None and d["gcd_ms"] is None and d["costs"] is None


def test_quantitative_scope_fails_closed_when_any_action_unready():
    ready = _mech(6, cooldown_ms=6000, gcd_ms=1500, costs={"Energy": 35})
    unready = _mech(7, cooldown_ms=None, gcd_ms=None, costs=None)
    catalog = build_action_catalog([_node(1, 6, "A"), _node(2, 7, "B")],
                                   MechanicsRepository([ready, unready]), role="dps", encounter="patchwerk")
    rd = catalog.quantitative_readiness
    assert rd["ready"] is False
    assert rd["blocking"][0]["field"] in ("gcd_ms", "cooldown_ms", "costs")
    with pytest.raises(QuantitativeScopeUnready):
        catalog.assert_quantitative_ready()


def test_fully_populated_catalog_is_ready():
    ready = _mech(6, cooldown_ms=6000, gcd_ms=1500, costs={"Energy": 35})
    catalog = build_action_catalog([_node(1, 6)], MechanicsRepository([ready]),
                                   role="dps", encounter="patchwerk")
    assert catalog.quantitative_readiness["ready"] is True
    catalog.assert_quantitative_ready()   # does not raise
