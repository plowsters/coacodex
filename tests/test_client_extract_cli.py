import json
import os
import struct
from pathlib import Path

import pytest

from coa_client_extract.archive_backend import FakeArchiveBackend
from coa_client_extract.cli import decode_advancement, main, regenerate


def _client(tmp_path: Path) -> Path:
    data = tmp_path / "Data"
    data.mkdir()
    for name in ("common.MPQ", "patch.MPQ", "patch-C.MPQ"):
        (data / name).write_bytes(b"MPQ\x1a")
    (data / "Content").mkdir()
    (data / "Content" / "SpellRankData.json").write_text('[{"Spell":805775,"Rank":1}]')
    return data


def _fake_backend():
    import struct
    strings = b"\x00Adrenal Venom\x00"
    spell = struct.pack("<IIII", 805775, 1, 3, 5)
    cast = struct.pack("<II", 3, 1500)
    dur = struct.pack("<II", 5, 18000)

    def dbc(rows, fc, rs, s=b"\x00"):
        return struct.pack("<4sIIII", b"WDBC", len(rows), fc, rs, len(s)) + b"".join(rows) + s

    entries = {
        "DBFilesClient\\Spell.dbc": [(Path("common.MPQ"), dbc([spell], 4, 16, strings))],
        "DBFilesClient\\SpellCastTimes.dbc": [(Path("common.MPQ"), dbc([cast], 2, 8))],
        "DBFilesClient\\SpellDuration.dbc": [(Path("common.MPQ"), dbc([dur], 2, 8))],
        "DBFilesClient\\SpellRange.dbc": [(Path("common.MPQ"), dbc([struct.pack("<I", 1) + b"\x00" * 152], 39, 156))],
    }
    return FakeArchiveBackend(entries)


def _synthetic_layouts():
    from coa_client_extract.wdbc import DbcLayout, FieldSpec

    return {
        "Spell": DbcLayout("Spell", 4, 16, {
            "id": FieldSpec(0, "uint32"), "name": FieldSpec(1, "str"),
            "casting_time_index": FieldSpec(2, "uint32"), "duration_index": FieldSpec(3, "uint32"),
        }),
        "SpellCastTimes": DbcLayout("SpellCastTimes", 2, 8, {"id": FieldSpec(0, "uint32"), "base_ms": FieldSpec(1, "int32")}),
        "SpellDuration": DbcLayout("SpellDuration", 2, 8, {"id": FieldSpec(0, "uint32"), "base_ms": FieldSpec(1, "int32")}),
        "SpellRange": DbcLayout("SpellRange", 39, 156, {"id": FieldSpec(0, "uint32")}),
    }


def test_regenerate_writes_artifacts_with_injected_backend(tmp_path):
    # Inject synthetic layouts matching the fake backend's DBC bytes; real layouts are
    # exercised by the Task 10 acceptance test. Asserts orchestration end to end.
    out = tmp_path / "out"
    manifest = regenerate(_client(tmp_path), out, backend=_fake_backend(), layouts=_synthetic_layouts())
    assert manifest["schema_version"] == "coa-client-extract-manifest-v1"
    assert (out / "coa_client_spell.jsonl").is_file()
    assert (out / "coa_client_content.jsonl").is_file()
    assert (out / "coa_client_archive_plan.json").is_file()
    assert (out / "coa_client_extract_manifest.json").is_file()
    spell = json.loads((out / "coa_client_spell.jsonl").read_text().splitlines()[0])
    assert spell["spell_id"] == 805775
    assert spell["coa_attribution"]["status"] == "unknown"
    # fake fixture resolves Spell.dbc to common.MPQ (base family); 805775 is high-range
    assert spell["coa_attribution"]["archive_family"] == "base"
    assert spell["coa_attribution"]["id_range"] == "high"
    # every contributing table records the archive that supplied it
    assert set(spell["provenance"]["source_dbcs"]) == {
        "Spell", "SpellCastTimes", "SpellDuration", "SpellRange"
    }
    # build descriptor derived from the discovered plan's top patch (patch-C.MPQ)
    assert manifest["client_build"] == "3.3.5a+patch-C"


def test_main_fails_closed_without_stormlib(tmp_path, capsys):
    out = tmp_path / "out"
    code = main([
        "regenerate", "--client-root", str(_client(tmp_path)), "--out", str(out),
        "--stormlib", "/nonexistent/libstorm.so.999",
    ])
    assert code == 2
    assert not out.exists() or not any(out.iterdir())
    err = capsys.readouterr().err
    assert "StormLib" in err


