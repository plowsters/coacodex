from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .archive_backend import ArchiveBackend
from .archive_plan import ArchivePlan, discover_plan, validate_load_order
from .artifacts import write_json, write_jsonl
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
    spell_policy=None,
    builder_entries_path: str | None = None,
    ca_decode_report: str | None = None,
    client_only_adjudication_path: str | None = None,
    budget: dict | None = None,
    validate_with_node: bool = True,
) -> dict:
    """Stream a full transactional generation (design A2/A4/A5): the shared topology verifier hard-holds
    the reviewed policy's `bound` against the opened client, every required child is streamed record-by-
    record into a CANDIDATE generation, the candidate is validated by path in BOTH Python and Node, the
    three-part budget is recorded, and only then is the pointer published LAST. Returns the noncanonical
    fixed-path compatibility summary (the authoritative manifest is the generation's manifest-v3)."""
    import resource
    import time as _time
    from .recordview import open_view
    from .spell_layout import load_default_policy
    from .spell_record import iter_spell_records
    from .spell_icons import iter_icon_catalog
    from .topology import verify_source_topology, topology_matches_bound
    from .publish import GenerationWriter, validate_candidate_generation, PublishError
    from .spell_mechanics import three_part_budget, DEFAULT_BUDGET
    from .errors import ClientBindingError

    started = _time.monotonic()
    if backend is None:
        from .stormlib_backend import StormLibBackend
        backend = StormLibBackend(stormlib_path=stormlib_path)  # may raise BackendUnavailable

    plan = discover_plan(client_root)
    layouts = layouts or SPELL_FAMILY
    policy = spell_policy or load_default_policy()
    root, attach = plan.open_chain  # StormLib root + all base+patch archives attached on top
    client_build = _client_build(plan)
    ceilings = budget or DEFAULT_BUDGET

    # === Shared full-topology hard hold (design A2) ===
    # The SAME verifier recon uses opens every required table independently (sha256, full header, member,
    # archive, patch chain, density, key-uniqueness) and the expected-absent set, then matches the
    # reviewed policy's structured `bound` facet-for-facet. A canonical build never promotes values proven
    # against a different client, and recon + regenerate can never diverge on what "the proven client" is.
    if not policy.reviewed:
        raise ClientBindingError("spell policy is not reviewed; refusing canonical v3 emission")
    topology = verify_source_topology(policy, backend, root, attach)
    topology["client_build"] = client_build          # recon holds the authoritative opened build
    if topology["blocking"]:
        raise ClientBindingError(f"source topology hard hold: {topology['blocking']}")
    mismatch = topology_matches_bound(topology, policy.bound)
    if mismatch:
        raise ClientBindingError(f"spell policy not bound to this client: {mismatch}")

    spell_member = backend.read_effective_file(root, attach, "DBFilesClient\\Spell.dbc")
    # Fail closed before staging any canonical artifact if the order StormLib applied disagrees with the
    # plan's declared load order for the canonical, CoA-overridden Spell table.
    validate_load_order(plan, spell_member)
    spell_view = open_view(spell_member.data).require_dense()

    # Every required side table was already proven present + dense by the topology hard hold; open them.
    side_views: dict[str, object] = {}
    for name in policy.required_tables:
        if name == "Spell":
            continue
        m = backend.read_effective_file(root, attach, f"DBFilesClient\\{name}.dbc")
        side_views[name] = open_view(m.data)

    provenance = {                                    # hoisted ONCE to the manifest, never per row (A4)
        "base_archive": spell_member.base_archive.name,
        "patch_chain": [p.name for p in spell_member.patch_chain],
        "effective_archive": spell_member.effective_archive.name,
        "extraction_date": date.today().isoformat(),
    }

    # The icon catalog hashes the ACTUAL BLP bytes; the resolver reads the effective client member (or
    # None when the icon file is absent from the chain -> the row is `missing`).
    def asset_resolver(client_path: str):
        member_name = _icon_member_name(client_path)
        if not backend.has_file(root, attach, member_name):
            return None
        m = backend.read_effective_file(root, attach, member_name)
        return {"bytes": m.data, "archive": m.effective_archive.name,
                "member": m.logical_path, "patch_chain": [p.name for p in m.patch_chain]}

    content_records = read_content_records(client_root / "Content")

    # === TWO-PASS attribution (design B / M1.14B): pass 1 builds the authoritative CoA attribution from
    # CharacterAdvancement + the proven skill-line index; pass 2 (below) streams the Spell table using it.
    # `coa_attribution.is_coa` is NEVER the `spell_id >= 100000` id floor (that is `id_range` provenance
    # only — it tags ~139k enemy/NPC/aura/dev spells and would distort the projection, closure, coverage).
    # --- advancement pipeline: read the CoA advancement graph, attribute spells, and prove parity ---
    import hashlib
    from .class_types import resolve_class_types, resolve_tab_types, assert_playable_cardinality
    from .advancement import read_advancement, validate_semantics
    from .attribution import attribute, derive_coa_skill_lines, build_skill_line_index
    from .artifacts import (
        build_advancement_records, build_class_type_records, build_tab_type_records,
        build_essence_raw_records, _sha256_bytes,
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

    # === PASS 2: the AUTHORITATIVE CoA spell-id set (graph attribution + proven skill-line fallback) drives
    # is_coa. Stream the v3 spell children sorted by spell_id (so the cross-child merge-join is a linear
    # scan and the icon catalog covers every spell); project ONLY authoritatively-attributed rows. ===
    coa_attributed_ids = {sid for sid, sa in spell_attr.items() if sa.result.is_coa}
    full_rows = sorted(iter_spell_records(spell_view, side_views, policy=policy, provenance=provenance,
                                          coa_spell_ids=coa_attributed_ids),
                       key=lambda r: r["spell_id"])
    projection_rows = [{**r, "schema_version": "coa-client-spell-projection-v3"}
                       for r in full_rows if r["coa_attribution"].get("is_coa") is True]
    icon_rows = sorted(iter_icon_catalog(spell_view, side_views, policy=policy, asset_resolver=asset_resolver),
                       key=lambda r: r["spell_id"])
    unknown_symbol_inventory = _unknown_symbol_inventory(spell_view, policy)

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
    spell_names = {r["spell_id"]: (r.get("name") or "") for r in full_rows}
    adv_records = build_advancement_records(coa_nodes, provenance=adv_provenance,
                                            spell_names=spell_names, attribution=spell_attr)
    class_type_records = build_class_type_records(class_types)
    tab_type_records = build_tab_type_records(tab_types)
    essence_records = build_essence_raw_records(ess_raw, provenance=essence_provenance)  # raw; undecoded

    # === stage the candidate generation: every REQUIRED_CHILD streamed into gen-<uuid>/ (design A5). The
    # generation's manifest-v3 is the AUTHORITATIVE manifest; the fixed-path summary below is noncanonical.
    out_dir.mkdir(parents=True, exist_ok=True)
    projection_manifest = {
        "schema_version": "coa-client-spell-projection-manifest-v3",
        "inclusion_rule": {"predicate": "coa_attribution.is_coa == true", "version": "m1.14e0r"},
        "client_build": client_build, "extractor_commit": _extractor_commit(),
        "extraction_date": date.today().isoformat(), "policy_sha256": policy.sha256,
        "counts": {"source_records": len(full_rows), "projected_records": len(projection_rows),
                   "unique_spell_ids": len({r["spell_id"] for r in projection_rows})},
    }
    base_manifest = build_manifest(
        backend_name=getattr(backend, "name", "unknown"),
        backend_version=getattr(backend, "version", "unknown"),
        stormlib_version=getattr(backend, "stormlib_version", None),
        client_root=str(client_root), client_build=client_build, outputs={},
        archive_plan=plan.to_dict())
    gw = GenerationWriter(out_dir)
    gw.add_jsonl("coa_client_spell.jsonl", full_rows, schema_version="coa-client-spell-v3")
    gw.add_jsonl("coa_client_spell_coa.jsonl", projection_rows, schema_version="coa-client-spell-projection-v3")
    gw.add_json("coa_client_spell_projection.manifest.json", projection_manifest,
                schema_version="coa-client-spell-projection-manifest-v3")
    gw.add_jsonl("coa_client_spell_icons.jsonl", icon_rows, schema_version="coa-client-spell-icons-v1")
    gw.add_jsonl("coa_client_content.jsonl", content_records, schema_version="coa-client-content-v1")
    gw.add_json("coa_client_archive_plan.json", plan.to_dict(), schema_version="coa-client-archive-plan-v1")
    gw.add_jsonl("coa_client_advancement.jsonl", adv_records, schema_version="coa-client-advancement-v1")
    gw.add_jsonl("coa_client_class_types.jsonl", class_type_records, schema_version="coa-client-class-types-v1")
    gw.add_jsonl("coa_client_tab_types.jsonl", tab_type_records, schema_version="coa-client-tab-types-v1")
    gw.add_jsonl("coa_client_essence.jsonl", essence_records, schema_version="coa-client-essence-v1")
    gw.add_json("spell_layout_v2.json", policy.doc, schema_version="coa-spell-layout-v2")  # reviewed policy child

    binding = {"topology": topology, "provenance": provenance, "policy_sha256": policy.sha256,
               "anchor_set_sha256": policy.anchor_sha256, "enum_policy_sha256": policy.enum_sha256}
    candidate = gw.publish_candidate(base_manifest=base_manifest, binding=binding,
                                     unknown_symbol_inventory=unknown_symbol_inventory)

    # === validate the candidate BY PATH in BOTH Python and Node, before the pointer flips (design A5) ===
    validate_candidate_generation(gw.gen_dir)                 # per-child + streaming cross-child merge-join
    if validate_with_node:
        _node_validate_candidate(gw.gen_dir)                 # independent Node trust boundary

    # === three-part budget over the ACTUAL serialized generation (bytes + peak RSS + elapsed) (A4) ===
    serialized_bytes = sum(meta["byte_length"] for meta in gw._children.values())
    elapsed_s = round(_time.monotonic() - started, 4)
    peak_rss_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)  # Linux ru_maxrss is KiB
    budget_report = three_part_budget(serialized_bytes=serialized_bytes, peak_rss_mb=peak_rss_mb,
                                      elapsed_s=elapsed_s, ceilings=ceilings)
    if not budget_report["within_budget"]:
        raise PublishError(f"regenerate exceeded the three-part budget: {budget_report['breach']}")

    # === publish the pointer LAST (candidate -> published; the trust digest is reproduced identically) ===
    gw.finalize_and_publish(candidate_manifest=candidate,
                            validation={"python": True, "node": bool(validate_with_node)},
                            budget=budget_report)

    outputs = {name: meta["sha256"] for name, meta in gw._children.items()}
    outputs["coa_client_extract.pointer.json"] = _sha256_bytes(
        (out_dir / "coa_client_extract.pointer.json").read_bytes())

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

    # Noncanonical fixed-path compatibility summary, produced AFTER publication — never a generation child
    # and never able to make regenerate() fail once the pointer flipped (design A5). The authoritative
    # manifest is gen-<uuid>/manifest.json (coa-client-extract-manifest-v3).
    manifest = build_manifest(
        backend_name=getattr(backend, "name", "unknown"),
        backend_version=getattr(backend, "version", "unknown"),
        stormlib_version=getattr(backend, "stormlib_version", None),
        client_root=str(client_root),
        client_build=_client_build(plan),
        outputs=outputs,
        archive_plan=plan.to_dict(),
    )
    manifest["generation_id"] = gw.generation_id
    manifest["publication_state"] = "published"
    manifest["budget"] = budget_report
    # The per-value domain gate's aggregate — unseen enum/bit symbols whose normalized value was withheld
    # (raw retained). An empty inventory means every value fell inside the policy domain.
    manifest["unknown_symbol_inventory"] = unknown_symbol_inventory
    manifest["spell_policy_sha256"] = policy.sha256
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


