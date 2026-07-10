from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .archive_backend import ArchiveBackend
from .errors import ArchiveError

ORDERING_RULE = "coa-archive-order-v1"
_BASE = ("common", "common-2", "expansion", "lichking")
_NUMERIC_PATCH = re.compile(r"^patch(-\d+)?$", re.IGNORECASE)
_COA_PATCH = re.compile(r"^patch-C[A-Z]*$", re.IGNORECASE)   # patch-C, patch-CA … patch-CZZ
_REBORN_PATCH = re.compile(r"^patch-W[A-Z]*$", re.IGNORECASE)  # Warcraft Reborn/Bronzebeard
_ANY_PATCH = re.compile(r"^patch(-[0-9A-Za-z]+)?$", re.IGNORECASE)


@dataclass(frozen=True)
class ArchivePlan:
    client_root: Path
    base_archives: tuple[Path, ...]
    patch_archives: tuple[Path, ...]
    excluded: dict[str, tuple[Path, ...]]
    ordering_rule: str = ORDERING_RULE

    def to_dict(self) -> dict:
        return {
            "schema_version": "coa-client-archive-plan-v1",
            "client_root": str(self.client_root),
            "ordering_rule": self.ordering_rule,
            "base_archives": [p.name for p in self.base_archives],
            "patch_archives": [p.name for p in self.patch_archives],
            "excluded": {k: [p.name for p in v] for k, v in self.excluded.items()},
        }


def _patch_sort_key(name: str) -> tuple:
    stem = name.rsplit(".", 1)[0]
    if _NUMERIC_PATCH.match(stem):
        # group 0: base patches — plain "patch" first, then patch-2, patch-3
        parts = stem.split("-")
        num = int(parts[1]) if len(parts) > 1 else 0
        return (0, num, "")
    if _COA_PATCH.match(stem):
        # group 2: CoA family loads last (highest priority) — C, CA, CB … CZ < CZZ
        letters = stem.split("-", 1)[1][1:]  # drop the leading 'C'
        return (2, len(letters), letters.upper())
    # group 1: other Ascension patches (patch-A, patch-B, patch-I, patch-M, …)
    suffix = stem.split("-", 1)[1] if "-" in stem else ""
    return (1, len(suffix), suffix.upper())


def discover_plan(client_root: Path) -> ArchivePlan:
    archives = sorted(p for p in client_root.glob("*.MPQ"))
    archives += sorted(p for p in client_root.glob("*.mpq"))
    by_name = {p.name.rsplit(".", 1)[0].lower(): p for p in archives}

    base = tuple(by_name[n] for n in _BASE if n in by_name)
    patches: list[Path] = []
    reborn: list[Path] = []
    for p in archives:
        stem = p.name.rsplit(".", 1)[0]
        if stem.lower() in _BASE:
            continue
        if _REBORN_PATCH.match(stem):
            reborn.append(p)  # Warcraft Reborn — excluded from the CoA chain
        elif _ANY_PATCH.match(stem):
            patches.append(p)  # base Ascension + CoA patches load together; attribution is M1.14B
    patches.sort(key=lambda p: _patch_sort_key(p.name))

    area52 = tuple(sorted((client_root / "area-52").glob("*.MPQ"))) if (client_root / "area-52").is_dir() else ()

    return ArchivePlan(
        client_root=client_root,
        base_archives=base,
        patch_archives=tuple(patches),
        excluded={"area52": area52, "reborn": tuple(reborn)},
    )


def validate_ordering(
    plan: ArchivePlan, backend: ArchiveBackend, logical_path: str, expected_effective: Path
) -> None:
    member = backend.read_effective_file(plan.base_archives[0], plan.patch_archives, logical_path)
    if member.effective_archive.name != expected_effective.name:
        raise ArchiveError(
            f"archive-plan ordering mismatch for {logical_path}: resolved "
            f"{member.effective_archive.name}, expected {expected_effective.name}"
        )