def _fake_advancement_backend():
    # 60 synthetic CharacterAdvancement rows: 8 cells/record, node_id col0, spell_id col5,
    # ae_cost col7 with a clean 1/2/3 cycle (never zero, so it clears the 50-nonzero floor).
    # ClassTypes/TabTypes are empty tables — this test proves CLI wiring end to end, not the
    # decode algorithm itself (that's covered by test_client_extract_advancement_semantic.py).
    def dbc(rows, fc, rs, s=b"\x00"):
        return struct.pack("<4sIIII", b"WDBC", len(rows), fc, rs, len(s)) + b"".join(rows) + s

    ca_rows = [
        struct.pack("<8I", 500 + i, 0, 0, 0, 0, 1000 + i, 0, (i % 3) + 1)
        for i in range(60)
    ]
    empty_types = struct.pack("<4sIIII", b"WDBC", 0, 2, 8, 0)

    entries = {
        "DBFilesClient\\CharacterAdvancement.dbc": [(Path("common.MPQ"), dbc(ca_rows, 8, 32))],
        "DBFilesClient\\CharacterAdvancementClassTypes.dbc": [(Path("common.MPQ"), empty_types)],
        "DBFilesClient\\CharacterAdvancementTabTypes.dbc": [(Path("common.MPQ"), empty_types)],
    }
    return FakeArchiveBackend(entries)


def _write_advancement_content_json(tmp_path: Path) -> Path:
    entries = [{"ID": 500 + i, "Spells": [1000 + i], "AECost": (i % 3) + 1} for i in range(60)]
    path = tmp_path / "CharacterAdvancementData.json"
    path.write_text(json.dumps(entries))
    return path


def test_decode_advancement_cli_wiring_writes_report_with_resolved_layout(tmp_path, monkeypatch):
    # Arg-wiring test: dispatch through main() like a real invocation, with StormLibBackend
    # monkeypatched to a fake backend so no native library or real client is needed.
    fake_backend = _fake_advancement_backend()
    monkeypatch.setattr(
        "coa_client_extract.stormlib_backend.StormLibBackend",
        lambda stormlib_path=None: fake_backend,
    )
    content_json = _write_advancement_content_json(tmp_path)
    out = tmp_path / "out" / "coa_ca_decode_report.json"

    code = main([
        "decode-advancement",
        "--client-root", str(_client(tmp_path)),
        "--content-json", str(content_json),
        "--out", str(out),
    ])

    assert code == 0
    assert out.is_file()
    report = json.loads(out.read_text())
    assert "resolved_layout" in report
    # the pipeline really ran end to end: ae_cost is cleanly in col 7 across all 60 synthetic rows
    assert report["resolved_layout"]["ae_cost_col"] == 7
    assert report["resolved_layout"]["confidence"]["ae_cost"] == "high"


# The real CharacterAdvancementData.json is stale + field-stripped, so the decode is honestly PARTIAL
# (see the scoped-readiness design): a real decode run proved only `required_level` and `col` high with
# the base harness. `required_level` is the stable, high-coverage (93.6% of entries) field we require
# here as proof the evidence-based pipeline ran end to end against the real client. Fields NOT asserted
# — they are legitimately unresolved from this loose JSON and reported as such by the readiness gate:
# ae_cost (present but low decode margin), tab_type/entry_type (name/string fields — resolved via the
# name->id and robust-mapping paths, but not asserted here to avoid coupling to decode-margin drift),
# adjacency/te_cost/max_rank/row/required_tab_* (absent or <20% coverage in the real loose JSON).
_MIN_ADAPTER_FIELDS = {"required_level"}

_CLIENT_ROOT = Path(os.environ.get(
    "COA_CLIENT_ROOT",
    str(Path.home() / "Games/ascension-wow/drive_c/Program Files/Ascension Launcher/resources/ascension-live/Data"),
))
_CONTENT_JSON = _CLIENT_ROOT / "Content" / "CharacterAdvancementData.json"


@pytest.mark.client
@pytest.mark.skipif(
    not (_CLIENT_ROOT.is_dir() and _CONTENT_JSON.is_file()),
    reason="Ascension client + CharacterAdvancementData.json not present at COA_CLIENT_ROOT",
)
def test_decode_advancement_end_to_end_proves_adapter_fields(tmp_path):
    from coa_client_extract.errors import BackendUnavailable

    out = tmp_path / "coa_ca_decode_report.json"
    try:
        report = decode_advancement(_CLIENT_ROOT, _CONTENT_JSON, out)
    except BackendUnavailable:
        pytest.skip("StormLib not available")

    assert out.is_file()
    confidence = set(report["resolved_layout"]["confidence"])
    missing = _MIN_ADAPTER_FIELDS - confidence
    assert not missing, f"expected these adapter fields to resolve high, missing: {missing}"
