import struct

import pytest

from coa_client_extract.errors import DbcDriftError
from coa_client_extract.wdbc import parse_gametable, classify_physical_form


def _gt(records: bytes, field_count: int, record_size: int) -> bytes:
    count = len(records) // record_size
    return struct.pack("<4sIIII", b"WDBC", count, field_count, record_size, 0) + records


def test_classify_physical_form():
    assert classify_physical_form(1, 4) == "implicit_row"
    assert classify_physical_form(2, 8) == "explicit_id"


def test_implicit_row_reads_floats_in_order():
    data = _gt(struct.pack("<fff", 1.5, 2.5, 3.5), field_count=1, record_size=4)
    table = parse_gametable(data, physical_form="implicit_row",
                            expected_field_count=1, expected_record_size=4)
    assert table.record_count == 3 and table.drift is False
    assert [(r["ordinal"], r["value"], r["id"]) for r in table.rows] == [
        (0, 1.5, None), (1, 2.5, None), (2, 3.5, None)]


def test_explicit_id_reads_id_and_float():
    body = struct.pack("<If", 7, 4.25) + struct.pack("<If", 9, 8.75)
    data = _gt(body, field_count=2, record_size=8)
    table = parse_gametable(data, physical_form="explicit_id", expected_field_count=2,
                            expected_record_size=8, value_cell=1, id_cell=0)
    assert [(r["ordinal"], r["id"], r["value"]) for r in table.rows] == [(0, 7, 4.25), (1, 9, 8.75)]


def test_drift_flags_non_strict_and_raises_strict():
    data = _gt(struct.pack("<ff", 1.0, 2.0), field_count=2, record_size=8)
    assert parse_gametable(data, physical_form="implicit_row",
                           expected_field_count=1, expected_record_size=4).drift is True
    with pytest.raises(DbcDriftError):
        parse_gametable(data, physical_form="implicit_row",
                        expected_field_count=1, expected_record_size=4, strict=True)


def test_record_size_not_multiple_of_cell_raises():
    data = struct.pack("<4sIIII", b"WDBC", 0, 1, 6, 0)
    with pytest.raises(DbcDriftError):
        parse_gametable(data, physical_form="implicit_row",
                        expected_field_count=1, expected_record_size=4)
