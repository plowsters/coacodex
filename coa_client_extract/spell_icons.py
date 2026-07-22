# coa_client_extract/spell_icons.py
"""The coa-client-spell-icons-v1 catalog: for every spell whose icon join RESOLVES, the client icon path
plus the hash of the ACTUAL BLP bytes (never the path string) read via an injected asset resolver, with
asset entries deduplicated by client_path. This is a separate output family from spell mechanics because
the icon is a string-valued join whose asset bytes live in the MPQ chain, not in Spell.dbc.

Resolution is routed through `make_string_join` + promotion (E0R.1 T2.3): a resolved path is emitted only
when the icon join AND its components are promotion-eligible (WS1 adjudicated the index cell); otherwise the
row is a `placeholder`. `missing` is reserved for a PROVEN path whose client BLP member is absent from the
chain -- it is NOT the fk-0 / no-side-row case, which the join reports as not_applicable / unresolved.
"""
from __future__ import annotations

import hashlib

from .contracts import policy_ref, policy_ref_component
from .spell_proof import FieldProof, make_envelope, make_string_join, make_string_observation

SCHEMA = "coa-client-spell-icons-v1"


def _proof(fp) -> FieldProof:
    # Records opened via a bound RecordView have verified structural integrity; layout+interpretation come
    # from the reviewed policy (compose_proof takes the weakest facet across the join's components).
    return FieldProof("verified", fp.layout, fp.interpretation)


def _placeholder(spell_id: int, fk: int | None) -> dict:
    """An unresolved icon join (index unadjudicated, fk 0, no side row, or a withheld promotion): there is
    no proven client path, so the row is a placeholder with unavailable readiness and no asset."""
    return {"schema_version": SCHEMA, "spell_id": spell_id, "spell_icon_id": fk,
            "client_path": None, "source_asset_sha256": None, "source_archive": None,
            "asset_status": "placeholder", "readiness": "unavailable"}


def iter_icon_catalog(spell_view, side_views, *, policy, asset_resolver):
    """Stream coa-client-spell-icons-v1 over the FULL-table domain. `asset_resolver(client_path) ->
    {bytes, archive, member, patch_chain} | None` reads the effective client BLP member; source_asset_sha256
    hashes those ACTUAL BLP bytes, and a resolved path with no member is `missing`. Emits {spell_id,
    spell_icon_id, client_path, source_asset_sha256, source_archive, asset_status, readiness}."""
    join = policy.joins["spell_icon_id"]
    icon_view = side_views.get(join.side_table)
    side_fields = policy.tables[join.side_table]["fields"]
    id_fp, path_fp = side_fields["id"], side_fields[join.side_value_field]
    by_id = {r.u32(id_fp.cell): r for r in icon_view.records()} if icon_view else {}
    asset_cache: dict[str, dict] = {}                    # client_path -> resolved asset facts (dedup)
    idx_fp = policy.tables["Spell"]["fields"][join.index_field]
    spell_id_cell = policy.tables["Spell"]["fields"]["id"].cell
    spec = {"index_field": join.index_field, "side_table": join.side_table,
            "side_value_field": join.side_value_field}
    idx_ref = policy_ref("Spell", join.index_field)

    for rec in spell_view.records():
        spell_id = rec.u32(spell_id_cell)
        # WS1 never adjudicated the icon index (null FK cell): the join is ambiguous -> placeholder only.
        if idx_fp.cell is None:
            yield _placeholder(spell_id, None)
            continue
        fk = rec.u32(idx_fp.cell)
        idx_env = make_envelope(fk, kind=idx_fp.kind, proof=_proof(idx_fp), evidence_ref=idx_ref)
        if fk == 0:                                       # index_zero -> not_applicable
            make_string_join({"index": idx_env}, resolution="index_zero")
            yield _placeholder(spell_id, fk)
            continue
        side = by_id.get(fk)
        if side is None:                                  # nonzero FK, no side row -> unresolved
            make_string_join({"index": idx_env}, resolution="side_row_missing")
            yield _placeholder(spell_id, fk)
            continue
        side_id_env = make_envelope(side.u32(id_fp.cell), kind=id_fp.kind, proof=_proof(id_fp),
                                    evidence_ref=policy_ref_component(spec, "side_id"))
        poff = side.u32(path_fp.cell)
        path_sob = make_string_observation(poff, icon_view.read_string(poff), proof=_proof(path_fp),
                                           evidence_ref=policy_ref_component(spec, "side_value"))
        jo = make_string_join({"index": idx_env, "side_id": side_id_env, "side_value": path_sob},
                              resolution="resolved")
        client_path = jo.decoded if jo.decoded_reason == "decoded" else None
        if not client_path:                               # withheld promotion or empty path -> placeholder
            yield _placeholder(spell_id, fk)
            continue
        if client_path not in asset_cache:
            resolved = asset_resolver(client_path)        # reads the effective BLP member once per path
            if resolved is None:
                asset_cache[client_path] = {"sha256": None, "archive": None, "status": "missing"}
            else:
                asset_cache[client_path] = {"sha256": hashlib.sha256(resolved["bytes"]).hexdigest(),
                                            "archive": resolved["archive"], "status": "source_only"}
        a = asset_cache[client_path]
        yield {"schema_version": SCHEMA, "spell_id": spell_id, "spell_icon_id": fk,
               "client_path": client_path, "source_asset_sha256": a["sha256"], "source_archive": a["archive"],
               "asset_status": a["status"],
               "readiness": "available" if a["status"] == "source_only" else "unavailable"}


def icon_coverage(rows) -> dict:
    """Honest resolved-icon coverage over a catalog stream (single pass — never materializes the rows;
    E0R.1 T4.1). A `resolved_path` is a row that carries a proven client_path (asset_status source_only/
    converted/missing); a `placeholder` is an unresolved join. Assets split into present
    (source_only/converted) vs missing (proven path, absent member)."""
    spells = resolved = present = missing = placeholders = 0
    unique_paths: set[str] = set()
    for r in rows:
        spells += 1
        if r.get("client_path"):
            resolved += 1
            unique_paths.add(r["client_path"])
            if r["asset_status"] in ("source_only", "converted"):
                present += 1
            elif r["asset_status"] == "missing":
                missing += 1
        if r["asset_status"] == "placeholder":
            placeholders += 1
    return {"spells": spells, "resolved_paths": resolved, "assets_present": present,
            "assets_missing": missing, "placeholders": placeholders,
            "unique_paths": len(unique_paths)}
