import struct

import pytest

from coa_client_extract.errors import DbcDriftError
from coa_client_extract.recordview import open_view


def _dbc(records, field_count, record_size, block=b"\x00hi\x00"):
    count = len(records) // record_size
    return struct.pack("<4sIIII", b"WDBC", count, field_count, record_size, len(block)) + records + block


def test_bounds_are_per_record_not_per_file():
    data = _dbc(struct.pack("<IIII", 1, 2, 3, 4), 2, 8)      # 2 records of 2 cells each
    v = open_view(data)
    assert [r.u32(0) for r in v.records()] == [1, 3]
    r0 = v.record(0)
    assert r0.u32(1) == 2
    with pytest.raises(DbcDriftError): r0.u32(2)             # cell 2 is in record 1 — must not read across
    with pytest.raises(DbcDriftError): r0.cells(1, 3)        # would overrun into record 1


def test_cells_with_stride():
    data = _dbc(struct.pack("<IIIIII", 10, 11, 20, 21, 30, 31), 6, 24)   # 1 record, 6 cells
    r = open_view(data).record(0)
    assert r.cells(0, 3, stride=2) == [10, 20, 30]


def test_read_string_strict_vs_try_string_lenient():
    v = open_view(_dbc(struct.pack("<II", 1, 1), 2, 8, b"\x00hi\x00"))
    assert v.read_string(1) == "hi" and v.read_string(0) == ""
    with pytest.raises(DbcDriftError): v.read_string(999)    # out-of-range offset raises (strict)
    assert v.try_string(999) is None                        # lenient for discovery scanning
    unterminated = struct.pack("<4sIIII", b"WDBC", 0, 1, 4, 3) + b"abc"   # block has no NUL
    with pytest.raises(DbcDriftError):
        open_view(unterminated).read_string(1)


def test_open_view_rejects_bad_magic_and_trailing_bytes():
    with pytest.raises(DbcDriftError):
        open_view(b"XXXX" + struct.pack("<IIII", 0, 1, 4, 0))
    good = _dbc(struct.pack("<II", 1, 2), 2, 8, b"\x00")
    with pytest.raises(DbcDriftError):
        open_view(good + b"EXTRA")                           # trailing bytes beyond header-implied length


def test_require_dense():
    dense = open_view(_dbc(struct.pack("<II", 1, 2), 2, 8, b"\x00"))         # 2 fields, 2 cells
    assert dense.require_dense() is dense and dense.cell_count == 2
    sparse = open_view(struct.pack("<4sIIII", b"WDBC", 0, 3, 8, 1) + b"\x00")  # 3 fields, 2 cells
    with pytest.raises(DbcDriftError):
        sparse.require_dense()
