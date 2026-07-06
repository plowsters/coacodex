from __future__ import annotations

from pathlib import Path

from coa_meta.apl import APLAction, APLDocument
from coa_meta.build_diversity import (
    BuildDiversityCandidate,
    PlaystyleFingerprint,
    RotationPlaystyleSignature,
    build_playstyle_fingerprint,
    fingerprint_distance,
    reliability_label,
    reliability_score,
    rotation_signature_from_apl,
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


def test_rotation_signature_from_apl_captures_core_loop_shape():
    apl = APLDocument(
        schema_version="coa-apl-v1",
        source="theorycraft",
        profile_id="test",
        class_name="Testclass",
        spec_key="Damage",
        role="caster_dps",
        encounter="single_target",
        actions=(
            APLAction("dot", "Poison Dot", 201, 2001, "maintenance", "dot.dot.remains<gcd", 10, "medium", tuple(), tuple()),
            APLAction("burst", "Burst", 202, 2002, "cooldown", "cooldown.burst.ready", 20, "medium", tuple(), tuple()),
            APLAction("filler", "Filler", 203, 2003, "filler", "", 30, "medium", tuple(), tuple()),
        ),
        assumptions=tuple(),
        warnings=tuple(),
        provenance={},
    )

    signature = rotation_signature_from_apl(apl, role="caster_dps")

    assert signature.schema_version == "coa-rotation-playstyle-v1"
    assert signature.maintenance_actions == ("dot",)
    assert signature.cooldown_actions == ("burst",)
    assert signature.resource_loop == "maintenance_loop"
    assert signature.burst_cadence == "medium"
    assert signature.range_profile == "caster"


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


def _fingerprint(label: str, *, node_id: int = 1) -> PlaystyleFingerprint:
    return PlaystyleFingerprint(
        schema_version="coa-build-playstyle-v1",
        label=label,
        primary_tags=(label,),
        active_ability_names=(label,),
        passive_ratio=0.0,
        active_count=1,
        cooldown_count=1 if "burst" in label else 0,
        dot_count=1 if "dot" in label else 0,
        summon_count=0,
        heal_count=0,
        defensive_count=0,
        support_count=0,
        melee_score=1.0 if "burst" in label else 0.0,
        ranged_score=0.0,
        caster_score=1.0 if "dot" in label else 0.0,
        schools={"nature": 1} if "dot" in label else {"physical": 1},
        resources={"energy": 1},
        apl_categories={"maintenance": 1} if "dot" in label else {"cooldown": 1},
        selected_node_ids=(node_id,),
    )


def _rotation_signature(kind: str) -> RotationPlaystyleSignature:
    if kind == "dot":
        return RotationPlaystyleSignature(
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
    return RotationPlaystyleSignature(
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


def _candidate(build_id: str, *, score: float, label: str, rotation_kind: str) -> BuildDiversityCandidate:
    return BuildDiversityCandidate(
        build_id=build_id,
        projected_dps_index=score,
        confidence_label="high",
        fingerprint=_fingerprint(label, node_id=hash(build_id) % 10000),
        reliability_score=0.9,
        reliability_label="high",
        rotation_signature=_rotation_signature(rotation_kind),
    )


def test_diverse_selection_collapses_near_duplicate_rotation_signatures():
    dot_a = _candidate("dot-a", score=100.0, label="dot", rotation_kind="dot")
    dot_b = _candidate("dot-b", score=99.0, label="dot", rotation_kind="dot")
    burst = _candidate("burst", score=96.0, label="burst", rotation_kind="burst")

    selected = select_diverse_builds((dot_a, dot_b, burst), top=3)

    assert [item.build_id for item in selected] == ["dot-a", "burst"]
