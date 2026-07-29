from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

from .archive_backend import ArchiveBackend
from .archive_plan import ArchivePlan, discover_plan, validate_load_order
from .artifacts import write_json, write_jsonl
from .class_types import resolve_class_types, resolve_tab_types
from .content_json import read_bound_content, read_content_records
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
    node_lock_path: Path | None = None,
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
    from .contracts import load_observation_wire_schema
    from .spell_record import (FIELD_DESCRIPTORS_CHILD, FIELD_DESCRIPTORS_SCHEMA,
                               WIRE_SCHEMA_CHILD, build_field_descriptors, iter_spell_records,
                               observation_accumulator, project_v3_row)
    from .spell_icons import (ASSET_CHILD as ICON_ASSET_CHILD, ASSET_SCHEMA as ICON_ASSET_SCHEMA,
                              ASSOCIATION_SCHEMA as ICON_ASSOCIATION_SCHEMA, icon_asset_table,
                              icon_coverage, iter_icon_catalog)
    from .topology import verify_source_topology, topology_matches_bound
    from .publish import GenerationWriter, validate_candidate_generation, PublishError
    from .contracts import (GENERATION_CONTRACT_CHILD, GENERATION_CONTRACT_SCHEMA,
                            generation_contract_sha256, load_current_contract)
    from .spell_mechanics import benchmark_env, policy_budget_report
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

    # BOUND read (E0R.2 T0.2): every reviewed file must be present and hash to the reviewed digest. The
    # closing derivation it returns is what the contract's `declared_content_derivation` rule verifies —
    # the Content child has no WDBC source, so `bound.tables` cannot express its domain.
    content = read_bound_content(client_root / "Content", policy=policy)
    content_records = content.records

    # === TWO-PASS attribution (design B / M1.14B): pass 1 builds the authoritative CoA attribution from
    # CharacterAdvancement + the proven skill-line index; pass 2 (below) streams the Spell table using it.
    # `coa_attribution.is_coa` is NEVER the `spell_id >= 100000` id floor (that is `id_range` provenance
    # only — it tags ~139k enemy/NPC/aura/dev spells and would distort the projection, closure, coverage).
    # --- advancement pipeline: read the CoA advancement graph, attribute spells, and prove parity ---
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

    # === PASS 2 (STREAMING, E0R.1 T4.1): the AUTHORITATIVE CoA spell-id set (graph attribution + proven
    # skill-line fallback) drives is_coa. Each producer row is serialized straight into an anonymous SPOOL
    # file, keeping only a (spell_id, offset, length) index in memory; the children are then written in
    # ascending spell_id by seeking the spool — no whole-table row list, no whole-child body (design A4). ===
    out_dir.mkdir(parents=True, exist_ok=True)
    coa_attributed_ids = {sid for sid, sa in spell_attr.items() if sa.result.is_coa}
    adv_spell_ids = {n.spell_id for n in coa_nodes if n.spell_id}
    spell_names: dict[int, str] = {}                 # names ONLY for graph-attributed ids (bounded by graph)

    def _spool(row_iter, per_row=None):
        fh = tempfile.TemporaryFile(dir=out_dir)
        index, offset = [], 0
        for row in row_iter:
            if per_row is not None:
                per_row(row)
            line = (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
            fh.write(line)
            index.append((row["spell_id"], offset, len(line)))
            offset += len(line)
        index.sort()
        return fh, index

    def _spool_lines(fh, index):
        for _sid, offset, length in index:
            fh.seek(offset)
            yield fh.read(length)

    full_is_coa: set[int] = set()
    # E0R.2 T4.1: observation coverage rides the streaming write loop's existing per-row hook — counters
    # only, so the single pass and the bounded retention are both preserved.
    observations = observation_accumulator()

    def _observe_full(row):
        observations.observe(row)
        if row["coa_attribution"].get("is_coa") is True:
            full_is_coa.add(row["spell_id"])
        if row["spell_id"] in adv_spell_ids:
            spell_names[row["spell_id"]] = row.get("name") or ""

    full_spool, full_index = _spool(
        iter_spell_records(spell_view, side_views, policy=policy, provenance=provenance,
                           coa_spell_ids=coa_attributed_ids), _observe_full)
    # E0R.2 T6.3: ONE pass emits the associations and accumulates the asset table beside them — 14,022
    # assets against 208,447 associations, so the table is counter-scale while the stream stays a stream.
    icon_assets = icon_asset_table()
    icon_spool, icon_index = _spool(
        iter_icon_catalog(spell_view, side_views, policy=policy, asset_resolver=asset_resolver,
                          assets=icon_assets))
    # Honest resolved-icon coverage: a streaming pass over the spool (never a row list).
    icon_cov = icon_coverage((json.loads(line) for line in _spool_lines(icon_spool, icon_index)),
                             icon_assets)

    def _projection_rows():
        # The projection is the RICH form: each compact `raw` cell expands into a canonical field
        # observation (project_v3_row), and the row carries NO compact `raw` — full=compact,
        # projection=rich, disjoint dialects. Streamed from the spool in ascending spell_id.
        for sid, offset, length in full_index:
            if sid in full_is_coa:
                full_spool.seek(offset)
                yield project_v3_row(json.loads(full_spool.read(length)), policy)

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
    # current names come from the already-extracted spell records (Spell.dbc), not the CA string block —
    # collected during the spool pass for graph-attributed ids only (bounded by the graph, not the table).
    adv_records = build_advancement_records(coa_nodes, provenance=adv_provenance,
                                            spell_names=spell_names, attribution=spell_attr)
    class_type_records = build_class_type_records(class_types)
    tab_type_records = build_tab_type_records(tab_types)
    essence_records = build_essence_raw_records(ess_raw, provenance=essence_provenance)  # raw; undecoded

    # === stage the candidate generation: every REQUIRED_CHILD streamed into gen-<uuid>/ (design A5). The
    # generation's manifest-v3 is the AUTHORITATIVE manifest; the fixed-path summary below is noncanonical.
    projection_manifest = {
        "schema_version": "coa-client-spell-projection-manifest-v3",
        "inclusion_rule": {"predicate": "coa_attribution.is_coa == true", "version": "m1.14e0r"},
        "client_build": client_build, "extractor_commit": _extractor_commit(),
        "extraction_date": date.today().isoformat(), "policy_sha256": policy.sha256,
        "counts": {"source_records": len(full_index), "projected_records": len(full_is_coa),
                   "unique_spell_ids": len(full_is_coa)},
    }
    base_manifest = build_manifest(
        backend_name=getattr(backend, "name", "unknown"),
        backend_version=getattr(backend, "version", "unknown"),
        stormlib_version=getattr(backend, "stormlib_version", None),
        client_root=str(client_root), client_build=client_build, outputs={},
        archive_plan=plan.to_dict())
    base_manifest["icon_coverage"] = icon_cov          # rides in the authoritative generation manifest-v3
    # Two coverages, two denominators: icons count SPELLS, observations count raw CELLS (E0R.2 T4.1).
    base_manifest["observation_coverage"] = observations.result()
    base_manifest["benchmark_env"] = benchmark_env()   # reproducible env pin for the budget (T4.3)
    gw = GenerationWriter(out_dir)
    gw.add_jsonl_lines("coa_client_spell.jsonl", _spool_lines(full_spool, full_index),
                       schema_version="coa-client-spell-v4")
    gw.add_jsonl("coa_client_spell_coa.jsonl", _projection_rows(),
                 schema_version="coa-client-spell-projection-v3")
    gw.add_json("coa_client_spell_projection.manifest.json", projection_manifest,
                schema_version="coa-client-spell-projection-manifest-v3")
    gw.add_jsonl_lines("coa_client_spell_icons.jsonl", _spool_lines(icon_spool, icon_index),
                       schema_version=ICON_ASSOCIATION_SCHEMA)
    gw.add_jsonl(ICON_ASSET_CHILD, icon_assets.rows(), schema_version=ICON_ASSET_SCHEMA)
    full_spool.close()
    icon_spool.close()
    gw.add_jsonl("coa_client_content.jsonl", content_records, schema_version="coa-client-content-v1")
    gw.add_json("coa_client_archive_plan.json", plan.to_dict(), schema_version="coa-client-archive-plan-v1")
    gw.add_jsonl("coa_client_advancement.jsonl", adv_records, schema_version="coa-client-advancement-v1")
    gw.add_jsonl("coa_client_class_types.jsonl", class_type_records, schema_version="coa-client-class-types-v1")
    gw.add_jsonl("coa_client_tab_types.jsonl", tab_type_records, schema_version="coa-client-tab-types-v1")
    gw.add_jsonl("coa_client_essence.jsonl", essence_records, schema_version="coa-client-essence-v1")
    gw.add_json("spell_layout_v2.json", policy.doc, schema_version="coa-spell-layout-v2")  # reviewed policy child
    # E0R.2 T6.2: a v4 row is only decodable WITH these two. The descriptors carry what every cell used
    # to repeat (policy_ref, join_name); the wire schema carries what `s`/`d` mean. Both travel with the
    # generation so a consumer holding only the generation can read it — and both are re-derived from
    # trusted sources by each validator rather than believed.
    gw.add_json(FIELD_DESCRIPTORS_CHILD, build_field_descriptors(policy.doc),
                schema_version=FIELD_DESCRIPTORS_SCHEMA)
    gw.add_json(WIRE_SCHEMA_CHILD, load_observation_wire_schema(),
                schema_version="coa-observation-wire-v1")
    # The contract the generation is produced under travels WITH it (E0R.2 T1.1): staged as a child so a
    # consumer can re-check the generation under its own contract, and named in `binding` so the staged
    # copy is covered by candidate_trust_sha256 rather than trusted on its own word.
    contract_revision, generation_contract = load_current_contract()
    gw.add_json(GENERATION_CONTRACT_CHILD, generation_contract,
                schema_version=GENERATION_CONTRACT_SCHEMA)

    # Accounting identities for the two children that are FILTERED projections of their source rather
    # than 1:1 extractions (E0R.2 T2.1). `kept` and `rejected` are counted at the point of filtering, from
    # the source rows actually read — NOT back-derived from the staged child, which would make the
    # identity self-fulfilling. The validator checks kept + rejected against the REVIEWED source count and
    # kept against the emitted child, so a silent drop fails on one leg or the other.
    derivations = {
        "coa_client_advancement.jsonl": {
            "source": "CharacterAdvancement", "kept": len(adv_records),
            "rejected": len(nodes) - len(adv_records)},
        "coa_client_content.jsonl": content.derivation,
    }
    binding = {"topology": topology, "provenance": provenance, "policy_sha256": policy.sha256,
               "anchor_set_sha256": policy.anchor_sha256, "enum_policy_sha256": policy.enum_sha256,
               "derivations": derivations,
               "generation_contract": {"schema_version": GENERATION_CONTRACT_SCHEMA,
                                       "revision": contract_revision,
                                       "sha256": generation_contract_sha256(generation_contract)}}
    # === the transaction window: candidate -> validation -> parity -> budget -> pointer flip. The publish
    # lock is held from publish_candidate's predecessor read; ANY failure before the flip aborts (lock
    # released, pointer untouched, the candidate left never-pointer-resolvable) (design A5, E0R.1 T3.4). ===
    candidate = gw.publish_candidate(base_manifest=base_manifest, binding=binding,
                                     unknown_symbol_inventory=unknown_symbol_inventory)
    parity_sha = None
    try:
        # === validate the candidate BY PATH in BOTH Python and Node, before the pointer flips ===
        # Per-child integrity + the contract's whitelist and cardinality rules + the streaming cross-child
        # merge-join. The lock is the SAME artifact the Node boundary checks, so both trust boundaries
        # agree on which policy is locally supported (E0R.2 T2.1).
        validate_candidate_generation(gw.gen_dir, lock_path=node_lock_path)
        node_elapsed_s = node_peak_rss_mb = None
        if validate_with_node:
            node_started = _time.monotonic()
            _node_validate_candidate(gw.gen_dir, node_lock_path)  # independent Node trust boundary
            node_elapsed_s = round(_time.monotonic() - node_started, 4)
            # Linux RUSAGE_CHILDREN ru_maxrss (KiB): the max over reaped children — the node validator
            # dominates any earlier tiny subprocess (git rev-parse), so this pins the node boundary.
            node_peak_rss_mb = round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024, 1)

        # === Builder parity is part of the candidate stage: a parity failure ABORTS publication ===
        if builder_entries_path:
            parity_sha = _write_parity_report(
                out_dir, builder_entries_path, client_only_adjudication_path, coa_nodes=coa_nodes,
                class_types=class_types, ca_layout=ca_layout, plan=plan, ca_member=ca_member,
                ct_member=ct_member, tt_member=tt_member, ess_member=ess_member,
                spell_member=spell_member, ca_decode_report=ca_decode_report)

        # === budget over the ACTUAL serialized generation. POLICY-BOUND ceilings, always (E0R.1 T4.3:
        # per-child + whole-generation bytes, separate python/node RSS+elapsed). E0R.2 T2.4 removed the
        # legacy three-part DEFAULT_BUDGET fallback: it applied whenever a policy declared no budget
        # block, which silently swapped the reviewed ceilings for hard-coded ones — an unreviewed budget
        # is not a budget. `budget=` remains as an explicit same-shape OVERRIDE for probes. ===
        elapsed_s = round(_time.monotonic() - started, 4)
        peak_rss_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)  # Linux ru_maxrss is KiB
        policy_ceilings = budget if budget is not None else policy.doc.get("budget")
        if policy_ceilings is None:
            raise PublishError(
                "the reviewed policy declares no budget block; refusing to publish against unreviewed "
                "ceilings")
        budget_report = policy_budget_report(
            children=gw._children,
            measured={"python_peak_rss_mb": peak_rss_mb, "python_elapsed_s": elapsed_s,
                      "node_peak_rss_mb": node_peak_rss_mb, "node_elapsed_s": node_elapsed_s},
            budget=policy_ceilings)
        if not budget_report["within_budget"]:
            raise PublishError(f"regenerate exceeded the budget: {budget_report['breach']}")

        # === publish the pointer LAST (candidate -> published; the trust digest reproduced identically) ===
        gw.finalize_and_publish(candidate_manifest=candidate,
                                validation={"python": True, "node": bool(validate_with_node)},
                                budget=budget_report)
    finally:
        gw.abort_publication()      # idempotent: releases the publish lock on failure; no-op after finalize

    outputs = {name: meta["sha256"] for name, meta in gw._children.items()}
    if parity_sha is not None:
        outputs["coa_builder_parity_report.json"] = parity_sha
    try:
        outputs["coa_client_extract.pointer.json"] = _sha256_bytes(
            (out_dir / "coa_client_extract.pointer.json").read_bytes())
    except OSError:
        outputs["coa_client_extract.pointer.json"] = None    # summary detail; never fails a publication

    # Noncanonical fixed-path compatibility summary, produced AFTER publication — never a generation child
    # and never able to make regenerate() fail once the pointer flipped (design A5, ENFORCED below: the
    # write is best-effort and a failure is reported in-band). The authoritative manifest is
    # gen-<uuid>/manifest.json (coa-client-extract-manifest-v3).
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
    manifest["icon_coverage"] = icon_cov
    manifest["observation_coverage"] = observations.result()
    try:
        write_json(manifest, out_dir / "coa_client_extract_manifest.json")
    except OSError as exc:
        manifest["summary_write_error"] = str(exc)           # reported in-band; publication already complete
    return manifest


