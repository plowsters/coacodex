from __future__ import annotations

from pathlib import Path

from coa_meta.apl import generate_apl
from coa_meta.apl_profiles import load_builtin_apl_profile
from coa_meta.builds import BuildConfig, BuildRules
from coa_meta.domain import SelectedRank
from coa_meta.repository import TalentRepository

FIXTURE = Path(__file__).parent / "fixtures" / "apl_build_fixture.jsonl"


def build_state():
    repo = TalentRepository.from_entries(FIXTURE)
    rules = BuildRules(repo, BuildConfig(class_name="Testclass", level=60, max_ae=10, max_te=5))
    result = rules.validate(
        [
            SelectedRank(101, 1),
            SelectedRank(102, 1),
            SelectedRank(103, 1),
            SelectedRank(104, 1),
            SelectedRank(105, 1),
            SelectedRank(106, 1),
        ]
    )
    assert result.valid
    assert result.state is not None
    return repo, result.state


def test_generates_single_target_apl_from_selected_build():
    repo, state = build_state()
    profile = load_builtin_apl_profile("generic_dps")

    document = generate_apl(state, repo, profile, encounter="single_target")
    categories = [action.category for action in document.actions]

    assert document.schema_version == "coa-apl-v1"
    assert document.source == "theorycraft"
    assert "maintenance" in categories
    assert "cooldown" in categories
    assert "execute" in categories
    assert "spender" in categories
    assert "builder" in categories
    assert "aoe" not in categories
    assert any(action.action_name == "Poison Talent" for action in document.actions)
    assert any("profile_rule:maintain_dots" in action.evidence for action in document.actions)


def test_generates_aoe_branch_independently():
    repo, state = build_state()
    profile = load_builtin_apl_profile("generic_dps")

    document = generate_apl(state, repo, profile, encounter="aoe_5")
    aoe_actions = [action for action in document.actions if action.category == "aoe"]

    assert aoe_actions
    assert aoe_actions[0].condition == "active_enemies>=3"
    assert aoe_actions[0].action_name == "Cleave Burst"


def test_orders_maintenance_before_spender_and_builder():
    repo, state = build_state()
    profile = load_builtin_apl_profile("generic_dps")

    document = generate_apl(state, repo, profile, encounter="single_target")
    by_category = {action.category: index for index, action in enumerate(document.actions)}

    assert by_category["maintenance"] < by_category["spender"]
    assert by_category["spender"] < by_category["builder"]


def test_generation_warns_when_generic_profile_used():
    repo, state = build_state()
    profile, warnings = load_builtin_apl_profile("generic_dps"), ["specific_apl_profile_missing"]

    document = generate_apl(state, repo, profile, encounter="single_target", profile_warnings=warnings)

    assert "specific_apl_profile_missing" in document.warnings