def write_acceptance_summary(dist: Path, manifest: dict, *, recon_status: str, benchmark_env_id: str,
                             build_mechanics: dict, out: Path | None = None) -> dict:
    """The schema-stable curated E0R acceptance record: pins the exact client build, generation identity,
    manifest + policy digests, extractor commit, per-child {sha256, byte_length, records}, the three-part
    regenerate budget, the canonical (pointer-only) build-mechanics measurement, the benchmark env, and the
    recon status. A record OF a clean run — never part of the commit it attests to."""
    import hashlib
    children = {name: {"sha256": meta.get("sha256"), "byte_length": meta.get("byte_length"),
                       "records": meta.get("records")}
                for name, meta in (manifest.get("children") or {}).items()}
    binding = manifest.get("binding") or {}
    manifest_sha256 = None
    pointer = Path(dist) / "coa_client_extract.pointer.json"
    if pointer.is_file():
        try:
            manifest_sha256 = json.loads(pointer.read_text(encoding="utf-8")).get("manifest_sha256")
        except (ValueError, OSError):
            manifest_sha256 = None
    if manifest_sha256 is None:
        manifest_sha256 = hashlib.sha256(
            (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        ).hexdigest()
    summary = {
        "schema_version": "coa-e0r-acceptance-summary-v1",
        "client_build": manifest.get("client_build"),
        "generation_id": manifest.get("generation_id"),
        "manifest_sha256": manifest_sha256,
        "policy_sha256": binding.get("policy_sha256"),
        "extractor_commit": manifest.get("extractor_commit") or _extractor_commit(),
        "benchmark_env_id": benchmark_env_id,
        "children": children,
        "budget": manifest.get("budget"),
        "recon_status": recon_status,
        "build_mechanics": build_mechanics,
        "generated_at": date.today().isoformat(),
    }
    if out is not None:
        write_json(summary, Path(out))
    return summary


def _parse_gnu_time(text: str) -> dict:
    """Parse `/usr/bin/time -v` output for elapsed wall time (Elapsed (wall clock)) and peak RSS (Maximum
    resident set size, KiB on Linux) -> {elapsed_s, peak_rss_mb}."""
    import re
    elapsed_s = None
    peak_rss_mb = None
    m = re.search(r"Elapsed \(wall clock\) time.*?:\s*([0-9:.]+)", text)
    if m:
        parts = [float(p) for p in m.group(1).split(":")]
        elapsed_s = parts[-1] + (parts[-2] * 60 if len(parts) >= 2 else 0) + (parts[-3] * 3600 if len(parts) >= 3 else 0)
    m = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", text)
    if m:
        peak_rss_mb = round(int(m.group(1)) / 1024, 1)
    return {"elapsed_s": elapsed_s, "peak_rss_mb": peak_rss_mb}


def _icon_member_name(client_path: str) -> str:
    """The SpellIcon.dbc path string -> the effective client member key. WoW stores icon paths with
    backslashes and (usually) no extension; the BLP file is that path + '.blp'."""
    p = client_path.replace("/", "\\")
    if not p.lower().endswith(".blp"):
        p += ".blp"
    return p


def _signed32(v: int) -> int:
    return v - 0x1_0000_0000 if v >= 0x8000_0000 else v


def _unknown_symbol_inventory(spell_view, policy) -> dict:
    """The per-value domain gate's aggregate over the WHOLE table: enum/bit symbols observed at the proven
    power_type/school_mask cells that fall OUTSIDE the reviewed policy domain (their normalized value was
    withheld, raw retained). Empty ⇒ every observed value was in-domain. Hoisted to the manifest (A4)."""
    sf = policy.tables["Spell"]["fields"]
    pt_cell = sf["power_type"].cell if "power_type" in sf else None
    sm_cell = sf["school_mask"].cell if "school_mask" in sf else None
    allowed_pt = set(policy.enum_policy["power_types"])
    allowed_bits = set(policy.enum_policy["school_bits"])
    unknown_pt: set[int] = set()
    unknown_bits: set[int] = set()
    for rec in spell_view.records():
        if pt_cell is not None:
            v = _signed32(rec.u32(pt_cell))
            if v not in allowed_pt:
                unknown_pt.add(v)
        if sm_cell is not None:
            mask = rec.u32(sm_cell)
            for b in range(32):
                bit = 1 << b
                if mask & bit and bit not in allowed_bits:
                    unknown_bits.add(bit)
    return {"power_type": sorted(unknown_pt), "school_bits": sorted(unknown_bits)}


def _node_validate_candidate(gen_dir: Path) -> None:
    """Run the independent Node trust boundary against the staged CANDIDATE generation by path, before the
    pointer flips (design A5). A non-zero exit fails the canonical publish closed."""
    import subprocess
    from .publish import PublishError
    script = Path(__file__).resolve().parents[1] / "coa_scraper" / "scripts" / "lib" / "generation.mjs"
    try:
        proc = subprocess.run(["node", str(script), "--candidate", str(gen_dir)],
                              capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise PublishError(f"node is required to validate a canonical generation: {exc}") from exc
    if proc.returncode != 0:
        raise PublishError(f"Node candidate validation failed: {proc.stderr.strip() or proc.stdout.strip()}")


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

    wc = sub.add_parser("wow-constants", help="extract coa-wow-constants-v1 GameTable primitives")
    wc.add_argument("--client-root", required=True, type=Path)
    wc.add_argument("--out", required=True, type=Path)
    wc.add_argument("--stormlib", default=None)
    wc.add_argument("--recon-only", action="store_true")
    wc.add_argument("--adjudication",
                    default="reports/client_extract/wow_class_axis_adjudication.json")

    mr = sub.add_parser("mechanics-recon", help="spell-mechanics recon hard hold (blocked=3/review=4/verified=0)")
    mr.add_argument("--client-root", required=True, type=Path)
    mr.add_argument("--out", required=True, type=Path)
    mr.add_argument("--stormlib", default=None)

    acc = sub.add_parser("acceptance-summary", help="write the curated E0R acceptance record from a published generation")
    acc.add_argument("--dist", required=True, type=Path)
    acc.add_argument("--recon-status", default="verified")
    acc.add_argument("--benchmark-env-id", default="local")
    acc.add_argument("--build-mechanics-time", default=None,
                     help="a /usr/bin/time -v capture of the canonical pointer-only build-mechanics run")
    acc.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    if args.command == "regenerate":
        from .errors import ClientBindingError
        from .publish import PublishError
        try:
            regenerate(
                args.client_root, args.out, stormlib_path=args.stormlib,
                builder_entries_path=args.builder_entries, ca_decode_report=args.decode_report,
                client_only_adjudication_path=args.client_only_adjudication,
            )
        except BackendUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except ClientBindingError as exc:
            print(f"error: client-binding hard hold: {exc}", file=sys.stderr)
            return 3
        except PublishError as exc:
            # A budget breach / staging failure fails CLOSED: the pointer is untouched and NO generation is
            # published (exit 4, distinct from the backend/binding holds), so a wrapper cannot mask it.
            print(f"error: publication hard hold: {exc}", file=sys.stderr)
            return 4
        return 0
    if args.command == "decode-advancement":
        try:
            decode_advancement(args.client_root, args.content_json, args.out, stormlib_path=args.stormlib)
        except BackendUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "wow-constants":
        try:
            wow_constants_command(args.client_root, args.out, stormlib_path=args.stormlib,
                                  recon_only=args.recon_only, adjudication_path=args.adjudication)
        except BackendUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "mechanics-recon":
        try:
            report = mechanics_recon_command(args.client_root, args.out, stormlib_path=args.stormlib)
        except BackendUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        status = report["status"]
        print(f"mechanics-recon: {status} ({len(report['blocking_findings'])} blocking)", file=sys.stderr)
        return _RECON_EXIT.get(status, 1)
    if args.command == "acceptance-summary":
        from .publish import resolve_active_generation, ResolveError
        try:
            manifest = resolve_active_generation(args.dist)["manifest"]
        except ResolveError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        bm = {"pointer_only": True}
        if args.build_mechanics_time and Path(args.build_mechanics_time).is_file():
            bm.update(_parse_gnu_time(Path(args.build_mechanics_time).read_text(encoding="utf-8")))
        write_acceptance_summary(args.dist, manifest, recon_status=args.recon_status,
                                 benchmark_env_id=args.benchmark_env_id, build_mechanics=bm, out=args.out)
        print(f"acceptance-summary: wrote {args.out}", file=sys.stderr)
        return 0
    return 1


_RECON_EXIT = {"blocked": 3, "review_required": 4, "verified": 0}


def mechanics_recon_command(client_root: Path, out_dir: Path, *, backend: ArchiveBackend | None = None,
                            stormlib_path: str | None = None, spell_policy=None) -> dict:
    """Run the spell-mechanics recon hard hold and write its report. Returns the report; the CLI maps
    report['status'] to an exit code (blocked=3, review_required=4, verified=0)."""
    from .archive_plan import discover_plan
    from .spell_layout import load_default_policy
    from .spell_mechanics import recon_spell_mechanics, DEFAULT_BUDGET
    from .artifacts import write_json

    if backend is None:
        from .stormlib_backend import StormLibBackend
        backend = StormLibBackend(stormlib_path=stormlib_path)  # may raise BackendUnavailable

    plan = discover_plan(client_root)
    policy = spell_policy or load_default_policy()
    root, attach = plan.open_chain
    report = recon_spell_mechanics(
        backend, root, attach, spell_policy=policy, anchors=policy.anchors, budget=DEFAULT_BUDGET,
        extractor_commit=_extractor_commit(), client_build=_client_build(plan))
    write_json(report, Path(out_dir) / "coa_spell_mechanics_recon.json")
    return report


def wow_constants_command(client_root: Path, out_dir: Path, *, backend: ArchiveBackend | None = None,
                          stormlib_path: str | None = None, recon_only: bool = False,
                          adjudication_path: str | None =
                          "reports/client_extract/wow_class_axis_adjudication.json") -> dict:
    if backend is None:
        from .stormlib_backend import StormLibBackend
        backend = StormLibBackend(stormlib_path=stormlib_path)  # may raise BackendUnavailable
    plan = discover_plan(client_root)
    from .wow_constants import run_recon
    if recon_only:
        return run_recon(client_root, out_dir, backend=backend, plan=plan)
    from .wow_constants import run_extract          # added in Task 10
    return run_extract(client_root, out_dir, backend=backend, plan=plan,
                       extractor_commit=_extractor_commit(), client_build=_client_build(plan),
                       adjudication_path=adjudication_path)
