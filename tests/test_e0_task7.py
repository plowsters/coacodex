import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from coa_client_extract.archive_backend import FakeArchiveBackend
from coa_client_extract.cli import main, mechanics_recon_command, _RECON_EXIT
from coa_client_extract.publish import GenerationWriter, resolve_active_generation
from coa_client_extract.spell_layout import compute_policy_sha256, load_spell_policy

REPO = Path(__file__).resolve().parents[1]

# --- recon-command fixtures (234-cell Spell like the real client, anchors at 41/225/136, cast idx 28) ---
ANCHORS = [(133, 0, 4, "Fireball"), (116, 0, 16, "Frostbolt"),
           (78, 1, 1, "Heroic Strike"), (585, 0, 2, "Smite")]


def _spell_dbc(rows):
    strings, off, bodies = b"\x00", 1, []
    for sid, pt, sm, name, ct in rows:
        cells = [0] * 234
        cells[0], cells[41], cells[225], cells[136], cells[28] = sid, pt & 0xFFFFFFFF, sm, off, ct
        strings += name.encode() + b"\x00"; off += len(name) + 1
        bodies.append(struct.pack("<234I", *cells))
    return struct.pack("<4sIIII", b"WDBC", len(rows), 234, 936, len(strings)) + b"".join(bodies) + strings


def _side(ids):
    body = b"".join(struct.pack("<II", i, i * 100) for i in ids)
    return struct.pack("<4sIIII", b"WDBC", len(ids), 2, 8, 1) + body + b"\x00"


def _recon_policy(*, reviewed):
    def f(cell, kind, layout="verified", interp="verified", promo="raw_only"):
        return {"cell": cell, "kind": kind, "layout": layout, "interpretation": interp,
                "promotion": promo, "evidence": "fx"}
    enum = {"power_types": [-2, 0, 1, 2, 3, 4, 5, 6], "school_bits": [1, 2, 4, 8, 16, 32, 64]}
    enum["sha256"] = compute_policy_sha256(enum)
    spells = [{"id": i, "name": n, "power_type": p, "school_mask": s} for (i, p, s, n) in ANCHORS]
    anchor = {"spells": spells}
    anchor["sha256"] = compute_policy_sha256(anchor)
    p = {"schema_version": "coa-spell-layout-v2", "reviewed": reviewed, "bound": None,
         "required_tables": ["Spell", "SpellCastTimes"], "expected_absent": ["SpellEffect"],
         "enum_policy": enum, "anchor_set": anchor,
         "tables": {
             "Spell": {"expected_field_count": 234, "key_cell": 0, "unique": True, "fields": {
                 "id": f(0, "uint32", promo="normalized"),
                 "name": f(136, "string", promo="normalized"),
                 "power_type": f(41, "int32", promo="normalized"),
                 "school_mask": f(225, "uint32", promo="normalized"),
                 "casting_time_index": f(28, "uint32")}},
             "SpellCastTimes": {"expected_field_count": 2, "key_cell": 0, "unique": True, "fields": {
                 "id": f(0, "uint32"), "base_ms": f(1, "int32")}}},
         "joins": {"cast_time_ms": {"index_field": "casting_time_index", "side_table": "SpellCastTimes",
                                    "side_value_field": "base_ms", "promotion": "raw_only"}}}
    p["sha256"] = compute_policy_sha256(p)
    return load_spell_policy(p)


def _client_with_backend(tmp_path):
    data = tmp_path / "Data"
    data.mkdir()
    for name in ("common.MPQ", "patch-C.MPQ"):
        (data / name).write_bytes(b"MPQ\x1a")
    entries = {
        "DBFilesClient\\Spell.dbc": [(Path("common.MPQ"), _spell_dbc(ANCHORS_WITH_CT))],
        "DBFilesClient\\SpellCastTimes.dbc": [(Path("common.MPQ"), _side((0, 5, 71)))],
    }
    return data, FakeArchiveBackend(entries)


ANCHORS_WITH_CT = [(133, 0, 4, "Fireball", 5), (116, 0, 16, "Frostbolt", 71),
                   (78, 1, 1, "Heroic Strike", 0), (585, 0, 2, "Smite", 5)]


def test_mechanics_recon_command_review_required_and_writes_report(tmp_path):
    client, backend = _client_with_backend(tmp_path)
    out = tmp_path / "out"
    report = mechanics_recon_command(client, out, backend=backend, spell_policy=_recon_policy(reviewed=False))
    assert report["status"] == "review_required"
    assert (out / "coa_spell_mechanics_recon.json").is_file()
    assert _RECON_EXIT[report["status"]] == 4          # CLI maps review_required -> exit 4


def test_mechanics_recon_exit_code_mapping():
    assert _RECON_EXIT == {"blocked": 3, "review_required": 4, "verified": 0}


def test_mechanics_recon_main_fails_closed_without_stormlib(tmp_path, capsys):
    code = main(["mechanics-recon", "--client-root", str(tmp_path / "Data"),
                 "--out", str(tmp_path / "out"), "--stormlib", "/nonexistent/libstorm.so.999"])
    assert code == 2
    assert "StormLib" in capsys.readouterr().err


