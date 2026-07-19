from __future__ import annotations

import hashlib
import json
import resource
import struct
import time
from pathlib import Path

from .archive_backend import ArchiveBackend
from .errors import ArchiveError, DbcDriftError
from .recordview import open_view

SCHEMA = "coa-spell-mechanics-recon-v1"
DEFAULT_BUDGET = {"artifact_size_mb": 512, "peak_rss_mb": 4096, "elapsed_s": 600}
_MIN_SUPPORT = 2          # a real index column references at least this many nonzero rows
_MIN_DISTINCT = 2         # ...spanning at least this many distinct side rows (not one repeated id)
_ANCHOR_FIELDS = (("power_type", False), ("school_mask", False), ("name", True))


def _norm(s) -> str:
    return (s or "").strip().casefold()


def _signed(u: int) -> int:
    return struct.unpack("<i", struct.pack("<I", u))[0]


def _bits(mask: int):
    for b in range(32):
        if (mask >> b) & 1:
            yield 1 << b


def _discover_column(view, id_to_rec, expected: dict, *, is_string: bool):
    """Every cell whose value matches EVERY present anchor. Returns (present_anchor_ids, matching_cells)."""
    present = {i: v for i, v in expected.items() if i in id_to_rec}
    matches = []
    if not present:
        return present, matches
    for c in range(view.cell_count):
        ok = True
        for aid, want in present.items():
            rec = id_to_rec[aid]
            if is_string:
                if _norm(view.try_string(rec.u32(c))) != _norm(want):
                    ok = False
                    break
            else:
                raw = rec.u32(c)
                if raw != want and _signed(raw) != want:
                    ok = False
                    break
        if ok:
            matches.append(c)
    return present, matches


def _discover_index_cell(view, side_ids: set):
    """Scan for the FK column into a side table: nonzero support, valid-nonzero fraction (zero excluded),
    distinct referenced ids, and a unique winner. Zero-heavy / mismatched columns cannot win."""
    best = None
    qualifiers = []
    for c in range(view.cell_count):
        vals = [r.u32(c) for r in view.records()]
        nonzero = [v for v in vals if v != 0]
        if len(nonzero) < _MIN_SUPPORT:
            continue
        valid = [v for v in nonzero if v in side_ids]
        frac = len(valid) / len(nonzero)
        distinct = len(set(valid))
        if frac >= 0.99 and distinct >= _MIN_DISTINCT:
            info = {"discovered_cell": c, "valid_fraction": round(frac, 4),
                    "distinct": distinct, "nonzero": len(nonzero)}
            qualifiers.append(info)
    if len(qualifiers) == 1:
        best = qualifiers[0]
    elif len(qualifiers) > 1:
        best = None   # ambiguous
    return best, qualifiers


def _bound_matches(bound, client_build, dbc_sha) -> bool:
    if not bound or bound.get("client_build") != client_build:
        return False
    return all(dbc_sha.get(t) == h for t, h in bound.get("source_dbc_sha256", {}).items())


