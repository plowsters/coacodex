# tests/test_e0r1_interlock_behavioral.py
"""E0R.1 T5.4 — the quantitative interlock is HONEST on every path, proven behaviorally rather than by
reading flags: over action_catalog, rotation_simulation, simulation (the invented-defaults combat
conversion), apl_interpreter, and reporting —

  * a missing load-bearing input BLOCKS: the canonical report emits an explicit `blocked` rotation
    section (never a silently-heuristic guide), and every quantitative entry point raises;
  * a verified `0` stays `0` and a verified `1500` stays `1500` — proven values are never re-defaulted;
  * a verified EMPTY cost stays free (`{}`), distinct from an unknown cost (`None`);
  * heuristics require EXPLICIT opt-in (default off) and every heuristic output reports
    `source: "heuristic"`.
"""
from pathlib import Path

import pytest

from coa_meta.action_catalog import ActionCatalog, CatalogAction, QuantitativeScopeUnready
from coa_meta.apl import APLAction, APLDocument
from coa_meta.apl_interpreter import APLInterpreter, APLRuntimeState
from coa_meta.rotation_simulation import RotationSimulationConfig, simulate_apl

FIXTURES = Path(__file__).parent / "fixtures"


def _apl(*actions: APLAction) -> APLDocument:
    return APLDocument(schema_version="coa-apl-v1", source="theorycraft", profile_id="test",
                       class_name="Testclass", spec_key="test", role="dps", encounter="single_target",
                       actions=actions, assumptions=tuple(), warnings=tuple(), provenance={})


def _apl_action(key="strike", condition="", priority=10.0) -> APLAction:
    return APLAction(action_key=key, action_name=key.title(), node_id=None, spell_id=1000,
                     category="test", condition=condition, priority=priority, confidence="medium",
                     notes=tuple(), evidence=tuple())


def _catalog(*actions: CatalogAction) -> ActionCatalog:
    return ActionCatalog(actions_by_key={a.action_key: a for a in actions},
                         actions_by_spell_id={a.spell_id: a for a in actions},
                         warnings=tuple(), coverage_summary={})


def _action(key="strike", *, costs, cooldown_ms, gcd_ms) -> CatalogAction:
    return CatalogAction(action_key=key, entry_id=1, spell_id=1000, name=key.title(),
                         costs=costs, generates={}, spends={}, cooldown_ms=cooldown_ms, gcd_ms=gcd_ms,
                         cast_time_ms=None, range_yards=None, duration_ms=None, tick_interval_ms=None,
                         effects=tuple(), tags=tuple(), mechanic_kind="ability", confidence="medium",
                         role_classification="damage", source="client")


PROVEN = dict(costs={}, cooldown_ms=0, gcd_ms=1500)
UNKNOWN_COSTS = dict(costs=None, cooldown_ms=0, gcd_ms=1500)


# --- proven values survive ---------------------------------------------------------------------------

def test_a_verified_zero_and_a_verified_1500_are_preserved():
    action = _action(**PROVEN)
    assert action.cooldown_ms == 0 and action.gcd_ms == 1500
    assert action.readiness_of("cooldown_ms") == "available"   # a proven 0 is available, not missing
    assert action.readiness_of("gcd_ms") == "available"


def test_a_verified_empty_cost_stays_free_and_is_not_unknown():
    free = _action(**PROVEN)
    assert free.costs == {} and free.readiness_of("costs") == "available"
    unknown = _action(**UNKNOWN_COSTS)
    assert unknown.costs is None and unknown.readiness_of("costs") == "unavailable"
    assert _catalog(free).quantitative_readiness["ready"] is True
    assert _catalog(unknown).quantitative_readiness["ready"] is False


# --- a missing input blocks every quantitative entry point ---------------------------------------------

def test_apl_simulation_fails_closed_on_a_missing_load_bearing_input():
    with pytest.raises(QuantitativeScopeUnready):
        simulate_apl(_apl(_apl_action()), _catalog(_action(**UNKNOWN_COSTS)),
                     RotationSimulationConfig(duration_ms=3000))


