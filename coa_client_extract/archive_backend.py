from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .errors import ArchiveError


@dataclass(frozen=True)
class ExtractedMember:
    logical_path: str
    data: bytes
    base_archive: Path
    patch_chain: tuple[Path, ...]
    effective_archive: Path
    backend_name: str
    backend_version: str


@runtime_checkable
class ArchiveBackend(Protocol):
    def read_effective_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> ExtractedMember: ...

    def has_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> bool: ...


class FakeArchiveBackend:
    """In-memory ArchiveBackend for tests. No native dependency."""

    name = "fake"
    version = "fake-v1"

    def __init__(self, entries: dict[str, list[tuple[Path, bytes | None]]]):
        self._entries = entries

    def _resolve(self, logical_path: str):
        history = self._entries.get(logical_path, [])
        chain: list[Path] = []
        winner: tuple[Path, bytes | None] | None = None
        for archive, payload in history:
            chain.append(archive)
            winner = (archive, payload)
        return chain, winner

    def read_effective_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> ExtractedMember:
        chain, winner = self._resolve(logical_path)
        if winner is None or winner[1] is None:
            raise ArchiveError(f"{logical_path}: not present in effective archive set")
        return ExtractedMember(
            logical_path=logical_path,
            data=winner[1],
            base_archive=base_archive,
            patch_chain=tuple(chain),
            effective_archive=winner[0],
            backend_name=self.name,
            backend_version=self.version,
        )

    def has_file(
        self, base_archive: Path, patch_archives: tuple[Path, ...], logical_path: str
    ) -> bool:
        _, winner = self._resolve(logical_path)
        return winner is not None and winner[1] is not None
