from __future__ import annotations

from pathlib import Path

from .archive_backend import ExtractedMember
from . import stormlib_ctypes as sl


class StormLibBackend:
    name = "stormlib_ctypes"
    version = "coa-stormlib-v1"

    def __init__(self, stormlib_path: str | None = None):
        # Raises BackendUnavailable (fail closed) if the library cannot be loaded.
        self._lib = sl.load_stormlib(stormlib_path)

    def read_effective_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> ExtractedMember:
        data = sl.read_effective_member(self._lib, base_archive, patch_archives, logical_path)
        return ExtractedMember(
            logical_path=logical_path,
            data=data,
            base_archive=base_archive,
            patch_chain=(base_archive, *patch_archives),
            effective_archive=patch_archives[-1] if patch_archives else base_archive,
            backend_name=self.name,
            backend_version=self.version,
        )

    def has_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> bool:
        return sl.member_exists(self._lib, base_archive, patch_archives, logical_path)
