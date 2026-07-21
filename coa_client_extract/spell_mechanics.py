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
from .topology import verify_source_topology, topology_matches_bound

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


def _read_side(rec, cell, kind):
    raw = rec.u32(cell)
    if kind == "float":
        return struct.unpack("<f", struct.pack("<I", raw))[0]
    if kind == "int32":
        return _signed(raw)
    return raw


def _anchor_holds(a, id_to_rec, side_by_id, index_cell, value_cell, kind) -> bool:
    """A STATE-BEARING anchor holds when the (index_cell -> side row -> value_cell) resolution matches its
    declared state AND value. not_applicable requires fk == 0; resolved requires a non-zero fk pointing at
    a present side row whose value_cell equals expected_value (expected_value may itself be 0 — a resolved
    zero, which is why the state, not the value, decides applicability)."""
    rec = id_to_rec.get(a["spell_id"])
    if rec is None:
        return False
    fk = rec.u32(index_cell)
    if a["expected_state"] == "not_applicable":
        return fk == 0
    if a["expected_state"] != "resolved":
        return False
    side = side_by_id.get(fk)
    return fk != 0 and side is not None and _read_side(side, value_cell, kind) == a["expected_value"]


def discover_join_pair(view, id_to_rec, side_view, *, side_id_cell, side_value_cells, anchors,
                       side_value_kind="int32"):
    """Discover BOTH the Spell index cell and the side value cell of a join as a jointly-unique pair.
    For each candidate index cell (whose non-zero values are ~all valid side ids) and each candidate
    side value cell, every state-bearing anchor must resolve THROUGH the pair. A bare FK-validity scan is
    ambiguous (dozens of small-int columns fall in a side id range) and knowing the value cell a priori is
    cheating; requiring the pair to be jointly unique over the state-bearing anchors breaks both."""
    side_by_id = {r.u32(side_id_cell): r for r in side_view.records()}
    side_ids = set(side_by_id)
    winners: list[tuple[int, int]] = []
    for ic in range(view.cell_count):
        nonzero = [r.u32(ic) for r in view.records() if r.u32(ic) != 0]
        if len(nonzero) < _MIN_SUPPORT or sum(1 for v in nonzero if v in side_ids) / len(nonzero) < 0.99:
            continue
        for vc in side_value_cells:
            if all(_anchor_holds(a, id_to_rec, side_by_id, ic, vc, side_value_kind) for a in anchors):
                winners.append((ic, vc))
    return (winners[0] if len(winners) == 1 else None), winners


def probe_joins(backend, root, attach, view, id_to_rec, spell_policy, join_value_anchors) -> dict:
    """Probe every join carrying authored value-anchors and record the outcome per index field.

    A join the human review adjudicated as un-disambiguable — `adjudication: "reviewed_ambiguous"`, i.e.
    no admissible independent evidence pins its index cell — is recorded PROBED-but-ambiguous (pair=None)
    WITHOUT a scan and WITHOUT reading its side table. The recon state machine accepts a recorded-ambiguous
    join as raw_only, so this keeps the join honestly documented (not silently unprobed) while the cell
    stays null. A join with real state-bearing anchors is discovered as a jointly-unique (index_cell,
    value_cell) pair; a non-unique / no-match result also yields pair=None (recorded-ambiguous)."""
    join_pairs: dict[str, dict] = {}
    if not join_value_anchors:
        return join_pairs
    field_to_side = {j.index_field: j.side_table for j in getattr(spell_policy, "joins", {}).values()}
    for field, spec in join_value_anchors.items():
        side_name = spec.get("side_table") or field_to_side.get(field)
        if not side_name:
            continue
        if spec.get("adjudication") == "reviewed_ambiguous":
            join_pairs[field] = {"table": side_name, "pair": None, "winners": [],
                                 "adjudication": "reviewed_ambiguous", "evidence": spec.get("evidence")}
            continue
        try:
            sm = backend.read_effective_file(root, attach, f"DBFilesClient\\{side_name}.dbc")
            side_view = open_view(sm.data)
        except (ArchiveError, DbcDriftError):
            continue
        pair, winners = discover_join_pair(
            view, id_to_rec, side_view, side_id_cell=spec.get("side_id_cell", 0),
            side_value_cells=spec["side_value_cells"], anchors=spec["anchors"],
            side_value_kind=spec.get("side_value_kind", "int32"))
        join_pairs[field] = {"table": side_name, "pair": pair, "winners": winners}
    return join_pairs


