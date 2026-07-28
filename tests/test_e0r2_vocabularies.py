# tests/test_e0r2_vocabularies.py
"""E0R.2 T0.1: `state` and `decoded_reason` are closed vocabularies with no declared set anywhere.
T6.2 assigns integer wire codes, so both the vocabulary and its code assignment must be schema-owned
and COMPLETE.

A regex over string literals is not sufficient evidence of completeness: `not_applicable` is emitted
positionally through `JoinObservation(...)` for every index-zero join (spell_proof.py:174,197) and a
regex never sees it. These tests are therefore BEHAVIOURAL — they drive every observation factory.

Note: `spell_proof._STATES` already existed as ("present", "not_applicable", "unresolved") but was
dead code AND incomplete (no "resolved"), which is exactly the failure mode this task closes.
"""
import json
from pathlib import Path

import pytest

from coa_client_extract.contracts import (DECODED_REASONS, OBSERVATION_STATES, decoded_reason_code,
                                          load_observation_wire_schema, observation_state_code)
from coa_client_extract.spell_proof import (FieldProof, ObservationError, absent_envelope,
                                            make_domain_gated_envelope, make_envelope, make_join,
                                            make_string_join, make_string_observation)

CORPUS = Path(__file__).resolve().parent / "golden" / "e0r1_corpus"


def _proof(interpretation="verified"):
    return FieldProof("verified", "verified", interpretation)


def _components():
    return {"index": make_envelope(3, kind="uint32", proof=_proof(), evidence_ref="/i"),
            "side_id": make_envelope(3, kind="uint32", proof=_proof(), evidence_ref="/s"),
            "side_value": make_envelope(1500, kind="int32", proof=_proof(), evidence_ref="/v")}


def _string_components():
    return {"index": make_envelope(1, kind="uint32", proof=_proof(), evidence_ref="/i"),
            "side_id": make_envelope(1, kind="uint32", proof=_proof(), evidence_ref="/s"),
            "side_value": make_string_observation(0, "Interface\\Icons\\x", proof=_proof(),
                                                  evidence_ref="/v")}


