from pathlib import Path

from coa_meta.builds import BuildConfig, BuildRules
from coa_meta.domain import SelectedRank
from coa_meta.profiles import load_builtin_profile
from coa_meta.repository import TalentRepository
from coa_meta.scoring import TheoryScorer


FIXTURE = Path(__file__).parent / "fixtures" / "legal_build_fixture.jsonl"


def build_state():
    repo = TalentRepository.from_entries(FIXTURE)
    rules = BuildRules(repo, BuildConfig(class_name="Testclass", level=60, max_ae=2, max_te=3))
    result = rules.validate([SelectedRank(101, 1), SelectedRank(102, 2)])
    assert result.valid
    return repo, result.state


def test_theory_scorer_outputs_projected_index_and_components():
    repo, state = build_state()
    profile = load_builtin_profile("generic_dps", encounter="single_target")
    scorer = TheoryScorer(profile)

    scored = scorer.score_build(state, repo)

    assert scored.source == "theorycraft"
    assert scored.projected_dps_index > 100
    assert scored.raw_score > 0
    assert scored.confidence in {"low", "medium", "high"}
    assert scored.uncertainty["low"] < scored.uncertainty["mid"] < scored.uncertainty["high"]
    assert any(component.kind == "tag" for component in scored.components)
    assert any(component.kind == "school" for component in scored.components)


def test_synergies_and_anti_synergies_are_explained():
    from dataclasses import replace

    repo, state = build_state()
    profile = load_builtin_profile("generic_dps", encounter="single_target")
    custom_profile = replace(
        profile,
        synergies=({"names": ["Builder Strike", "Poison Talent"], "weight": 10.0, "reason": "test synergy"},),
        anti_synergies=({"names": ["Builder Strike", "Poison Talent"], "weight": -2.0, "reason": "test anti"},),
    )
    scorer = TheoryScorer(custom_profile)

    scored = scorer.score_build(state, repo)

    assert any(component.kind == "synergy" and component.reason == "test synergy" for component in scored.components)
    assert any(component.kind == "anti_synergy" and component.reason == "test anti" for component in scored.components)
