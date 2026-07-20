# tests/test_spell_record.py
import types
from coa_client_extract.spell_record import iter_spell_records
from coa_client_extract.contracts import policy_ref
from tests._spell_fixtures import v2_policy, spell_dbc, side_views


def test_iter_spell_records_is_a_generator_and_compact_raw():
    gen = iter_spell_records(spell_dbc(), side_views(), policy=v2_policy(),
                             provenance={"effective_archive": "patch-T.MPQ"})
    assert isinstance(gen, types.GeneratorType)          # streaming, not a materialized list
    rows = list(gen)
    r = rows[0]
    assert r["schema_version"] == "coa-client-spell-v3" and r["spell_id"] == 133
    # a normalized value is present WITH its compact raw retained
    assert r["mechanics"]["power_type"] == 3
    assert r["raw"]["power_type"]["raw_u32"] == 3
    assert r["raw"]["power_type"]["policy_ref"] == policy_ref("Spell", "power_type")
    # no free-form evidence text leaks into the row
    assert "evidence" not in r["raw"]["power_type"] and "evidence_ref" not in r["raw"]["power_type"]
    # a resolved normalized join carries its value + compact component raws
    assert r["mechanics"]["cast_time_ms"] == 1500
    assert r["raw"]["cast_time_ms"]["components"]["side_value"]["raw_u32"] == 1500


def test_raw_only_join_withholds_normalized_but_keeps_compact_raw():
    rows = list(iter_spell_records(spell_dbc(), side_views(), policy=v2_policy(raw_only_cast=True),
                                   provenance={"effective_archive": "patch-T.MPQ"}))
    r = rows[0]
    assert r["mechanics"]["cast_time_ms"] is None                       # withheld (raw_only join)
    assert r["raw"]["cast_time_ms"]["state"] in ("resolved", "not_applicable")   # compact raw retained


def test_custom_id_row_is_marked_is_coa():
    rows = {r["spell_id"]: r for r in iter_spell_records(
        spell_dbc(), side_views(), policy=v2_policy(), provenance={"effective_archive": "patch-T.MPQ"})}
    assert rows[805775]["coa_attribution"]["is_coa"] is True
    assert rows[133]["coa_attribution"]["is_coa"] is False
