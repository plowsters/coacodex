"""E0R.2 T2.3: lossless extraction means every field has an OBSERVATION, even when it has no
normalized value. A raw_only join in `unresolved` state is still a required cell; omitting it is silent
loss, which is exactly what E0R exists to prevent.

What this replaces: an OPTIONAL `required_scalar_fields` list that named only the normalized scalars —
and that the production policy never carried at all, so the consumer read `policyDoc
.required_scalar_fields || []` and asked nothing of any real row. The domain is now a mandatory
`artifact_contract`, re-derived from the layout at load so a reviewed claim cannot drift away from the
tables and joins it describes.
"""
import json
from pathlib import Path

import pytest

from coa_client_extract.publish import ResolveError, _observation_domain
from coa_client_extract.shapes import SHAPES, ShapeError
from coa_client_extract.spell_layout import (
    SpellPolicyError, compute_policy_sha256, derive_artifact_contract, load_spell_policy,
)
from coa_client_extract.spell_record import verify_row_against_policy
from tests.golden import golden_rows, producer_spell_rows

POLICY = Path(__file__).resolve().parents[1] / "coa_client_extract/data/spell_layout_v2.json"
CORPUS = Path(__file__).resolve().parent / "golden" / "e0r1_corpus"


def _policy_doc():
    return json.loads(POLICY.read_text(encoding="utf-8"))


