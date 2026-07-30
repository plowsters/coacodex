# tests/test_topology.py
import copy, hashlib, struct
import pytest
from coa_client_extract.topology import verify_source_topology, topology_matches_bound, require_dense

BUILD = "3.3.5a+patch-CZZ"


def _dbc(rows: list[tuple[int, int]], field_count=2, string_block=b"") -> bytes:
    rs = field_count * 4
    body = b"".join(struct.pack("<II", a, b) for a, b in rows)
    return struct.pack("<4sIIII", b"WDBC", len(rows), field_count, rs, len(string_block)) + body + string_block


class _Member:
    def __init__(self, data, name, archive="patch-CZZ.MPQ", patch_chain=()):
        self.data = data
        self.logical_path = name   # ExtractedMember exposes logical_path (not .name)
        self.effective_archive = type("A", (), {"name": archive})()
        self.patch_chain = [type("A", (), {"name": p})() for p in patch_chain]


class _Backend:
    def __init__(self, files, build=BUILD): self.files, self.client_build = files, build
    def has_file(self, root, attach, name): return name in self.files
    def read_effective_file(self, root, attach, name):
        if name not in self.files: raise KeyError(name)
        return _Member(self.files[name], name)


class _Policy:
    required_tables = ("Spell",)
    expected_absent = ("SpellEffect",)
    def __init__(self, key_cell=0, unique=True):
        self.tables = {"Spell": {"key_cell": key_cell, "unique": unique, "expected_field_count": 2}}
        self.bound = None


def _bound_from(rep):
    """The structured bound a matching client would carry (deep-copied from a good report so mutating the
    bound in a facet test never also mutates the report it is compared against)."""
    t = copy.deepcopy(rep["tables"]["Spell"])
    return {"client_build": rep["client_build"], "expected_absent": ["SpellEffect"], "tables": {
        "Spell": {"sha256": t["sha256"], "header": t["header"], "source": {
            "member": t["member"], "effective_archive": t["effective_archive"], "patch_chain": t["patch_chain"]}}}}


def test_require_dense_rejects_trailing_bytes():
    good = _dbc([(1, 10)])
    hdr = {"record_count": 1, "field_count": 2, "record_size": 8, "string_block_size": 0}
    assert require_dense(good, hdr) is True
    assert require_dense(good + b"\x00\x00", hdr) is False       # trailing junk => not dense


def test_topology_report_captures_header_member_dense_and_uniqueness():
    data = _dbc([(1, 10), (2, 20)])
    be = _Backend({"DBFilesClient\\Spell.dbc": data})
    rep = verify_source_topology(_Policy(), be, None, None)
    t = rep["tables"]["Spell"]
    assert t["sha256"] == hashlib.sha256(data).hexdigest()
    assert t["header"]["field_count"] == 2 and t["header"]["magic"] == "WDBC"
    assert t["member"] == "DBFilesClient\\Spell.dbc" and t["dense"] is True
    assert rep["client_build"] == BUILD
    assert t["key_unique"] is True and rep["expected_absent_ok"] is True and rep["blocking"] == []


def test_duplicate_key_and_expected_absent_present_block():
    dup = _dbc([(1, 10), (1, 20)])   # dense but non-unique id column
    be = _Backend({"DBFilesClient\\Spell.dbc": dup, "DBFilesClient\\SpellEffect.dbc": dup})
    rep = verify_source_topology(_Policy(), be, None, None)
    assert rep["tables"]["Spell"]["key_unique"] is False and rep["tables"]["Spell"]["dense"] is True
    assert rep["expected_absent_ok"] is False
    reasons = {b["reason"] for b in rep["blocking"]}
    assert {"duplicate_key", "expected_absent_present"} <= reasons


def test_nondense_file_blocks():
    # A non-dense file cannot be trusted for layout OR scanned for uniqueness — it blocks as not_dense.
    be = _Backend({"DBFilesClient\\Spell.dbc": _dbc([(1, 10)]) + b"\xff"})
    rep = verify_source_topology(_Policy(), be, None, None)
    assert rep["tables"]["Spell"]["dense"] is False
    assert any(b["reason"] == "not_dense" for b in rep["blocking"])


def test_matching_bound_reports_no_mismatch():
    be = _Backend({"DBFilesClient\\Spell.dbc": _dbc([(1, 10)])})
    rep = verify_source_topology(_Policy(), be, None, None)
    assert topology_matches_bound(rep, _bound_from(rep)) == []


@pytest.mark.parametrize("facet,mutate", [
    ("sha256", lambda b: b["tables"]["Spell"].__setitem__("sha256", "0" * 64)),
    ("header", lambda b: b["tables"]["Spell"]["header"].__setitem__("record_size", 999)),
    ("member", lambda b: b["tables"]["Spell"]["source"].__setitem__("member", "DBFilesClient\\Other.dbc")),
    ("effective_archive", lambda b: b["tables"]["Spell"]["source"].__setitem__("effective_archive", "patch-Z.MPQ")),
    ("patch_chain", lambda b: b["tables"]["Spell"]["source"].__setitem__("patch_chain", ["patch-A.MPQ"])),
    ("client_build", lambda b: b.__setitem__("client_build", "3.3.5a+patch-OLD")),
    ("expected_absent", lambda b: b.__setitem__("expected_absent", [])),
])
def test_each_bound_facet_is_independently_bound(facet, mutate):
    be = _Backend({"DBFilesClient\\Spell.dbc": _dbc([(1, 10)])})
    rep = verify_source_topology(_Policy(), be, None, None)
    bound = _bound_from(rep); mutate(bound)
    mism = topology_matches_bound(rep, bound)
    assert any(m["field"] == facet for m in mism), f"{facet} mutation not detected: {mism}"


def test_bound_table_set_must_match_exactly():
    be = _Backend({"DBFilesClient\\Spell.dbc": _dbc([(1, 10)])})
    rep = verify_source_topology(_Policy(), be, None, None)
    extra = _bound_from(rep); extra["tables"]["SpellExtra"] = extra["tables"]["Spell"]
    assert any(m["field"] == "table_set" for m in topology_matches_bound(rep, extra))
