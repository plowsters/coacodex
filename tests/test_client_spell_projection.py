from coa_client_extract.artifacts import build_client_spell_records
from coa_client_extract.wdbc import DbcTable


def _table(name, rows, drift=False):
    return DbcTable(layout_name=name, field_count=1, record_size=4, record_count=len(rows), rows=rows, drift=drift)


def _spell_family(*, spell_drift=False, cast_drift=False):
    spell = _table("Spell", [{
        "id": 805775, "name": "Adrenal Venom", "school_mask": 8, "power_type": 3,
        "casting_time_index": 1, "duration_index": 1, "range_index": 1,
        "category": 0, "spell_icon_id": 4583,
    }], drift=spell_drift)
    cast = _table("SpellCastTimes", [{"id": 1, "base_ms": 0}], drift=cast_drift)
    dur = _table("SpellDuration", [{"id": 1, "base_ms": 12000}])
    rng = _table("SpellRange", [{"id": 1, "min_yd": 0, "max_yd": 30}])
    return spell, cast, dur, rng


def test_per_table_confidence_high_when_no_drift():
    spell, cast, dur, rng = _spell_family()
    rec = build_client_spell_records(spell, cast, dur, rng, provenance={"effective_archive": "patch-T.MPQ"})[0]
    by_dbc = rec["provenance"]["schema_match_confidence_by_dbc"]
    assert by_dbc == {"Spell": "high", "SpellCastTimes": "high", "SpellDuration": "high", "SpellRange": "high"}


def test_per_table_confidence_low_for_drifted_table_only():
    spell, cast, dur, rng = _spell_family(cast_drift=True)
    rec = build_client_spell_records(spell, cast, dur, rng, provenance={"effective_archive": "patch-T.MPQ"})[0]
    by_dbc = rec["provenance"]["schema_match_confidence_by_dbc"]
    assert by_dbc["SpellCastTimes"] == "low"
    assert by_dbc["Spell"] == "high"
    assert by_dbc["SpellDuration"] == "high"
    assert by_dbc["SpellRange"] == "high"


def test_per_table_confidence_low_for_spell_drift():
    spell, cast, dur, rng = _spell_family(spell_drift=True)
    rec = build_client_spell_records(spell, cast, dur, rng, provenance={"effective_archive": "patch-T.MPQ"})[0]
    by_dbc = rec["provenance"]["schema_match_confidence_by_dbc"]
    assert by_dbc["Spell"] == "low"
    assert by_dbc["SpellCastTimes"] == "high"  # only Spell drifted; side-tables stay high


def test_absent_table_is_low_confidence():
    spell, cast, dur, rng = _spell_family()
    rec = build_client_spell_records(spell, cast, dur, None, provenance={"effective_archive": "patch-T.MPQ"})[0]
    assert rec["provenance"]["schema_match_confidence_by_dbc"]["SpellRange"] == "low"


import json
from pathlib import Path
from coa_client_extract.artifacts import write_client_spell_projection


def _coa_rec(spell_id, is_coa, conf="high", modes=("coa",)):
    return {
        "schema_version": "coa-client-spell-v1", "spell_id": spell_id, "name": f"S{spell_id}",
        "mechanics": {"school_mask": 8, "power_type": 3, "cast_time_ms": 0, "duration_ms": 12000,
                      "range_min_yd": 0, "range_max_yd": 30, "category": 0, "spell_icon_id": 1},
        "provenance": {"schema_match_confidence": "high",
                       "schema_match_confidence_by_dbc": {"Spell": "high", "SpellCastTimes": "high",
                                                          "SpellDuration": "high", "SpellRange": "high"}},
        "coa_attribution": {"is_coa": is_coa, "modes": list(modes), "exclusive_mode": modes[0] if modes else None,
                            "confidence": conf},
    }


def test_projection_keeps_only_is_coa_and_writes_manifest(tmp_path):
    records = [_coa_rec(1, True), _coa_rec(2, False, conf="low", modes=()), _coa_rec(3, True, conf="medium")]
    manifest = write_client_spell_projection(
        records, tmp_path, source_path="coa_client_spell.jsonl", source_sha="abc", source_bytes=100,
        client_build="3.3.5a+patch-T", extractor_commit="deadbeef")
    proj = [json.loads(l) for l in (tmp_path / "coa_client_spell_coa.jsonl").read_text().splitlines() if l.strip()]
    assert sorted(r["spell_id"] for r in proj) == [1, 3]
    assert manifest["schema_version"] == "coa-client-spell-projection-v1"
    assert manifest["counts"]["projected_records"] == 2
    assert manifest["counts"]["by_confidence"] == {"high": 1, "medium": 1}
    assert manifest["source_artifact"]["sha256"] == "abc"
    written = json.loads((tmp_path / "coa_client_spell_projection.manifest.json").read_text())
    assert written["projection"]["sha256"] == manifest["projection"]["sha256"]


def test_projection_rejects_duplicate_spell_ids(tmp_path):
    import pytest
    records = [_coa_rec(1, True), _coa_rec(1, True)]
    with pytest.raises(ValueError, match="duplicate spell_ids"):
        write_client_spell_projection(records, tmp_path, source_path="x", source_sha="a", source_bytes=1,
                                      client_build="b", extractor_commit="c")
