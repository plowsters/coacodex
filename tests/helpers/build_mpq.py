from __future__ import annotations

import ctypes
from pathlib import Path

from coa_client_extract.stormlib_ctypes import load_stormlib


def build_mpq(path: Path, files: dict[str, bytes]) -> Path:
    lib = load_stormlib()
    lib.SFileCreateArchive.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
    lib.SFileCreateArchive.restype = ctypes.c_bool
    lib.SFileAddFileEx.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
    lib.SFileAddFileEx.restype = ctypes.c_bool

    handle = ctypes.c_void_p()
    assert lib.SFileCreateArchive(str(path).encode(), 0, 0x1000, ctypes.byref(handle)), "create failed"
    try:
        for logical, payload in files.items():
            tmp = path.parent / (logical.replace("\\", "_"))
            tmp.write_bytes(payload)
            assert lib.SFileAddFileEx(handle, str(tmp).encode(), logical.encode(), 0x0200, 0x02, 0), f"add {logical} failed"
    finally:
        lib.SFileCloseArchive(handle)
    return path
