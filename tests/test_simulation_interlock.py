# tests/test_simulation_interlock.py
import pytest

from coa_meta.action_catalog import QuantitativeScopeUnready, build_action_catalog
from coa_meta.apl import APLAction, APLDocument
from coa_meta.domain import TalentNode
from coa_meta.mechanics import MechanicRecord
from coa_meta.mechanics_repository import MechanicsRepository
from coa_meta.rotation_simulation import RotationSimulationConfig, simulate_apl


def _node(entry_id, spell_id, name):
    return TalentNode(
        entry_id=entry_id, spell_id=spell_id, name=name, class_id=1, class_name="Venomancer",
        tab_id=1, tab_name="Stalking", entry_type="Ability", essence_kind="talent",
        ae_cost=0, te_cost=1, required_tab_ae=0, required_tab_te=0, required_level=10, max_rank=1,
        row=0, col=0, node_type="SpendCircle", is_passive=False, is_starting_node=False,
        required_ids=tuple(), connected_node_ids=tuple(), tags=("spender",),
        damage_schools=tuple(), resources=tuple(), description_text="")


def _mech(spell_id, *, cooldown_ms, gcd_ms, costs):
    return MechanicRecord(
        schema_version="coa-mechanics-v2", spell_id=spell_id, name=f"S{spell_id}", kind="ability",
        source_node_ids=(), source_urls=(), cooldown_ms=cooldown_ms, gcd_ms=gcd_ms, costs=costs)


def _catalog(*mechs):
    nodes = [_node(i + 1, m.spell_id, m.name) for i, m in enumerate(mechs)]
    return build_action_catalog(nodes, MechanicsRepository(list(mechs)), role="dps", encounter="patchwerk")


def _apl(catalog):
    actions = tuple(
        APLAction(action_key=a.action_key, action_name=a.name, node_id=a.entry_id, spell_id=a.spell_id,
                  category="spender", condition="", priority=i, confidence="low", notes=(), evidence=())
        for i, a in enumerate(catalog.actions))
    return APLDocument(
        schema_version="coa-apl-v1", source="theorycraft", profile_id="test", class_name="Testclass",
        spec_key="test", role="dps", encounter="single_target", actions=actions,
        assumptions=tuple(), warnings=tuple(), provenance={})


def test_canonical_sim_fails_closed_when_timing_is_unknown():
    catalog = _catalog(_mech(7, cooldown_ms=None, gcd_ms=None, costs=None))
    with pytest.raises(QuantitativeScopeUnready):
        simulate_apl(_apl(catalog), catalog, RotationSimulationConfig(duration_ms=3000))


def test_heuristic_mode_runs_over_unknown_timing():
    catalog = _catalog(_mech(7, cooldown_ms=None, gcd_ms=None, costs=None))
    result = simulate_apl(_apl(catalog), catalog,
                          RotationSimulationConfig(duration_ms=3000, allow_heuristic=True))
    assert result.duration_ms == 3000                      # ran without raising

def test_canonical_sim_runs_over_fully_populated_actions():
    catalog = _catalog(_mech(6, cooldown_ms=6000, gcd_ms=1500, costs={}))
    result = simulate_apl(_apl(catalog), catalog, RotationSimulationConfig(duration_ms=3000))
    assert result.duration_ms == 3000
