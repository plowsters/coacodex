from __future__ import annotations

from coa_meta.gear import (
    GearProfile,
    ItemRecord,
    rank_items_for_role,
    recommend_gear_for_guide_role,
    recommend_weapon_and_armor,
)


def test_item_records_parse_coa_item_schema_and_gear_totals():
    sword = ItemRecord.from_raw(
        {
            "schema_version": "coa-item-v1",
            "item_id": 100,
            "name": "Venom-Forged Sword",
            "slot": "main_hand",
            "item_class": "weapon",
            "weapon_type": "sword",
            "stats": {"strength": 12, "stamina": 5},
            "ratings": {"crit_rating": 8},
            "attack_power": 20,
            "confidence": "medium",
        }
    )
    robe = ItemRecord.from_raw(
        {
            "schema_version": "coa-item-v1",
            "item_id": 101,
            "name": "Restorer Robe",
            "slot": "chest",
            "item_class": "armor",
            "armor_type": "cloth",
            "stats": {"intellect": 14, "stamina": 4},
            "spell_power": 22,
            "confidence": "medium",
        }
    )

    totals = GearProfile(items=(sword, robe)).total_stats()

    assert sword.weapon_type == "sword"
    assert totals.strength == 12
    assert totals.intellect == 14
    assert totals.attack_power == 20
    assert totals.spell_power == 22
    assert totals.crit_rating == 8


def test_role_item_ranking_and_recommendation_warnings():
    sword = ItemRecord(
        item_id=100,
        name="Venom-Forged Sword",
        slot="main_hand",
        item_class="weapon",
        weapon_type="sword",
        stats={"strength": 12},
        ratings={"crit_rating": 8},
        attack_power=20,
    )
    robe = ItemRecord(
        item_id=101,
        name="Restorer Robe",
        slot="chest",
        item_class="armor",
        armor_type="cloth",
        stats={"intellect": 14},
        spell_power=22,
    )

    healer_scores = rank_items_for_role("healer_support", (sword, robe))
    missing = recommend_weapon_and_armor("tank", tuple())

    assert healer_scores[0].item_id == 101
    assert "cloth" in recommend_weapon_and_armor("healer_support", (robe,))["armor_types"]
    assert "item_data_missing" in missing["warnings"]


def test_guide_gear_recommendation_splits_best_and_available():
    payload = recommend_gear_for_guide_role("tank", engine_role="tank", items=tuple()).to_dict()

    assert payload["schema_version"] == "coa-gear-recommendation-v2"
    assert payload["role"] == "tank"
    assert payload["best_weapon_types"]
    assert payload["available_weapon_types"]
    assert "item_data_missing" in payload["warnings"]
