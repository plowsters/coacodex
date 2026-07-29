"""Shared recon fixtures for E0R.2 WS3 — clients whose ambiguity is a FACT of the bytes, not a claim.

Every builder returns the full `probe_joins` argument tuple
`(backend, root, attach, view, id_to_rec, policy, anchors)` so a test can call it directly and, where a
case needs it, mutate the backend first (`backend.forget(member)`).
"""
from __future__ import annotations

import struct
from pathlib import Path
from types import SimpleNamespace

from coa_client_extract.archive_backend import FakeArchiveBackend
from coa_client_extract.recordview import open_view

_ROOT = Path("common.MPQ")
_ATTACH = (Path("patch-T.MPQ"),)
_CAST_MEMBER = "DBFilesClient\\SpellCastTimes.dbc"


class Backend(FakeArchiveBackend):
    """A FakeArchiveBackend a test can take a member away from, so "the side table is gone" is a real
    state rather than a mocked exception."""

    def forget(self, logical_path: str) -> None:
        self._entries.pop(logical_path, None)


def _wdbc(rows, field_count):
    body = b"".join(struct.pack("<%dI" % field_count, *r) for r in rows)
    return struct.pack("<4sIIII", b"WDBC", len(rows), field_count, field_count * 4, 0) + body


def _side(pairs):
    """SpellCastTimes-shaped: id@0, base_ms@1."""
    return _wdbc([(i, v) for i, v in pairs], 2)


def _policy():
    return SimpleNamespace(joins={"cast_time_ms": SimpleNamespace(index_field="casting_time_index",
                                                                  side_table="SpellCastTimes")})


# The join anchors recon carries for an adjudicated-ambiguous join: no state-bearing anchors exist (that
# is WHY it is ambiguous), only the recorded verdict and its evidence.
AMBIGUOUS_ANCHORS = {
    "casting_time_index": {
        "side_table": "SpellCastTimes", "side_id_cell": 0,
        "adjudication": "reviewed_ambiguous",
        "evidence": "no admissible independent value evidence disambiguates the FK",
    },
}

SIDE_IDS = [(5, 500), (71, 7100), (3, 300)]


def _bundle(spell_rows, field_count):
    view = open_view(_wdbc(spell_rows, field_count))
    id_to_rec = {r.u32(0): r for r in view.records()}
    backend = Backend({_CAST_MEMBER: [(Path("patch-T.MPQ"), _side(SIDE_IDS))]})
    return backend, _ROOT, _ATTACH, view, id_to_rec, _policy(), AMBIGUOUS_ANCHORS


def ambiguous_backend():
    """A client where TWO cells hold nothing but valid SpellCastTimes ids — cells 1 and 2 — so no scan
    can pick a winner. This is the state the review adjudicated, reproduced in bytes.

    Cell 0 is the spell id (5/71/3 are also valid side ids, which is exactly the accidental collision
    that makes a bare FK-validity scan ambiguous in the first place)."""
    return _bundle([(5, 5, 71), (71, 71, 5), (3, 3, 3)], field_count=3)


def unique_backend():
    """The day the client makes the join unique: only cell 1 still holds valid side ids. A recon that
    copied its verdict forward would keep reporting ambiguity here; a recon that scans reports one
    candidate."""
    # Cell 0 = spell ids well outside the side-id range; cell 2 = values that are not side ids.
    return _bundle([(9001, 5, 40000), (9002, 71, 40001), (9003, 3, 40002)], field_count=3)


# --- E0R.2 T3.2: ambiguity baselines --------------------------------------------------------------
# A live ambiguous probe and the reviewed baseline it is compared against are two views of the SAME
# candidate list, so both are built from one place here. A test that wants a disagreement changes one
# side and leaves the other alone.

def candidates(cells, *, nonzero=100, valid=100, distinct_ids=41):
    return [{"cell": c, "nonzero_count": nonzero, "valid_count": valid, "distinct_ids": distinct_ids}
            for c in sorted(cells)]


def scanned_probe(cands, *, table="SpellCastTimes", thresholds=None, algorithm=None):
    """A probe record shaped exactly as `probe_joins` emits one for a reviewed_ambiguous join."""
    from coa_client_extract.spell_mechanics import (SCAN_ALGORITHM, SCAN_THRESHOLDS,
                                                    candidates_digest)
    return {"table": table, "pair": None, "winners": [], "scanned": True, "side_table_missing": False,
            "adjudication": "reviewed_ambiguous", "evidence": "fixture",
            "candidates": cands,
            "scan_algorithm": SCAN_ALGORITHM if algorithm is None else algorithm,
            "scan_thresholds": dict(SCAN_THRESHOLDS if thresholds is None else thresholds),
            "candidates_digest": candidates_digest(cands)}


def baseline(joins: dict, *, thresholds=None, algorithm=None):
    """The reviewed `ambiguity_baseline` block for `{field: candidate_list}`."""
    from coa_client_extract.spell_mechanics import (SCAN_ALGORITHM, SCAN_THRESHOLDS,
                                                    candidates_digest)
    return {
        "scan_algorithm": SCAN_ALGORITHM if algorithm is None else algorithm,
        "thresholds": dict(SCAN_THRESHOLDS if thresholds is None else thresholds),
        "joins": {f: {"candidates": c, "digest": candidates_digest(c)} for f, c in joins.items()},
    }
