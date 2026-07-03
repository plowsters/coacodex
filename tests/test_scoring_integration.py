from pathlib import Path

from coa_meta.builds import BuildConfig, BuildRules
from coa_meta.explain import scored_build_to_dict
from coa_meta.profiles import load_builtin_profile
from coa_meta.repository import TalentRepository
from coa_meta.scoring import TheoryScorer
from coa_meta.search import BuildSearchConfig, BuildSearcher


def test_scores_venomancer_search_result_from_current_artifacts():
    repo = TalentRepository.from_entries(Path("coa_scraper/dist/coa_entries.jsonl"))
    rules = BuildRules(repo, BuildConfig(class_name="Venomancer", level=60, max_ae=26, max_te=25))
    result = BuildSearcher(repo, rules).search(BuildSearchConfig(top=1, beam_width=5, branch_width=10))[0]
    profile = load_builtin_profile("venomancer_stalker", encounter="single_target")

    scored = TheoryScorer(profile).score_build(result.state, repo)
    report = scored_build_to_dict(scored)

    assert report["source"] == "theorycraft"
    assert report["projected_dps_index"] > 100
    assert report["confidence"] == "high"