def recon_spell_mechanics(backend: ArchiveBackend, root: Path, attach, *, spell_policy, anchors,
                          budget=DEFAULT_BUDGET, extractor_commit: str, client_build: str) -> dict:
    started = time.monotonic()
    blocking: list[dict] = []
    dbc_sha: dict[str, str] = {}

    member = backend.read_effective_file(root, attach, "DBFilesClient\\Spell.dbc")
    dbc_sha["Spell"] = hashlib.sha256(member.data).hexdigest()
    view = open_view(member.data).require_dense()

    # duplicate ids
    id_to_rec, dupes = {}, set()
    for rec in view.records():
        sid = rec.u32(0)
        if sid in id_to_rec:
            dupes.add(sid)
        else:
            id_to_rec[sid] = rec
    if dupes:
        blocking.append({"field": "id", "reason": "duplicate_spell_ids", "sample": sorted(dupes)[:5]})

    # anchor column discovery (scan; never assume the policy cell)
    layout_proof: dict[str, dict] = {}
    for field, is_string in _ANCHOR_FIELDS:
        expected = {a["id"]: a[field] for a in anchors}
        present, matches = _discover_column(view, id_to_rec, expected, is_string=is_string)
        unique = len(matches) == 1
        cell = matches[0] if unique else None
        proof = {"discovered_cell": cell, "coverage": f"{len(present)}/{len(anchors)}",
                 "unique": unique, "matches_policy": cell == spell_policy.columns.get(field)}
        layout_proof[field] = proof
        if not unique or len(present) < len(anchors):
            blocking.append({"field": field, "reason": "anchor_not_uniquely_discoverable",
                             "matching_cells": matches, "coverage": proof["coverage"]})

    # index-column FK discovery
    index_fk: dict[str, dict] = {}
    for field, side_name in spell_policy.index_fields.items():
        try:
            sm = backend.read_effective_file(root, attach, f"DBFilesClient\\{side_name}.dbc")
            dbc_sha[side_name] = hashlib.sha256(sm.data).hexdigest()
            side_ids = {r.u32(0) for r in open_view(sm.data).records()}
        except (ArchiveError, DbcDriftError):
            index_fk[field] = {"error": "side_table_unreadable", "table": side_name}
            blocking.append({"field": field, "reason": "side_table_unreadable", "table": side_name})
            continue
        best, qualifiers = _discover_index_cell(view, side_ids)
        if best is None:
            index_fk[field] = {"table": side_name, "qualifiers": qualifiers}
            blocking.append({"field": field, "reason": "no_unique_index_cell", "table": side_name,
                             "qualifiers": qualifiers})
        else:
            index_fk[field] = {**best, "table": side_name}

    # enum domains (only meaningful once the anchor cells are discovered)
    enum_domains = {}
    pt_cell, sm_cell = layout_proof["power_type"]["discovered_cell"], layout_proof["school_mask"]["discovered_cell"]
    if pt_cell is not None:
        observed = sorted({_signed(r.u32(pt_cell)) for r in view.records()})
        enum_domains["power_type_observed"] = observed
        enum_domains["unknown_power_types"] = [v for v in observed if v not in spell_policy.enum_policy["power_types"]]
    if sm_cell is not None:
        unknown_bits = sorted({b for r in view.records() for b in _bits(r.u32(sm_cell))
                               if b not in spell_policy.enum_policy["school_bits"]})
        enum_domains["unknown_school_bits"] = unknown_bits

    # topology (required/expected-absent come from the POLICY, not caller args)
    topology = {}
    for name in spell_policy.required_tables:
        present = backend.has_file(root, attach, f"DBFilesClient\\{name}.dbc")
        topology[name] = {"present": present, "required": True}
        if not present:
            blocking.append({"field": name, "reason": "required_table_missing"})
    for name in spell_policy.expected_absent:
        present = backend.has_file(root, attach, f"DBFilesClient\\{name}.dbc")
        topology[name] = {"present": present, "expected_absent": True}
        if present:
            blocking.append({"field": name, "reason": "expected_absent_table_present"})

    # proposed policy delta (recon proposes; it NEVER writes the policy)
    delta = {f: p["discovered_cell"] for f, p in layout_proof.items() if p["discovered_cell"] is not None}
    delta.update({f: i["discovered_cell"] for f, i in index_fk.items() if "discovered_cell" in i})

    # real budgets: elapsed, forward artifact-size estimate, process peak RSS (Linux KiB -> MiB)
    est_mb = round((view.record_count * view.record_size) / (1024 * 1024), 2)
    elapsed = round(time.monotonic() - started, 4)
    rss_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)  # Linux ru_maxrss is KiB
    budget_report = {"estimated_artifact_mb": est_mb, "elapsed_s": elapsed,
                     "peak_rss_mb_process": rss_mb, "ceilings": dict(budget),
                     "within_budget": est_mb <= budget["artifact_size_mb"] and elapsed <= budget["elapsed_s"]}
    if not budget_report["within_budget"]:
        blocking.append({"field": "budget", "reason": "over_budget"})

    # lifecycle
    if blocking:
        status = "blocked"
    elif (getattr(spell_policy, "reviewed", False) and _bound_matches(getattr(spell_policy, "bound", None),
          client_build, dbc_sha) and all(p["matches_policy"] for p in layout_proof.values())):
        status = "verified"
    else:
        status = "review_required"

    return {
        "schema_version": SCHEMA, "status": status, "blocking_findings": blocking,
        "source_pins": {"dbc": {t: {"sha256": h} for t, h in dbc_sha.items()},
                        "policy_sha256": getattr(spell_policy, "sha256", None),
                        "extractor_commit": extractor_commit, "client_build": client_build,
                        "effective_archive": str(member.effective_archive),
                        "patch_chain": [str(p) for p in member.patch_chain]},
        "layout_proof": layout_proof, "index_fk": index_fk, "enum_domains": enum_domains,
        "topology": topology, "proposed_policy_delta": delta, "duplicates": sorted(dupes)[:20],
        "budget": budget_report,
    }


def _report_bytes(report: dict) -> int:
    return len(json.dumps(report, sort_keys=True).encode("utf-8"))
