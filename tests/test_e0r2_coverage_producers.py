"""E0R.2 T4.1: raw extraction states are OBSERVATION coverage, not mechanics readiness.

Two different layers with two different denominators, and conflating them is how a generation reports a
healthy-looking number about the wrong population:

  observation_coverage      generation manifest   every raw cell of every full row
  icon_coverage             generation manifest   every spell in the domain (already existed)
  field_readiness_coverage  mechanics manifest    Builder-domain mechanics fields (Node side)
  source_coverage           mechanics manifest    per_field_winner_counts_by_source (already existed)

The denominator is the whole point. A coverage number computed over "the cells we happened to emit"
cannot distinguish complete extraction from silent loss — it is 100% either way.
"""
import pytest

from coa_client_extract.contracts import DECODED_REASONS, OBSERVATION_STATES
from coa_client_extract.spell_record import (OBSERVATION_COVERAGE_SCHEMA, iter_spell_records,
                                             observation_accumulator)
from tests._spell_fixtures import side_views, spell_dbc, v2_policy


def _rows():
    return list(iter_spell_records(spell_dbc(), side_views(), policy=v2_policy(),
                                   provenance={"extraction_date": "2026-07-29"}))


def _coverage(rows=None):
    acc = observation_accumulator()
    for row in (_rows() if rows is None else rows):
        acc.observe(row)
    return acc.result()


def test_the_accumulator_counts_every_cell_of_every_row():
    rows = _rows()
    cov = _coverage(rows)
    assert cov["schema_version"] == OBSERVATION_COVERAGE_SCHEMA
    assert cov["rows"] == len(rows)
    assert cov["cells"] == sum(len(r["raw"]) for r in rows)


def test_the_denominator_is_exact_at_every_level():
    """Each cell lands in exactly one state bucket and exactly one reason bucket, per field and overall.
    A coverage report whose parts do not sum to its denominator is describing a different population
    from the one it names."""
    cov = _coverage()
    assert sum(cov["states"].values()) == cov["cells"]
    assert sum(cov["decoded_reasons"].values()) == cov["cells"]
    assert sum(f["cells"] for f in cov["fields"].values()) == cov["cells"]
    for field, f in cov["fields"].items():
        assert sum(f["states"].values()) == f["cells"], field
        assert sum(f["decoded_reasons"].values()) == f["cells"], field


def test_only_closed_vocabulary_values_are_counted():
    cov = _coverage()
    assert set(cov["states"]) <= set(OBSERVATION_STATES)
    assert set(cov["decoded_reasons"]) <= set(DECODED_REASONS)


def test_the_fields_counted_are_the_fields_the_rows_carry():
    rows = _rows()
    cov = _coverage(rows)
    assert set(cov["fields"]) == {f for r in rows for f in r["raw"]}


def test_an_unresolved_join_is_counted_not_skipped():
    """A join in `unresolved` state is an observation with no value. Counting only resolved cells is
    exactly the arithmetic that turns silent loss into 100% coverage."""
    rows = _rows()
    cov = _coverage(rows)
    join = cov["fields"]["cast_time_ms"]
    assert join["cells"] == len(rows)
    assert sum(join["states"].values()) == len(rows)


def test_a_join_component_is_not_double_counted():
    # A join's components are sub-observations of the one field cell; counting them too would inflate
    # both the numerator and the denominator with a different unit.
    rows = _rows()
    assert _coverage(rows)["cells"] == sum(len(r["raw"]) for r in rows)


def test_an_empty_stream_reports_nothing_rather_than_everything():
    cov = _coverage([])
    assert cov["rows"] == 0 and cov["cells"] == 0
    assert cov["fields"] == {} and cov["states"] == {} and cov["decoded_reasons"] == {}


def test_the_accumulator_holds_counters_and_nothing_else():
    """It is folded into the streaming write loop over a 200k-row table; retaining rows would defeat the
    streaming design (A4). Its state is counters, and `__slots__` means it cannot quietly grow a row
    list later either."""
    acc = observation_accumulator()
    for row in _rows():
        acc.observe(row)
    assert not hasattr(acc, "__dict__")
    held = [getattr(acc, name) for name in acc.__slots__]
    assert all(isinstance(v, (int, dict)) for v in held)
    for slot in held:
        if isinstance(slot, dict):
            for value in slot.values():
                assert isinstance(value, (int, dict)), "a counter, never a row"


def test_regenerate_hoists_observation_coverage_into_the_generation_manifest():
    import json

    from tests.golden import _generation

    manifest = json.loads((_generation() / "manifest.json").read_text(encoding="utf-8"))
    cov = manifest["observation_coverage"]
    assert cov["schema_version"] == OBSERVATION_COVERAGE_SCHEMA
    assert cov["rows"] == manifest["children"]["coa_client_spell.jsonl"]["records"]
    assert sum(cov["states"].values()) == cov["cells"] > 0


def test_observation_coverage_is_a_different_population_from_icon_coverage():
    """The correction this task carries: icon coverage counts SPELLS, observation coverage counts CELLS.
    Reporting one as the other would look like a healthy number about the wrong denominator."""
    import json

    from tests.golden import _generation

    manifest = json.loads((_generation() / "manifest.json").read_text(encoding="utf-8"))
    obs, icons = manifest["observation_coverage"], manifest["icon_coverage"]
    assert obs["rows"] == icons["spells"]          # same domain ...
    assert obs["cells"] > obs["rows"]              # ... counted in a different unit
