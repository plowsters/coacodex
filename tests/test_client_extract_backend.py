from pathlib import Path

import pytest

from coa_client_extract.archive_backend import ExtractedMember, FakeArchiveBackend
from coa_client_extract.errors import ArchiveError

BASE = Path("common.MPQ")
P1 = Path("patch.MPQ")
PC = Path("patch-C.MPQ")


def _backend():
    return FakeArchiveBackend(
        {
            "DBFilesClient\\Spell.dbc": [
                (BASE, b"base-bytes"),
                (PC, b"coa-bytes"),
            ],
            "DBFilesClient\\Deleted.dbc": [
                (BASE, b"present"),
                (PC, None),  # deletion marker
            ],
        }
    )


def test_effective_file_wins_from_latest_patch():
    member = _backend().read_effective_file(BASE, (P1, PC), "DBFilesClient\\Spell.dbc")
    assert isinstance(member, ExtractedMember)
    assert member.data == b"coa-bytes"
    assert member.effective_archive == PC
    assert member.patch_chain == (BASE, PC)
    assert member.base_archive == BASE
    assert member.backend_name == "fake"


def test_deletion_marker_raises_archive_error():
    with pytest.raises(ArchiveError):
        _backend().read_effective_file(BASE, (P1, PC), "DBFilesClient\\Deleted.dbc")


def test_has_file_reflects_deletion():
    backend = _backend()
    assert backend.has_file(BASE, (P1, PC), "DBFilesClient\\Spell.dbc") is True
    assert backend.has_file(BASE, (P1, PC), "DBFilesClient\\Deleted.dbc") is False
