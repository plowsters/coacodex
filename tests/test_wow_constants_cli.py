import hashlib
import json
import struct
from pathlib import Path

import pytest

from coa_client_extract.archive_backend import FakeArchiveBackend
from coa_client_extract.cli import main, wow_constants_command
from coa_client_extract.errors import BackendUnavailable


def _client(tmp_path: Path) -> Path:
    data = tmp_path / "Data"
    data.mkdir()
    for name in ("common.MPQ", "patch.MPQ", "patch-M.MPQ"):
        (data / name).write_bytes(b"MPQ\x1a")
    return data


def _implicit(values):
    return struct.pack("<4sIIII", b"WDBC", len(values), 1, 4, 0) + b"".join(
        struct.pack("<f", v) for v in values)


def _chr_classes(pairs):
    strings = b"\x00" + b"".join(f"C{i}".encode() + b"\x00" for i, _ in pairs)
    rows, off = [], 1
    for i, p in pairs:
        cells = [0] * 60
        cells[0], cells[2], cells[5] = i, p, off
        off += len(f"C{i}") + 1
        rows.append(struct.pack("<" + "I" * 60, *cells))
    return struct.pack("<4sIIII", b"WDBC", len(pairs), 60, 240, len(strings)) + b"".join(rows) + strings


def make_backend(**overrides):
    ids = [(i, 0) for i in [1, 2, 3, 4, 5, 6, 7, 8, 9, 11]]
    e = {
        "DBFilesClient\\gtCombatRatings.dbc": [(Path("patch-M.MPQ"), _implicit([float(i) for i in range(3200)]))],
        "DBFilesClient\\gtOCTClassCombatRatingScalar.dbc": [(Path("patch-M.MPQ"), _implicit([1.0] * (12 * 32)))],
        "DBFilesClient\\gtChanceToMeleeCrit.dbc": [(Path("patch-M.MPQ"), _implicit([0.05] * (12 * 100)))],
        "DBFilesClient\\gtChanceToMeleeCritBase.dbc": [(Path("patch-M.MPQ"), _implicit([0.01] * 12))],
        "DBFilesClient\\gtChanceToSpellCrit.dbc": [(Path("patch-M.MPQ"), _implicit([0.05] * (12 * 100)))],
        "DBFilesClient\\gtChanceToSpellCritBase.dbc": [(Path("patch-M.MPQ"), _implicit([0.01] * 12))],
        "DBFilesClient\\gtRegenMPPerSpt.dbc": [(Path("patch-M.MPQ"), _implicit([0.1] * (12 * 100)))],
        "DBFilesClient\\ChrClasses.dbc": [(Path("patch-M.MPQ"), _chr_classes(ids))],
    }
    for k, v in overrides.items():
        key = "DBFilesClient\\" + k + ".dbc"
        if v is None:
            e.pop(key, None)
        else:
            e[key] = [(Path("patch-M.MPQ"), v)]
    return FakeArchiveBackend(e)


def _plan(client_root):
    from coa_client_extract.archive_plan import discover_plan
    return discover_plan(client_root)


def test_recon_only_writes_report_not_snapshot(tmp_path):
    out = tmp_path / "out"
    report = wow_constants_command(_client(tmp_path), out, backend=make_backend(), recon_only=True)
    assert report["class_axis"]["comparison"] == "exact"
    assert (out / "coa_wow_constants_recon.json").is_file()
    assert not (out / "coa_wow_constants.json").exists()


def test_cli_recon_only_fails_closed_without_stormlib(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise BackendUnavailable("StormLib not found")
    monkeypatch.setattr("coa_client_extract.stormlib_backend.StormLibBackend", boom, raising=False)
    rc = main(["wow-constants", "--client-root", str(_client(tmp_path)),
               "--out", str(tmp_path / "o"), "--recon-only"])
    assert rc == 2


def test_canonical_extract_writes_snapshot_and_manifest(tmp_path):
    from coa_client_extract.wow_constants import run_extract
    client = _client(tmp_path)
    out = tmp_path / "out"
    manifest = run_extract(client, out, backend=make_backend(), plan=_plan(client),
                           extractor_commit="c0ffee", client_build="3.3.5a+patch-M")
    snap = json.loads((out / "coa_wow_constants.json").read_text())
    assert snap["schema_version"] == "coa-wow-constants-v1"
    assert snap["class_axis"]["comparison"] == "exact"
    ct = snap["game_tables"]["combat_ratings"]
    assert next(e for e in ct["entries"] if e["rating_id"] == 6 and e["level"] == 60)["value"] == 659.0
    assert ct["reference_comparison"]["checked"] >= 1
    assert manifest["class_context_resolution"] == "unproven"


def test_missing_required_table_fails_closed(tmp_path):
    from coa_client_extract.wow_constants import run_extract, MissingRequiredTable
    client = _client(tmp_path)
    b = make_backend(gtChanceToMeleeCrit=None)
    with pytest.raises(MissingRequiredTable):
        run_extract(client, tmp_path / "o", backend=b, plan=_plan(client),
                    extractor_commit="x", client_build="y")
    assert not (tmp_path / "o" / "coa_wow_constants.json").exists()


def test_strict_drift_produces_no_output(tmp_path):
    from coa_client_extract.wow_constants import run_extract
    from coa_client_extract.errors import DbcDriftError
    client = _client(tmp_path)
    bad = struct.pack("<4sIIII", b"WDBC", 1, 2, 8, 0) + struct.pack("<ff", 1.0, 2.0)
    b = make_backend(gtCombatRatings=bad)
    with pytest.raises(DbcDriftError):
        run_extract(client, tmp_path / "o", backend=b, plan=_plan(client),
                    extractor_commit="x", client_build="y")
    assert not (tmp_path / "o" / "coa_wow_constants.json").exists()


def test_non_exact_axis_requires_adjudication(tmp_path):
    from coa_client_extract.wow_constants import run_extract, ClassAxisAdjudicationRequired
    client = _client(tmp_path)
    ids = [(i, 0) for i in [1, 2, 3, 4, 5, 6, 7, 8, 11]]           # drop class 9 -> "changed"
    b = make_backend(ChrClasses=_chr_classes(ids))
    with pytest.raises(ClassAxisAdjudicationRequired):
        run_extract(client, tmp_path / "o", backend=b, plan=_plan(client),
                    extractor_commit="x", client_build="y")
    adj = tmp_path / "adj.json"
    adj.write_text(json.dumps({"schema": "wow-class-axis-adjudication-v1", "accepted_comparison": "changed",
                               "observed_client_ids": [1, 2, 3, 4, 5, 6, 7, 8, 11],
                               "rationale": "test", "version": "v1"}))
    manifest = run_extract(client, tmp_path / "o2", backend=b, plan=_plan(client),
                           extractor_commit="x", client_build="y", adjudication_path=str(adj))
    assert manifest["authored_inputs"]["class_axis_adjudication"]["sha256"] == \
        hashlib.sha256(adj.read_bytes()).hexdigest()
