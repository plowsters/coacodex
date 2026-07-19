from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass

from .errors import DbcDriftError

_H = struct.Struct("<4sIIII")   # magic, records, fields, record_size, string_block_size
_MAGIC = b"WDBC"
_CELL = 4


@dataclass(frozen=True)
class RecordView:
    _data: bytes
    _base: int
    record_size: int

    def _check(self, cell: int, width: int = 1, stride: int = 1) -> None:
        if cell < 0 or stride < 1 or width < 1:
            raise DbcDriftError(f"bad cell/width/stride ({cell}/{width}/{stride})")
        last = cell + (width - 1) * stride
        if (last + 1) * _CELL > self.record_size:
            raise DbcDriftError(f"cell {last} out of record bounds ({self.record_size} bytes)")

    def u32(self, cell: int) -> int:
        self._check(cell)
        (v,) = struct.unpack_from("<I", self._data, self._base + cell * _CELL)
        return v

    def cells(self, start: int, width: int, stride: int = 1) -> list[int]:
        self._check(start, width, stride)
        return [struct.unpack_from("<I", self._data, self._base + (start + k * stride) * _CELL)[0]
                for k in range(width)]


@dataclass(frozen=True)
class DbcView:
    _data: bytes
    record_count: int
    field_count: int
    record_size: int
    _sstart: int
    _ssize: int

    @property
    def cell_count(self) -> int:
        return self.record_size // _CELL

    def require_dense(self) -> "DbcView":
        """Spell-family tables must be dense (field_count*4 == record_size). Wide/sparse tables like
        CharacterAdvancement are read by other paths and never call this."""
        if self.field_count * _CELL != self.record_size:
            raise DbcDriftError(f"field_count {self.field_count}*4 != record_size {self.record_size}")
        return self

    def record(self, i: int) -> RecordView:
        if not (0 <= i < self.record_count):
            raise DbcDriftError(f"record {i} out of range ({self.record_count})")
        return RecordView(self._data, _H.size + i * self.record_size, self.record_size)

    def records(self) -> Iterator[RecordView]:
        for i in range(self.record_count):
            yield self.record(i)

    def read_string(self, off: int) -> str:
        """STRICT: for a proven string field. Raises on out-of-range offset or an unterminated string."""
        if off < 0 or off >= self._ssize:
            raise DbcDriftError(f"string offset {off} out of block ({self._ssize})")
        if off == 0:
            return ""
        block = self._data[self._sstart:self._sstart + self._ssize]
        end = block.find(b"\x00", off)
        if end < 0:
            raise DbcDriftError(f"unterminated string at offset {off}")
        return block[off:end].decode("utf-8", "replace")

    def try_string(self, off: int) -> str | None:
        """LENIENT: for discovery scanning of arbitrary candidate cells; returns None on any drift."""
        try:
            return self.read_string(off)
        except DbcDriftError:
            return None


def open_view(data: bytes) -> DbcView:
    if len(data) < _H.size:
        raise DbcDriftError("file smaller than DBC header")
    magic, rc, fc, rs, ss = _H.unpack_from(data, 0)
    if magic != _MAGIC:
        raise DbcDriftError(f"bad magic {magic!r}, expected WDBC")
    if rs <= 0 or rs % _CELL != 0:
        raise DbcDriftError(f"bad record_size {rs}")
    sstart = _H.size + rc * rs
    if len(data) != sstart + ss:                # reject unadjudicated trailing / short bytes
        raise DbcDriftError(f"length {len(data)} != header-implied {sstart + ss}")
    return DbcView(data, rc, fc, rs, sstart, ss)
