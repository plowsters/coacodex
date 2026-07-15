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
    builder_entries_path: str | None = None,
    ca_decode_report: str | None = None,
    client_only_adjudication_path: str | None = None,
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

    # --- advancement pipeline: read the CoA advancement graph, attribute spells, and prove parity ---
    import hashlib
    from .class_types import resolve_class_types, resolve_tab_types, assert_playable_cardinality
    from .advancement import read_advancement, validate_semantics
    from .attribution import attribute, derive_coa_skill_lines, build_skill_line_index
    from .artifacts import (
        build_advancement_records, build_class_type_records, build_tab_type_records,
        build_essence_raw_records, fill_spell_attribution, _sha256_bytes,
    )
    from .decode_advancement import load_resolved_layout
    # parse_dbc/parse_positional are already imported at module scope (used by read_table above);
    # re-importing them here would shadow that name for this whole function and break read_table's
    # closure over parse_dbc (a local import makes the name local to the entire enclosing scope).
    from .dbc_layouts import (
        CHARACTER_ADVANCEMENT_CLASS_TYPES, CHARACTER_ADVANCEMENT_TAB_TYPES, CHARACTER_ADVANCEMENT,
        CHARACTER_ADVANCEMENT_ESSENCE, CHARACTER_ADVANCEMENT_SKILL_LINE_ABILITY,
    )

    # CANONICAL emission parses STRICT: a structural header mismatch raises before anything is written,
    # so no canonical artifact is ever emitted with header drift. (Non-strict parsing lives only in the
    # exploratory decode-advancement command.)
    def read_named(name, layout):
        m = backend.read_effective_file(root, attach, f"DBFilesClient\\{name}.dbc")
        return m, parse_dbc(m.data, layout, strict=True)          # named columns incl. "name" (col 1)

    def read_positional(name, fc, rs):
        m = backend.read_effective_file(root, attach, f"DBFilesClient\\{name}.dbc")
        return m, parse_positional(m.data, fc, rs, strict=True)   # {index: value} rows

    ct_member, ct_tbl = read_named("CharacterAdvancementClassTypes", CHARACTER_ADVANCEMENT_CLASS_TYPES)
    tt_member, tt_tbl = read_named("CharacterAdvancementTabTypes", CHARACTER_ADVANCEMENT_TAB_TYPES)
    # The layout is the PROVEN one from the committed decode report (self-applying, no hand-edit); tests
    # inject a synthetic layout; the anchors-only constant is only a last resort.
    ca_layout = ((load_resolved_layout(ca_decode_report) if ca_decode_report else None)
                 or (layouts.get("CharacterAdvancementLayout") if layouts else None)
                 or CHARACTER_ADVANCEMENT)
    ca_member, ca_raw = read_positional("CharacterAdvancement",
                                        ca_layout.header_field_count, ca_layout.header_record_size)
    ess_member, ess_raw = read_positional("CharacterAdvancementEssence",
                                          CHARACTER_ADVANCEMENT_ESSENCE.expected_field_count,
                                          CHARACTER_ADVANCEMENT_ESSENCE.expected_record_size)
    sla_member, sla_raw = read_positional("SkillLineAbility",
                                          CHARACTER_ADVANCEMENT_SKILL_LINE_ABILITY.expected_field_count,
                                          CHARACTER_ADVANCEMENT_SKILL_LINE_ABILITY.expected_record_size)

    # CharacterAdvancement is now a canonical CoA-overridden table too: fail closed before writing if
    # StormLib's applied order disagrees with the plan's declared load order (same rule as Spell).
    validate_load_order(plan, ca_member)

    class_types = resolve_class_types(ct_tbl)
    tab_types = resolve_tab_types(tt_tbl)
    assert_playable_cardinality(class_types)         # exactly 21 playable CoA classes (raises otherwise)

    nodes = read_advancement(ca_raw, class_types, tab_types, ca_layout)
    # CharacterAdvancement.dbc is a UNIFIED all-class registry (stock talents + meta + reborn + CoA +
    # None). M1.14B owns the CoA subgraph: validate, emit, and parity-check ONLY coa_class nodes.
    coa_nodes = [n for n in nodes if n.class_kind == "coa_class"]
    validate_semantics(coa_nodes, class_types, tab_types)   # FK/adjacency/range + graph invariants; fail closed
    # skill-line fallback set is PROVEN from the graph's own CoA spells (per-spec lines, not a fixed range)
    coa_spell_ids = {n.spell_id for n in nodes if n.class_kind == "coa_class" and n.spell_id}
    coa_skill_lines = derive_coa_skill_lines(sla_raw.rows, coa_spell_ids)
    skill_index = build_skill_line_index(sla_raw.rows, coa_skill_lines)
    spell_attr = attribute(nodes, class_types, skill_line_index=skill_index)

    adv_provenance = {
        "client_build": _client_build(plan),
        "source_dbcs": {"CharacterAdvancement": ca_member.effective_archive.name,
                        "CharacterAdvancementClassTypes": ct_member.effective_archive.name,
                        "CharacterAdvancementTabTypes": tt_member.effective_archive.name,
                        "Spell": spell_member.effective_archive.name},
        "supersedes": {"source_file": "CharacterAdvancementData.json"},
        "extraction_date": date.today().isoformat(),
    }
    essence_provenance = {                           # names its OWN source table, not CharacterAdvancement
        "client_build": _client_build(plan),
        "source_dbcs": {"CharacterAdvancementEssence": ess_member.effective_archive.name},
        "semantics": "undecoded_per_level_progression",
        "extraction_date": date.today().isoformat(),
    }
    # current names come from the already-extracted spell records (Spell.dbc), not the CA string block
    spell_names = {r["spell_id"]: r.get("name", "") for r in spell_records}
    adv_records = build_advancement_records(coa_nodes, provenance=adv_provenance,
                                            spell_names=spell_names, attribution=spell_attr)
    class_type_records = build_class_type_records(class_types)
    tab_type_records = build_tab_type_records(tab_types)
    essence_records = build_essence_raw_records(ess_raw, provenance=essence_provenance)  # raw; undecoded
    spell_records = fill_spell_attribution(spell_records, spell_attr)

    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "coa_client_spell.jsonl": write_jsonl(spell_records, out_dir / "coa_client_spell.jsonl"),
        "coa_client_content.jsonl": write_jsonl(content_records, out_dir / "coa_client_content.jsonl"),
        "coa_client_archive_plan.json": write_json(plan.to_dict(), out_dir / "coa_client_archive_plan.json"),
    }
    outputs["coa_client_advancement.jsonl"] = write_jsonl(adv_records, out_dir / "coa_client_advancement.jsonl")
    outputs["coa_client_class_types.jsonl"] = write_jsonl(class_type_records, out_dir / "coa_client_class_types.jsonl")
    outputs["coa_client_tab_types.jsonl"] = write_jsonl(tab_type_records, out_dir / "coa_client_tab_types.jsonl")
    outputs["coa_client_essence.jsonl"] = write_jsonl(essence_records, out_dir / "coa_client_essence.jsonl")

    from .artifacts import write_client_spell_projection
    spell_full_path = out_dir / "coa_client_spell.jsonl"
    projection_manifest = write_client_spell_projection(
        spell_records, out_dir,
        source_path=spell_full_path.name,
        source_sha=outputs["coa_client_spell.jsonl"],
        source_bytes=spell_full_path.stat().st_size,
        client_build=_client_build(plan),
        extractor_commit=_extractor_commit(),
    )
    outputs["coa_client_spell_coa.jsonl"] = projection_manifest["projection"]["sha256"]
    outputs["coa_client_spell_projection.manifest.json"] = _sha256_bytes(
        (out_dir / "coa_client_spell_projection.manifest.json").read_bytes())

    if builder_entries_path:
        from .parity import build_parity_report, flip_gate_inputs, EXPECTED_BUILDER_RECORDS
        builder_path = Path(builder_entries_path)
        builder_entries = [json.loads(l) for l in builder_path.read_text().splitlines()]
        low_conf, unresolved_cols = flip_gate_inputs(ca_layout)          # 2-tuple; adjacency folded in
        pins = {
            "client_build": _client_build(plan),
            "extractor_commit": _extractor_commit(),                    # git HEAD of this extractor tree
            "source_dbc_sha256": {
                "CharacterAdvancement": hashlib.sha256(ca_member.data).hexdigest(),
                "CharacterAdvancementClassTypes": hashlib.sha256(ct_member.data).hexdigest(),
                "CharacterAdvancementTabTypes": hashlib.sha256(tt_member.data).hexdigest(),
                "CharacterAdvancementEssence": hashlib.sha256(ess_member.data).hexdigest(),
                "Spell": hashlib.sha256(spell_member.data).hexdigest(),
            },
            "builder_entries_file": builder_path.name,
            "builder_entries_sha256": hashlib.sha256(builder_path.read_bytes()).hexdigest(),
            "builder_record_count": len(builder_entries),
            "builder_build_slugs": sorted({e.get("build_slug") for e in builder_entries
                                           if e.get("build_slug")}),
            "decode_report_sha256": (hashlib.sha256(Path(ca_decode_report).read_bytes()).hexdigest()
                                     if ca_decode_report and Path(ca_decode_report).is_file() else None),
            "resolved_class_set": sorted(c.class_type_id for c in class_types.values()
                                         if c.kind == "coa_class"),
            "layout_version": "m1-14-b",
            "extraction_date": date.today().isoformat(),
        }
        adjudication = None
        if client_only_adjudication_path and Path(client_only_adjudication_path).is_file():
            adjudication = {int(k): v for k, v in
                            json.loads(Path(client_only_adjudication_path).read_text())["records"].items()}
        report = build_parity_report(
            coa_nodes, builder_entries, class_types=class_types,
            low_confidence_fields=low_conf, unresolved_layout_columns=unresolved_cols,
            expected_builder_records=EXPECTED_BUILDER_RECORDS,
            client_only_adjudication=adjudication, provenance=pins,
        )
        outputs["coa_builder_parity_report.json"] = write_json(
            report, out_dir / "coa_builder_parity_report.json")

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


def _extractor_commit():
    """Best-effort git HEAD of the extractor tree, for parity/artifact provenance."""
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True,
            cwd=str(Path(__file__).resolve().parent), stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


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
    reg.add_argument("--builder-entries", default=None)
    reg.add_argument("--decode-report", default="reports/client_extract/coa_ca_decode_report.json")
    reg.add_argument("--client-only-adjudication",
                     default="reports/client_extract/client_only_adjudication.json")

    dec = sub.add_parser("decode-advancement", help="decode & prove CharacterAdvancement.dbc columns")
    dec.add_argument("--client-root", required=True, type=Path)
    dec.add_argument("--content-json", required=True, type=Path)
    dec.add_argument("--out", required=True, type=Path)
    dec.add_argument("--stormlib", default=None)
    args = parser.parse_args(argv)

    if args.command == "regenerate":
        try:
            regenerate(
                args.client_root, args.out, stormlib_path=args.stormlib,
                builder_entries_path=args.builder_entries, ca_decode_report=args.decode_report,
                client_only_adjudication_path=args.client_only_adjudication,
            )
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
