# tests/test_spell_proof_string_join.py
import pytest
from coa_client_extract.spell_proof import (
    FieldProof, make_envelope, make_string_observation, make_string_join,
)

VER = FieldProof("verified", "verified", "verified")
REF = FieldProof("verified", "verified", "reference")


def _idx():
    return make_envelope(5, kind="uint32", proof=VER, evidence_ref="/joins/icon/index")


def test_string_join_resolves_when_all_verified():
    side = make_string_observation(12, "Ability_Fireball", proof=VER, evidence_ref="/joins/icon/side_value")
    sid = make_envelope(5, kind="uint32", proof=VER, evidence_ref="/joins/icon/side_id")
    jo = make_string_join({"index": _idx(), "side_id": sid, "side_value": side}, resolution="resolved")
    assert jo.state == "resolved" and jo.decoded == "Ability_Fireball"


def test_string_join_withholds_when_side_reference_only():
    side = make_string_observation(12, None, proof=REF, evidence_ref="/joins/icon/side_value")
    jo = make_string_join({"index": _idx(), "side_value": side}, resolution="resolved")
    assert jo.state == "resolved" and jo.decoded is None and jo.decoded_reason == "proof_withheld"


def test_string_join_index_zero_and_missing():
    side = make_string_observation(0, "", proof=VER, evidence_ref="/joins/icon/side_value")
    assert make_string_join({"index": _idx(), "side_value": side}, resolution="index_zero").state == "not_applicable"
    assert make_string_join({"index": _idx(), "side_value": side}, resolution="side_row_missing").state == "unresolved"
    with pytest.raises(ValueError):
        make_string_join({}, resolution="resolved")
