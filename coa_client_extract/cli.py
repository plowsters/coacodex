from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .archive_backend import ArchiveBackend
from .archive_plan import ArchivePlan, discover_plan, validate_load_order
from .artifacts import build_client_spell_records, write_json, write_jsonl
from .class_types import resolve_class_types, resolve_tab_types
from .content_json import read_content_records
from .decode_advancement import decode_layout, write_report
from .dbc_layouts import (
    CHARACTER_ADVANCEMENT,
    CHARACTER_ADVANCEMENT_CLASS_TYPES,
    CHARACTER_ADVANCEMENT_TAB_TYPES,
    SPELL_FAMILY,
)
from .errors import BackendUnavailable
from .manifest import build_manifest
from .wdbc import DbcLayout, parse_dbc, parse_positional


def regenerate(
    client_root: Path,
    out_dir: Path,
    *,
    backend: ArchiveBackend | None = None,
    stormlib_path: str | None = None,
    layouts: dict[str, DbcLayout] | None = None,
) -> dict:
    if backend is None:
        from .stormlib_backend import StormLibBackend
        backend = StormLibBackend(stormlib_path=stormlib_path)  # may raise BackendUnavailable

    plan = discover_plan(client_root)
    layouts = layouts or SPELL_FAMILY
    root, attach = plan.open_chain  # StormLib root + all base+patch archives attached on top

    def read_table(name: str):
        member = backend.read_effective_file(root, attach, f"DBFilesClient\\{name}.dbc")
        return member, parse_dbc(member.data, layouts[name])

    spell_member, spell = read_table("Spell")
    cast_member, cast = read_table("SpellCastTimes")
    dur_member, dur = read_table("SpellDuration")
    rng_member, rng = read_table("SpellRange")

    # Fail closed before writing canonical artifacts if the order StormLib applied disagrees
    # with the plan's declared load order for the canonical, CoA-overridden Spell table.
    validate_load_order(plan, spell_member)

    provenance = {
        "base_archive": spell_member.base_archive.name,
        "patch_chain": [p.name for p in spell_member.patch_chain],
        "effective_archive": spell_member.effective_archive.name,
        "source_dbcs": {
            "Spell": spell_member.effective_archive.name,
            "SpellCastTimes": cast_member.effective_archive.name,
            "SpellDuration": dur_member.effective_archive.name,
            "SpellRange": rng_member.effective_archive.name,
        },
        "extraction_date": date.today().isoformat(),
    }

    spell_records = build_client_spell_records(spell, cast, dur, rng, provenance=provenance)
    content_records = read_content_records(client_root / "Content")

    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "coa_client_spell.jsonl": write_jsonl(spell_records, out_dir / "coa_client_spell.jsonl"),
        "coa_client_content.jsonl": write_jsonl(content_records, out_dir / "coa_client_content.jsonl"),
        "coa_client_archive_plan.json": write_json(plan.to_dict(), out_dir / "coa_client_archive_plan.json"),
    }
    manifest = build_manifest(
        backend_name=getattr(backend, "name", "unknown"),
        backend_version=getattr(backend, "version", "unknown"),
        stormlib_version=getattr(backend, "stormlib_version", None),
        client_root=str(client_root),
        client_build=_client_build(plan),
        outputs=outputs,
        archive_plan=plan.to_dict(),
    )
    write_json(manifest, out_dir / "coa_client_extract_manifest.json")
    return manifest


def _client_build(plan: ArchivePlan) -> str:
    """The WoW client generation plus the top (highest-priority) content patch, which
    identifies the CoA content revision the artifacts were extracted from. The full patch
    list lives in the archive plan; this is the one-line build descriptor."""
    if plan.patch_archives:
        top = plan.patch_archives[-1].name.rsplit(".", 1)[0]
        return f"3.3.5a+{top}"
    return "3.3.5a"


def _load_content_entries(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else payload.get("data", [])


def decode_advancement(
    client_root: Path,
    content_json: Path,
    out_path: Path,
    *,
    backend: ArchiveBackend | None = None,
    stormlib_path: str | None = None,
    score_threshold: float = 0.85,
    margin_threshold: float = 0.15,
    min_nonzero: int = 50,
) -> dict:
    """Self-applying decode: open the client (StormLib), read CharacterAdvancement positionally
    plus the companion *Types tables and the loose content JSON, run decode_layout, and write the
    full report (including its resolved_layout block) to out_path. Non-strict positional/named
    parses here — this is the exploratory decode tier; drift is diagnostic, not fatal. Strict
    canonical parsing is Task 8's regenerate path, not this one."""
    if backend is None:
        from .stormlib_backend import StormLibBackend
        backend = StormLibBackend(stormlib_path=stormlib_path)  # may raise BackendUnavailable

    plan = discover_plan(client_root)
    root, attach = plan.open_chain  # StormLib root + all base+patch archives attached on top

    ca_member = backend.read_effective_file(root, attach, "DBFilesClient\\CharacterAdvancement.dbc")
    ca = parse_positional(
        ca_member.data, CHARACTER_ADVANCEMENT.header_field_count, CHARACTER_ADVANCEMENT.header_record_size
    )

    class_types_member = backend.read_effective_file(
        root, attach, "DBFilesClient\\CharacterAdvancementClassTypes.dbc"
    )
    class_types = resolve_class_types(parse_dbc(class_types_member.data, CHARACTER_ADVANCEMENT_CLASS_TYPES))

    tab_types_member = backend.read_effective_file(
        root, attach, "DBFilesClient\\CharacterAdvancementTabTypes.dbc"
    )
    tab_types = resolve_tab_types(parse_dbc(tab_types_member.data, CHARACTER_ADVANCEMENT_TAB_TYPES))

    json_entries = _load_content_entries(content_json)

    _layout, report = decode_layout(
        ca, class_types, tab_types, json_entries,
        score_threshold=score_threshold, margin_threshold=margin_threshold, min_nonzero=min_nonzero,
    )
    write_report(report, out_path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coa_client_extract")
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("regenerate", help="extract client artifacts")
    reg.add_argument("--client-root", required=True, type=Path)
    reg.add_argument("--out", required=True, type=Path)
    reg.add_argument("--stormlib", default=None)

    dec = sub.add_parser("decode-advancement", help="decode & prove CharacterAdvancement.dbc columns")
    dec.add_argument("--client-root", required=True, type=Path)
    dec.add_argument("--content-json", required=True, type=Path)
    dec.add_argument("--out", required=True, type=Path)
    dec.add_argument("--stormlib", default=None)
    args = parser.parse_args(argv)

    if args.command == "regenerate":
        try:
            regenerate(args.client_root, args.out, stormlib_path=args.stormlib)
        except BackendUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "decode-advancement":
        try:
            decode_advancement(args.client_root, args.content_json, args.out, stormlib_path=args.stormlib)
        except BackendUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0
    return 1