def test_migration_completeness_pointer_is_wired():
    """Guard: the canonical Node build requires the pointer, regenerate publishes it, and the Node
    resolver exists — so the transactional contract cannot silently regress to the fixed path."""
    build_js = (REPO / "coa_scraper/scripts/build-mechanics-artifacts.mjs").read_text()
    assert "--client-extract-pointer" in build_js
    assert "a canonical build requires --client-extract-pointer" in build_js
    assert (REPO / "coa_scraper/scripts/lib/generation.mjs").is_file()
    cli_py = (REPO / "coa_client_extract/cli.py").read_text()
    assert "GenerationWriter" in cli_py and "coa_client_extract.pointer.json" in cli_py


# --- end-to-end: Python publishes a generation -> node resolves it -> node build via the pointer ---
def _v2_rec(spell_id):
    proof = {"integrity": "verified", "layout": "verified", "interpretation": "verified"}
    env = lambda v, k: {"state": "present", "raw_u32": v, "decoded": {"kind": k, "value": v},
                        "decoded_reason": "decoded", "proof": proof, "evidence_ref": "fx"}
    return {"schema_version": "coa-client-spell-v2", "spell_id": spell_id, "name": f"S{spell_id}",
            "mechanics": {"school_mask": 8, "power_type": 3},
            "field_observations": {"school_mask": env(8, "uint32"), "power_type": env(3, "int32")},
            "coa_attribution": {"is_coa": True, "confidence": "high"}}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_e2e_publish_then_node_resolves_and_builds(tmp_path):
    root = tmp_path / "ce"
    records = [_v2_rec(92117)]
    body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records).encode()
    proj_manifest = {
        "schema_version": "coa-client-spell-projection-v2",
        "inclusion_rule": {"predicate": "coa_attribution.is_coa == true", "version": "m1.14e-1"},
        "projection": {"path": "coa_client_spell_coa.jsonl", "sha256": hashlib.sha256(body).hexdigest(),
                       "byte_length": len(body)},
        "client_build": "3.3.5a+patch-CZZ",
        "counts": {"source_records": 1, "projected_records": 1, "unique_spell_ids": 1, "by_confidence": {"high": 1}},
    }
    gw = GenerationWriter(root)
    gw.add_jsonl("coa_client_spell_coa.jsonl", records, schema_version="coa-client-spell-v2")
    gw.add_json("coa_client_spell_projection.manifest.json", proj_manifest,
                schema_version="coa-client-spell-projection-v2")
    from coa_client_extract.manifest import build_manifest
    base = build_manifest(backend_name="fake", backend_version="v1", stormlib_version=None,
                          client_root="/x", client_build="3.3.5a+patch-CZZ", outputs={},
                          archive_plan={"schema_version": "coa-client-archive-plan-v1"})
    gw.publish(base_manifest=base, binding={"policy_sha256": "p", "anchor_set_sha256": "a", "enum_policy_sha256": "e", "source_dbc": {}},
               unknown_symbol_inventory={"power_type": [], "school_bits": []})

    # sanity: the Python resolver accepts it
    assert set(resolve_active_generation(root)["children"]) == {
        "coa_client_spell_coa.jsonl", "coa_client_spell_projection.manifest.json"}

    pointer = root / "coa_client_extract.pointer.json"
    cwd = REPO / "coa_scraper"
    # node resolver CLI validates the pointer
    r = subprocess.run(["node", "scripts/lib/generation.mjs", str(pointer)], cwd=cwd,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    entries = tmp_path / "entries.jsonl"
    entries.write_text(json.dumps({"spell_id": 92117, "entry_id": 1, "entry_type": "Ability",
                                   "name": "S92117", "damage_schools": [], "resources": []}) + "\n")
    dist = tmp_path / "dist"
    b = subprocess.run(["node", "scripts/build-mechanics-artifacts.mjs",
                        "--builder-entries", str(entries), "--client-extract-pointer", str(pointer),
                        "--out", str(dist)], cwd=cwd, capture_output=True, text=True)
    assert b.returncode == 0, b.stderr
    rows = [json.loads(l) for l in (dist / "coa_mechanics.jsonl").read_text().splitlines() if l.strip()]
    assert any(row.get("spell_id") == 92117 for row in rows)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_e2e_node_build_canonical_requires_pointer(tmp_path):
    entries = tmp_path / "entries.jsonl"
    entries.write_text(json.dumps({"spell_id": 1, "entry_id": 1, "entry_type": "Ability",
                                   "name": "S1", "damage_schools": [], "resources": []}) + "\n")
    cwd = REPO / "coa_scraper"
    b = subprocess.run(["node", "scripts/build-mechanics-artifacts.mjs",
                        "--builder-entries", str(entries), "--out", str(tmp_path / "dist")],
                       cwd=cwd, capture_output=True, text=True)
    assert b.returncode == 2
    assert "requires --client-extract-pointer" in b.stderr
