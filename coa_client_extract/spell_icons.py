# coa_client_extract/spell_icons.py
"""The icon catalog, normalized (E0R.2 T6.3): an ASSET table keyed by a content-derived `asset_id`, and
one ASSOCIATION row per spell that references it.

The v1 catalog repeated the whole client path, its BLP hash and its source archive on every one of
179,774 rows over 14,022 distinct paths — 66.1 MB of a 523 MB generation. Splitting the two makes each
fact appear once, and the association row shrinks to a reference plus its two interned observation codes.

Those codes are the second half of the change. The v1 row computed
`jo.decoded if jo.decoded_reason == "decoded" else None`, so FOUR different situations arrived as one
`placeholder`: no FK at all (`index_zero`), a nonzero FK with no side row (`side_row_missing`), a
withheld promotion (`proof_withheld`), and an unproven index cell (`not_present`). The producer even
CONSTRUCTED the JoinObservation for the first two and discarded it. Carrying `s`/`d` costs two small
integers and makes "this spell has no icon" and "this spell's icon is missing from the client"
different values instead of the same one.

Resolution is still routed through `make_string_join` + promotion (E0R.1 T2.3): a path is referenced
only when the icon join AND its components are promotion-eligible. `missing` remains reserved for a
PROVEN path whose client BLP member is absent from the chain — never the fk-0 / no-side-row case.
"""
from __future__ import annotations

import hashlib

from .contracts import (decoded_reason_code, observation_state_code, policy_ref,
                        policy_ref_component)
from .spell_proof import FieldProof, make_envelope, make_string_join, make_string_observation

SCHEMA = "coa-client-spell-icons-v1"                 # retained: `e0r-v1`/`e0r-v2` still name it
ASSOCIATION_SCHEMA = "coa-client-spell-icons-v2"
ASSET_SCHEMA = "coa-client-icon-assets-v1"
ASSET_CHILD = "coa_client_icon_assets.jsonl"


class IconCollisionError(ValueError):
    """Two distinct canonical paths produced one `asset_id`. Truncating a digest is a probability
    argument; identity must not rest on one, so this fails closed rather than coalescing two icons."""


def canonical_icon_path(client_path: str) -> str:
    """The path's identity: lowercased, backslashes normalized. WoW stores `Interface\\Icons\\X`, and a
    client that spells the same asset two ways must not produce two assets."""
    return client_path.replace("\\", "/").lower()


def icon_asset_id(client_path: str) -> str:
    """128 bits of the canonical path's digest. CONTENT-derived, never encounter-order: numbering assets
    as they are met would make byte-identical inputs produce different generations."""
    return hashlib.sha256(canonical_icon_path(client_path).encode("utf-8")).hexdigest()[:32]


class _IconAssetTable:
    """`canonical_path -> asset row`, accumulated during the single catalog pass. 14,022 entries on the
    real client — counter-scale, unlike the 208,447-row streams around it."""

    __slots__ = ("_by_id",)

    def __init__(self):
        self._by_id: dict[str, dict] = {}

    def id_for(self, client_path: str) -> str:
        """Looked up through the module so a test can force a collision and prove this is a real gate."""
        from . import spell_icons

        return spell_icons.icon_asset_id(client_path)

    def record(self, client_path: str, *, sha256: str | None, archive: str | None) -> str:
        canonical = canonical_icon_path(client_path)
        asset_id = self.id_for(client_path)
        existing = self._by_id.get(asset_id)
        if existing is not None:
            if existing["client_path"] != canonical:
                raise IconCollisionError(
                    f"asset_id {asset_id} maps to two distinct canonical paths "
                    f"({existing['client_path']!r} and {canonical!r}); refusing to coalesce two icons")
            return asset_id
        self._by_id[asset_id] = {
            "schema_version": ASSET_SCHEMA, "asset_id": asset_id, "client_path": canonical,
            "availability": "source_only" if sha256 is not None else "missing",
            "source_asset_sha256": sha256, "source_archive": archive}
        return asset_id

    def get(self, asset_id: str) -> dict | None:
        return self._by_id.get(asset_id)

    def rows(self):
        """Sorted by `asset_id`, so the child's BYTES do not depend on the order paths were met."""
        return [self._by_id[k] for k in sorted(self._by_id)]

    def __len__(self) -> int:
        return len(self._by_id)


def icon_asset_table() -> _IconAssetTable:
    return _IconAssetTable()


def _proof(fp) -> FieldProof:
    # Records opened via a bound RecordView have verified structural integrity; layout+interpretation come
    # from the reviewed policy (compose_proof takes the weakest facet across the join's components).
    return FieldProof("verified", fp.layout, fp.interpretation)


