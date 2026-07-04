from __future__ import annotations

import pytest

from coa_meta.apl_profiles import (
    APLProfileLoadError,
    load_apl_profile_by_role,
    load_builtin_apl_profile,
    validate_apl_profile_data,
)


def test_loads_builtin_generic_dps_profile():
    profile = load_builtin_apl_profile("generic_dps")

    assert profile.schema_version == "coa-apl-profile-v1"
    assert profile.profile_id == "generic_dps"
    assert profile.class_name == "*"
    assert profile.role == "dps"
    assert "single_target" in profile.supported_encounters
    assert profile.rules
    assert profile.branches


def test_rejects_invalid_schema_version():
    data = {
        "schema_version": "bad",
        "profile_id": "bad_profile",
        "class_name": "*",
        "spec_key": "*",
        "role": "dps",
        "supported_encounters": ["single_target"],
        "resources": [],
        "thresholds": {},
        "condition_templates": {},
        "rules": [],
        "branches": [],
        "assumptions": [],
    }

    with pytest.raises(APLProfileLoadError, match="invalid schema_version"):
        validate_apl_profile_data(data, source="test")


def test_rejects_unsupported_match_operator():
    data = {
        "schema_version": "coa-apl-profile-v1",
        "profile_id": "bad_profile",
        "class_name": "*",
        "spec_key": "*",
        "role": "dps",
        "supported_encounters": ["single_target"],
        "resources": [],
        "thresholds": {},
        "condition_templates": {"ready": ""},
        "rules": [
            {
                "id": "bad_rule",
                "category": "builder",
                "match": {"unsupported_operator": ["builder"]},
                "condition_template": "ready",
                "priority": 10,
                "confidence": "medium",
                "note": "bad matcher",
            }
        ],
        "branches": [{"encounter": "single_target", "include_categories": ["builder"]}],
        "assumptions": [],
    }

    with pytest.raises(APLProfileLoadError, match="unsupported match operator"):
        validate_apl_profile_data(data, source="test")


def test_rejects_unknown_condition_template():
    data = {
        "schema_version": "coa-apl-profile-v1",
        "profile_id": "bad_profile",
        "class_name": "*",
        "spec_key": "*",
        "role": "dps",
        "supported_encounters": ["single_target"],
        "resources": [],
        "thresholds": {},
        "condition_templates": {"ready": ""},
        "rules": [
            {
                "id": "bad_rule",
                "category": "builder",
                "match": {"tags_any": ["builder"]},
                "condition_template": "missing_template",
                "priority": 10,
                "confidence": "medium",
                "note": "bad template",
            }
        ],
        "branches": [{"encounter": "single_target", "include_categories": ["builder"]}],
        "assumptions": [],
    }

    with pytest.raises(APLProfileLoadError, match="unknown condition template"):
        validate_apl_profile_data(data, source="test")


def test_rejects_required_future_input():
    data = {
        "schema_version": "coa-apl-profile-v1",
        "profile_id": "bad_profile",
        "class_name": "*",
        "spec_key": "*",
        "role": "dps",
        "supported_encounters": ["single_target"],
        "resources": [],
        "thresholds": {},
        "condition_templates": {"ready": ""},
        "rules": [],
        "branches": [{"encounter": "single_target", "include_categories": ["builder"]}],
        "assumptions": [],
        "required_inputs": ["saved_variables_snapshot"],
    }

    with pytest.raises(APLProfileLoadError, match="future input"):
        validate_apl_profile_data(data, source="test")


def test_profile_by_role_falls_back_to_generic_profile():
    profile, warnings = load_apl_profile_by_role(
        class_name="Imaginary Class",
        spec_key="missing",
        role="dps",
    )

    assert profile.profile_id == "generic_dps"
    assert warnings == ["specific_apl_profile_missing"]


def test_loads_venomancer_stalker_profile_without_python_special_case():
    profile, warnings = load_apl_profile_by_role(
        class_name="Venomancer",
        spec_key="stalker",
        role="dps",
    )

    assert profile.profile_id == "venomancer_stalker"
    assert profile.class_name == "Venomancer"
    assert profile.spec_key == "stalker"
    assert warnings == []
    assert any(rule.id == "stalker_spenders" for rule in profile.rules)
