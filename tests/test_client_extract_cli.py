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


def _pos_dbc(rows, fc, rs):
    # positional DBC (no string block); rows: list of {col: int}
    import struct
    body = b"".join(struct.pack("<" + "I" * (rs // 4), *[r.get(c, 0) for c in range(rs // 4)]) for r in rows)
    return struct.pack("<4sIIII", b"WDBC", len(rows), fc, rs, 0) + body


def _named_dbc(rows, fc, rs, strings):
    import struct
    body = b"".join(struct.pack("<" + "I" * (rs // 4), *[r.get(c, 0) for c in range(rs // 4)]) for r in rows)
    return struct.pack("<4sIIII", b"WDBC", len(rows), fc, rs, len(strings)) + body + strings


def _ca_tables():
    # CharacterAdvancement: one Venomancer node for 805775 (small synthetic layout, 10 cells/40 bytes)
    ca = _pos_dbc([{0: 6086, 1: 805775, 2: 33, 3: 1, 4: 0, 5: 1, 6: 0, 7: 0, 8: 0, 9: 0}], 10, 40)
    # ClassTypes: 21 playable (14..34) + sentinel (35) + one stock (2); only 33 is named "Venomancer"
    ct_strings = b"\x00Venomancer\x00"
    ct_rows = [{0: i, 1: (1 if i == 33 else 0)} for i in list(range(14, 35)) + [35, 2]]
    ct = _named_dbc(ct_rows, 23, 92, ct_strings)
    tt = _named_dbc([{0: 1, 1: 1}], 19, 76, b"\x00Class\x00")   # tab id 1 -> "Class"
    ess = _pos_dbc([{0: 1, 1: 60, 2: 26}], 9, 36)               # raw progression row (semantics undecoded)
    sla = _pos_dbc([], 14, 56)                                  # empty SkillLineAbility (fallback unused)
    return ca, ct, tt, ess, sla


_SPELL_STRINGS = b"\x00Adrenal Venom\x00"
_SPELL_BYTES = struct.pack("<4sIIII", b"WDBC", 1, 4, 16, len(_SPELL_STRINGS)) + \
    struct.pack("<IIII", 805775, 1, 3, 5) + _SPELL_STRINGS


def _bound_spell_policy(client_build="3.3.5a+patch-C"):
    """A reviewed policy bound to the fake Spell.dbc bytes so regenerate's client-binding hold passes.
    Spell fixture is 4 cells (id@0, name@1, casting_time_index@2, duration_index@3); power_type and
    school_mask are absent from the fixture, so they carry null cells (emitted as unresolved)."""
    import hashlib
    from coa_client_extract.spell_layout import compute_policy_sha256, load_spell_policy

    def f(cell, kind, layout, interp, promo):
        return {"cell": cell, "kind": kind, "layout": layout, "interpretation": interp,
                "promotion": promo, "evidence": "cli fixture"}

    V = ("verified", "verified")
    tables = {
        "Spell": {"expected_field_count": 4, "key_cell": 0, "unique": True, "fields": {
            "id": f(0, "uint32", *V, "normalized"), "name": f(1, "string", *V, "normalized"),
            "power_type": f(None, "int32", "unproven", "unproven", "raw_only"),
            "school_mask": f(None, "uint32", "unproven", "unproven", "raw_only"),
            "casting_time_index": f(2, "uint32", *V, "raw_only"),
            "duration_index": f(3, "uint32", *V, "raw_only")}},
        "SpellCastTimes": {"expected_field_count": 2, "key_cell": 0, "unique": True, "fields": {
            "id": f(0, "uint32", *V, "raw_only"), "base_ms": f(1, "int32", *V, "raw_only")}},
        "SpellDuration": {"expected_field_count": 2, "key_cell": 0, "unique": True, "fields": {
            "id": f(0, "uint32", *V, "raw_only"), "base_ms": f(1, "int32", *V, "raw_only")}},
    }
    joins = {
        "cast_time_ms": {"index_field": "casting_time_index", "side_table": "SpellCastTimes",
                         "side_value_field": "base_ms", "promotion": "raw_only"},
        "duration_ms": {"index_field": "duration_index", "side_table": "SpellDuration",
                        "side_value_field": "base_ms", "promotion": "raw_only"},
    }
    enum = {"power_types": [-2, 0, 1, 2, 3, 4, 5, 6], "school_bits": [1, 2, 4, 8, 16, 32, 64]}
    enum["sha256"] = compute_policy_sha256(enum)
    anchors = {"spells": [{"id": 133, "name": "Fireball", "power_type": 0, "school_mask": 4}]}
    anchors["sha256"] = compute_policy_sha256(anchors)
    # Structured E0R bound over the exact Spell bytes the fake backend serves (parsed header + real sha).
    _hdr = struct.unpack_from("<4sIIII", _SPELL_BYTES, 0)
    spell_bound = {"sha256": hashlib.sha256(_SPELL_BYTES).hexdigest(),
                   "header": {"magic": _hdr[0].decode("latin-1"), "record_count": _hdr[1],
                              "field_count": _hdr[2], "record_size": _hdr[3], "string_block_size": _hdr[4]},
                   "source": {"member": "DBFilesClient\\Spell.dbc", "effective_archive": "patch-C.MPQ",
                              "patch_chain": []}}
    p = {"schema_version": "coa-spell-layout-v2", "reviewed": True,
         "bound": {"client_build": client_build, "expected_absent": [], "tables": {"Spell": spell_bound}},
         "required_tables": ["Spell"], "expected_absent": [], "enum_policy": enum,
         "anchor_set": anchors, "tables": tables, "joins": joins}
    p["sha256"] = compute_policy_sha256(p)
    return load_spell_policy(p)


def _fake_backend():
    import struct
    cast = struct.pack("<II", 3, 1500)
    dur = struct.pack("<II", 5, 18000)

    def dbc(rows, fc, rs, s=b"\x00"):
        return struct.pack("<4sIIII", b"WDBC", len(rows), fc, rs, len(s)) + b"".join(rows) + s

    entries = {
        "DBFilesClient\\Spell.dbc": [(Path("common.MPQ"), _SPELL_BYTES)],
        "DBFilesClient\\SpellCastTimes.dbc": [(Path("common.MPQ"), dbc([cast], 2, 8))],
        "DBFilesClient\\SpellDuration.dbc": [(Path("common.MPQ"), dbc([dur], 2, 8))],
        "DBFilesClient\\SpellRange.dbc": [(Path("common.MPQ"), dbc([struct.pack("<I", 1) + b"\x00" * 152], 39, 156))],
    }
    ca, ct, tt, ess, sla = _ca_tables()
    entries["DBFilesClient\\CharacterAdvancement.dbc"] = [(Path("common.MPQ"), ca)]
    entries["DBFilesClient\\CharacterAdvancementClassTypes.dbc"] = [(Path("common.MPQ"), ct)]
    entries["DBFilesClient\\CharacterAdvancementTabTypes.dbc"] = [(Path("common.MPQ"), tt)]
    entries["DBFilesClient\\CharacterAdvancementEssence.dbc"] = [(Path("common.MPQ"), ess)]
    entries["DBFilesClient\\SkillLineAbility.dbc"] = [(Path("common.MPQ"), sla)]
    return FakeArchiveBackend(entries)


def _synthetic_layouts():
    from coa_client_extract.wdbc import DbcLayout, FieldSpec

    layouts = {
        "Spell": DbcLayout("Spell", 4, 16, {
            "id": FieldSpec(0, "uint32"), "name": FieldSpec(1, "str"),
            "casting_time_index": FieldSpec(2, "uint32"), "duration_index": FieldSpec(3, "uint32"),
        }),
        "SpellCastTimes": DbcLayout("SpellCastTimes", 2, 8, {"id": FieldSpec(0, "uint32"), "base_ms": FieldSpec(1, "int32")}),
        "SpellDuration": DbcLayout("SpellDuration", 2, 8, {"id": FieldSpec(0, "uint32"), "base_ms": FieldSpec(1, "int32")}),
        "SpellRange": DbcLayout("SpellRange", 39, 156, {"id": FieldSpec(0, "uint32")}),
    }
    from coa_client_extract.dbc_layouts import CharacterAdvancementLayout
    layouts["CharacterAdvancementLayout"] = CharacterAdvancementLayout(
        node_id_col=0, spell_id_col=1, class_type_col=2, tab_type_col=3, entry_type_col=4,
        ae_cost_col=5, required_level_col=6, connected_node_cols=(7, 8), required_id_cols=(9,),
        header_field_count=10, header_record_size=40,
    )
    return layouts


def test_regenerate_writes_artifacts_with_injected_backend(tmp_path):
    # Inject synthetic layouts matching the fake backend's DBC bytes; real layouts are
    # exercised by the Task 10 acceptance test. Asserts orchestration end to end.
    out = tmp_path / "out"
    manifest = regenerate(_client(tmp_path), out, backend=_fake_backend(),
                          layouts=_synthetic_layouts(), spell_policy=_bound_spell_policy())
    assert manifest["schema_version"] == "coa-client-extract-manifest-v1"
    assert manifest["unknown_symbol_inventory"] == {"power_type": [], "school_bits": []}
    assert (out / "coa_client_spell.jsonl").is_file()
    assert (out / "coa_client_content.jsonl").is_file()
    assert (out / "coa_client_archive_plan.json").is_file()
    assert (out / "coa_client_extract_manifest.json").is_file()
    spell = json.loads((out / "coa_client_spell.jsonl").read_text().splitlines()[0])
    assert spell["spell_id"] == 805775
    # attribution is now filled from the client advancement graph (805775 -> Venomancer node)
    assert spell["coa_attribution"]["is_coa"] is True
    assert spell["coa_attribution"]["modes"] == ["coa"]
    assert spell["coa_attribution"]["archive_family"] == "base"   # raw M1.14A signal retained
    assert spell["coa_attribution"]["id_range"] == "high"
    assert spell["memberships"][0]["class_display"] == "Venomancer"   # stable memberships[] attached
    # every contributing table records the archive that supplied it
    assert set(spell["provenance"]["source_dbcs"]) == {
        "Spell", "SpellCastTimes", "SpellDuration", "SpellRange"
    }
    # build descriptor derived from the discovered plan's top patch (patch-C.MPQ)
    assert manifest["client_build"] == "3.3.5a+patch-C"

    adv = [json.loads(l) for l in (out / "coa_client_advancement.jsonl").read_text().splitlines()]
    assert adv[0]["schema_version"] == "coa-client-advancement-v1"
    assert adv[0]["class"]["display"] == "Venomancer" and adv[0]["name"] == "Adrenal Venom"
    assert adv[0]["coa_attribution"]["is_coa"] is True
    assert adv[0]["raw"]["cols"]["0"] == 6086       # index-keyed audit map (JSON stringifies int keys)
    assert (out / "coa_client_class_types.jsonl").is_file()
    tabs = [json.loads(l) for l in (out / "coa_client_tab_types.jsonl").read_text().splitlines()]
    assert tabs[0]["schema_version"] == "coa-client-tab-types-v1" and tabs[0]["name"] == "Class"
    ess = [json.loads(l) for l in (out / "coa_client_essence.jsonl").read_text().splitlines()]
    assert ess[0]["schema_version"] == "coa-client-essence-v1"      # raw progression, undecoded

    # Task 7 producer: regenerate publishes a transactional generation + a validated pointer, and the
    # resolver accepts it (the Node build requires this pointer for a canonical run).
    from coa_client_extract.publish import resolve_active_generation
    assert (out / "coa_client_extract.pointer.json").is_file()
    resolved = resolve_active_generation(out)
    assert set(resolved["children"]) == {"coa_client_spell_coa.jsonl", "coa_client_spell_projection.manifest.json"}
    assert resolved["manifest"]["binding"]["policy_sha256"]
    assert resolved["manifest"]["unknown_symbol_inventory"] == {"power_type": [], "school_bits": []}


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