def _write_parity_report(out_dir: Path, builder_entries_path, client_only_adjudication_path, *,
                         coa_nodes, class_types, ca_layout, plan, ca_member, ct_member, tt_member,
                         ess_member, spell_member, ca_decode_report) -> str:
    """Build + write the Builder parity report DURING the candidate stage (E0R.1 T3.4): any failure here
    (unreadable/malformed builder entries, a parity invariant, the report write itself) aborts publication
    before the pointer flips. Returns the written report's sha256 for the fixed-path summary outputs."""
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
    return write_json(report, out_dir / "coa_builder_parity_report.json")


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


class AcceptanceError(RuntimeError):
    """An acceptance record was requested for a run that is not acceptable. E0R.1 T6.2: the summary is a
    BINDING attestation, so every claim in it must come from a resolved generation, a committed recon
    report, and an executed build — never from a caller's assertion."""


def _normalized_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _require_executed_build_mechanics(build_mechanics: dict) -> dict:
    """The canonical build must have RUN, under the network trap, pointer-only, and succeeded. Each fact is
    a measurement the acceptance run produced; a caller cannot simply assert them."""
    if not isinstance(build_mechanics, dict) or build_mechanics.get("executed") is not True:
        raise AcceptanceError(
            "build_mechanics must be an executed measurement (executed=True with the command, exit code, "
            "network-trap result and pointer-only evidence), not a caller-asserted boolean")
    if build_mechanics.get("exit_code") != 0:
        raise AcceptanceError(f"build-mechanics failed (exit_code={build_mechanics.get('exit_code')!r})")
    attempts = build_mechanics.get("network_attempts")
    if attempts is None or attempts != 0:
        raise AcceptanceError(f"build-mechanics made {attempts!r} network attempt(s) under the trap; a "
                              "canonical build must be network-free")
    if build_mechanics.get("pointer_only") is not True:
        raise AcceptanceError("build-mechanics was not pointer-only; a canonical build reads ONLY the "
                              "published generation pointer")
    return dict(build_mechanics)


