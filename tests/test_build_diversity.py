from __future__ import annotations

from pathlib import Path

from coa_meta.apl import APLAction, APLDocument
from coa_meta.build_diversity import (
    BuildDiversityCandidate,
    RotationPlaystyleSignature,
    build_playstyle_fingerprint,
    fingerprint_distance,
    reliability_label,
    reliability_score,
    rotation_signature_distance,
    select_diverse_builds,
)
from coa_meta.repository import TalentRepository


FIXTURES = Path(__file__).parent / "fixtures"


def test_fingerprint_uses_selected_tags_and_apl_actions():
    repo = TalentRepository.from_entries(FIXTURES / "meta_report_fixture.jsonl")
    nodes = [repo.node_by_id(201), repo.node_by_id(202)]
    apl = APLDocument(
        schema_version="coa-apl-v1",
        source="theorycraft",
        profile_id="test",
        class_name="Testclass",
        spec_key="Damage",
        role="melee_dps",
        encounter="single_target",
        actions=(
            APLAction(
                action_key="damage_talent",
                action_name="Damage Talent",
                node_id=201,
                spell_id=2001,
                category="builder",
                condition="use when available",
                priority=1,
                confidence="high",
                notes=("selected ability",),
                evidence=tuple(),
            ),
        ),
        assumptions=tuple(),
        warnings=tuple(),
        provenance={},
    )

    fp = build_playstyle_fingerprint(nodes=nodes, apl=apl, role="melee_dps")

    assert fp.active_count >= 1
    assert fp.apl_categories["builder"] == 1
    assert fp.label


def test_fingerprint_distance_separates_different_playstyles():
    repo = TalentRepository.from_entries(FIXTURES / "meta_report_fixture.jsonl")
    node_a = repo.node_by_id(201)
    node_b = repo.node_by_id(301)

    fp_a = build_playstyle_fingerprint(nodes=[node_a], apl=None, role="melee_dps")
    fp_b = build_playstyle_fingerprint(nodes=[node_b], apl=None, role="healer")

    assert fingerprint_distance(fp_a, fp_b) > 0.20


def test_rotation_signature_separates_dot_loop_from_burst_loop():
    dot = RotationPlaystyleSignature(
        schema_version="coa-rotation-playstyle-v1",
        core_actions=("poison_bite", "venom_tick"),
        opener_actions=("poison_bite",),
        maintenance_actions=("venom_tick",),
        cooldown_actions=tuple(),
        role_tool_actions=tuple(),
        resource_loop="maintenance_loop",
        burst_cadence="none",
        uptime_mechanics=("dot",),
        range_profile="caster",
    )
    burst = RotationPlaystyleSignature(
        schema_version="coa-rotation-playstyle-v1",
        core_actions=("shadowstep", "ambush"),
        opener_actions=("stealth", "ambush"),
        maintenance_actions=tuple(),
        cooldown_actions=("shadow_dance",),
        role_tool_actions=tuple(),
        resource_loop="cooldown_driven",
        burst_cadence="medium",
        uptime_mechanics=tuple(),
        range_profile="melee",
    )

    assert rotation_signature_distance(dot, burst) >= 0.5
    assert rotation_signature_distance(dot, dot) == 0.0


def test_reliability_penalizes_missing_active_apl_actions():
    repo = TalentRepository.from_entries(FIXTURES / "meta_report_fixture.jsonl")
    nodes = [repo.node_by_id(201)]

    score = reliability_score(nodes=nodes, apl=None, role="melee_dps", warnings=tuple())

    assert score < 0.85
    assert reliability_label(score) in {"medium", "low"}


def test_diverse_selector_prefers_different_reliable_builds():
    repo = TalentRepository.from_entries(FIXTURES / "meta_report_fixture.jsonl")
    dot_fp = build_playstyle_fingerprint(nodes=[repo.node_by_id(201)], apl=None, role="melee_dps")
    duplicate_dot_fp = build_playstyle_fingerprint(nodes=[repo.node_by_id(201), repo.node_by_id(202)], apl=None, role="melee_dps")
    support_fp = build_playstyle_fingerprint(nodes=[repo.node_by_id(301)], apl=None, role="healer")

    selected = select_diverse_builds(
        (
            BuildDiversityCandidate("dot-a", 100.0, "high", dot_fp, 0.9, "high"),
            BuildDiversityCandidate("dot-b", 99.0, "high", duplicate_dot_fp, 0.9, "high"),
            BuildDiversityCandidate("support", 97.0, "medium", support_fp, 0.85, "high"),
        ),
        top=2,
        minimum_distance=0.10,
    )

    assert [candidate.build_id for candidate in selected] == ["dot-a", "support"]
    assert selected[1].selection_reason is not None
    assert selected[1].selection_reason.diversity_label
