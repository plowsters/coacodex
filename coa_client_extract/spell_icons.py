# coa_client_extract/spell_icons.py
"""The coa-client-spell-icons-v1 catalog: for every spell whose icon join resolves, the client icon path
plus the hash of the ACTUAL BLP bytes (never the path string) read via an injected asset resolver, with
asset entries deduplicated by client_path. This is a separate output family from spell mechanics because
the icon is a string-valued join whose asset bytes live in the MPQ chain, not in Spell.dbc.
"""
from __future__ import annotations

import hashlib

SCHEMA = "coa-client-spell-icons-v1"


def iter_icon_catalog(spell_view, side_views, *, policy, asset_resolver):
    """Stream coa-client-spell-icons-v1 over the FULL-table domain. `asset_resolver(client_path) ->
    {bytes, archive, member, patch_chain} | None` reads the effective client BLP member;
    source_asset_sha256 hashes those ACTUAL BLP bytes, and `missing` means the resolver found no client
    member. Emits {spell_id, spell_icon_id, client_path, source_asset_sha256, source_archive,
    asset_status, readiness}."""
    join = policy.joins["spell_icon_id"]
    icon_view = side_views.get(join.side_table)
    id_cell = policy.tables[join.side_table]["fields"]["id"].cell
    path_cell = policy.tables[join.side_table]["fields"][join.side_value_field].cell
    by_id = {r.u32(id_cell): r for r in icon_view.records()} if icon_view else {}
    asset_cache: dict[str, dict] = {}                    # client_path -> resolved asset facts (dedup)
    idx_cell = policy.tables["Spell"]["fields"][join.index_field].cell
    spell_id_cell = policy.tables["Spell"]["fields"]["id"].cell

    for rec in spell_view.records():
        spell_id = rec.u32(spell_id_cell)
        fk = rec.u32(idx_cell) if idx_cell is not None else 0
        side = by_id.get(fk)
        client_path = icon_view.read_string(side.u32(path_cell)) if (side is not None and icon_view) else None
        if not client_path:
            yield {"schema_version": SCHEMA, "spell_id": spell_id, "spell_icon_id": fk,
                   "client_path": None, "source_asset_sha256": None, "source_archive": None,
                   "asset_status": "missing", "readiness": "unavailable"}
            continue
        if client_path not in asset_cache:
            resolved = asset_resolver(client_path)          # reads the effective BLP member once per path
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