MECHANICS_MANIFEST_NAME = "coa_mechanics.manifest.json"
# The five identities a canonical mechanics build must record about ITS OWN inputs. Each names a
# different way the build could have read something other than the generation under acceptance.
MECHANICS_BINDING_KEYS = ("builder_entries_sha256", "input_generation_id", "policy_sha256",
                          "pointer_manifest_sha256", "projection_child_sha256")
# Fail closed rather than record `{}`: an absent coverage block is an unmeasured run, not a clean one.
GENERATION_COVERAGE_KEYS = ("icon_coverage", "observation_coverage")
MECHANICS_COVERAGE_KEYS = ("field_readiness_coverage", "per_field_winner_counts_by_source")


def _under_scraper(scraper_dir: Path, path: Path) -> Path:
    """Resolve a build input/output exactly as the build itself does: the canonical run spawns with
    cwd=<scraper dir>, so a relative path (`dist/coa_entries.jsonl`) means scraper-relative. Hashing it
    against the record-writer's own cwd instead would hash a different file, or none."""
    path = Path(path)
    return path if path.is_absolute() else Path(scraper_dir) / path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_and_count_jsonl(path: Path) -> tuple[str, int]:
    """Hash and count the emitted artifact ITSELF, streaming. What the build's manifest claims about its
    own output is a claim; this is the measurement."""
    digest, records = hashlib.sha256(), 0
    with Path(path).open("rb") as handle:
        for line in handle:
            digest.update(line)
            if line.strip():
                records += 1
    return digest.hexdigest(), records


