# tests/_streaming_probe.py
"""E0R.1 T4.1 RSS probe — run a COMPLETE synthetic regenerate (fake backend, N spells, Python validation;
Node is T4.2's boundary) in an ISOLATED subprocess and print peak RSS, so the parent test can assert
bounded (sub-linear) growth as the record count scales. The spell ids are staged in DESCENDING DBC order,
so the ascending sorted-unique cross-child contract also proves the writer's sort survived streaming."""
import json
import resource
import shutil
import struct
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from coa_client_extract.archive_backend import FakeArchiveBackend
from tests.test_client_extract_cli import _ca_tables, _ICON_BLP, _ICON_PATH


def _spell_dbc(n: int) -> bytes:
    strings = b"\x00Adrenal Venom\x00"
    # ids DESCENDING on purpose; 805775 present so the CA graph attributes one is_coa row.
    ids = [805775 + i for i in range(n)][::-1]
    rows = b"".join(struct.pack("<8I", sid, 1, 0, 8, 3, 5, 1, 100) for sid in ids)
    return struct.pack("<4sIIII", b"WDBC", n, 8, 32, len(strings)) + rows + strings


def _backend(n: int) -> FakeArchiveBackend:
    def dbc(rows, fc, rs, s=b"\x00"):
        return struct.pack("<4sIIII", b"WDBC", len(rows), fc, rs, len(s)) + b"".join(rows) + s
    cast = struct.pack("<II", 3, 1500)
    dur = struct.pack("<II", 5, 18000)
    rng = struct.pack("<Iii", 1, 0, 40)
    icon_strings = b"\x00" + _ICON_PATH.encode("latin-1") + b"\x00"
    icon = struct.pack("<II", 100, 1)
    entries = {
        "DBFilesClient\\Spell.dbc": [(Path("common.MPQ"), _spell_dbc(n))],
        "DBFilesClient\\SpellCastTimes.dbc": [(Path("common.MPQ"), dbc([cast], 2, 8))],
        "DBFilesClient\\SpellDuration.dbc": [(Path("common.MPQ"), dbc([dur], 2, 8))],
        "DBFilesClient\\SpellRange.dbc": [(Path("common.MPQ"), dbc([rng], 3, 12))],
        "DBFilesClient\\SpellIcon.dbc": [(Path("common.MPQ"), dbc([icon], 2, 8, icon_strings))],
        _ICON_PATH: [(Path("common.MPQ"), _ICON_BLP)],
    }
    ca, ct, tt, ess, sla = _ca_tables()
    entries["DBFilesClient\\CharacterAdvancement.dbc"] = [(Path("common.MPQ"), ca)]
    entries["DBFilesClient\\CharacterAdvancementClassTypes.dbc"] = [(Path("common.MPQ"), ct)]
    entries["DBFilesClient\\CharacterAdvancementTabTypes.dbc"] = [(Path("common.MPQ"), tt)]
    entries["DBFilesClient\\CharacterAdvancementEssence.dbc"] = [(Path("common.MPQ"), ess)]
    entries["DBFilesClient\\SkillLineAbility.dbc"] = [(Path("common.MPQ"), sla)]
    return FakeArchiveBackend(entries)


def main() -> None:
    n = int(sys.argv[1])
    tmp = Path(tempfile.mkdtemp(prefix=f"t41-{n}-"))
    try:
        _probe(n, tmp)
    finally:
        # A 100k-row generation is ~300MB; leaking one per run filled /tmp and then produced a FALSE
        # failure ("Disk quota exceeded") that looked like a memory regression. Always clean up.
        shutil.rmtree(tmp, ignore_errors=True)


def _probe(n: int, tmp: Path) -> None:
    from coa_client_extract.cli import regenerate
    from coa_client_extract.publish import resolve_active_generation
    from tests.test_client_extract_cli import _bound_spell_policy, _client, _synthetic_layouts

    client_root = _client(tmp)
    out = tmp / "out"
    policy = _bound_spell_policy(_backend(n), client_root)
    lock = tmp / "spell_layout.lock.json"
    lock.write_text(json.dumps({"schema_version": "coa-spell-layout-lock-v1", "sha256": policy.sha256}))
    generous = {"artifact_size_mb": 4096, "peak_rss_mb": 16384, "elapsed_s": 3600}
    # Node validation runs (both trust boundaries are required for the generation to be resolvable) but in
    # its OWN process — it never contributes to the Python peak RSS this probe measures (Node streaming is
    # T4.2's boundary).
    regenerate(client_root, out, backend=_backend(n), layouts=_synthetic_layouts(),
               spell_policy=policy, node_lock_path=lock, budget=generous)

    resolved = resolve_active_generation(out)
    children = resolved["manifest"]["children"]
    assert children["coa_client_spell.jsonl"]["records"] == n
    assert children["coa_client_spell_icons.jsonl"]["records"] == n
    assert children["coa_client_spell_coa.jsonl"]["records"] == 1     # only the CA-attributed spell
    first = json.loads(next(iter(
        (resolved["gen_dir"] / "coa_client_spell.jsonl").open(encoding="utf-8"))))
    assert first["spell_id"] == 805775                                # ascending despite descending DBC order

    peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux: KiB
    print(json.dumps({"n": n, "peak_rss_mb": round(peak_rss_mb, 1)}))


if __name__ == "__main__":
    main()
