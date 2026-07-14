import struct

from coa_client_extract.errors import DbcSemanticError, ExtractError
from coa_client_extract.wdbc import parse_positional
from coa_client_extract.dbc_layouts import (
    CHARACTER_ADVANCEMENT_CLASS_TYPES, CharacterAdvancementLayout, CHARACTER_ADVANCEMENT,
)


def test_semantic_error_is_extract_error():
    assert issubclass(DbcSemanticError, ExtractError)


def test_class_types_layout_headers_match_observed_client():
    lt = CHARACTER_ADVANCEMENT_CLASS_TYPES
    assert lt.expected_field_count == 23
    assert lt.expected_record_size == 92
    assert lt.columns["id"].index == 0
    assert lt.columns["name"].index == 1          # verified on real client


def test_advancement_layout_defaults_to_anchors_only():
    lt = CHARACTER_ADVANCEMENT
    assert (lt.node_id_col, lt.spell_id_col, lt.class_type_col) == (0, 5, 32)
    # unresolved fields default to None/() and no field is proven until the decode fills confidence
    assert lt.ae_cost_col is None
    assert lt.connected_node_cols == ()
    assert lt.confidence == {}


def test_parse_positional_returns_index_keyed_rows_and_strings():
    import pytest
    from coa_client_extract.errors import DbcDriftError
    strings = b"\x00Adrenal Venom\x00"
    rec0 = struct.pack("<III", 6086, 1, 805775)   # col1 = string offset 1 -> "Adrenal Venom"
    rec1 = struct.pack("<III", 6096, 0, 12345)
    data = struct.pack("<4sIIII", b"WDBC", 2, 3, 12, len(strings)) + rec0 + rec1 + strings
    raw = parse_positional(data, 3, 12)
    assert raw.drift is False
    assert raw.cell_count == 3 and raw.record_size == 12
    assert raw.rows[0] == {0: 6086, 1: 1, 2: 805775}
    assert raw.rows[1][0] == 6096
    assert raw.strings == strings                 # string block retained for name/icon correlation
    assert raw.read_string(1) == "Adrenal Venom"


def test_parse_positional_rejects_truncation():
    import pytest
    from coa_client_extract.errors import DbcDriftError
    # header claims 2 records * 12 bytes + 4-byte string block, but body is short
    data = struct.pack("<4sIIII", b"WDBC", 2, 3, 12, 4) + struct.pack("<III", 1, 0, 0)
    with pytest.raises(DbcDriftError, match="truncated"):
        parse_positional(data, 3, 12)


def test_parse_positional_rejects_non_divisible_record_size():
    import pytest
    from coa_client_extract.errors import DbcDriftError
    data = struct.pack("<4sIIII", b"WDBC", 0, 3, 13, 0)   # 13 not divisible by 4
    with pytest.raises(DbcDriftError, match="record_size"):
        parse_positional(data, 3, 13)


def test_parse_positional_strict_raises_on_drift():
    import pytest
    from coa_client_extract.errors import DbcDriftError
    data = struct.pack("<4sIIII", b"WDBC", 0, 99, 12, 0)  # field_count 99 != expected 3
    assert parse_positional(data, 3, 12).drift is True    # non-strict: flagged
    with pytest.raises(DbcDriftError):
        parse_positional(data, 3, 12, strict=True)


from coa_client_extract.decode_advancement import (
    correlate_scalar, prove_adjacency_domain, decode_layout,
)


def _pairs(json_field, values, ca_cols):
    # values: list of ints; ca_cols: dict col->list aligned with values. Builds (json,row) pairs.
    pairs = []
    for i, v in enumerate(values):
        je = {"Spells": [1000 + i], json_field: v}
        row = {5: 1000 + i, **{c: col[i] for c, col in ca_cols.items()}}
        pairs.append((je, row))
    return pairs


def test_correlate_scalar_records_margin_and_nonzero():
    vals = [i % 4 for i in range(200)]
    # col 7 == field; col 9 is pure noise (constant); col 8 partially agrees
    ca = {7: vals, 8: [v if i % 2 else 0 for i, v in enumerate(vals)], 9: [3] * 200}
    proof = correlate_scalar(_pairs("AECost", vals, ca), "AECost")
    assert proof.column == 7 and proof.score == 1.0
    assert proof.runner_up < proof.score and proof.margin > 0.15
    assert proof.nonzero >= 50


def test_correlate_scalar_none_when_no_min_evidence():
    # only 10 pairs -> below the 50-nonzero floor -> no proof
    vals = [1] * 10
    assert correlate_scalar(_pairs("AECost", vals, {7: vals}), "AECost") is None


