from __future__ import annotations

import json
from pathlib import Path

import pytest

from coa_meta.mechanics import MECHANICS_SCHEMA_VERSION, MechanicsLoadError, mechanic_from_raw
from coa_meta.mechanics_repository import MechanicsRepository

FIXTURES = Path(__file__).parent / "fixtures"
MECHANICS = FIXTURES / "mechanics_fixture.jsonl"


def _first_raw() -> dict:
    return json.loads(MECHANICS.read_text(encoding="utf-8").splitlines()[0])


def test_mechanic_record_parses_effects_scaling_and_provenance():
    record = mechanic_from_raw(_first_raw(), "fixture:1")

    assert record.schema_version == MECHANICS_SCHEMA_VERSION
    assert record.spell_id == 2001
    assert record.kind == "ability"
    assert record.costs == {"Energy": 35.0}
    assert record.effects[0].effect_type == "damage"
    assert record.effects[0].scaling is not None
    assert record.effects[0].scaling.spell_power_pct == 0.42
    assert record.provenance[0].source == "ascension_db"
    assert record.provenance[0].source_url == "https://db.ascension.gg/spell/2001"
    assert record.to_dict()["schema_version"] == MECHANICS_SCHEMA_VERSION


def test_mechanics_repository_indexes_by_spell_node_name_and_kind():
    repository = MechanicsRepository.from_jsonl(MECHANICS)

    assert len(repository.records) == 6
    assert repository.by_spell_id(2002).tick_interval_ms == 2000
    assert repository.records_for_node(205)[0].name == "Serpent Companion"
    assert repository.by_name("restorative spores").effects[0].effect_type == "heal"
    assert [record.spell_id for record in repository.records_by_kind("ability")] == [2001, 2006]


def test_mechanics_repository_rejects_wrong_schema_version(tmp_path):
    bad = tmp_path / "bad_mechanics.jsonl"
    bad.write_text(
        MECHANICS.read_text(encoding="utf-8").replace(MECHANICS_SCHEMA_VERSION, "old-mechanics", 1),
        encoding="utf-8",
    )

    with pytest.raises(MechanicsLoadError, match="schema_version"):
        MechanicsRepository.from_jsonl(bad)
