from __future__ import annotations

from pathlib import Path

from .archive_backend import ExtractedMember
from .errors import ArchiveError
from . import stormlib_ctypes as sl


class StormLibBackend:
    name = "stormlib_ctypes"
    version = "coa-stormlib-v1"

    def __init__(self, stormlib_path: str | None = None):
        # Raises BackendUnavailable (fail closed) if the library cannot be loaded.
        self._lib = sl.load_stormlib(stormlib_path)

    def _open_chain(self, base_archive: Path, patch_archives: tuple[Path, ...]):
        cm = sl.open_archive(self._lib, str(base_archive))
        handle = cm.__enter__()
        for patch in patch_archives:
            if not self._lib.SFileOpenPatchArchive(handle, str(patch).encode("utf-8"), b"", 0):
                # A patch that does not apply to this base is skipped by StormLib returning false;
                # only raise if none applied and the file is later missing.
                continue
        return cm, handle

    def read_effective_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> ExtractedMember:
        cm, handle = self._open_chain(base_archive, patch_archives)
        try:
            if not self._lib.SFileHasFile(handle, logical_path.encode("utf-8")):
                raise ArchiveError(f"{logical_path}: not found in patched archive chain")
            with sl.open_file(self._lib, handle, logical_path) as fh:
                data = sl.read_all(self._lib, fh)
            # Provenance: StormLib resolves the effective bytes across the attached chain.
            # The full participating chain is the attached patch set plus the base.
            chain = (base_archive, *patch_archives)
            return ExtractedMember(
                logical_path=logical_path,
                data=data,
                base_archive=base_archive,
                patch_chain=chain,
                effective_archive=patch_archives[-1] if patch_archives else base_archive,
                backend_name=self.name,
                backend_version=self.version,
            )
        finally:
            cm.__exit__(None, None, None)

    def has_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> bool:
        cm, handle = self._open_chain(base_archive, patch_archives)
        try:
            return bool(self._lib.SFileHasFile(handle, logical_path.encode("utf-8")))
        finally:
            cm.__exit__(None, None, None)
