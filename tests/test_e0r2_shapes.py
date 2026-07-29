"""E0R.2 T2.2: a shape is a TYPE CONTRACT, not a key list.

`{}` passed as a one-record JSON artifact because nothing asked anything of it — checking
`schema_version` plus top-level key presence establishes neither field types, nullability, nested
envelope shape, nor JSON-document semantics.

Every shape's positive case is what the PRODUCER actually emits (tests/golden.py runs the synthetic
regenerate and reads the rows back), so a builder that starts emitting a different shape moves the
golden document and fails here rather than shipping.
"""
from __future__ import annotations

import copy

import pytest

from coa_client_extract.contracts import (decoded_reason_code, load_contract_registry,
                                          load_supported_contract)
from coa_client_extract.shapes import SHAPES, ShapeError

from tests.golden import golden_rows, producer_spell_rows


def test_every_supported_revisions_shapes_are_implemented_and_nothing_else_is():
    """A contract shape with no validator is a gate that silently does nothing.

    E0R.2 T6.2: the union over SUPPORTED revisions, not just `current`. A revision stays in the registry
    so generations published under it remain resolvable — which is only true while the shapes it names
    are still implemented. `full_spell_row_v3` is exactly that case: retired from the current contract,
    retained here."""
    registry = load_contract_registry()
    contracted = set()
    for revision, entry in registry["supported"].items():
        contract = load_supported_contract(revision, entry["sha256"])
        contracted |= {spec["shape"] for spec in contract["children"].values()}
    assert contracted == set(SHAPES)
    assert "full_spell_row_v3" in contracted, "a supported revision's shape may never be deleted"


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_shape_accepts_its_golden_document(shape):
    SHAPES[shape](golden_rows(shape))


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_shape_rejects_an_unknown_key(shape):
    doc = copy.deepcopy(golden_rows(shape))
    doc["smuggled"] = 1
    with pytest.raises(ShapeError, match="smuggled"):
        SHAPES[shape](doc)


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_shape_rejects_a_non_object(shape):
    with pytest.raises(ShapeError):
        SHAPES[shape]([])


def test_the_producer_rows_satisfy_the_same_shapes_as_the_corpus():
    """The corpus is a hand-authored subset. Holding the REAL rows to the same validators is what stops
    the corpus drifting into a shape the producer never emits."""
    full, projection, icon = producer_spell_rows()
    SHAPES["full_spell_row_v4"](full)
    SHAPES["projection_row_v3"](projection)
    SHAPES["icon_row_v1"](icon)


# --- JSON documents: the `{}` hole ---

@pytest.mark.parametrize("shape", ["archive_plan_v1", "projection_manifest_v3", "spell_policy_v2",
                                   "generation_contract_v1"])
def test_an_empty_json_document_is_not_a_valid_artifact(shape):
    with pytest.raises(ShapeError):
        SHAPES[shape]({})


def test_an_archive_plan_without_an_ordering_rule_is_rejected():
    """The load order is what the whole extraction is bound to; a plan that omits it describes nothing."""
    doc = copy.deepcopy(golden_rows("archive_plan_v1"))
    doc.pop("ordering_rule")
    with pytest.raises(ShapeError, match="ordering_rule"):
        SHAPES["archive_plan_v1"](doc)


def test_a_projection_manifest_with_a_non_integer_count_is_rejected():
    doc = copy.deepcopy(golden_rows("projection_manifest_v3"))
    doc["counts"]["projected_records"] = "3"
    with pytest.raises(ShapeError, match="projected_records"):
        SHAPES["projection_manifest_v3"](doc)


def test_an_unreviewed_policy_may_not_be_staged():
    doc = copy.deepcopy(golden_rows("spell_policy_v2"))
    doc["reviewed"] = False
    with pytest.raises(ShapeError, match="reviewed"):
        SHAPES["spell_policy_v2"](doc)


def test_the_contract_shape_delegates_to_the_contract_validator():
    doc = copy.deepcopy(golden_rows("generation_contract_v1"))
    doc["children"]["coa_client_spell.jsonl"]["kind"] = "parquet"
    with pytest.raises(ShapeError, match="kind"):
        SHAPES["generation_contract_v1"](doc)


# --- observation envelopes ---

def test_a_full_row_with_a_malformed_raw_envelope_is_rejected():
    row = copy.deepcopy(golden_rows("full_spell_row_v3"))
    row["raw"] = {"id": {"state": "present"}}          # no decoded_reason, no substrate
    with pytest.raises(ShapeError, match="raw.id"):
        SHAPES["full_spell_row_v3"](row)


def test_a_full_row_with_no_observations_at_all_is_rejected():
    row = copy.deepcopy(golden_rows("full_spell_row_v3"))
    row["raw"] = {}
    with pytest.raises(ShapeError, match="not lossless"):
        SHAPES["full_spell_row_v3"](row)


