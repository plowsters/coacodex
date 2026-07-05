from __future__ import annotations

from coa_meta.stats import StatProfile, stat_priority_for_role, stat_priority_report_for_role


def test_stat_profiles_add_values_and_keep_known_fields():
    base = StatProfile(strength=10, stamina=20, attack_power=30)
    bonus = StatProfile(strength=5, intellect=8, spell_power=12)

    total = base + bonus

    assert total.strength == 15
    assert total.stamina == 20
    assert total.intellect == 8
    assert total.attack_power == 30
    assert total.spell_power == 12


def test_stat_priority_is_role_specific_and_confidence_labeled():
    tank = stat_priority_for_role("tank")
    healer = stat_priority_for_role("healer_support")

    assert tank[0].stat in {"stamina", "armor"}
    assert healer[0].stat in {"spell_power", "intellect"}
    assert all(priority.confidence == "medium" for priority in tank)


def test_stat_priority_report_groups_stats_and_has_one_disclaimer():
    report = stat_priority_report_for_role("caster_dps", engine_role="dps")
    payload = report.to_dict()

    assert payload["schema_version"] == "coa-stat-priority-v2"
    assert payload["role"] == "caster_dps"
    assert payload["engine_role"] == "dps"
    assert "simulations or combat logs" in payload["disclaimer"]
    assert [group["group_id"] for group in payload["groups"]] == ["primary", "secondary", "situational"]
    assert payload["groups"][0]["entries"]
