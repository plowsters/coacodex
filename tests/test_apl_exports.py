from __future__ import annotations

from coa_meta.apl import APLAction, APLDocument, apl_to_simc_lines


def test_apl_document_serializes_to_canonical_dict():
    document = APLDocument(
        schema_version="coa-apl-v1",
        source="theorycraft",
        profile_id="generic_dps",
        class_name="Testclass",
        spec_key="generic",
        role="dps",
        encounter="single_target",
        actions=(
            APLAction(
                action_key="poison_talent",
                action_name="Poison Talent",
                node_id=103,
                spell_id=1003,
                category="maintenance",
                condition="dot.poison_talent.remains<gcd",
                priority=20,
                confidence="medium",
                notes=("maintain DoT/debuff uptime",),
                evidence=("tag:dot", "profile_rule:maintain_dots"),
            ),
        ),
        assumptions=("Generated from normalized builder data.",),
        warnings=("condition inferred from normalized tooltip tags",),
        provenance={"profile_schema": "coa-apl-profile-v1"},
    )

    payload = document.to_dict()

    assert payload["schema_version"] == "coa-apl-v1"
    assert payload["source"] == "theorycraft"
    assert payload["actions"][0]["action_key"] == "poison_talent"
    assert payload["actions"][0]["evidence"] == ["tag:dot", "profile_rule:maintain_dots"]


def test_simc_export_uses_action_key_condition_and_note():
    document = APLDocument(
        schema_version="coa-apl-v1",
        source="theorycraft",
        profile_id="generic_dps",
        class_name="Testclass",
        spec_key="generic",
        role="dps",
        encounter="single_target",
        actions=(
            APLAction(
                action_key="poison_talent",
                action_name="Poison Talent",
                node_id=103,
                spell_id=1003,
                category="maintenance",
                condition="dot.poison_talent.remains<gcd",
                priority=20,
                confidence="medium",
                notes=("maintain DoT/debuff uptime",),
                evidence=("tag:dot", "profile_rule:maintain_dots"),
            ),
        ),
        assumptions=(),
        warnings=(),
        provenance={},
    )

    assert apl_to_simc_lines(document) == [
        "actions+=/poison_talent,if=dot.poison_talent.remains<gcd  # maintain DoT/debuff uptime"
    ]


def test_simc_export_omits_if_when_condition_is_empty():
    document = APLDocument(
        schema_version="coa-apl-v1",
        source="theorycraft",
        profile_id="generic_dps",
        class_name="Testclass",
        spec_key="generic",
        role="dps",
        encounter="single_target",
        actions=(
            APLAction(
                action_key="auto_attack",
                action_name="Auto Attack",
                node_id=None,
                spell_id=None,
                category="filler",
                condition="",
                priority=200,
                confidence="low",
                notes=("fallback active ability",),
                evidence=("profile_rule:active_filler",),
            ),
        ),
        assumptions=(),
        warnings=(),
        provenance={},
    )

    assert apl_to_simc_lines(document) == ["actions+=/auto_attack  # fallback active ability"]