def test_an_observation_outside_the_closed_vocabulary_is_rejected():
    row = copy.deepcopy(golden_rows("full_spell_row_v3"))
    row["raw"]["id"]["state"] = "candidate"            # a publication_state, never an observation state
    with pytest.raises(ShapeError, match="closed vocabulary"):
        SHAPES["full_spell_row_v3"](row)


def test_a_compact_full_row_may_not_carry_rich_proof():
    """The two v3 dialects are disjoint: the full child is the substrate, the projection is the proof."""
    row = copy.deepcopy(golden_rows("full_spell_row_v3"))
    row["raw"]["id"]["proof"] = {"integrity": "verified", "layout": "verified",
                                 "interpretation": "verified"}
    with pytest.raises(ShapeError, match="proof"):
        SHAPES["full_spell_row_v3"](row)


def test_a_projection_row_with_a_malformed_proof_is_rejected():
    row = copy.deepcopy(golden_rows("projection_row_v3"))
    row["field_observations"]["id"]["proof"] = {"integrity": "verified"}
    with pytest.raises(ShapeError, match="proof"):
        SHAPES["projection_row_v3"](row)


def test_a_join_observation_with_an_invented_component_is_rejected():
    full, projection, _ = producer_spell_rows()
    row = copy.deepcopy(projection)
    row["field_observations"]["cast_time_ms"]["components"]["invented"] = \
        row["field_observations"]["cast_time_ms"]["components"]["index"]
    with pytest.raises(ShapeError, match="invented"):
        SHAPES["projection_row_v3"](row)


def test_a_string_observation_may_resolve_to_null_but_not_to_a_number():
    row = copy.deepcopy(golden_rows("full_spell_row_v3"))
    row["raw"]["name"]["resolved"] = None
    SHAPES["full_spell_row_v3"](row)                   # an unresolved string is a recorded observation
    row["raw"]["name"]["resolved"] = 7
    with pytest.raises(ShapeError, match="resolved"):
        SHAPES["full_spell_row_v3"](row)


# --- mechanics nullability ---

def test_mechanics_values_may_be_null_but_the_keys_may_not_be_absent():
    """Nullability is STRUCTURAL; whether a null is legitimate is a semantic question the per-row
    verifier answers. An absent key, though, is silent loss."""
    full, _, _ = producer_spell_rows()
    row = copy.deepcopy(full)
    row["mechanics"] = {k: None for k in row["mechanics"]}
    SHAPES["full_spell_row_v4"](row)
    row["mechanics"]["power_type"] = "3"
    with pytest.raises(ShapeError, match="power_type"):
        SHAPES["full_spell_row_v4"](row)


def test_a_domain_gated_school_mask_row_is_structurally_valid():
    """A proven policy still yields a null normalized value when an unseen school bit trips the
    per-value domain gate. The structural schema must not contradict the extractor."""
    full, _, _ = producer_spell_rows()
    row = copy.deepcopy(full)
    row["mechanics"] = {**row["mechanics"], "school_mask": None}
    row["raw"]["school_mask"] = {**row["raw"]["school_mask"],
                                 "d": decoded_reason_code("value_out_of_domain")}   # v4: the code
    SHAPES["full_spell_row_v4"](row)


# --- ancillary rows ---

def test_an_attribution_without_is_coa_is_rejected():
    row = copy.deepcopy(golden_rows("advancement_row_v1"))
    row["coa_attribution"].pop("is_coa")
    with pytest.raises(ShapeError, match="is_coa"):
        SHAPES["advancement_row_v1"](row)


def test_a_raw_cols_map_keyed_by_a_name_is_rejected():
    """`cols` is an index-keyed audit map. A named key means someone asserted a column meaning."""
    row = copy.deepcopy(golden_rows("essence_row_v1"))
    row["cols"] = {"required_level": 60}
    with pytest.raises(ShapeError, match="decimal cell index"):
        SHAPES["essence_row_v1"](row)


def test_a_content_row_missing_its_provenance_digest_is_rejected():
    row = copy.deepcopy(golden_rows("content_row_v1"))
    row["provenance"].pop("file_sha256")
    with pytest.raises(ShapeError, match="file_sha256"):
        SHAPES["content_row_v1"](row)


def test_a_class_type_row_with_a_non_integer_id_is_rejected():
    row = copy.deepcopy(golden_rows("class_type_row_v1"))
    row["class_type_id"] = "14"
    with pytest.raises(ShapeError, match="class_type_id"):
        SHAPES["class_type_row_v1"](row)


def test_a_tab_type_row_with_a_boolean_id_is_rejected():
    """isinstance(True, int) is True in Python; a boolean is never a valid id."""
    row = copy.deepcopy(golden_rows("tab_type_row_v1"))
    row["tab_type_id"] = True
    with pytest.raises(ShapeError, match="tab_type_id"):
        SHAPES["tab_type_row_v1"](row)
