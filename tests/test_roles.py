from __future__ import annotations

from pathlib import Path

from coa_meta.repository import TalentRepository
from coa_meta.reporting import BuildScope
from coa_meta.roles import (
    GUIDE_ROLES,
    RoleResolution,
    engine_role_for_guide_role,
    resolve_spec_role,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_engine_role_bridge_preserves_existing_profile_roles():
    assert GUIDE_ROLES == ("melee_dps", "caster_dps", "tank", "healer", "support")
    assert engine_role_for_guide_role("melee_dps") == "dps"
    assert engine_role_for_guide_role("caster_dps") == "dps"
    assert engine_role_for_guide_role("tank") == "tank"
    assert engine_role_for_guide_role("healer") == "healer_support"
    assert engine_role_for_guide_role("support") == "healer_support"


def test_role_resolution_serializes_provenance():
    resolution = RoleResolution(
        role="caster_dps",
        engine_role="dps",
        source="inferred",
        confidence="medium",
        evidence=("spell_text:3",),
        scores={"caster_dps": 8.0, "melee_dps": 2.0},
    )

    payload = resolution.to_dict()

    assert payload["schema_version"] == "coa-role-resolution-v1"
    assert payload["role"] == "caster_dps"
    assert payload["engine_role"] == "dps"
    assert payload["evidence"] == ["spell_text:3"]


def test_curated_override_wins_for_fixture_support_spec():
    repo = TalentRepository.from_entries(FIXTURES / "meta_report_fixture.jsonl")
    scope = BuildScope(
        class_name="Testclass",
        spec_id=12,
        spec_name="Support",
        level=60,
        encounter_profile_id="baseline_single_target",
        search_profile_id="default",
        scoring_profile_id="auto",
        apl_profile_id="auto",
        top=1,
    )

    resolution = resolve_spec_role(repo, scope)

    assert resolution.role == "healer"
    assert resolution.engine_role == "healer_support"
    assert resolution.source == "curated"
