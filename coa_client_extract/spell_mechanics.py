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
_MIN_SUPPORT = 2          # a real index column references at least this many nonzero rows
_MIN_DISTINCT = 2         # ...spanning at least this many distinct side rows (not one repeated id)
_ANCHOR_FIELDS = (("power_type", False), ("school_mask", False), ("name", True))

# E0R.2 T3.2: the ambiguity baseline binds the scan that produced it, not just its output. A candidate
# set is only comparable to another scan run under the SAME algorithm and thresholds — loosen the
# validity ratio and "the same candidates" means something else entirely.
#
# The ratio is an integer fraction, never a float. The baseline and its digest are hash-bound, and float
# repr/rounding differs across platforms and across Python/Node: 0.99 stored as a float would digest
# differently on machines that agree completely about the client.
SCAN_ALGORITHM = "fk_validity_v1"
SCAN_THRESHOLDS = {"min_support": _MIN_SUPPORT, "min_distinct": _MIN_DISTINCT,
                   "valid_num": 99, "valid_den": 100}
_THRESHOLD_KEYS = tuple(sorted(SCAN_THRESHOLDS))
_CANDIDATE_KEYS = ("cell", "distinct_ids", "nonzero_count", "valid_count")


def candidates_digest(candidates) -> str:
    """Canonical sha256 over an integer candidate list (E0R.2 T3.2).

    Digesting the LIST rather than comparing it field-by-field is what makes "the ambiguity is
    unchanged" a single reviewable fact: one value in the policy, one value from the client, equal or
    not. Every leaf is an int, so the canonical form has no formatting freedom to disagree about."""
    canonical = [{k: int(c[k]) for k in _CANDIDATE_KEYS} for c in candidates]
    body = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


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


def scan_index_candidates(view, side_view, *, side_id_cell: int = 0, thresholds=None) -> list[dict]:
    """Every Spell cell that could be the FK into `side_view`, with its supporting metrics (E0R.2 T3.1).

    An adjudicated-ambiguous join is still SCANNED on every run. Copying the authored verdict forward
    means recon cannot notice the day the client makes the join unique — the one thing the hold exists
    to catch — so what "ambiguous" means has to be re-measured against the client in front of us, not
    re-read from the review.

    Metrics are INTEGERS. T3.2 hashes this list into a baseline, and hashing floats is needlessly
    fragile: repr and rounding differ across platforms and across Python/Node, so the same client would
    produce different digests. The fraction is derived for display, never stored.

    Two passes, not one per cell: pass 1 tallies nonzero/valid counts for every cell at once (the
    per-cell loop `discover_join_pair` uses re-reads the whole table `cell_count` times), pass 2 counts
    distinct ids for the few survivors — which is what keeps the distinct-id sets from being 234
    simultaneous sets over a 200k-row table.

    `thresholds` defaults to SCAN_THRESHOLDS and is compared integer-wise (`valid_num/valid_den`), so a
    scan is reproducible from the baseline that records it.
    """
    th = SCAN_THRESHOLDS if thresholds is None else thresholds
    num, den = th["valid_num"], th["valid_den"]
    side_ids = {r.u32(side_id_cell) for r in side_view.records()}
    cells = range(view.cell_count)
    nonzero = [0] * view.cell_count
    valid = [0] * view.cell_count
    for rec in view.records():
        for c in cells:
            v = rec.u32(c)
            if v == 0:
                continue
            nonzero[c] += 1
            if v in side_ids:
                valid[c] += 1
    # Integer cross-multiplication rather than `valid/nonzero >= num/den`: the comparison is exact and
    # carries no float rounding into a value that gets hashed.
    survivors = [c for c in cells
                 if nonzero[c] >= th["min_support"] and valid[c] * den >= num * nonzero[c]]
    distinct: dict[int, set] = {c: set() for c in survivors}
    if survivors:
        for rec in view.records():
            for c in survivors:
                v = rec.u32(c)
                if v != 0 and v in side_ids:
                    distinct[c].add(v)
    return [{"cell": c, "nonzero_count": nonzero[c], "valid_count": valid[c],
             "distinct_ids": len(distinct[c])}
            for c in survivors if len(distinct[c]) >= th["min_distinct"]]


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