def _association(spell_id: int, fk: int | None, asset_ref: str | None, *, state: str, reason: str,
                 availability: str | None = None) -> dict:
    """One association row. `readiness` is DERIVED from the referenced asset's AVAILABILITY, not from
    whether a reference exists: a proven path whose BLP member is absent from the chain is referenced and
    still unavailable. The cross-child check re-derives the same value rather than trusting this one, so
    it is a convenience for consumers, never an authority."""
    return {"schema_version": ASSOCIATION_SCHEMA, "spell_id": spell_id, "spell_icon_id": fk,
            "asset_ref": asset_ref, "s": observation_state_code(state),
            "d": decoded_reason_code(reason),
            "readiness": "available" if availability == "source_only" else "unavailable"}


def iter_icon_catalog(spell_view, side_views, *, policy, asset_resolver, assets):
    """Stream coa-client-spell-icons-v2 association rows over the FULL-table domain, recording every
    referenced asset into `assets`.

    `asset_resolver(client_path) -> {bytes, archive, member, patch_chain} | None` reads the effective
    client BLP member; `source_asset_sha256` hashes those ACTUAL BLP bytes (never the path string), and a
    proven path with no member is `missing`.
    """
    join = policy.joins["spell_icon_id"]
    icon_view = side_views.get(join.side_table)
    side_fields = policy.tables[join.side_table]["fields"]
    id_fp, path_fp = side_fields["id"], side_fields[join.side_value_field]
    by_id = {r.u32(id_fp.cell): r for r in icon_view.records()} if icon_view else {}
    idx_fp = policy.tables["Spell"]["fields"][join.index_field]
    spell_id_cell = policy.tables["Spell"]["fields"]["id"].cell
    spec = {"index_field": join.index_field, "side_table": join.side_table,
            "side_value_field": join.side_value_field}
    idx_ref = policy_ref("Spell", join.index_field)

    for rec in spell_view.records():
        spell_id = rec.u32(spell_id_cell)
        # WS1 never adjudicated the icon index (null FK cell): the index itself is unproven.
        if idx_fp.cell is None:
            yield _association(spell_id, None, None, state="unresolved", reason="not_present")
            continue
        fk = rec.u32(idx_fp.cell)
        idx_env = make_envelope(fk, kind=idx_fp.kind, proof=_proof(idx_fp), evidence_ref=idx_ref)
        if fk == 0:                                       # index_zero -> "this spell has no icon"
            jo = make_string_join({"index": idx_env}, resolution="index_zero")
            yield _association(spell_id, fk, None, state=jo.state, reason=jo.decoded_reason)
            continue
        side = by_id.get(fk)
        if side is None:                                  # nonzero FK, no side row in this client
            jo = make_string_join({"index": idx_env}, resolution="side_row_missing")
            yield _association(spell_id, fk, None, state=jo.state, reason=jo.decoded_reason)
            continue
        side_id_env = make_envelope(side.u32(id_fp.cell), kind=id_fp.kind, proof=_proof(id_fp),
                                    evidence_ref=policy_ref_component(spec, "side_id"))
        poff = side.u32(path_fp.cell)
        path_sob = make_string_observation(poff, icon_view.read_string(poff), proof=_proof(path_fp),
                                           evidence_ref=policy_ref_component(spec, "side_value"))
        jo = make_string_join({"index": idx_env, "side_id": side_id_env, "side_value": path_sob},
                              resolution="resolved")
        client_path = jo.decoded if jo.decoded_reason == "decoded" else None
        if not client_path:                               # withheld promotion or an empty path
            yield _association(spell_id, fk, None, state=jo.state, reason=jo.decoded_reason)
            continue
        asset_ref = assets.id_for(client_path)
        if assets.get(asset_ref) is None:
            resolved = asset_resolver(client_path)    # the effective BLP member, read once per path
            asset_ref = assets.record(
                client_path,
                sha256=hashlib.sha256(resolved["bytes"]).hexdigest() if resolved is not None else None,
                archive=resolved["archive"] if resolved is not None else None)
        yield _association(spell_id, fk, asset_ref, state=jo.state, reason=jo.decoded_reason,
                           availability=assets.get(asset_ref)["availability"])


def icon_coverage(rows, assets) -> dict:
    """Honest resolved-icon coverage over the association stream plus its asset table (single pass —
    never materializes the rows; E0R.1 T4.1).

    FOUR units in one report, which is exactly how a coverage number gets misread: `spells` and
    `resolved_paths` and `placeholders` count SPELL ROWS; `unique_paths` counts ASSETS. Present/missing
    count spell rows by the availability of the asset each references, so they sum to `resolved_paths`.
    """
    spells = resolved = present = missing = placeholders = 0
    for r in rows:
        spells += 1
        ref = r.get("asset_ref")
        if ref is None:
            placeholders += 1
            continue
        resolved += 1
        asset = assets.get(ref)
        if asset is not None and asset["availability"] == "source_only":
            present += 1
        else:
            missing += 1
    return {"spells": spells, "resolved_paths": resolved, "assets_present": present,
            "assets_missing": missing, "placeholders": placeholders,
            "unique_paths": len(assets)}