def test_apl_simulation_runs_on_a_fully_proven_catalog_without_any_opt_in():
    result = simulate_apl(_apl(_apl_action()), _catalog(_action(**PROVEN)),
                          RotationSimulationConfig(duration_ms=3000))
    assert result.events, "a fully proven catalog needs no heuristic authorization"
    assert result.source_kind == "verified"
    assert not any("heuristic" in w for w in result.warnings)


def test_heuristic_mode_is_opt_in_and_marks_its_output():
    result = simulate_apl(_apl(_apl_action()), _catalog(_action(**UNKNOWN_COSTS)),
                          RotationSimulationConfig(duration_ms=3000, allow_heuristic=True))
    assert result.source_kind == "heuristic"
    assert "quantitative_heuristic_authorized" in result.warnings


def test_the_default_simulation_config_is_not_heuristic():
    assert RotationSimulationConfig().allow_heuristic is False


# --- the apl interpreter never invents a gcd -----------------------------------------------------------

def test_the_interpreter_reports_unsupported_rather_than_assuming_a_gcd():
    # `remains<gcd` cannot be evaluated when the gcd is unknown; the honest answer is "unsupported",
    # not a silent comparison against an invented 1500.
    interpreter = APLInterpreter(_apl(_apl_action(condition="dot.strike.remains<gcd")), {})
    decision = interpreter.choose_action(APLRuntimeState(debuffs={"strike": 100}))
    assert any("gcd" in warning for warning in decision.warnings), decision.warnings
    assert decision.action is None


def test_the_runtime_state_gcd_defaults_to_unknown():
    assert APLRuntimeState().gcd_ms is None


def test_a_known_gcd_still_evaluates_the_condition():
    interpreter = APLInterpreter(_apl(_apl_action(condition="dot.strike.remains<gcd")), {})
    decision = interpreter.choose_action(APLRuntimeState(debuffs={"strike": 100}, gcd_ms=1500))
    assert not any("gcd" in warning for warning in decision.warnings)


# --- the build simulation (invented-defaults combat conversion) -------------------------------------------

def test_simulate_build_requires_explicit_authorization_and_labels_its_output():
    from coa_meta.apl import generate_apl
    from coa_meta.apl_profiles import load_builtin_apl_profile
    from coa_meta.builds import BuildConfig, BuildRules
    from coa_meta.domain import SelectedRank
    from coa_meta.repository import TalentRepository
    from coa_meta.simulation import SimulationConfig, simulate_build

    repo = TalentRepository.from_entries(FIXTURES / "apl_build_fixture.jsonl")
    rules = BuildRules(repo, BuildConfig(class_name="Testclass", level=60, max_ae=10, max_te=5))
    validation = rules.validate([SelectedRank(nid, 1) for nid in (101, 102, 103, 104, 105, 106)])
    state = validation.state
    apl = generate_apl(state, repo, load_builtin_apl_profile("generic_dps"), encounter="single_target")

    with pytest.raises(QuantitativeScopeUnready):
        simulate_build(state, repo, apl, SimulationConfig(duration_ms=3000))

    result = simulate_build(state, repo, apl, SimulationConfig(duration_ms=3000, allow_heuristic=True))
    assert result.source == "heuristic"                 # never "simulated": these are invented defaults
    assert result.to_dict()["source"] == "heuristic"


# --- the canonical report blocks instead of quietly going heuristic ------------------------------------------

def test_canonical_report_emits_a_blocked_rotation_section_never_a_silent_heuristic():
    from coa_meta.reporting import MetaRunConfig, rotation_blocked_section

    assert MetaRunConfig(entries_path=FIXTURES / "meta_report_fixture.jsonl").allow_heuristic is False
    blocked = rotation_blocked_section({"ready": False, "blocking": [
        {"action_key": "strike", "field": "costs", "status": "unavailable",
         "reason_code": "pending_e1_operand"}]})
    assert blocked["status"] == "blocked"
    assert blocked["source"] == "blocked"
    assert blocked["blocking"][0]["field"] == "costs"
    assert blocked["blocking"][0]["reason_code"] == "pending_e1_operand"
