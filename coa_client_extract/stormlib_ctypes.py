from __future__ import annotations

import ctypes
import ctypes.util
import os
from contextlib import contextmanager

from .errors import ArchiveError, BackendUnavailable

_CANDIDATES = ("libstorm.so", "libstorm.so.9", "libStorm.dylib", "StormLib.dll")

# SFileInfoClass enum value for SFileGetFileInfo: the chain of archives that supply the
# open file, winner last (StormLib.h `SFileInfoPatchChain`). 40 archive-info classes precede it.
SFILE_INFO_PATCH_CHAIN = 40
SFILE_INVALID_SIZE = 0xFFFFFFFF

STORMLIB_FUNCTIONS = (
    "SFileOpenArchive", "SFileOpenPatchArchive", "SFileHasFile",
    "SFileOpenFileEx", "SFileGetFileSize", "SFileReadFile", "SFileGetFileInfo",
    "SFileCloseFile", "SFileCloseArchive",
)


def load_stormlib(explicit_path: str | None = None) -> ctypes.CDLL:
    # An explicitly configured path (--stormlib or STORMLIB_PATH) is honored strictly:
    # a failure to load there is a hard BackendUnavailable, never a silent fall-through
    # to auto-discovery. This keeps the fail-closed guarantee independent of what happens
    # to be installed on the machine.
    configured = explicit_path or os.environ.get("STORMLIB_PATH")
    if configured:
        try:
            lib = ctypes.CDLL(configured)
        except OSError as exc:
            raise BackendUnavailable(f"StormLib could not be loaded from {configured}: {exc}")
        _bind(lib)
        return lib

    tried: list[str] = []
    ordered: list[str] = []
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


def resolve_version(lib: ctypes.CDLL) -> str:
    """Best-effort identity of the loaded StormLib, for provenance pinning in the manifest.
    Returns the resolved shared-object filename; the soname carries the ABI major version
    (e.g. ``libstorm.so.9``). StormLib exposes no runtime version function, so the library
    identity is the strongest pin available at extraction time."""
    name = getattr(lib, "_name", None) or "unknown"
    try:
        real = os.path.realpath(name)
        if os.path.exists(real):
            name = real
    except OSError:
        pass
    return os.path.basename(name)


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
    lib.SFileGetFileInfo.argtypes = [h, ctypes.c_int, ctypes.c_void_p, dw, ctypes.POINTER(dw)]
    lib.SFileGetFileInfo.restype = b
    lib.SFileCloseFile.argtypes = [h]
    lib.SFileCloseFile.restype = b
    lib.SFileCloseArchive.argtypes = [h]
    lib.SFileCloseArchive.restype = b


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
    # SFileGetFileSize returns the low 32 bits of the size as its RETURN value; the
    # out-parameter receives the high 32 bits (for >4GB files). DBC/GameTable members are
    # always well under 4GB, so the return value is the size. (The prior code read the
    # high-dword out-param, which is always 0, and produced empty members.)
    high = ctypes.c_uint32(0)
    size = lib.SFileGetFileSize(file_handle, ctypes.byref(high))
    if size == SFILE_INVALID_SIZE:
        raise ArchiveError("SFileGetFileSize failed")
    if size == 0:
        return b""
    buffer = ctypes.create_string_buffer(size)
    read = ctypes.c_uint32(0)
    if not lib.SFileReadFile(file_handle, buffer, size, ctypes.byref(read), None):
        # SFileReadFile returns false at EOF even on success; accept when all bytes read
        if read.value != size:
            raise ArchiveError("SFileReadFile short read")
    return buffer.raw[: read.value or size]


def file_patch_chain(lib: ctypes.CDLL, file_handle: ctypes.c_void_p) -> list[str]:
    """Return the archive filesystem paths that supply the currently open file, winner
    last, as reported by StormLib's SFileInfoPatchChain. The chain is the set of archives
    whose bytes actually compose the effective member: for a complete override it is just
    the winning archive; for incremental patches it is base plus each applied patch.
    Returns an empty list when StormLib cannot report a chain."""
    dw = ctypes.c_uint32
    need = dw(0)
    # First call with a null buffer to learn the required byte length.
    lib.SFileGetFileInfo(file_handle, SFILE_INFO_PATCH_CHAIN, None, 0, ctypes.byref(need))
    if not need.value:
        return []
    buffer = ctypes.create_string_buffer(need.value)
    if not lib.SFileGetFileInfo(
        file_handle, SFILE_INFO_PATCH_CHAIN, buffer, need.value, ctypes.byref(need)
    ):
        return []
    # The info class returns a double-null-terminated list of NUL-separated paths.
    return [part.decode("utf-8", "replace") for part in buffer.raw.split(b"\x00") if part]


def open_patched_handle(lib, base_path, patch_paths):
    """Open the base archive and attach each patch in load order, returning the handle. The caller owns
    the handle and MUST close_handle() it. Opening a 50+-archive chain is the dominant cost of a read
    (~1.5 min on the real client), so callers that read many members should open ONCE and reuse."""
    handle = ctypes.c_void_p()
    if not lib.SFileOpenArchive(str(base_path).encode("utf-8"), 0, 0x00000100, ctypes.byref(handle)):
        raise ArchiveError(f"SFileOpenArchive failed for {base_path}")
    for patch in patch_paths:
        # StormLib returns false for a patch that does not apply to this base; skip it.
        lib.SFileOpenPatchArchive(handle, str(patch).encode("utf-8"), b"", 0)
    return handle


def close_handle(lib, handle):
    lib.SFileCloseArchive(handle)


@contextmanager
def open_patched_archive(lib, base_path, patch_paths):
    """Open the base archive and attach each patch in load order. Always closes the
    archive handle on exit, even if a patch attach or a read raises."""
    handle = open_patched_handle(lib, base_path, patch_paths)
    try:
        yield handle
    finally:
        close_handle(lib, handle)


def read_member_with_handle(lib, handle, logical_path):
    """Read (effective bytes, participating archive paths) for logical_path from an already-open patched
    archive handle. Reusing one handle across many reads avoids re-attaching the whole chain each call."""
    if not lib.SFileHasFile(handle, logical_path.encode("utf-8")):
        raise ArchiveError(f"{logical_path}: not found in patched archive chain")
    with open_file(lib, handle, logical_path) as fh:
        # Query the chain while the file handle is still open.
        data = read_all(lib, fh)
        chain = file_patch_chain(lib, fh)
        return data, chain


def member_exists_with_handle(lib, handle, logical_path):
    return bool(lib.SFileHasFile(handle, logical_path.encode("utf-8")))


def read_effective_member(lib, base_path, patch_paths, logical_path):
    """Return (effective bytes, participating archive paths) for logical_path across the
    patched archive chain. The chain is StormLib's own report (winner last), not the
    attach order, so it reflects which archives actually supplied the winning bytes."""
    with open_patched_archive(lib, base_path, patch_paths) as handle:
        return read_member_with_handle(lib, handle, logical_path)


def member_exists(lib, base_path, patch_paths, logical_path):
    with open_patched_archive(lib, base_path, patch_paths) as handle:
        return member_exists_with_handle(lib, handle, logical_path)