def discover_power_type_signedness(view, id_to_rec, *, cell, anchors) -> bool:
    """The signed int32 reading of power_type is admissible only when a STATIC health-cost anchor
    (expected_signed == -2) reads 0xFFFFFFFE at `cell`. No anchor -> stay raw_only (return False)."""
    if not anchors:
        return False
    for a in anchors:
        rec = id_to_rec.get(a["spell_id"])
        if rec is None or rec.u32(cell) != 0xFFFFFFFE or a.get("expected_signed") != -2:
            return False
    return True


def _recon_status(*, blocking, bound_mismatch, layout_proof, reviewed, required_joins, join_pairs,
                  authored_join_cells, power_type_interpretation, power_type_signed) -> str:
    """The E0R.1 recon lifecycle (self-consistent). `verified` requires: no blocking finding; a reviewed
    policy whose structured bound matches; every scalar anchor at its policy cell; **every** required join
    probed and either uniquely discovered AND adopted at the authored cell, or ambiguous (recorded with
    evidence); and — ONLY if the policy claims a verified `power_type` interpretation — a proven signed
    reading. When the policy declares `power_type` raw_only/unproven, `no_static_anchor` is acceptable and
    signedness is not required. A uniquely-discovered join the policy has not adopted ⇒ `review_required`."""
    if blocking:
        return "blocked"
    if not reviewed or bound_mismatch:
        return "review_required"
    if not all(p.get("matches_policy") for p in layout_proof.values()):
        return "review_required"
    for field in required_joins:
        probe = join_pairs.get(field)
        if probe is None:                                  # a required join was never probed
            return "review_required"
        pair = probe.get("pair")
        if pair is None:
            continue                                       # ambiguous, recorded ⇒ stays raw_only, ok
        discovered_index = pair[0]                         # (index_cell, value_cell)
        if authored_join_cells.get(field) != discovered_index:
            return "review_required"                       # unique but unadopted, or mismatched
    if power_type_interpretation == "verified" and power_type_signed is not True:
        return "review_required"
    return "verified"


def three_part_budget(*, serialized_bytes, peak_rss_mb, elapsed_s, ceilings) -> dict:
    """within_budget requires ALL THREE of serialized bytes, subprocess peak RSS, and elapsed to be
    under ceiling (the shipped code estimated raw DBC bytes and ignored RSS)."""
    size_mb = round(serialized_bytes / (1024 * 1024), 2)
    breach = []
    if size_mb > ceilings["artifact_size_mb"]:
        breach.append("artifact_size_mb")
    if peak_rss_mb > ceilings["peak_rss_mb"]:
        breach.append("peak_rss_mb")
    if elapsed_s > ceilings["elapsed_s"]:
        breach.append("elapsed_s")
    return {"serialized_mb": size_mb, "peak_rss_mb": peak_rss_mb, "elapsed_s": elapsed_s,
            "ceilings": dict(ceilings), "within_budget": not breach, "breach": breach}


