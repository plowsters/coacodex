from pathlib import Path

from coa_meta.builds import BuildConfig, BuildRules
from coa_meta.repository import TalentRepository
from coa_meta.search import BuildSearchConfig, BuildSearcher


FIXTURE = Path(__file__).parent / "fixtures" / "legal_build_fixture.jsonl"


def test_search_uses_legal_rules_and_returns_serializable_states():
    repo = TalentRepository.from_entries(FIXTURE)
    rules = BuildRules(repo, BuildConfig(class_name="Testclass", level=60, max_ae=2, max_te=3))
    searcher = BuildSearcher(repo, rules)

    results = searcher.search(BuildSearchConfig(top=3, beam_width=5, branch_width=5))

    assert results
    assert all(result.valid for result in results)
    assert all(result.state is not None for result in results)
    assert results[0].state.to_dict()["class_name"] == "Testclass"
    assert 100 in results[0].state.free_node_ids


def test_search_does_not_return_builds_that_fail_tab_gates():
    repo = TalentRepository.from_entries(FIXTURE)
    rules = BuildRules(repo, BuildConfig(class_name="Testclass", level=60, max_ae=2, max_te=1))
    searcher = BuildSearcher(repo, rules)

    results = searcher.search(BuildSearchConfig(top=10, beam_width=5, branch_width=5))

    for result in results:
        selected_ids = result.state.selected_ids
        assert 103 not in selected_ids