def test_prove_adjacency_rejects_all_zero_and_out_of_domain():
    node_ids = {10, 11, 12, 13}
    rows = [{0: 10, 20: 11, 21: 0}, {0: 11, 20: 12, 21: 13}, {0: 12, 20: 13, 21: 0},
            {0: 13, 20: 10, 21: 12}]
    assert prove_adjacency_domain(rows, node_ids, (20, 21), min_nonzero=3)[0] == "node_id"
    # all-zero block: no evidence -> unresolved (not a silent pass)
    zeros = [{0: n, 40: 0} for n in node_ids]
    assert prove_adjacency_domain(zeros, node_ids, (40,), min_nonzero=1)[0] == "unresolved"
    # out-of-domain value -> unresolved
    bad = [{0: 10, 50: 99999}]
    assert prove_adjacency_domain(bad, node_ids, (50,), min_nonzero=1)[0] == "unresolved"


def test_decode_layout_marks_unproven_fields_unproven():
    # a table where AECost is cleanly in col 7 but RequiredLevel has no matching column
    vals = [i % 4 for i in range(200)]
    ca_rows = [{0: 500 + i, 5: 1000 + i, 7: vals[i]} for i in range(200)]
    json_entries = [{"Spells": [1000 + i], "AECost": vals[i], "RequiredLevel": 99} for i in range(200)]
    from coa_client_extract.wdbc import PositionalDbc
    ca = PositionalDbc(179, 173, 692, 200, ca_rows, b"\x00", drift=False)
    layout, report = decode_layout(ca, {}, {}, json_entries)
    # confidence is keyed by the FIELD name read_advancement gates on, NOT the "_col" attribute
    assert layout.confidence.get("ae_cost") == "high"
    assert layout.ae_cost_col == 7
    assert report["fields"]["ae_cost_col"]["column"] == 7
    assert report["fields"]["required_level_col"]["confidence"] != "high"  # no clean column


def test_decode_layout_resolves_tab_entry_and_both_adjacency_blocks():
    from coa_client_extract.wdbc import PositionalDbc
    from coa_client_extract.decode_advancement import load_resolved_layout
    from coa_client_extract.class_types import resolve_tab_types

    class _T:
        def __init__(self, rows): self.rows = rows
    tab_types = resolve_tab_types(_T([{"id": 1, "name": "Class"}, {"id": 49, "name": "Brewing"}]))

    n = 200
    ca_rows, json_entries = [], []
    for i in range(n):
        nid, nxt, prev = 500 + i, 500 + (i + 1) % n, 500 + (i - 1) % n
        tab = 1 if i % 3 == 0 else 49                             # tab pattern independent of entry type
        etype_num, etype_str = (0, "Ability") if i % 2 == 0 else (1, "Talent")
        ca_rows.append({0: nid, 5: 1000 + i, 32: 33,
                        6: tab, 4: etype_num, 7: i % 4,          # tab col 6, entry col 4, ae col 7
                        20: nxt, 21: 0, 40: prev})               # connected col 20, required col 40
        # loose JSON "Tab" is the display NAME (as in the real client), not the numeric id -> the
        # decode must translate it back through tab_types to resolve tab_type_col.
        json_entries.append({"ID": nid, "Spells": [1000 + i], "Tab": tab_types[tab], "Type": etype_str,
                             "AECost": i % 4, "ConnectedNodes": [nxt], "RequiredIDs": [prev]})
    ca = PositionalDbc(179, 173, 692, n, ca_rows, b"\x00", drift=False)
    layout, report = decode_layout(ca, {}, tab_types, json_entries, min_nonzero=50)

    assert layout.tab_type_col == 6 and layout.confidence["tab_type"] == "high"   # resolved via name->id
    assert layout.entry_type_col == 4 and layout.confidence["entry_type"] == "high"
    assert report["entry_type_map"] == {"0": "Ability", "1": "Talent"}   # proven, not hard-coded
    assert layout.connected_node_cols == (20,) and layout.confidence["connected_node_ids"] == "high"
    assert layout.required_id_cols == (40,) and layout.confidence["required_ids"] == "high"

    # the finished layout round-trips through the report so regenerate loads it with no hand-editing
    import tempfile, os
    from coa_client_extract.decode_advancement import write_report
    path = os.path.join(tempfile.mkdtemp(), "report.json")
    write_report(report, __import__("pathlib").Path(path))
    reloaded = load_resolved_layout(path)
    assert reloaded.tab_type_col == 6 and reloaded.entry_type_col == 4
    assert reloaded.connected_node_cols == (20,) and reloaded.confidence["required_ids"] == "high"
    assert reloaded.entry_type_map == {"0": "Ability", "1": "Talent"}   # proven map survives round-trip
