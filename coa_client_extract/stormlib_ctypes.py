from __future__ import annotations

import ctypes
import ctypes.util
import os
from contextlib import contextmanager

from .errors import ArchiveError, BackendUnavailable

_CANDIDATES = ("storm", "libstorm.so", "libstorm.so.9", "libStorm.dylib", "StormLib.dll")


def load_stormlib(explicit_path: str | None = None) -> ctypes.CDLL:
    tried: list[str] = []
    ordered: list[str] = []
    if explicit_path:
        ordered.append(explicit_path)
    if os.environ.get("STORMLIB_PATH"):
        ordered.append(os.environ["STORMLIB_PATH"])
    found = ctypes.util.find_library("storm")
    if found:
        ordered.append(found)
    ordered.extend(_CANDIDATES)
    for name in ordered:
        try:
            lib = ctypes.CDLL(name)
        except OSError:
            tried.append(name)
            continue
        _bind(lib)
        return lib
    raise BackendUnavailable(
        "StormLib shared library not found. Install StormLib (MIT) or pass --stormlib PATH / "
        f"set STORMLIB_PATH. Tried: {', '.join(tried)}"
    )


def _bind(lib: ctypes.CDLL) -> None:
    b = ctypes.c_bool
    h = ctypes.c_void_p
    dw = ctypes.c_uint32
    lib.SFileOpenArchive.argtypes = [ctypes.c_char_p, dw, dw, ctypes.POINTER(h)]
    lib.SFileOpenArchive.restype = b
    lib.SFileOpenPatchArchive.argtypes = [h, ctypes.c_char_p, ctypes.c_char_p, dw]
    lib.SFileOpenPatchArchive.restype = b
    lib.SFileHasFile.argtypes = [h, ctypes.c_char_p]
    lib.SFileHasFile.restype = b
    lib.SFileOpenFileEx.argtypes = [h, ctypes.c_char_p, dw, ctypes.POINTER(h)]
    lib.SFileOpenFileEx.restype = b
    lib.SFileGetFileSize.argtypes = [h, ctypes.POINTER(dw)]
    lib.SFileGetFileSize.restype = dw
    lib.SFileReadFile.argtypes = [h, ctypes.c_void_p, dw, ctypes.POINTER(dw), ctypes.c_void_p]
    lib.SFileReadFile.restype = b
    lib.SFileCloseFile.argtypes = [h]
    lib.SFileCloseFile.restype = b
    lib.SFileCloseArchive.argtypes = [h]
    lib.SFileCloseArchive.restype = b


@contextmanager
def open_archive(lib: ctypes.CDLL, path: str):
    handle = ctypes.c_void_p()
    if not lib.SFileOpenArchive(path.encode("utf-8"), 0, 0x00000100, ctypes.byref(handle)):
        raise ArchiveError(f"SFileOpenArchive failed for {path} (err {ctypes.get_errno()})")
    try:
        yield handle
    finally:
        lib.SFileCloseArchive(handle)


@contextmanager
def open_file(lib: ctypes.CDLL, archive: ctypes.c_void_p, logical_path: str):
    fh = ctypes.c_void_p()
    if not lib.SFileOpenFileEx(archive, logical_path.encode("utf-8"), 0, ctypes.byref(fh)):
        raise ArchiveError(f"SFileOpenFileEx failed for {logical_path}")
    try:
        yield fh
    finally:
        lib.SFileCloseFile(fh)


def read_all(lib: ctypes.CDLL, file_handle: ctypes.c_void_p) -> bytes:
    size = ctypes.c_uint32(0)
    lib.SFileGetFileSize(file_handle, ctypes.byref(size))
    buffer = ctypes.create_string_buffer(size.value)
    read = ctypes.c_uint32(0)
    if not lib.SFileReadFile(file_handle, buffer, size.value, ctypes.byref(read), None):
        # SFileReadFile returns false at EOF even on success; accept when all bytes read
        if read.value != size.value:
            raise ArchiveError("SFileReadFile short read")
    return buffer.raw[: read.value or size.value]
