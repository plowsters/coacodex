from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import date
from pathlib import Path

from .archive_plan import family_of
from .wdbc import DbcTable

# Spell ids at or above this floor are custom high-range content; below it is stock
# 3.3.5a/base-game range. A coarse, purely mechanical magnitude band — a raw attribution
# signal only. M1.14B owns the actual id-range attribution policy.
_CUSTOM_ID_FLOOR = 100_000


def _index_lookup(table: DbcTable | None, value_key: str) -> dict[int, int]:
    if table is None:
        return {}
    return {row["id"]: row[value_key] for row in table.rows}


def _table_conf(table: DbcTable | None) -> str:
    """A contributing side-table is 'high' only if present and drift-free; absent or drifted is 'low'."""
    if table is None or table.drift:
        return "low"
    return "high"


def build_client_spell_records(
    spell: DbcTable,
    cast_times: DbcTable | None,
    durations: DbcTable | None,
    ranges: DbcTable | None,
    *,
    provenance: dict,
) -> list[dict]:
    cast_by_idx = _index_lookup(cast_times, "base_ms")
    dur_by_idx = _index_lookup(durations, "base_ms")
    range_max = {row["id"]: row.get("max_yd") for row in ranges.rows} if ranges else {}
    range_min = {row["id"]: row.get("min_yd") for row in ranges.rows} if ranges else {}

    # The whole Spell table is supplied by one effective archive, so its family is a
    # record-independent raw signal recorded on every row for M1.14B to consume.
    effective = provenance.get("effective_archive", "")
    archive_family = family_of(effective) if effective else "unknown"

    records: list[dict] = []
    for row in spell.rows:
        mechanics = {
            "school_mask": row.get("school_mask"),
            "power_type": row.get("power_type"),
            "cast_time_ms": cast_by_idx.get(row.get("casting_time_index")),
            "duration_ms": dur_by_idx.get(row.get("duration_index")),
            "range_min_yd": range_min.get(row.get("range_index")),
            "range_max_yd": range_max.get(row.get("range_index")),
            "category": row.get("category"),
            "spell_icon_id": row.get("spell_icon_id"),
        }
        records.append({
            "schema_version": "coa-client-spell-v1",
            "spell_id": row["id"],
            "name": row.get("name", ""),
            "mechanics": mechanics,
            "provenance": {
                **provenance,
                "schema_match_confidence": "low" if spell.drift else "high",
                "schema_match_confidence_by_dbc": {
                    "Spell": "low" if spell.drift else "high",
                    "SpellCastTimes": _table_conf(cast_times),
                    "SpellDuration": _table_conf(durations),
                    "SpellRange": _table_conf(ranges),
                },
            },
            "coa_attribution": {
                "status": "unknown",  # M1.14A records raw signals; M1.14B decides
                "archive_family": archive_family,
                "id_range": "high" if row["id"] >= _CUSTOM_ID_FLOOR else "base",
            },
        })
    return records


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write_bytes(data: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def write_jsonl(records: list[dict], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records)
    data = payload.encode("utf-8")
    path.write_bytes(data)
    return _sha256_bytes(data)


def write_json(doc: dict, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(data)
    return _sha256_bytes(data)


def _attribution_block(attr) -> dict:
    """One participation block from a SpellAttribution, or the low/absent default."""
    if attr is None:
        return {"is_coa": False, "modes": [], "exclusive_mode": None, "confidence": "low"}
    r = attr.result
    return {"is_coa": r.is_coa, "modes": list(r.modes),
            "exclusive_mode": r.exclusive_mode, "confidence": r.confidence}


def build_advancement_records(nodes, *, provenance: dict, spell_names: dict | None = None,
                              attribution: dict | None = None) -> list[dict]:
    spell_names = spell_names or {}
    attribution = attribution or {}
    records = []
    for n in nodes:
        records.append({
            "schema_version": "coa-client-advancement-v1",
            "node_id": n.node_id,
            "spell_id": n.spell_id,
            "name": spell_names.get(n.spell_id, ""),   # current name from coa-client-spell-v1 join
            "class": {"class_type_id": n.class_type_id, "internal": n.class_internal,
                      "display": n.class_display, "kind": n.class_kind},
            "tab": {"tab_type_id": n.tab_type_id, "name": n.tab_name},
            "entry_type": n.entry_type,
            "essence_kind": n.essence_kind,
            "legality": n.legality,
            "field_confidence": n.field_confidence,
            "raw": {"cols": dict(n.raw)},              # index-keyed {cell_index: value} audit map
            "provenance": dict(provenance),
            "coa_attribution": _attribution_block(attribution.get(n.spell_id)),
        })
    return records


def build_class_type_records(class_types) -> list[dict]:
    out = []
    for ct in class_types.values():
        out.append({
            "schema_version": "coa-client-class-types-v1",
            "class_type_id": ct.class_type_id,
            "internal": ct.internal, "display": ct.display, "kind": ct.kind,
            "display_source": ct.display_source,
            "display_evidence": list(ct.display_evidence),
        })
    return out


def build_tab_type_records(tab_types) -> list[dict]:
    """Emit coa-client-tab-types-v1 from the resolved {tab_type_id: name} map."""
    return [{"schema_version": "coa-client-tab-types-v1", "tab_type_id": tid, "name": name}
            for tid, name in sorted(tab_types.items())]


def build_essence_raw_records(essence, *, provenance: dict) -> list[dict]:
    """Emit CharacterAdvancementEssence RAW as coa-client-essence-v1.

    This table is per-level/per-tier essence *progression* data, NOT per-class caps (caps are the
    documented uniform constants AE 26 / TE 25). Its per-level semantics are undecoded, so M1.14B
    ships the raw index-keyed cells + provenance for auditability; the parity report reflects this as
    `readiness.leveling_progression_ready: false` (an M1.15 leveling gate) and it NEVER blocks any
    max-level readiness dimension or `full_builder_retirement_ready`. No column meaning is asserted here."""
    return [{"schema_version": "coa-client-essence-v1", "cols": dict(row),
             "provenance": dict(provenance)} for row in essence.rows]


def fill_spell_attribution(spell_records, attribution) -> list[dict]:
    for rec in spell_records:
        # Retain the M1.14A raw signals (archive_family/id_range) as provenance (spec: archive
        # family is kept as raw provenance only), and replace the M1.14A `status: unknown`.
        raw = rec.get("coa_attribution", {})
        keep = {k: raw[k] for k in ("archive_family", "id_range") if k in raw}
        attr = attribution.get(rec.get("spell_id"))
        block = _attribution_block(attr)
        block.update(keep)
        rec["coa_attribution"] = block
        # Stable multi-membership: attach the aggregated memberships[] (never a scalar that flips
        # to an array, never discarded). Absent attribution -> empty list.
        rec["memberships"] = list(attr.memberships) if attr is not None else []
    return spell_records


def write_client_spell_projection(
    records: list[dict],
    out_dir: Path,
    *,
    source_path: str,
    source_sha: str,
    source_bytes: int,
    client_build: str,
    extractor_commit: str,
) -> dict:
    """Filter coa-client-spell-v1 records to the CoA set (coa_attribution.is_coa) and write the
    projection + its manifest. Scoped by client-native attribution, never by Builder spell IDs.
    Uses the manifest-as-validity-marker protocol: reject duplicate projected spell ids, remove the
    old manifest first, write the JSONL atomically, then write the manifest atomically last — so an
    interruption never leaves a new JSONL beside a stale manifest."""
    projected = [r for r in records if r.get("coa_attribution", {}).get("is_coa") is True]
    spell_ids = [r["spell_id"] for r in projected]
    dupes = sorted(s for s, n in Counter(spell_ids).items() if n > 1)  # single pass, not O(n^2)
    if dupes:
        raise ValueError(f"projection has duplicate spell_ids: {dupes[:5]}")

    proj_path = out_dir / "coa_client_spell_coa.jsonl"
    manifest_path = out_dir / "coa_client_spell_projection.manifest.json"

    body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in projected).encode("utf-8")
    proj_sha = _sha256_bytes(body)

    by_conf: dict[str, int] = {}
    by_dbc_low = 0
    for r in projected:
        c = r.get("coa_attribution", {}).get("confidence", "low")
        by_conf[c] = by_conf.get(c, 0) + 1
        vals = r.get("provenance", {}).get("schema_match_confidence_by_dbc", {}).values()
        if any(v != "high" for v in vals):
            by_dbc_low += 1

    manifest = {
        "schema_version": "coa-client-spell-projection-v1",
        "inclusion_rule": {"predicate": "coa_attribution.is_coa == true", "version": "m1.14c-1"},
        "source_artifact": {"path": source_path, "sha256": source_sha, "byte_length": source_bytes},
        "projection": {"path": proj_path.name, "sha256": proj_sha, "byte_length": len(body)},
        "client_build": client_build,
        "extractor_commit": extractor_commit,
        "extraction_date": date.today().isoformat(),
        "counts": {"source_records": len(records), "projected_records": len(projected),
                   "unique_spell_ids": len(set(spell_ids)),
                   "by_confidence": by_conf},
        "schema_confidence_summary": {"records_with_any_low_table": by_dbc_low,
                                      "records_all_high": len(projected) - by_dbc_low},
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    # manifest-as-validity-marker: remove old manifest first, then JSONL, then manifest — each atomic.
    out_dir.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        manifest_path.unlink()
    _atomic_write_bytes(body, proj_path)
    _atomic_write_bytes(manifest_bytes, manifest_path)
    return manifest


_AUTHORED_MANIFEST_KEYS = {"wow_rules": "rules", "rating_enum": "rating_enum",
                           "power_type_enum": "power_type_enum",
                           "gt_axis_policy": "axis_layout_policy",
                           "wotlk_reference_anchors": "reference_anchors",
                           "class_axis_adjudication": "class_axis_adjudication"}


def write_wow_constants(snapshot: dict, out_dir: Path, *, authored_inputs, source_dbc_sha256: dict,
                        class_context_resolution: str, extractor_commit: str, client_build: str,
                        table_summary: dict, class_axis_adjudication=None) -> dict:
    art_path = out_dir / "coa_wow_constants.json"
    manifest_path = out_dir / "coa_wow_constants.manifest.json"
    body = (json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    inputs = list(authored_inputs)
    if class_axis_adjudication is not None:
        adj = class_axis_adjudication
        if isinstance(adj, dict):
            from types import SimpleNamespace
            adj = SimpleNamespace(**adj)
        inputs.append(adj)
    authored = {_AUTHORED_MANIFEST_KEYS[ai.name]: {"version": ai.version, "sha256": ai.sha256}
                for ai in inputs}

    manifest = {
        "schema_version": "coa-wow-constants-manifest-v1",
        "artifact": {"path": art_path.name, "sha256": _sha256_bytes(body), "byte_length": len(body)},
        "source_dbc_sha256": dict(source_dbc_sha256), "authored_inputs": authored,
        "class_context_resolution": class_context_resolution, "table_summary": dict(table_summary),
        "extractor_commit": extractor_commit, "client_build": client_build,
        "extraction_date": date.today().isoformat(),
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    out_dir.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        manifest_path.unlink()                 # remove stale marker first
    _atomic_write_bytes(body, art_path)         # write artifact
    _atomic_write_bytes(manifest_bytes, manifest_path)  # write marker LAST
    return manifest