def _unique_builder_spell_ids(path: Path) -> int:
    """The Builder domain the canonical build must cover, counted by the same grouping key the build uses
    (`buildCanonicalMechanics` emits one row per unique, finite `spell_id`)."""
    seen: set[int] = set()
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                seen.add(int(json.loads(line)["spell_id"]))
            except (KeyError, TypeError, ValueError):
                continue
    return len(seen)


def _pointer_identity(dist: Path) -> tuple[str, str]:
    """The active generation's identity as the pointer states it: WHICH generation, and which manifest
    bytes. Read as a pair — a rewritten manifest under an unchanged id moves only the second."""
    from .publish import POINTER_NAME

    path = Path(dist) / POINTER_NAME
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AcceptanceError(f"active generation pointer unreadable: {exc}") from exc
    return doc.get("generation_id"), doc.get("manifest_sha256")


def _require_recon_binding(recon_report: dict, manifest: dict) -> str:
    """One equality over one canonical object, computed independently from the recon report and from
    `manifest.binding`. A recon of a different capture, a different policy, a different absent-table
    state or a different schema cannot bind to this generation."""
    from .spell_mechanics import generation_binding_facts, recon_binding_digest, recon_binding_facts

    try:
        from_recon = recon_binding_digest(**recon_binding_facts(recon_report))
    except ValueError as exc:
        raise AcceptanceError(f"the recon report cannot be bound: {exc}") from exc
    try:
        from_generation = recon_binding_digest(**generation_binding_facts(manifest.get("binding") or {}))
    except ValueError as exc:
        raise AcceptanceError(f"the published generation cannot be bound: {exc}") from exc
    if from_recon != from_generation:
        raise AcceptanceError(
            "recon binding digest mismatch: the recon report describes a different run from the one this "
            f"generation was published under (recon {from_recon}, generation {from_generation})")
    return from_recon


