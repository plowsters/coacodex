from __future__ import annotations

from pathlib import Path

from coa_meta.apl import generate_apl
from coa_meta.apl_profiles import load_builtin_apl_profile
from coa_meta.builds import BuildConfig, BuildRules
from coa_meta.domain import SelectedRank
from coa_meta.repository import TalentRepository
from coa_meta.simulation import SimulationConfig, simulate_build

FIXTURE = Path(__file__).parent / "fixtures" / "apl_build_fixture.jsonl"


def test_simulation_runner_executes_generated_apl_for_build():
    repo = TalentRepository.from_entries(FIXTURE)
    rules = BuildRules(repo, BuildConfig(class_name="Testclass", level=60, max_ae=10, max_te=5))
    validation = rules.validate(
        [
            SelectedRank(101, 1),
            SelectedRank(102, 1),
            SelectedRank(103, 1),
            SelectedRank(104, 1),
            SelectedRank(105, 1),
            SelectedRank(106, 1),
        ]
    )
    assert validation.valid
    assert validation.state is not None
    apl = generate_apl(validation.state, repo, load_builtin_apl_profile("generic_dps"), encounter="single_target")

    result = simulate_build(
        validation.state,
        repo,
        apl,
        SimulationConfig(duration_ms=10_000, iterations=2, seed=11),
    )

    payload = result.to_dict()

    assert payload["schema_version"] == "coa-simulation-result-v1"
    assert payload["source"] == "simulated"
    assert payload["iterations"] == 2
    assert payload["dps"] > 0
    assert payload["spell_breakdown"]