def _corpus_full_row():
    """A valid compact full row from the shared corpus — the same rows Node validates, so a domain rule
    that passes here and fails there (or the reverse) is caught."""
    for line in (CORPUS / "full_rows.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["case"] == "valid_full":
            return {k: v for k, v in row.items() if k not in ("case", "golden_accept")}
    raise LookupError("no valid_full row in the corpus")


def _rehash(doc):
    doc.pop("sha256", None)
    doc["sha256"] = compute_policy_sha256(doc)
    return doc


# --- the production domain ---

def test_the_production_policy_requires_the_full_raw_domain():
    # Every one of the nine cells, not just the four with normalized values. The five that used to be
    # omissible — description, cast_time_ms, duration_ms, range_min_yd, range_max_yd — are join-derived
    # or reference-only, and a row that drops them has LOST an observation it made.
    contract = _policy_doc()["artifact_contract"]
    assert set(contract["required_raw_observations"]) == {
        "cast_time_ms", "description", "duration_ms", "id", "name", "power_type",
        "range_max_yd", "range_min_yd", "school_mask"}


def test_the_icon_join_is_the_icon_child_domain_not_the_spell_row_domain():
    contract = _policy_doc()["artifact_contract"]
    assert contract["icon_observation_domain"] == ["spell_icon_id"]
    assert "spell_icon_id" not in contract["required_raw_observations"]
    assert "spell_icon_id" not in contract["required_mechanics_keys"]


def test_every_mechanics_key_is_structurally_nullable():
    """Including school_mask: a proven policy still yields a null normalized value when an unseen school
    bit trips the per-value domain gate (`value_out_of_domain`, spell_record._emit_school). Nullability
    is structural; legitimacy is semantic. Asserting school_mask were non-nullable would make the schema
    contradict the extractor and break on the first new school bit a patch introduces."""
    contract = _policy_doc()["artifact_contract"]
    assert set(contract["nullable_mechanics_keys"]) == set(contract["required_mechanics_keys"])
    assert "school_mask" in contract["nullable_mechanics_keys"]


def test_the_mechanics_domain_excludes_the_identity_and_prose_fields():
    # id is the row key and name/description are strings carried outside `mechanics`; every OTHER
    # observed field must have a mechanics key, present even when its value is null.
    contract = _policy_doc()["artifact_contract"]
    assert set(contract["required_mechanics_keys"]) == (
        set(contract["required_raw_observations"]) - {"id", "name", "description"})


# --- structural vs semantic nullability ---

def test_a_domain_gated_school_mask_row_is_accepted_by_the_structural_schema():
    row = dict(golden_rows("full_spell_row_v3"))
    row["mechanics"] = {**row["mechanics"], "school_mask": None}
    row["raw"] = {**row["raw"], "school_mask": {**row["raw"]["school_mask"],
                                                "decoded_reason": "value_out_of_domain"}}
    SHAPES["full_spell_row_v3"](row)              # structurally valid


def test_a_mechanics_key_may_hold_null_but_may_not_be_absent():
    # Key PRESENCE is a policy question, not a structural one — the shape has no policy, so the domain
    # gate lives in the validator that does. A null is a recorded observation; an absent key is loss.
    policy = load_spell_policy(json.loads((CORPUS / "policy.json").read_text(encoding="utf-8")))
    row = _corpus_full_row()
    row["mechanics"] = {k: None for k in row["mechanics"]}
    SHAPES["full_spell_row_v3"](row)
    _observation_domain(row["spell_id"], row, policy)
    row["mechanics"] = {k: v for k, v in row["mechanics"].items() if k != "school_mask"}
    SHAPES["full_spell_row_v3"](row)              # still structurally a row ...
    with pytest.raises(ResolveError, match="school_mask"):
        _observation_domain(row["spell_id"], row, policy)   # ... but it has lost an observation


def test_the_producer_side_gate_rejects_an_omitted_raw_observation():
    """The blocker this task closes: before the domain was policy-declared, a full row could drop
    description, cast_time_ms, duration_ms, range_min_yd and range_max_yd entirely and no gate noticed."""
    policy = load_spell_policy(json.loads((CORPUS / "policy.json").read_text(encoding="utf-8")))
    row = _corpus_full_row()
    del row["raw"]["duration_ms"]                 # the unresolved join — an observation, not an absence
    with pytest.raises(ResolveError, match="duration_ms"):
        _observation_domain(row["spell_id"], row, policy)


def test_the_producer_side_gate_rejects_a_mechanics_key_outside_the_domain():
    policy = load_spell_policy(json.loads((CORPUS / "policy.json").read_text(encoding="utf-8")))
    row = _corpus_full_row()
    row["mechanics"]["invented_stat"] = 7
    with pytest.raises(ResolveError, match="invented_stat"):
        _observation_domain(row["spell_id"], row, policy)


def test_an_icon_observation_does_not_belong_in_the_spell_row():
    policy = load_spell_policy(json.loads((CORPUS / "policy.json").read_text(encoding="utf-8")))
    row = _corpus_full_row()
    row["raw"]["spell_icon_id"] = row["raw"]["power_type"]
    with pytest.raises(ResolveError, match="spell_icon_id"):
        _observation_domain(row["spell_id"], row, policy)


def test_the_semantic_verifier_rejects_a_null_value_whose_cell_decoded_cleanly():
    """The rule a static nullability list cannot express: a null is legitimate ONLY when the cell
    explains it. Structurally, every mechanics key may be null; semantically, `eligible iff populated`
    decides. This is why nullability had to stay uniform rather than be tightened per field."""
    _full, projection, _icon = producer_spell_rows()
    policy_doc = golden_rows("spell_policy_v2")
    verify_row_against_policy(projection, policy_doc)          # the producer's own row holds
    assert projection["mechanics"]["school_mask"] is not None  # decoded, eligible, populated
    projection["mechanics"]["school_mask"] = None              # ... but the observation still says decoded
    with pytest.raises(ValueError, match="school_mask"):
        verify_row_against_policy(projection, policy_doc)


# --- the contract cannot drift from the layout it describes ---

def test_load_spell_policy_rejects_an_incoherent_artifact_contract():
    doc = _policy_doc()
    keys = doc["artifact_contract"]["nullable_mechanics_keys"]
    doc["artifact_contract"]["nullable_mechanics_keys"] = sorted(keys + ["not_a_field"])
    with pytest.raises(SpellPolicyError, match="not_a_field"):
        load_spell_policy(_rehash(doc))


def test_load_spell_policy_rejects_a_contract_that_drops_a_declared_field():
    doc = _policy_doc()
    doc["artifact_contract"]["required_raw_observations"] = [
        f for f in doc["artifact_contract"]["required_raw_observations"] if f != "duration_ms"]
    with pytest.raises(SpellPolicyError, match="required_raw_observations"):
        load_spell_policy(_rehash(doc))


def test_load_spell_policy_rejects_a_missing_artifact_contract():
    doc = _policy_doc()
    del doc["artifact_contract"]
    with pytest.raises(SpellPolicyError, match="artifact_contract"):
        load_spell_policy(_rehash(doc))


def test_adding_a_field_to_the_layout_without_rereviewing_the_domain_is_rejected():
    # The failure mode the derivation exists to catch: a new observed cell lands in the layout and the
    # reviewed domain silently keeps under-checking every row.
    doc = _policy_doc()
    doc["tables"]["Spell"]["fields"]["reagent_count"] = {
        "cell": 100, "kind": "uint32", "layout": "unproven", "interpretation": "unproven",
        "promotion": "raw_only", "evidence": "recon-pending"}
    with pytest.raises(SpellPolicyError, match="reagent_count"):
        load_spell_policy(_rehash(doc))
    doc["artifact_contract"] = derive_artifact_contract(doc)   # re-reviewed alongside the layout
    load_spell_policy(_rehash(doc))


def test_the_staged_policy_child_must_carry_the_domain_structurally():
    # Node has no load_spell_policy behind its shape check, so an absent contract has to be a SHAPE
    # failure too — otherwise the consumer's domain check degrades to `undefined` and asks nothing.
    doc = golden_rows("spell_policy_v2")
    SHAPES["spell_policy_v2"](doc)
    del doc["artifact_contract"]
    with pytest.raises(ShapeError, match="artifact_contract"):
        SHAPES["spell_policy_v2"](doc)