def probe_joins(backend, root, attach, view, id_to_rec, spell_policy, join_value_anchors,
                *, thresholds=None) -> dict:
    """Probe every join carrying authored value-anchors and record the outcome per index field.

    A join the human review adjudicated as un-disambiguable — `adjudication: "reviewed_ambiguous"`, i.e.
    no admissible independent evidence pins its index cell — is recorded PROBED-but-ambiguous (pair=None)
    and, since E0R.2 T3.1, LIVE-SCANNED against the client's own bytes. It used to be recorded from the
    authored verdict alone, without reading the side table at all, which meant recon could never notice
    the day a client patch made the join unique — the one thing the hold exists to catch. The recon state
    machine still accepts a recorded-ambiguous join as raw_only and the cell stays null; what changed is
    that "ambiguous" is now a measurement rather than a quotation.

    A join with real state-bearing anchors is discovered as a jointly-unique (index_cell, value_cell)
    pair; a non-unique / no-match result also yields pair=None (recorded-ambiguous).

    A side table that cannot be opened is recorded `scanned: False` + `side_table_missing: True` rather
    than dropped: the old `continue` made an absent side table indistinguishable from an ambiguous join,
    because both simply produced no record."""
    join_pairs: dict[str, dict] = {}
    if not join_value_anchors:
        return join_pairs
    thresholds = SCAN_THRESHOLDS if thresholds is None else thresholds
    field_to_side = {j.index_field: j.side_table for j in getattr(spell_policy, "joins", {}).values()}
    for field, spec in join_value_anchors.items():
        side_name = spec.get("side_table") or field_to_side.get(field)
        if not side_name:
            continue
        ambiguous = spec.get("adjudication") == "reviewed_ambiguous"
        record: dict = {"table": side_name, "pair": None, "winners": [], "scanned": False,
                        "side_table_missing": False}
        if ambiguous:
            record["adjudication"] = "reviewed_ambiguous"
            record["evidence"] = spec.get("evidence")
        try:
            sm = backend.read_effective_file(root, attach, f"DBFilesClient\\{side_name}.dbc")
            side_view = open_view(sm.data)
        except (ArchiveError, DbcDriftError):
            record["side_table_missing"] = True
            join_pairs[field] = record
            continue
        record["scanned"] = True
        side_id_cell = spec.get("side_id_cell", 0)
        if ambiguous:
            record["candidates"] = scan_index_candidates(view, side_view, side_id_cell=side_id_cell,
                                                         thresholds=thresholds)
            # E0R.2 T3.2: the scan records WHAT PRODUCED IT. A candidate list is only comparable to a
            # baseline produced by the same algorithm under the same thresholds.
            record["scan_algorithm"] = SCAN_ALGORITHM
            record["scan_thresholds"] = dict(thresholds)
            record["candidates_digest"] = candidates_digest(record["candidates"])
        else:
            pair, winners = discover_join_pair(
                view, id_to_rec, side_view, side_id_cell=side_id_cell,
                side_value_cells=spec["side_value_cells"], anchors=spec["anchors"],
                side_value_kind=spec.get("side_value_kind", "int32"))
            record["pair"], record["winners"] = pair, winners
        join_pairs[field] = record
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


def ambiguity_agrees(probe: dict, baseline: dict | None) -> str | None:
    """Compare ONE live ambiguous-join scan against its reviewed baseline (E0R.2 T3.2).

    Returns None on exact agreement, else a short reason. "Ambiguous" was previously satisfied by
    `pair is None` — a join that was never scanned and one whose candidates changed completely both
    read as unchanged. Accepting "any candidate set of size >= 2" is barely better: a move from cells
    {10,11} to {90,91} keeps the count and replaces the ambiguity outright.

    Exact agreement means all four of: the same scan algorithm, the same thresholds, the same candidate
    digest, and the same candidate list. Any addition, removal, or metric drift is review_required —
    the point is that a human looks again, not that the machine picks a winner."""
    if baseline is None:
        return "no reviewed ambiguity baseline for this join"
    if not probe.get("scanned"):
        return "join was not scanned against this client"
    if probe.get("scan_algorithm") != baseline.get("scan_algorithm"):
        return (f"scan algorithm {probe.get('scan_algorithm')!r} != baseline "
                f"{baseline.get('scan_algorithm')!r}")
    probe_th, base_th = probe.get("scan_thresholds") or {}, baseline.get("thresholds") or {}
    if {k: probe_th.get(k) for k in _THRESHOLD_KEYS} != {k: base_th.get(k) for k in _THRESHOLD_KEYS}:
        return f"scan thresholds {probe_th} != baseline {base_th}"
    live = probe.get("candidates")
    if live is None:
        return "scan recorded no candidate list"
    expected = baseline.get("candidates")
    if candidates_digest(live) != baseline.get("digest"):
        return (f"candidate digest {candidates_digest(live)[:12]} != baseline "
                f"{str(baseline.get('digest'))[:12]}")
    # The digest already decides; comparing the list too means a baseline whose stored `candidates` and
    # `digest` disagree with each other is caught here rather than silently trusting the digest.
    if [{k: c.get(k) for k in _CANDIDATE_KEYS} for c in live] != \
            [{k: c.get(k) for k in _CANDIDATE_KEYS} for c in (expected or [])]:
        return "baseline candidates disagree with the baseline digest"
    return None


