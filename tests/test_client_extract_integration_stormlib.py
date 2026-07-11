import struct
from pathlib import Path

import pytest

pytestmark = pytest.mark.stormlib

from coa_client_extract.stormlib_backend import StormLibBackend  # noqa: E402


def _dbc(value: int) -> bytes:
    row = struct.pack("<II", 1, value)
    return struct.pack("<4sIIII", b"WDBC", 1, 2, 8, 1) + row + b"\x00"


def test_patch_overrides_base(tmp_path):
    from tests.helpers.build_mpq import build_mpq

    base = build_mpq(tmp_path / "common.MPQ", {"DBFilesClient\\Test.dbc": _dbc(100)})
    patch = build_mpq(tmp_path / "patch-C.MPQ", {"DBFilesClient\\Test.dbc": _dbc(999)})

    backend = StormLibBackend()
    member = backend.read_effective_file(base, (patch,), "DBFilesClient\\Test.dbc")

    # the patched value (999) must win over the base value (100)
    _, _, _, _, _ = struct.unpack_from("<4sIIII", member.data, 0)
    (value,) = struct.unpack_from("<I", member.data, 24)  # header(20)+id(4) -> value cell
    assert value == 999
    assert member.effective_archive == patch
    assert base in member.patch_chain and patch in member.patch_chain
