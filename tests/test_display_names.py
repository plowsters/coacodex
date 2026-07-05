from __future__ import annotations

from coa_meta.display_names import display_spec_name, display_spec_title
from coa_meta.reporting import SpecResult


def test_display_spec_name_applies_user_facing_legacy_renames():
    assert display_spec_name("Runemaster", "Arcane") == "Glyphic"
    assert display_spec_name("Runemaster", "Runic") == "Engravement"
    assert display_spec_name("Venomancer", "Venom") == "Rot"
    assert display_spec_name("Primalist", "Life") == "Grovekeeper"
    assert display_spec_name("Primalist", "Primal") == "Wildwalker"
    assert display_spec_name("Witch Hunter", "Houndmaster") == "Darkness"


def test_display_spec_title_uses_display_spec_and_source_class_name():
    assert display_spec_title("Venomancer", "Venom") == "Rot Venomancer"
    assert display_spec_title("Testclass", "Damage") == "Damage Testclass"


def test_spec_result_serializes_display_name_without_losing_source_name():
    result = SpecResult(
        class_name="Venomancer",
        spec_id=29,
        spec_name="Venom",
        role="caster_dps",
        engine_role="dps",
        role_provenance={},
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

    assert payload["spec_name"] == "Rot"
    assert payload["source_spec_name"] == "Venom"