def _baseline_entry(ambiguity_baseline: dict | None, field: str) -> dict | None:
    """The per-join baseline with the block-level algorithm/thresholds folded in, so a caller compares
    one complete record rather than reaching into two levels."""
    baseline = ambiguity_baseline or {}
    entry = dict((baseline.get("joins") or {}).get(field) or {})
    if not entry:
        return None
    entry.setdefault("scan_algorithm", baseline.get("scan_algorithm"))
    entry.setdefault("thresholds", baseline.get("thresholds"))
    return entry


def _recon_status(*, blocking, bound_mismatch, layout_proof, reviewed, required_joins, join_pairs,
                  authored_join_cells, power_type_interpretation, power_type_signed,
                  ambiguity_baseline=None) -> str:
    """The E0R.1 recon lifecycle (self-consistent). `verified` requires: no blocking finding; a reviewed
    policy whose structured bound matches; every scalar anchor at its policy cell; **every** required join
    probed and either uniquely discovered AND adopted at the authored cell, or ambiguous in EXACT
    agreement with the reviewed hash-bound baseline (E0R.2 T3.2); and — ONLY if the policy claims a
    verified `power_type` interpretation — a proven signed reading. When the policy declares `power_type`
    raw_only/unproven, `no_static_anchor` is acceptable and signedness is not required. A
    uniquely-discovered join the policy has not adopted ⇒ `review_required`."""
    if blocking:
        return "blocked"
    if not reviewed or bound_mismatch:
        return "review_required"
    if not all(p.get("matches_policy") for p in layout_proof.values()):
        return "review_required"
    baseline = ambiguity_baseline or {}
    for field in required_joins:
        probe = join_pairs.get(field)
        if probe is None:                                  # a required join was never probed
            return "review_required"
        pair = probe.get("pair")
        if pair is None:
            # Ambiguous. It stays raw_only either way — but `verified` now means the ambiguity was
            # RE-MEASURED and matches what the review looked at, not merely that no winner emerged.
            if ambiguity_agrees(probe, _baseline_entry(baseline, field)) is not None:
                return "review_required"
            continue
        discovered_index = pair[0]                         # (index_cell, value_cell)
        if authored_join_cells.get(field) != discovered_index:
            return "review_required"                       # unique but unadopted, or mismatched
    if power_type_interpretation == "verified" and power_type_signed is not True:
        return "review_required"
    return "verified"


def recon_budget(*, peak_rss_mb, elapsed_s, ceilings) -> dict:
    """Gate a RECON against the reviewed policy ceilings — and claim nothing else (E0R.2 T3.3).

    What this replaces made a size claim it could not support: `record_count * record_size` is the raw
    DBC byte count of the SOURCE table, not the size of the artifact a later `regenerate` serializes. On
    the real client it read ~187 MB against a real generation of ~523 MB — off by 2.8x, in the optimistic
    direction, and gated as if it meant something.

    A forecast from a serialized sample is an explicit NON-GOAL: a wrong forecast is worse than none, and
    publication measures the real thing exactly, per child and whole-generation (T2.4). So recon gates
    the two quantities it actually measured, and there is no size key to misread.

    Ceilings come from the reviewed policy's `budget` block. The python_* ceilings are the ones a recon
    can be held to; the node_* ones belong to a boundary a recon never runs. A ceilings dict missing
    either python key raises KeyError rather than defaulting — an absent ceiling is not an infinite one.
    """
    breach = []
    if peak_rss_mb > ceilings["python_peak_rss_mb"]:
        breach.append(f"python_peak_rss_mb {peak_rss_mb} > {ceilings['python_peak_rss_mb']}")
    if elapsed_s > ceilings["python_elapsed_s"]:
        breach.append(f"python_elapsed_s {elapsed_s} > {ceilings['python_elapsed_s']}")
    return {"peak_rss_mb": peak_rss_mb, "elapsed_s": elapsed_s, "ceilings": dict(ceilings),
            "within_budget": not breach, "breach": breach}


