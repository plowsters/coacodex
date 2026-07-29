from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import date
from pathlib import Path



REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_ROOT_LABEL = "$COA_CLIENT_ROOT"


def portable_path(value, *, client_root=None) -> str:
    """A path as a RECORD should state it (E0R.2 T7.1).

    A tracked artifact is a published artifact, and a machine-local absolute path makes two people
    running the identical pipeline against the identical client produce records that differ in a field
    neither of them chose. In-repo paths become repo-relative; anything under the out-of-tree client root
    becomes `$COA_CLIENT_ROOT/...`.

    The client root is a SYMBOLIC label, never a hash of the expansion: hashing it would look canonical
    while still making otherwise identical runs machine-dependent. Archive names and content digests
    carry the real identity, which is why anything else absolute degrades to its basename — the part
    that identifies the file rather than the machine it sat on.
    """
    raw = str(value)
    if not os.path.isabs(raw):
        return raw
    path = Path(raw)
    for root, prefix in ((REPO_ROOT, None),
                         (client_root or os.environ.get("COA_CLIENT_ROOT"), CLIENT_ROOT_LABEL)):
        if not root:
            continue
        try:
            relative = path.relative_to(Path(root).resolve())
        except ValueError:
            continue
        return f"{prefix}/{relative.as_posix()}" if prefix else relative.as_posix()
    return path.name


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

    # v2: per-field/per-value observation proof is authoritative — table-level confidence is no longer
    # a field certification. Summarize instead how many projected rows withheld a normalized value for
    # an out-of-domain symbol (raw retained), from the field_observations block.
    by_conf: dict[str, int] = {}
    withheld = 0
    for r in projected:
        c = r.get("coa_attribution", {}).get("confidence", "low")
        by_conf[c] = by_conf.get(c, 0) + 1
        fobs = r.get("field_observations", {})
        if any(isinstance(o, dict) and o.get("decoded_reason") == "value_out_of_domain" for o in fobs.values()):
            withheld += 1

    manifest = {
        "schema_version": "coa-client-spell-projection-v2",
        "inclusion_rule": {"predicate": "coa_attribution.is_coa == true", "version": "m1.14e-1"},
        "source_artifact": {"path": source_path, "sha256": source_sha, "byte_length": source_bytes},
        "projection": {"path": proj_path.name, "sha256": proj_sha, "byte_length": len(body)},
        "client_build": client_build,
        "extractor_commit": extractor_commit,
        "extraction_date": date.today().isoformat(),
        "counts": {"source_records": len(records), "projected_records": len(projected),
                   "unique_spell_ids": len(set(spell_ids)),
                   "by_confidence": by_conf},
        "value_gate_summary": {"records_with_withheld_value": withheld,
                               "records_all_in_domain": len(projected) - withheld},
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
