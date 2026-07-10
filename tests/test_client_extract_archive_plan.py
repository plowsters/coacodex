from pathlib import Path

import pytest

from coa_client_extract.archive_backend import FakeArchiveBackend
from coa_client_extract.archive_plan import ArchivePlan, discover_plan, validate_ordering
from coa_client_extract.errors import ArchiveError

FAMILY = [
    "common.MPQ", "common-2.MPQ", "expansion.MPQ", "lichking.MPQ",
    "patch.MPQ", "patch-2.MPQ", "patch-3.MPQ",
    "patch-A.MPQ", "patch-C.MPQ", "patch-CA.MPQ", "patch-CZZ.MPQ",
    "patch-WA.MPQ",
]


def _make_client(tmp_path: Path) -> Path:
    data = tmp_path / "Data"
    data.mkdir()
    for name in FAMILY:
        (data / name).write_bytes(b"MPQ\x1a")
    area = data / "area-52"
    area.mkdir()
    (area / "patch-D.MPQ").write_bytes(b"MPQ\x1a")
    return data


def test_discover_plan_partitions_families(tmp_path):
    plan = discover_plan(_make_client(tmp_path))
    names = {p.name for p in plan.patch_archives}
    assert "patch-C.MPQ" in names and "patch-CZZ.MPQ" in names
    assert "patch-WA.MPQ" not in names  # Reborn excluded
    assert all("patch-D.MPQ" != p.name for p in plan.patch_archives)  # Area-52 excluded
    assert {p.name for p in plan.base_archives} == {
        "common.MPQ", "common-2.MPQ", "expansion.MPQ", "lichking.MPQ"
    }
    assert "reborn" in plan.excluded and "area52" in plan.excluded


def test_patch_c_family_orders_after_numeric_patches(tmp_path):
    plan = discover_plan(_make_client(tmp_path))
    order = [p.name for p in plan.patch_archives]
    assert order.index("patch.MPQ") < order.index("patch-C.MPQ")
    assert order.index("patch-C.MPQ") < order.index("patch-CA.MPQ")
    assert order.index("patch-CA.MPQ") < order.index("patch-CZZ.MPQ")


def test_plan_to_dict_shape(tmp_path):
    plan = discover_plan(_make_client(tmp_path))
    doc = plan.to_dict()
    assert doc["schema_version"] == "coa-client-archive-plan-v1"
    assert doc["ordering_rule"] == "coa-archive-order-v1"
    assert isinstance(doc["patch_archives"], list)


def test_validate_ordering_detects_wrong_effective(tmp_path):
    plan = discover_plan(_make_client(tmp_path))
    backend = FakeArchiveBackend(
        {"DBFilesClient\\Spell.dbc": [(Path("common.MPQ"), b"a"), (Path("patch-CA.MPQ"), b"b")]}
    )
    validate_ordering(plan, backend, "DBFilesClient\\Spell.dbc", Path("patch-CA.MPQ"))
    with pytest.raises(ArchiveError):
        validate_ordering(plan, backend, "DBFilesClient\\Spell.dbc", Path("patch-C.MPQ"))
