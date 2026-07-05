from __future__ import annotations

from pathlib import Path

from coa_meta.reporting import MetaReportRunner, MetaRunConfig

FIXTURES = Path(__file__).parent / "fixtures"


def test_meta_report_runner_generates_spec_results_from_fixture():
    config = MetaRunConfig(
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        classes_path=FIXTURES / "meta_classes.json",
        class_names=("Testclass",),
        top=2,
        beam_width=4,
        branch_width=4,
        require_budget_fraction=0.0,
    )

    report = MetaReportRunner(config).run()
    data = report.to_dict()

    assert data["schema_version"] == "coa-meta-report-v1"
    assert data["run_config"]["top"] == 2
    assert [row["spec_name"] for row in data["spec_results"]] == ["Damage", "Support"]
    assert data["spec_results"][0]["top_builds"]
    assert data["spec_results"][0]["top_builds"][0]["projected_dps_index"] > 0
    assert data["spec_results"][0]["top_builds"][0]["generated_apl"]["schema_version"] == "coa-apl-v1"
    assert data["spec_results"][0]["summary"]["role"] == "dps"
    assert data["spec_results"][0]["top_builds"][0]["rotation_summary"]["sections"]
    assert data["spec_results"][0]["top_builds"][0]["stat_priority"]
    assert "item_data_missing" in data["spec_results"][0]["top_builds"][0]["gear_recommendation"]["warnings"]


def test_meta_report_runner_infers_roles_for_specs():
    config = MetaRunConfig(
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        classes_path=FIXTURES / "meta_classes.json",
        class_names=("Testclass",),
        top=1,
        beam_width=2,
        branch_width=2,
        require_budget_fraction=0.0,
    )

    report = MetaReportRunner(config).run()
    by_spec = {result.spec_name: result for result in report.spec_results}

    assert by_spec["Damage"].role == "dps"
    assert by_spec["Support"].role == "healer_support"
    assert by_spec["Support"].scoring_profile_id == "generic_healer_support"
    assert by_spec["Support"].apl_profile_id == "generic_healer_support"
    assert by_spec["Support"].top_builds[0].provenance["role"] == "healer_support"


def test_meta_report_runner_allows_explicit_role_override():
    config = MetaRunConfig(
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        classes_path=FIXTURES / "meta_classes.json",
        class_names=("Testclass",),
        spec_names_or_ids=("Support",),
        role="dps",
        top=1,
        beam_width=2,
        branch_width=2,
        require_budget_fraction=0.0,
    )

    report = MetaReportRunner(config).run()
    result = report.spec_results[0]

    assert result.role == "dps"
    assert result.scoring_profile_id == "generic_dps"


def test_meta_report_runner_preserves_metadata_warnings():
    config = MetaRunConfig(
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        classes_path=FIXTURES / "meta_classes.json",
        class_names=("Testclass",),
        top=1,
        beam_width=2,
        branch_width=2,
        require_budget_fraction=0.0,
    )

    report = MetaReportRunner(config).run()

    assert any("metadata_tab_has_no_nodes:Testclass:Empty" in warning for warning in report.warnings)


def test_meta_report_runner_falls_back_when_budget_floor_is_unreachable():
    config = MetaRunConfig(
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        classes_path=FIXTURES / "meta_classes.json",
        class_names=("Testclass",),
        spec_names_or_ids=("Damage",),
        top=1,
        beam_width=2,
        branch_width=2,
        require_budget_fraction=1.0,
    )

    report = MetaReportRunner(config).run()
    result = report.spec_results[0]

    assert result.top_builds
    assert "budget_floor_unreachable_with_current_gates" in result.warnings


def test_meta_report_runner_can_attach_simulation_results():
    config = MetaRunConfig(
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        classes_path=FIXTURES / "meta_classes.json",
        class_names=("Testclass",),
        spec_names_or_ids=("Damage",),
        top=1,
        beam_width=2,
        branch_width=2,
        require_budget_fraction=0.0,
        simulate=True,
        simulation_duration_ms=5000,
        simulation_iterations=1,
        simulation_seed=13,
    )

    report = MetaReportRunner(config).run()
    simulation = report.spec_results[0].top_builds[0].simulation_result

    assert simulation is not None
    assert simulation["schema_version"] == "coa-simulation-result-v1"
    assert simulation["source"] == "simulated"
