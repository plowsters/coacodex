from __future__ import annotations

from pathlib import Path

from coa_meta.reporting import SpecResult, MetaReportRunner, MetaRunConfig

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
    assert data["spec_results"][0]["summary"]["role"] == "caster_dps"
    assert data["spec_results"][0]["engine_role"] == "dps"
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

    assert by_spec["Damage"].role == "caster_dps"
    assert by_spec["Damage"].engine_role == "dps"
    assert by_spec["Support"].role == "healer"
    assert by_spec["Support"].engine_role == "healer_support"
    assert by_spec["Support"].scoring_profile_id == "generic_healer_support"
    assert by_spec["Support"].apl_profile_id == "generic_healer_support"
    assert by_spec["Support"].top_builds[0].provenance["role"] == "healer"
    assert by_spec["Support"].top_builds[0].provenance["engine_role"] == "healer_support"


def test_meta_report_exposes_guide_role_engine_role_and_provenance():
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
    by_spec = {result.spec_name: result.to_dict() for result in report.spec_results}

    assert by_spec["Damage"]["role"] in {"melee_dps", "caster_dps"}
    assert by_spec["Damage"]["engine_role"] == "dps"
    assert by_spec["Support"]["role"] == "healer"
    assert by_spec["Support"]["engine_role"] == "healer_support"
    assert by_spec["Support"]["role_provenance"]["source"] == "curated"
    build = by_spec["Support"]["top_builds"][0]
    assert build["projected_dps_index"] > 0
    assert build["primary_index"] == build["projected_dps_index"]
    assert build["primary_index_label"] == "Projected Healing Index"
    assert build["objective_id"] == "healing"
    assert build["objective_breakdown"]
    assert build["alternate_objective_scores"] == {}
    assert build["provenance"]["engine_role"] == "healer_support"
    assert build["stat_priority_report"]["schema_version"] == "coa-stat-priority-v2"
    assert build["stat_priority_report"]["role"] == "healer"
    assert build["gear_recommendation_report"]["schema_version"] == "coa-gear-recommendation-v2"
    assert build["gear_recommendation_report"]["role"] == "healer"
    assert "best_weapon_types" in build["gear_recommendation_report"]


def test_spec_result_serializes_primary_and_secondary_roles():
    result = SpecResult(
        class_name="Guardian",
        spec_id=18,
        spec_name="Inspiration",
        role="melee_dps",
        primary_role="melee_dps",
        secondary_roles=("support",),
        roles=("melee_dps", "support"),
        engine_role="dps",
        role_provenance={"source": "authoritative_video", "secondary_roles": ["support"]},
        level=60,
        encounter_profile_id="baseline_single_target",
        search_profile_id="default",
        scoring_profile_id="auto",
        apl_profile_id="auto",
        summary={},
        top_builds=tuple(),
        warnings=tuple(),
    )

    payload = result.to_dict()

    assert payload["role"] == "melee_dps"
    assert payload["primary_role"] == "melee_dps"
    assert payload["secondary_roles"] == ["support"]
    assert payload["roles"] == ["melee_dps", "support"]
    assert payload["role_provenance"]["source"] == "authoritative_video"


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

    assert result.role == "melee_dps"
    assert result.engine_role == "dps"
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


def test_meta_report_runner_can_attach_simulated_rotation_guides():
    config = MetaRunConfig(
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        classes_path=FIXTURES / "meta_classes.json",
        class_names=("Testclass",),
        spec_names_or_ids=("Damage",),
        top=1,
        beam_width=2,
        branch_width=2,
        require_budget_fraction=0.0,
        simulate_rotations=True,
        rotation_duration_ms=10_000,
        rotation_candidates=8,
    )

    report = MetaReportRunner(config).run()
    build = report.spec_results[0].top_builds[0].to_dict()

    assert build["rotation_guide"]["schema_version"] == "coa-rotation-guide-v1"
    assert build["rotation_guide"]["simulation_summary"]["source"] == "simulated"
    assert build["rotation_loop"]["schema_version"] == "coa-rotation-loop-v1"


def test_meta_report_top_builds_include_playstyle_selection_and_rotation_loop():
    config = MetaRunConfig(
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        classes_path=FIXTURES / "meta_classes.json",
        class_names=("Testclass",),
        spec_names_or_ids=("Damage",),
        top=2,
        beam_width=4,
        branch_width=4,
        require_budget_fraction=0.0,
    )

    report = MetaReportRunner(config).run()
    build = report.spec_results[0].top_builds[0].to_dict()

    assert build["playstyle_fingerprint"]["schema_version"] == "coa-build-playstyle-v1"
    assert build["selection_reason"]["schema_version"] == "coa-build-selection-v1"
    assert build["rotation_loop"]["schema_version"] == "coa-rotation-loop-v1"
    assert build["rotation_signature"]["schema_version"] == "coa-rotation-playstyle-v1"
    assert build["rotation_summary"]["sections"]