def _require_generation_facts(manifest: dict) -> dict:
    """The generation-side facts the record must carry, required BEFORE the build runs — a generation
    that can never be accepted must not spend a canonical build first (T4.2)."""
    for key in GENERATION_COVERAGE_KEYS:
        if not manifest.get(key):
            raise AcceptanceError(f"the published generation records no {key}; an unmeasured run cannot "
                                  "be accepted as a clean one")
    contract = (manifest.get("binding") or {}).get("generation_contract")
    if not isinstance(contract, dict) or not contract.get("revision") or not contract.get("sha256"):
        raise AcceptanceError("the published generation names no generation contract revision")
    return contract


def _require_mechanics_artifacts(mech_dir: Path, *, generation_id: str, manifest_sha256: str,
                                 manifest: dict, builder_entries: Path) -> dict:
    """Check the mechanics build against the ARTIFACTS it left, not against its own summary of them."""
    path = Path(mech_dir) / MECHANICS_MANIFEST_NAME
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AcceptanceError(f"mechanics manifest unreadable at {path}: {exc}") from exc

    binding = doc.get("binding")
    if not isinstance(binding, dict) or set(binding) != set(MECHANICS_BINDING_KEYS):
        raise AcceptanceError(
            f"the mechanics manifest records no input-identity binding ({sorted(MECHANICS_BINDING_KEYS)}); "
            "a build that does not say what it read cannot be bound to a generation")
    children = manifest.get("children") or {}
    expected = {
        "input_generation_id": generation_id,
        "pointer_manifest_sha256": manifest_sha256,
        "policy_sha256": (manifest.get("binding") or {}).get("policy_sha256"),
        "projection_child_sha256": (children.get("coa_client_spell_coa.jsonl") or {}).get("sha256"),
        "builder_entries_sha256": _sha256_file(builder_entries),
    }
    for key in MECHANICS_BINDING_KEYS:
        if binding.get(key) != expected[key]:
            raise AcceptanceError(f"the mechanics build's {key} is {binding.get(key)!r}, not this "
                                  f"generation's {expected[key]!r}")

    outputs = doc.get("outputs") or {}
    jsonl = Path(mech_dir) / str(outputs.get("mechanics_jsonl") or "")
    if not jsonl.is_file():
        raise AcceptanceError(f"the mechanics build emitted no {outputs.get('mechanics_jsonl')!r}")
    recomputed, records = _hash_and_count_jsonl(jsonl)
    if outputs.get("sha256") != recomputed:
        raise AcceptanceError(f"mechanics jsonl sha256 mismatch: the manifest claims "
                              f"{outputs.get('sha256')!r}, {jsonl.name} hashes to {recomputed}")
    if outputs.get("record_count") != records:
        raise AcceptanceError(f"mechanics jsonl record count mismatch: the manifest claims "
                              f"{outputs.get('record_count')!r}, {jsonl.name} holds {records}")
    unique = _unique_builder_spell_ids(builder_entries)
    if records != unique:
        raise AcceptanceError(
            f"incomplete mechanics build: record_count {records} does not cover the {unique} unique "
            "builder spell ids. Completeness, not non-emptiness — a build that silently dropped rows "
            "still emits a plausible-looking artifact")
    for key in MECHANICS_COVERAGE_KEYS:
        if not doc.get(key):
            raise AcceptanceError(f"the mechanics manifest records no {key}; an unmeasured build cannot "
                                  "be accepted as a covered one")
    return {"manifest_path": str(path), "manifest_sha256": _sha256_file(path),
            "jsonl": jsonl.name, "jsonl_sha256": recomputed, "record_count": records,
            "builder_unique_spell_ids": unique, "binding": binding,
            "client_build": doc.get("client_build"), "canonical": doc.get("canonical"),
            "coverage": doc.get("coverage"),
            "readiness_coverage": doc["field_readiness_coverage"],
            "source_coverage": doc["per_field_winner_counts_by_source"]}


