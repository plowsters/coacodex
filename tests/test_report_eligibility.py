from __future__ import annotations

from pathlib import Path

from coa_meta.builds import BuildConfig, BuildRules
from coa_meta.domain import SelectedRank
from coa_meta.repository import TalentRepository
from coa_meta.reporting import BuildScope, EligibilityPolicy, load_class_metadata

FIXTURE = Path(__file__).parent / "fixtures" / "legal_build_fixture.jsonl"
META_CLASSES = Path(__file__).parent / "fixtures" / "meta_classes.json"
META_NODES = Path(__file__).parent / "fixtures" / "meta_report_fixture.jsonl"


def test_build_rules_restrict_paid_nodes_to_allowed_scope():
    repo = TalentRepository.from_entries(FIXTURE)
    rules = BuildRules(
        repo,
        BuildConfig(
            class_name="Testclass",
            level=60,
            max_ae=2,
            max_te=3,
            allowed_node_ids=(100, 101, 102),
        ),
    )

    assert sorted(rules.nodes) == [100, 101, 102]
    result = rules.validate([SelectedRank(103, 1)])

    assert result.valid is False
    assert "node_not_in_scope" in result.issue_codes()


def test_build_rules_allow_valid_selection_inside_scope():
    repo = TalentRepository.from_entries(FIXTURE)
    rules = BuildRules(
        repo,
        BuildConfig(
            class_name="Testclass",
            level=60,
            max_ae=2,
            max_te=3,
            allowed_node_ids=(100, 101, 102),
        ),
    )

    result = rules.validate([SelectedRank(101, 1), SelectedRank(102, 1)])

    assert result.valid is True
    assert result.state is not None
    assert result.state.ae_spent == 1
    assert result.state.te_spent == 1


def test_reportable_specs_exclude_shared_empty_and_none_tabs():
    repo = TalentRepository.from_entries(META_NODES)
    classes = load_class_metadata(META_CLASSES)
    policy = EligibilityPolicy()

    specs = policy.reportable_specs(repo, classes)

    assert [(spec.class_name, spec.spec_id, spec.spec_name) for spec in specs] == [
        ("Testclass", 11, "Damage"),
        ("Testclass", 12, "Support"),
    ]
    warnings = policy.metadata_warnings(repo, classes)
    assert any("Testclass:Empty" in warning for warning in warnings)


def test_eligible_nodes_include_spec_tree_and_shared_class_pool():
    repo = TalentRepository.from_entries(META_NODES)
    policy = EligibilityPolicy()
    scope = BuildScope(
        class_name="Testclass",
        spec_id=11,
        spec_name="Damage",
        level=60,
        encounter_profile_id="baseline_single_target",
        search_profile_id="default",
        scoring_profile_id="auto",
        apl_profile_id="auto",
        top=3,
    )

    eligible = policy.eligible_node_ids(repo, scope)

    assert eligible == (100, 101, 102, 201, 202)


def test_level_filtering_excludes_known_high_level_shared_nodes():
    repo = TalentRepository.from_entries(META_NODES)
    policy = EligibilityPolicy()
    scope = BuildScope(
        class_name="Testclass",
        spec_id=11,
        spec_name="Damage",
        level=15,
        encounter_profile_id="baseline_single_target",
        search_profile_id="default",
        scoring_profile_id="auto",
        apl_profile_id="auto",
        top=3,
    )

    eligible = policy.eligible_node_ids(repo, scope)
    warnings = policy.scope_warnings(repo, scope)

    assert eligible == (100, 101, 201, 202)
    assert "shared_class_level_gating_incomplete" in warnings


def test_level_filtering_uses_medium_confidence_effective_required_level():
    repo = TalentRepository.from_entries(META_NODES)
    node = repo.node_by_id(202)
    node.raw["availability"] = {
        "effective_required_level": 50,
        "level_confidence": "medium",
        "level_source": "db_tooltip",
        "notes": [],
    }
    policy = EligibilityPolicy()
    scope = BuildScope(
        class_name="Testclass",
        spec_id=11,
        spec_name="Damage",
        level=15,
        encounter_profile_id="baseline_single_target",
        search_profile_id="default",
        scoring_profile_id="auto",
        apl_profile_id="auto",
        top=3,
    )

    eligible = policy.eligible_node_ids(repo, scope)

    assert 202 not in eligible