def recon_spell_mechanics(backend: ArchiveBackend, root: Path, attach, *, spell_policy, anchors,
                          budget=DEFAULT_BUDGET, extractor_commit: str, client_build: str,
                          join_value_anchors=None, power_type_anchors=None) -> dict:
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

    # index-column FK discovery. A join adjudicated by value-anchors (present in join_value_anchors) is
    # SKIPPED here: its bare FK-validity scan is provably ambiguous (dozens of small-int columns fall in a
    # side id range — empirically 75 for SpellIcon on the real client), so the weaker scan must not raise a
    # no_unique_index_cell block against a cell the stronger joined-pair discovery has already resolved.
    index_fk: dict[str, dict] = {}
    for field, side_name in spell_policy.index_fields.items():
        if join_value_anchors and field in join_value_anchors:
            continue
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

    # topology via the ONE shared verifier (design A2) so recon and regenerate can never diverge: full
    # header, member/archive/patch chain, density, and key-uniqueness for every required table + the
    # expected-absent set. recon holds the authoritative opened build.
    topology = verify_source_topology(spell_policy, backend, root, attach)
    topology["client_build"] = client_build
    for b in topology["blocking"]:
        entry = {"field": b.get("table", "topology"), "reason": b["reason"]}
        entry.update({k: v for k, v in b.items() if k not in ("table", "reason")})
        blocking.append(entry)
    for tname, tspec in topology["tables"].items():
        dbc_sha.setdefault(tname, tspec["sha256"])

    # joined-pair value-anchor discovery (design A5/A6): value anchors break the bare-FK ambiguity and a
    # reviewed_ambiguous marker records a join the review could not disambiguate; power_type_anchors admit
    # the signed int32 reading only via a static negative. Delegated to probe_joins so it is unit-testable.
    join_pairs = probe_joins(backend, root, attach, view, id_to_rec, spell_policy, join_value_anchors)
    power_type_signed = None
    if power_type_anchors is not None:
        pt_cell_probe = layout_proof["power_type"]["discovered_cell"]
        if pt_cell_probe is not None:
            power_type_signed = discover_power_type_signedness(view, id_to_rec, cell=pt_cell_probe,
                                                               anchors=power_type_anchors)

    # proposed policy delta (recon proposes; it NEVER writes the policy)
    delta = {f: p["discovered_cell"] for f, p in layout_proof.items() if p["discovered_cell"] is not None}
    delta.update({f: i["discovered_cell"] for f, i in index_fk.items() if "discovered_cell" in i})
    delta.update({f: jp["pair"] for f, jp in join_pairs.items() if jp["pair"] is not None})
    if power_type_signed is not None:
        delta["power_type_signed"] = power_type_signed

    # real budgets, ALL THREE gated: forward serialized-size estimate, process peak RSS, elapsed.
    est_bytes = view.record_count * view.record_size
    elapsed = round(time.monotonic() - started, 4)
    rss_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)  # Linux ru_maxrss is KiB
    budget_report = three_part_budget(serialized_bytes=est_bytes, peak_rss_mb=rss_mb,
                                      elapsed_s=elapsed, ceilings=budget)
    if not budget_report["within_budget"]:
        blocking.append({"field": "budget", "reason": "over_budget", "breach": budget_report["breach"]})

    # lifecycle (E0R.1 state machine): verified requires the reviewed bound to match AND every required
    # join probed+adopted-or-ambiguous AND power_type signedness ONLY if the policy claims a verified
    # power_type interpretation. A uniquely-discovered-but-unadopted join is review_required.
    bound_mismatch = topology_matches_bound(topology, getattr(spell_policy, "bound", None))
    # EVERY join is required to be probed (E0R.1 pulls all four forward). Use the full join set on a real
    # SpellPolicy (incl. null-cell joins); fall back to a stub's `index_fields`. Authored cells come from
    # the public `columns` view (non-null cells only), so a null-cell join reads as unadopted.
    _joins = getattr(spell_policy, "joins", None)
    if _joins is not None:
        required_joins = tuple(dict.fromkeys(j.index_field for j in _joins.values()))
    else:
        required_joins = tuple(getattr(spell_policy, "index_fields", {}).keys())
    columns = getattr(spell_policy, "columns", {}) or {}
    authored_join_cells = {f: columns.get(f) for f in required_joins}
    _spell_tbl = getattr(spell_policy, "tables", {}).get("Spell", {})
    _fields = _spell_tbl.get("fields") if isinstance(_spell_tbl, dict) else None
    power_type_interpretation = (_fields["power_type"].interpretation
                                 if _fields and "power_type" in _fields else "unproven")
    # A raw_only/unproven power_type with no proven signed reading records no_static_anchor (honest, and an
    # admissible `verified` state — observation of a negative value is NOT static authorization).
    no_static_anchor = power_type_interpretation != "verified" and power_type_signed is not True
    status = _recon_status(
        blocking=blocking, bound_mismatch=bound_mismatch, layout_proof=layout_proof,
        reviewed=getattr(spell_policy, "reviewed", False), required_joins=required_joins,
        join_pairs=join_pairs, authored_join_cells=authored_join_cells,
        power_type_interpretation=power_type_interpretation, power_type_signed=power_type_signed)

    return {
        "schema_version": SCHEMA, "status": status, "blocking_findings": blocking,
        "source_pins": {"dbc": {t: {"sha256": h} for t, h in dbc_sha.items()},
                        "policy_sha256": getattr(spell_policy, "sha256", None),
                        "extractor_commit": extractor_commit, "client_build": client_build,
                        "effective_archive": str(member.effective_archive),
                        "patch_chain": [str(p) for p in member.patch_chain]},
        "layout_proof": layout_proof, "index_fk": index_fk, "join_pairs": join_pairs,
        "power_type_signed": power_type_signed, "no_static_anchor": no_static_anchor,
        "required_joins": list(required_joins), "enum_domains": enum_domains,
        "topology": topology, "proposed_policy_delta": delta, "duplicates": sorted(dupes)[:20],
        "budget": budget_report,
    }


def _report_bytes(report: dict) -> int:
    return len(json.dumps(report, sort_keys=True).encode("utf-8"))