def _iter_observations(node):
    """Every nested dict carrying both keys — scalar cells, join wrappers, and join components."""
    if isinstance(node, dict):
        if "state" in node and "decoded_reason" in node:
            yield node["state"], node["decoded_reason"]
        for value in node.values():
            yield from _iter_observations(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_observations(value)


def test_the_vocabularies_are_exactly_what_the_producer_emits():
    assert OBSERVATION_STATES == ("not_applicable", "present", "resolved", "unresolved")
    assert DECODED_REASONS == ("decoded", "index_zero", "non_finite", "not_present",
                               "proof_withheld", "side_row_missing", "value_out_of_domain")


def test_states_that_are_not_observation_states_are_absent():
    """`candidate` is a publication_state; `absent` is a dict key in {"absent": env.to_dict()};
    `unknown_symbol` is a READINESS reason. All three were wrongly proposed as observation vocabulary
    in an earlier draft, derived from a grep that conflated three enumerations."""
    assert "candidate" not in OBSERVATION_STATES
    assert "absent" not in OBSERVATION_STATES
    assert "unknown_symbol" not in DECODED_REASONS


@pytest.mark.parametrize("resolution, expected_state, expected_reason", [
    ("index_zero", "not_applicable", "index_zero"),
    ("side_row_missing", "unresolved", "side_row_missing"),
    ("resolved", "resolved", "decoded"),
])
def test_every_join_constructor_outcome_is_in_the_vocabulary(resolution, expected_state, expected_reason):
    """Behavioural coverage of the constructors, which is where not_applicable actually comes from."""
    obs = make_join(_components(), resolution=resolution, decode=lambda c: 1500)
    assert obs.state == expected_state
    assert obs.decoded_reason == expected_reason
    assert obs.state in OBSERVATION_STATES
    assert obs.decoded_reason in DECODED_REASONS


def test_a_proof_withheld_join_is_in_the_vocabulary():
    obs = make_join(_components(), resolution="resolved", decode=lambda c: 1500)
    withheld = make_join({"index": make_envelope(3, kind="uint32", proof=_proof("unproven"),
                                                 evidence_ref="/i")},
                         resolution="resolved", decode=lambda c: 1500)
    assert obs.decoded_reason == "decoded"
    assert withheld.decoded_reason == "proof_withheld"
    assert withheld.state in OBSERVATION_STATES


@pytest.mark.parametrize("factory", [
    lambda: make_envelope(1, kind="int32", proof=_proof(), evidence_ref="/x"),
    lambda: make_envelope(1, kind="uint32", proof=_proof(), evidence_ref="/x"),
    lambda: make_envelope(1, kind="float", proof=_proof(), evidence_ref="/x"),
    lambda: make_envelope(1, kind="int32", proof=_proof("unproven"), evidence_ref="/x"),
    lambda: absent_envelope(proof=_proof(), evidence_ref="/x", state="unresolved"),
    lambda: absent_envelope(proof=_proof(), evidence_ref="/x", state="not_applicable"),
    # `_KINDS` is ("int32", "uint32", "float") — there is no "bitmask" kind; the mask REFINEMENT is the
    # `refine` callback, not a kind. Passing one raises ValueError before the vocabulary is exercised.
    lambda: make_domain_gated_envelope(999, kind="uint32", proof=_proof(), evidence_ref="/x",
                                       refine=lambda v: (v, False)),
    lambda: make_domain_gated_envelope(1, kind="uint32", proof=_proof(), evidence_ref="/x",
                                       refine=lambda v: (v, True)),
    lambda: make_string_observation(0, "n", proof=_proof(), evidence_ref="/x"),
    lambda: make_string_observation(0, "n", proof=_proof("unproven"), evidence_ref="/x"),
    lambda: make_string_join(_string_components(), resolution="resolved"),
    lambda: make_string_join(_string_components(), resolution="index_zero"),
    lambda: make_string_join(_string_components(), resolution="side_row_missing"),
])
def test_every_observation_factory_emits_in_vocabulary_values(factory):
    obs = factory()
    assert obs.state in OBSERVATION_STATES, obs.state
    assert obs.decoded_reason in DECODED_REASONS, obs.decoded_reason


def test_a_non_finite_float_is_in_the_vocabulary():
    """0x7F800000 is +inf: decoded is withheld with reason `non_finite`."""
    obs = make_envelope(0x7F800000, kind="float", proof=_proof(), evidence_ref="/x")
    assert obs.decoded_reason == "non_finite"
    assert obs.decoded_reason in DECODED_REASONS


@pytest.mark.parametrize("bad_state", ["probably_fine", "candidate", "absent", ""])
def test_the_constructors_reject_an_out_of_vocabulary_state(bad_state):
    """The guard that makes the vocabulary real: a future contributor adding a fifth state fails here
    rather than silently producing an uncodeable cell in T6.2."""
    with pytest.raises(ObservationError, match="state"):
        absent_envelope(proof=_proof(), evidence_ref="/x", state=bad_state)


def test_every_golden_corpus_observation_is_in_vocabulary():
    for line in (CORPUS / "full_rows.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        observed = list(_iter_observations(row.get("raw", {})))
        assert observed, "corpus row carries no observations; the walker is not seeing them"
        for state, reason in observed:
            assert state in OBSERVATION_STATES, (row.get("spell_id"), state)
            assert reason in DECODED_REASONS, (row.get("spell_id"), reason)


def test_codes_are_dense_and_come_from_the_shared_wire_schema():
    schema = load_observation_wire_schema()
    assert schema["schema_version"] == "coa-observation-wire-v1"
    assert [schema["states"][s] for s in OBSERVATION_STATES] == list(range(len(OBSERVATION_STATES)))
    assert [schema["decoded_reasons"][r] for r in DECODED_REASONS] == list(range(len(DECODED_REASONS)))
    assert observation_state_code("not_applicable") == schema["states"]["not_applicable"]
    assert decoded_reason_code("index_zero") == schema["decoded_reasons"]["index_zero"]


def test_the_wire_schema_covers_exactly_the_vocabularies():
    schema = load_observation_wire_schema()
    assert set(schema["states"]) == set(OBSERVATION_STATES)
    assert set(schema["decoded_reasons"]) == set(DECODED_REASONS)


@pytest.mark.parametrize("lookup, bad", [(observation_state_code, "probably_fine"),
                                         (decoded_reason_code, "unknown_symbol")])
def test_an_unknown_code_fails_closed(lookup, bad):
    with pytest.raises(KeyError):
        lookup(bad)


def test_the_dead_incomplete_states_tuple_is_gone():
    """spell_proof._STATES was declared and never used, and omitted "resolved". A half-built closed
    set that nothing enforces is how the vocabulary drifted in the first place."""
    import coa_client_extract.spell_proof as sp
    assert not hasattr(sp, "_STATES")
