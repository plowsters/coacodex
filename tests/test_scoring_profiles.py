import pytest

from coa_meta.profiles import ProfileLoadError, load_builtin_profile, load_profile_by_role


def test_loads_builtin_stalker_profile_from_json():
    profile = load_builtin_profile("venomancer_stalker", encounter="single_target")

    assert profile.profile_id == "venomancer_stalker"
    assert profile.class_name == "Venomancer"
    assert profile.spec_key == "stalker"
    assert profile.role == "dps"
    assert profile.encounter == "single_target"
    assert profile.baseline_index == 100
    assert profile.weights["tags"]["dot"] > 0


def test_loads_generic_role_profile_when_specific_profile_is_missing():
    profile, warnings = load_profile_by_role(class_name="Unknown", spec_key="unknown", role="dps", encounter="aoe_5")

    assert profile.profile_id == "generic_dps"
    assert warnings == ["specific_profile_missing"]
    assert profile.encounter == "aoe_5"


def test_rejects_unknown_encounter():
    with pytest.raises(ProfileLoadError, match="encounter"):
        load_builtin_profile("generic_dps", encounter="unknown")