def policy_budget_report(*, children: dict, measured: dict, budget: dict) -> dict:
    """Enforce the POLICY-BOUND ceilings (E0R.1 T4.3): every child's serialized bytes against its
    per-child ceiling (an explicit per_child_overrides entry wins over max_serialized_bytes_per_child),
    the whole-generation byte total, and the SEPARATE python/node peak-RSS + elapsed ceilings. A single
    child over its ceiling breaches even when the whole generation is under. `measured` carries
    {python_peak_rss_mb, python_elapsed_s, node_peak_rss_mb, node_elapsed_s} (a node value may be None
    when Node validation was skipped — nothing to enforce, and the strict resolver already rejects a
    generation not validated by both boundaries)."""
    overrides = budget.get("per_child_overrides") or {}
    breach = []
    total = 0
    for name, meta in children.items():
        size = meta["byte_length"]
        total += size
        ceiling = overrides.get(name, budget["max_serialized_bytes_per_child"])
        if size > ceiling:
            breach.append(f"child {name} bytes {size} > {ceiling}")
    if total > budget["max_whole_generation_bytes"]:
        breach.append(f"whole_generation bytes {total} > {budget['max_whole_generation_bytes']}")
    for key in ("python_peak_rss_mb", "python_elapsed_s", "node_peak_rss_mb", "node_elapsed_s"):
        value = measured.get(key)
        if value is not None and value > budget[key]:
            breach.append(f"{key} {value} > {budget[key]}")
    return {"whole_generation_bytes": total, "measured": dict(measured), "ceilings": dict(budget),
            "within_budget": not breach, "breach": breach}


def benchmark_env() -> dict:
    """A reproducible pin of the environment the budget was measured under — rides in the authoritative
    generation manifest so a ceiling breach elsewhere is attributable to hardware, not regression."""
    import os
    import platform
    return {"python_version": platform.python_version(), "platform": platform.platform(),
            "machine": platform.machine(), "cpu_count": os.cpu_count() or 1}


def recon_spell_mechanics(backend: ArchiveBackend, root: Path, attach, *, spell_policy, anchors,
                          budget=None, extractor_commit: str, client_build: str,
                          join_value_anchors=None, power_type_anchors=None) -> dict:
    """E0R.2 T3.3: ceilings come from the REVIEWED policy's `budget` block. `budget=` remains as an
    explicit same-shape override for probes; a policy that declares neither is refused rather than
    silently held to hard-coded limits nobody reviewed."""
    from .publish import PublishError

    started = time.monotonic()
    ceilings = budget if budget is not None else (getattr(spell_policy, "doc", {}) or {}).get("budget")
    if ceilings is None:
        raise PublishError(
            "the reviewed policy declares no budget block; refusing to recon against unreviewed ceilings")
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
    # E0R.2 T3.2: the scan runs under the thresholds the REVIEWED baseline declares, so a live scan and
    # the baseline it is compared against are produced the same way. A policy with no baseline falls back
    # to the shipped defaults and simply cannot reach `verified` for an ambiguous join.
    ambiguity_baseline = (getattr(spell_policy, "doc", {}) or {}).get("ambiguity_baseline")
    scan_thresholds = (ambiguity_baseline or {}).get("thresholds") or SCAN_THRESHOLDS
    join_pairs = probe_joins(backend, root, attach, view, id_to_rec, spell_policy, join_value_anchors,
                             thresholds=scan_thresholds)
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

    # E0R.2 T3.3: a recon gates what a recon MEASURES — its own peak RSS and elapsed — against the
    # reviewed ceilings. The retired `est_bytes = record_count * record_size` was the raw DBC byte count
    # of the source table masquerading as a forecast of the serialized artifact (~187 MB claimed against
    # a real ~523 MB generation). Publication measures the real thing exactly; recon claims no size.
    elapsed = round(time.monotonic() - started, 4)
    rss_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)  # Linux ru_maxrss is KiB
    budget_report = recon_budget(peak_rss_mb=rss_mb, elapsed_s=elapsed, ceilings=ceilings)
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
        power_type_interpretation=power_type_interpretation, power_type_signed=power_type_signed,
        ambiguity_baseline=ambiguity_baseline)

    return {
        "schema_version": SCHEMA, "status": status, "blocking_findings": blocking,
        "source_pins": {"dbc": {t: {"sha256": h} for t, h in dbc_sha.items()},
                        "policy_sha256": getattr(spell_policy, "sha256", None),
                        "extractor_commit": extractor_commit, "client_build": client_build,
                        "effective_archive": str(member.effective_archive),
                        "patch_chain": [str(p) for p in member.patch_chain]},
        "layout_proof": layout_proof, "index_fk": index_fk, "join_pairs": join_pairs,
        "ambiguity_agreement": {
            f: ambiguity_agrees(join_pairs[f], _baseline_entry(ambiguity_baseline, f))
            for f in required_joins
            if f in join_pairs and join_pairs[f].get("pair") is None},
        "power_type_signed": power_type_signed, "no_static_anchor": no_static_anchor,
        "required_joins": list(required_joins), "enum_domains": enum_domains,
        "topology": topology, "proposed_policy_delta": delta, "duplicates": sorted(dupes)[:20],
        "budget": budget_report,
    }


def _report_bytes(report: dict) -> int:
    return len(json.dumps(report, sort_keys=True).encode("utf-8"))