def run_acceptance(dist: Path, *, recon_report_path: Path, scraper_dir: Path, builder_entries: Path,
                   mechanics_out: Path, benchmark_env_id: str = "local", out: Path | None = None,
                   node: str = "node") -> dict:
    """Run the acceptance and write the record (v3). Every claim is derived, never accepted:

    * the generation is RESOLVED here (strict V3 / published / both-language validation / within budget),
      so a caller cannot hand in a fabricated manifest or its own publication verdict;
    * the recon report is read from disk, COMMITTED into the record in normalized form, bound by its
      sha256, and required to be `verified`;
    * the recon is BOUND to this generation by a canonical identity digest computed independently from
      the report and from `manifest.binding` (E0R.2 T4.3) — a recon of a different capture, policy or
      absent-table state cannot be accepted merely for saying `verified`;
    * the canonical build is EXECUTED here, under the network trap, and `pointer_only`, the trap result
      and the runtime measurement come from that run;
    * the pointer is re-read afterwards on BOTH identities, so a publish landing under the build cannot
      combine two generations' measurements into one attestation;
    * the mechanics artifacts are hashed and counted HERE, and the count must cover the whole Builder
      domain — `record_count > 0` would accept a build that silently dropped most of it;
    * coverage counts ride along from the authoritative manifest of the layer that owns them: icon and
      observation from the GENERATION, readiness and source from the executed BUILD.

    E0R.2 T4.2: this replaces `write_acceptance_summary(..., build_mechanics=...)`, which took the
    measurement as a PARAMETER. It checked that measurement hard — executed, exit 0, zero network
    attempts, pointer-only — but every check ran against a dict the caller supplied. The CLI happened to
    pass a real one; nothing in the function required that. A record whose central attestation is
    "whatever I was told" is not an attestation, so the executor moves inside and the seam disappears.

    Order matters: resolve, then validate the recon, and only THEN execute. A run that can never be
    accepted must not spend a full canonical build first.

    A record OF a clean run — never part of the commit it attests to.
    """

    from .publish import POINTER_NAME, ResolveError, resolve_active_generation

    dist = Path(dist)
    try:
        resolved = resolve_active_generation(dist)
    except ResolveError as exc:
        raise AcceptanceError(f"no acceptable published generation: {exc}") from exc
    manifest = resolved["manifest"]
    generation_contract = _require_generation_facts(manifest)

    report_path = Path(recon_report_path)
    if not report_path.is_file():
        raise AcceptanceError(f"recon report not found: {report_path}")
    try:
        recon_report = json.loads(report_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise AcceptanceError(f"recon report is not valid JSON: {exc}") from exc
    recon_status = recon_report.get("status")
    if recon_status != "verified":
        raise AcceptanceError(f"recon status is {recon_status!r}; acceptance requires a verified recon")
    normalized_report = _normalized_json(recon_report)
    recon_binding_sha256 = _require_recon_binding(recon_report, manifest)

    generation_id, manifest_sha256 = _pointer_identity(dist)

    # === EXECUTE, then require what the execution produced (E0R.2 T4.2) ===
    # Looked up through the module so a test can substitute the executor and still prove it was CALLED —
    # the one thing a fabricated-measurement parameter could never demonstrate.
    measured = _require_executed_build_mechanics(run_measured_build_mechanics(
        Path(scraper_dir), dist / POINTER_NAME,
        builder_entries=builder_entries, out_dir=mechanics_out, node=node))

    # The pointer is read at the START to run the build and again HERE, on both identities: a publish
    # that landed under the build would otherwise put one generation's measurements in another's record.
    after_id, after_sha256 = _pointer_identity(dist)
    if after_id != generation_id:
        raise AcceptanceError(f"the active generation pointer moved during the build: {generation_id} -> "
                              f"{after_id}; the measurements and the generation are not the same run")
    if after_sha256 != manifest_sha256:
        raise AcceptanceError(f"the active generation's manifest_sha256 changed during the build: "
                              f"{manifest_sha256} -> {after_sha256}")
    try:
        resolve_active_generation(dist)
    except ResolveError as exc:
        raise AcceptanceError(f"the generation no longer resolves after the build: {exc}") from exc

    mechanics = _require_mechanics_artifacts(
        _under_scraper(scraper_dir, mechanics_out), generation_id=generation_id,
        manifest_sha256=manifest_sha256, manifest=manifest,
        builder_entries=_under_scraper(scraper_dir, builder_entries))
    # The two mechanics-layer coverage blocks are reported once, under `coverage`, beside the two
    # generation-layer ones — four denominators in one place rather than two of them buried per layer.
    readiness_coverage = mechanics.pop("readiness_coverage")
    source_coverage = mechanics.pop("source_coverage")

    children = {name: {"sha256": meta.get("sha256"), "byte_length": meta.get("byte_length"),
                       "records": meta.get("records"), "schema_version": meta.get("schema_version")}
                for name, meta in (manifest.get("children") or {}).items()}
    binding = manifest.get("binding") or {}

    summary = {
        "schema_version": "coa-e0r-acceptance-summary-v3",
        "client_build": manifest.get("client_build"),
        "generation_id": manifest.get("generation_id"),
        "predecessor_generation_id": manifest.get("predecessor_generation_id"),
        "manifest_schema_version": manifest.get("schema_version"),
        "manifest_sha256": manifest_sha256,
        "candidate_trust_sha256": manifest.get("candidate_trust_sha256"),
        "publication_state": manifest.get("publication_state"),
        "validation": manifest.get("validation"),
        "budget": manifest.get("budget"),
        "policy_sha256": binding.get("policy_sha256"),
        "extractor_commit": manifest.get("extractor_commit") or _extractor_commit(),
        "benchmark_env_id": benchmark_env_id,
        "benchmark_env": manifest.get("benchmark_env"),
        "generation_contract": generation_contract,
        "children": children,
        "coverage": {
            # E0R.2 T4.1 split the two layers, T4.3 bound each half to the manifest that owns it. `icon`
            # and `observation` are GENERATION facts; `readiness` and `source` are MECHANICS facts and
            # were read from the generation manifest until now — which never carried them, so both were
            # `{}` in every record ever written. All four are required, never defaulted.
            "icon": manifest["icon_coverage"],
            "observation": manifest["observation_coverage"],
            "readiness": readiness_coverage,
            "source": source_coverage,
        },
        "recon_status": recon_status,
        "recon_report_path": str(report_path),
        # Two hashes, two jobs: the identity is what must MATCH this generation, the report hash is what
        # the record ATTESTS to. Everything outside the identity (scan metrics, budget measurements,
        # proposed_policy_delta) moves only the second — so neither substitutes for the other.
        "recon_binding_sha256": recon_binding_sha256,
        "recon_report_sha256": hashlib.sha256(normalized_report.encode("utf-8")).hexdigest(),
        "recon_report": recon_report,
        "build_mechanics": measured,
        "mechanics": mechanics,
        "generated_at": date.today().isoformat(),
    }
    if out is not None:
        write_json(summary, Path(out))
    return summary


def run_measured_build_mechanics(scraper_dir: Path, pointer_path: Path, *, builder_entries: Path,
                                 out_dir: Path, node: str = "node") -> dict:
    """EXECUTE the canonical, pointer-only build under the runnable network trap and MEASURE it (E0R.1
    T6.2). Returns the evidence the acceptance summary requires: the exact command, its exit code, the
    trap's attempt count, the pointer-only derivation (read back out of the emitted mechanics manifest,
    not from the flags we passed), and the runtime measurement."""
    import resource
    import subprocess
    import tempfile
    import time

    scraper_dir = Path(scraper_dir)
    # The build runs with cwd=<scraper dir>, so the pointer — which the caller names relative to ITS OWN
    # cwd (e.g. reports/client_extract/...) — must be absolute or it resolves against the wrong directory
    # and the canonical build exits 2. `builder_entries`/`out_dir` are deliberately scraper-relative.
    pointer_path = Path(pointer_path).resolve()
    cmd = [node, "--import", "./scripts/network-trap.mjs", "scripts/build-mechanics-artifacts.mjs",
           "--builder-entries", str(builder_entries),
           "--client-extract-pointer", str(pointer_path),
           "--out", str(out_dir)]
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        trap_log = Path(handle.name)
    env = {**os.environ, "COA_NETWORK_TRAP_LOG": str(trap_log)}
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    started = time.monotonic()
    proc = subprocess.run(cmd, cwd=scraper_dir, env=env, capture_output=True, text=True)
    elapsed_s = round(time.monotonic() - started, 3)
    after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss

    try:
        trap = json.loads(trap_log.read_text(encoding="utf-8"))
        network_attempts = int(trap.get("attempts"))
    except (OSError, ValueError, TypeError):
        network_attempts = None                      # unproven trap -> the writer refuses
    finally:
        trap_log.unlink(missing_ok=True)

    # pointer_only is DERIVED from what the build recorded about its own inputs: a canonical run reads the
    # projection children out of the resolved generation and names no legacy fixed-path/DB input.
    pointer_only = None
    mech_manifest = Path(out_dir)
    if not mech_manifest.is_absolute():
        mech_manifest = scraper_dir / mech_manifest
    mech_manifest = mech_manifest / "coa_mechanics.manifest.json"
    if proc.returncode == 0 and mech_manifest.is_file():
        try:
            emitted = json.loads(mech_manifest.read_text(encoding="utf-8"))
            inputs = emitted.get("inputs") or {}
            gen_dir = str(Path(pointer_path).parent)
            pointer_only = bool(
                emitted.get("canonical") is True
                and emitted.get("fallback_authorized") is not True
                and inputs.get("db_spell_tooltips") in (None, "")
                and str((inputs.get("projection") or {}).get("path") or "").startswith(gen_dir)
            )
        except (OSError, ValueError):
            pointer_only = None

    return {
        "executed": True,
        "command": cmd,
        "cwd": str(scraper_dir),
        "exit_code": proc.returncode,
        "network_attempts": network_attempts,
        "pointer_only": pointer_only,
        "elapsed_s": elapsed_s,
        "peak_rss_mb": round(max(after - before, after) / 1024, 1),
        "stderr_tail": proc.stderr[-2000:] if proc.stderr else "",
    }


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


def _node_validate_candidate(gen_dir: Path, lock_path: Path | None = None) -> None:
    """Run the independent Node trust boundary against the staged CANDIDATE generation by path, before the
    pointer flips (design A5). A non-zero exit fails the canonical publish closed. `lock_path` overrides the
    committed policy lock the staged policy child is checked against (production uses the committed lock)."""
    import subprocess
    from .publish import PublishError
    script = Path(__file__).resolve().parents[1] / "coa_scraper" / "scripts" / "lib" / "generation.mjs"
    cmd = ["node", str(script), "--candidate", str(gen_dir)]
    if lock_path is not None:
        cmd += ["--lock", str(lock_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
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
    acc.add_argument("--recon-report", required=True, type=Path,
                     help="the mechanics-recon report to COMMIT into the record; must be status=verified")
    acc.add_argument("--scraper-dir", type=Path, default=Path("coa_scraper"),
                     help="where the canonical build-mechanics run is executed under the network trap")
    acc.add_argument("--builder-entries", type=Path, default=Path("dist/coa_entries.jsonl"))
    acc.add_argument("--mechanics-out", type=Path, default=Path("dist"))
    acc.add_argument("--benchmark-env-id", default="local")
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
        # E0R.2 T4.2: ONE call. The canonical build is executed inside `run_acceptance`, under the trap,
        # after the generation resolves and the recon is verified — so the record can only ever describe
        # a build the record-writer itself ran, and an unacceptable run never pays for one.
        try:
            run_acceptance(args.dist, recon_report_path=args.recon_report,
                           scraper_dir=args.scraper_dir, builder_entries=args.builder_entries,
                           mechanics_out=args.mechanics_out,
                           benchmark_env_id=args.benchmark_env_id, out=args.out)
        except AcceptanceError as exc:
            print(f"error: acceptance refused: {exc}", file=sys.stderr)
            return 5
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
    from .spell_mechanics import recon_spell_mechanics
    from .artifacts import write_json

    if backend is None:
        from .stormlib_backend import StormLibBackend
        backend = StormLibBackend(stormlib_path=stormlib_path)  # may raise BackendUnavailable

    plan = discover_plan(client_root)
    policy = spell_policy or load_default_policy()
    root, attach = plan.open_chain
    # E0R.1: the join value-anchors + the static power_type negative anchor are MANDATORY recon inputs.
    # They live in the reviewed anchor_set (authored in T1.2/T1.3); absent them the join/negative probes
    # cannot run, so recon cannot reach `verified` (the state machine records the unprobed joins).
    join_value_anchors = policy.anchor_set.get("joins")
    power_type_anchors = policy.anchor_set.get("power_type_static")
    report = recon_spell_mechanics(
        backend, root, attach, spell_policy=policy, anchors=policy.anchors,
        extractor_commit=_extractor_commit(), client_build=_client_build(plan),
        join_value_anchors=join_value_anchors, power_type_anchors=power_type_anchors)
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
