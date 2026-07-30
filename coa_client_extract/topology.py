# coa_client_extract/topology.py
"""The single shared source-topology verifier used by BOTH recon and canonical regeneration (design A2),
so the two can never diverge on what "the client we proved against" means. For every required table it
opens the effective member and captures sha256 + the full 5-field WDBC header + member/archive/patch
chain + density + id-uniqueness under the policy key cell, and confirms the expected-absent set. The
structured `bound` in a reviewed policy is then matched facet-by-facet against this report.
"""
from __future__ import annotations

import hashlib
import struct

from .recordview import open_view
from .errors import ArchiveError, DbcDriftError

_H = struct.Struct("<4sIIII")
_HEADER_BYTES = 20


def _header(data: bytes) -> dict:
    magic, rc, fc, rs, ss = _H.unpack_from(data, 0)
    return {"magic": magic.decode("latin-1"), "record_count": rc, "field_count": fc,
            "record_size": rs, "string_block_size": ss}


def require_dense(data: bytes, header: dict) -> bool:
    """A WDBC file is dense iff its length is EXACTLY 20-byte header + record_count*record_size +
    string_block_size — no gaps, no trailing bytes. A non-dense file means the record region is not what
    the header claims and the layout cannot be trusted."""
    expected = _HEADER_BYTES + header["record_count"] * header["record_size"] + header["string_block_size"]
    return len(data) == expected


def verify_source_topology(policy, backend, root, attach) -> dict:
    """Independently open + verify every required table (sha256, full 5-field header, member, archive,
    patch chain, density, id-uniqueness under the policy key cell) and the expected-absent set. Shared by
    recon AND regenerate so they can never diverge."""
    tables: dict[str, dict] = {}
    blocking: list[dict] = []
    for name in policy.required_tables:
        member_name = f"DBFilesClient\\{name}.dbc"
        try:
            member = backend.read_effective_file(root, attach, member_name)
        except (ArchiveError, KeyError) as exc:
            blocking.append({"table": name, "reason": "required_table_unreadable", "detail": str(exc)})
            continue
        if len(member.data) < _HEADER_BYTES or member.data[:4] != b"WDBC":
            blocking.append({"table": name, "reason": "required_table_unreadable", "detail": "not a WDBC file"})
            continue
        # Density is a property of the raw bytes vs the declared header — check it BEFORE open_view (which
        # itself rejects a non-dense file), so a non-dense table gets its own distinct blocking reason.
        header = _header(member.data)
        dense = require_dense(member.data, header)
        key_cell = policy.tables[name]["key_cell"]
        unique = True
        if dense:
            try:
                view = open_view(member.data)
                seen: set[int] = set()
                for rec in view.records():
                    k = rec.u32(key_cell)
                    if k in seen:
                        unique = False
                        break
                    seen.add(k)
            except (ArchiveError, DbcDriftError) as exc:
                blocking.append({"table": name, "reason": "required_table_unreadable", "detail": str(exc)})
        tables[name] = {
            "sha256": hashlib.sha256(member.data).hexdigest(), "header": header,
            "member": getattr(member, "logical_path", None) or getattr(member, "name", None),
            "effective_archive": member.effective_archive.name,
            "patch_chain": [p.name for p in member.patch_chain], "key_unique": unique, "dense": dense,
        }
        if policy.tables[name].get("unique", True) and not unique:
            blocking.append({"table": name, "reason": "duplicate_key", "key_cell": key_cell})
        if not dense:
            blocking.append({"table": name, "reason": "not_dense"})

    expected_absent_ok = True
    for name in policy.expected_absent:
        if backend.has_file(root, attach, f"DBFilesClient\\{name}.dbc"):
            expected_absent_ok = False
            blocking.append({"table": name, "reason": "expected_absent_present"})

    return {"client_build": getattr(backend, "client_build", None), "tables": tables,
            "expected_absent_ok": expected_absent_ok, "expected_absent_set": list(policy.expected_absent),
            "blocking": blocking}


def topology_matches_bound(report: dict, bound: dict | None) -> list[dict]:
    """Return the list of mismatches between an opened-client topology report and a policy's structured
    `bound`. Empty ⇒ the opened client is the client the policy was proven against. EVERY facet is bound:
    client_build, exact required-table set equality, sha256, full header, member, effective_archive,
    patch_chain, and expected_absent topology."""
    if not bound:
        return [{"table": "*", "field": "bound", "reason": "policy has no bound"}]
    mism: list[dict] = []
    if report.get("client_build") != bound.get("client_build"):
        mism.append({"table": "*", "field": "client_build", "reason": "build_mismatch"})
    want = bound.get("tables", {})
    if set(want) != set(report["tables"]):
        mism.append({"table": "*", "field": "table_set", "reason": "required_table_set_differs",
                     "missing": sorted(set(want) - set(report["tables"])),
                     "extra": sorted(set(report["tables"]) - set(want))})
    for name, w in want.items():
        got = report["tables"].get(name)
        if got is None:
            mism.append({"table": name, "field": "*", "reason": "missing_from_client"})
            continue
        src = w["source"]
        for field, got_v, want_v in (
            ("sha256", got["sha256"], w["sha256"]),
            ("header", got["header"], w["header"]),
            ("member", got["member"], src["member"]),
            ("effective_archive", got["effective_archive"], src["effective_archive"]),
            ("patch_chain", got["patch_chain"], src["patch_chain"]),
        ):
            if got_v != want_v:
                mism.append({"table": name, "field": field, "reason": f"{field}_differs"})
    # expected-absent is two facts: the bound pins WHICH tables must be absent (set), and the report
    # proves they ARE absent on the opened client.
    if sorted(bound.get("expected_absent", [])) != sorted(report.get("expected_absent_set", [])):
        mism.append({"table": "*", "field": "expected_absent", "reason": "expected_absent_set_differs"})
    if not report["expected_absent_ok"]:
        mism.append({"table": "*", "field": "expected_absent", "reason": "expected_absent_present"})
    return mism
