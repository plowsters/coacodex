# tests/test_e0r1_power_type_rawonly.py
"""E0R.1 Task 1.3 — power_type is DEMOTED (promotion raw_only AND interpretation not verified) with a
withheld decode. The E0 policy overclaimed power_type as verified/normalized, but the signed int32 reading
has no static anchor and value 7 is an unknown symbol; the honest state emits NO normalized power_type and
records `decoded_reason: "proof_withheld"` in the retained raw, for every value (in-domain 0-6 AND 7)."""
import struct

from coa_client_extract.recordview import open_view
from coa_client_extract.spell_layout import load_default_policy
from coa_client_extract.spell_record import iter_spell_records
from tests._spell_fixtures import v2_policy, side_views, _SPELL_FC


def _spell_view(power_types):
    # id@0, power_type@1, school_mask@2, name@3(->0 empty), casting_time_index@4(0=n/a), spell_icon_id@5
    rows = [(1000 + i, pt & 0xFFFFFFFF, 4, 0, 0, 0) for i, pt in enumerate(power_types)]
    body = b"".join(struct.pack("<%dI" % _SPELL_FC, *r) for r in rows)
    return open_view(struct.pack("<4sIIII", b"WDBC", len(rows), _SPELL_FC, _SPELL_FC * 4, 1) + body + b"\x00")


def test_default_policy_demotes_power_type():
    fp = load_default_policy().tables["Spell"]["fields"]["power_type"]
    assert fp.promotion == "raw_only"
    assert fp.interpretation != "verified"
    assert fp.layout == "verified"          # the cell @41 stays proven; only the semantic decode is withheld


def test_streaming_withholds_power_type_decode_for_every_value():
    # 3 = in-domain, 0 = in-domain, 7 = unknown symbol — ALL withheld under the demoted policy.
    view = _spell_view([3, 0, 7])
    rows = list(iter_spell_records(view, side_views(), policy=v2_policy(raw_only_power_type=True),
                                   provenance={"effective_archive": "patch-T.MPQ"}))
    assert len(rows) == 3
    for row, raw_val in zip(rows, [3, 0, 7]):
        assert row["mechanics"]["power_type"] is None                        # no normalized value
        assert row["raw"]["power_type"]["decoded_reason"] == "proof_withheld"  # withheld, not decoded
        assert row["raw"]["power_type"]["raw_u32"] == raw_val                 # raw retained (incl. 7)


def test_normalized_power_type_still_decodes_when_verified():
    # Control: the SAME machinery still emits a normalized value when the policy proves the interpretation,
    # so the withholding above is a property of the demotion, not a regression.
    view = _spell_view([3])
    rows = list(iter_spell_records(view, side_views(), policy=v2_policy(),
                                   provenance={"effective_archive": "patch-T.MPQ"}))
    assert rows[0]["mechanics"]["power_type"] == 3
    assert rows[0]["raw"]["power_type"]["decoded_reason"] == "decoded"
