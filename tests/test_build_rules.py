import json
from pathlib import Path

from coa_meta.builds import BuildConfig, BuildRules
from coa_meta.domain import SelectedRank
from coa_meta.repository import TalentRepository


FIXTURE = Path(__file__).parent / "fixtures" / "legal_build_fixture.jsonl"
EXAMPLES = Path(__file__).parent / "fixtures" / "builder_examples.json"


def rules(level=60, max_ae=2, max_te=3):
    repo = TalentRepository.from_entries(FIXTURE)
    return BuildRules(repo, BuildConfig(class_name="Testclass", level=level, max_ae=max_ae, max_te=max_te))


def test_free_zero_cost_closure_is_in_initial_state():
    state = rules().initial_state()

    assert state.free_node_ids == (100,)
    assert state.ae_spent == 0
    assert state.te_spent == 0


def test_valid_build_serializes_spend_and_ranks():
    result = rules().validate([SelectedRank(101, 1), SelectedRank(102, 2)])

    assert result.valid is True
    assert result.state is not None
    assert result.state.ae_spent == 1
    assert result.state.te_spent == 2
    assert result.state.to_dict()["selected_ranks"] == [{"node_id": 101, "rank": 1}, {"node_id": 102, "rank": 2}]


def test_missing_prerequisite_and_tab_gate_are_explained():
    result = rules().validate([SelectedRank(103, 1)])

    assert result.valid is False
    assert "required_node_missing" in result.issue_codes()
    assert "tab_te_gate_unmet" in result.issue_codes()


def test_budget_and_rank_failures_are_explained():
    result = rules(max_te=2).validate([SelectedRank(102, 4)])

    assert result.valid is False
    assert "rank_above_maximum" in result.issue_codes()
    assert "te_budget_exceeded" in result.issue_codes()


def test_wrong_class_node_is_explained():
    result = rules().validate([SelectedRank(200, 1)])

    assert result.valid is False
    assert "wrong_class" in result.issue_codes()


def test_builder_example_fixture_expectations():
    engine = rules()
    examples = json.loads(EXAMPLES.read_text(encoding="utf-8"))

    for example in examples:
        selected = [SelectedRank(item["node_id"], item.get("rank", 1)) for item in example["selected"]]
        result = engine.validate(selected)
        assert result.valid is example["expected_valid"], example["name"]
        for code in example["expected_issue_codes"]:
            assert code in result.issue_codes(), example["name"]
