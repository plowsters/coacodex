from __future__ import annotations

from coa_meta.stats import StatProfile, stat_priority_for_role


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
