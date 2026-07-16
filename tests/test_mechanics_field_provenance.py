import json
from coa_meta.mechanics import mechanic_from_raw
from coa_meta.mechanics_repository import MechanicsRepository


def _raw(**over):
    base = {
        "schema_version": "coa-mechanics-v1", "spell_id": 805775, "name": "Adrenal Venom",
        "kind": "ability", "school": "nature", "schools": ["nature"],
        "field_provenance": {"schools": {"selected_source": "client_dbc", "selected_tier": "client_dbc",
                                         "selected_value": ["nature"], "selection_reason": "highest_precedence_eligible",
                                         "warnings": [], "candidates": []}},
        "effects": [{"effect_type": "damage", "period_ms": 3000}],
    }
    base.update(over)
    return base


def test_schools_and_field_provenance_round_trip():
    rec = mechanic_from_raw(_raw(), "<test>")
    assert rec.schools == ("nature",)
    assert rec.field_provenance["schools"]["selected_source"] == "client_dbc"
    out = rec.to_dict()
    assert out["schools"] == ["nature"]
    assert out["field_provenance"]["schools"]["selected_tier"] == "client_dbc"


def test_effect_accepts_legacy_period_ms_reserializes_tick_interval():
    rec = mechanic_from_raw(_raw(), "<test>")
    assert rec.effects[0].tick_interval_ms == 3000
    out = rec.to_dict()
    assert out["effects"][0]["tick_interval_ms"] == 3000
    assert "period_ms" not in out["effects"][0]


def test_repository_loads_and_round_trips_field_provenance_and_schools(tmp_path):
    row = {
        "schema_version": "coa-mechanics-v1", "spell_id": 805775, "name": "Adrenal Venom",
        "kind": "ability", "schools": ["fire", "frost"],
        "field_provenance": {"schools": {"selected_source": "client_dbc", "selected_tier": "client_dbc",
                                         "selected_value": ["fire", "frost"], "selection_reason": "highest_precedence_eligible",
                                         "warnings": [], "candidates": []}},
        "effects": [{"effect_type": "damage", "tick_interval_ms": 3000}],
    }
    p = tmp_path / "coa_mechanics.jsonl"
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    repo = MechanicsRepository.from_jsonl(p)
    rec = repo.get_spell_id(805775)
    assert rec is not None
    assert rec.schools == ("fire", "frost")
    out = rec.to_dict()
    assert out["schools"] == ["fire", "frost"]
    assert out["field_provenance"]["schools"]["selected_tier"] == "client_dbc"
    assert out["effects"][0]["tick_interval_ms"] == 3000
