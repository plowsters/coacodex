"""E0R.2 T6.2: v4 spell rows — per-field constants hoisted, vocabularies interned.

The measured attribution over the real 523 MB generation:

    policy_ref       23.6%   88.6 MB   constant per field  -> the descriptor child
    decoded_reason   14.8%   55.4 MB   closed vocabulary   -> one integer
    state             9.7%   36.3 MB   closed vocabulary   -> one integer
    join_name         5.9%   22.3 MB   constant per field  -> the descriptor child

A v4 compact cell is `{"s": <state code>, "d": <reason code>, <substrate>}`. Everything else is restored
from the staged field descriptors, which both languages re-derive from the policy (T6.1).

The projection stays `coa-client-spell-projection-v3` on purpose: `_expand_compact` absorbs the encoding
change, so `expand_compact(full.raw) == projection.field_observations` stays literally true and the
consumer sees no change at all.

What this must NOT break: `e0r-v1` stays in `supported`, so a generation published under it must still
validate and still expand. The v3 decoder and its shapes are retained and the v3 corpus stays where it
is — a new corpus is added BESIDE it. What goes away is the dual-encoding tolerance T6.1 added WITHIN a
schema: a v4 row must be v4-encoded.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from coa_client_extract.contracts import (DECODED_REASONS, GENERATION_CONTRACT_CHILD,
                                          OBSERVATION_STATES, WireSchemaError, decoded_reason_code,
                                          decoded_reason_name, load_contract_registry,
                                          load_observation_wire_schema, observation_state_code,
                                          observation_state_name, require_observation_wire)
from coa_client_extract.shapes import SHAPES, ShapeError
from coa_client_extract.spell_layout import load_spell_policy
from coa_client_extract.spell_record import (FIELD_DESCRIPTORS_CHILD, SPELL_SCHEMA_V3,
                                             SPELL_SCHEMA_V4, WIRE_SCHEMA_CHILD, _compact,
                                             _expand_compact, build_field_descriptors,
                                             compact_cell_v4)
from tests._e0r2_fixtures import corpus_policy_doc, corpus_rows

CORPUS_V3 = Path(__file__).resolve().parent / "golden" / "e0r1_corpus"
CORPUS_V4 = Path(__file__).resolve().parent / "golden" / "e0r2_corpus_v4"


def _policy():
    return load_spell_policy(payload=corpus_policy_doc())


def _descriptors():
    return build_field_descriptors(corpus_policy_doc())


def _v3_rows():
    return corpus_rows("full_rows.jsonl", "valid_full")


def _v4_rows():
    rows = [json.loads(line) for line in
            (CORPUS_V4 / "full_rows.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return [{k: v for k, v in r.items() if k not in ("case", "golden_accept")}
            for r in rows if r["case"] == "valid_full"]


# --- the vocabularies intern bijectively, and fail closed ---

def test_every_vocabulary_member_round_trips_through_its_code():
    for state in OBSERVATION_STATES:
        assert observation_state_name(observation_state_code(state)) == state
    for reason in DECODED_REASONS:
        assert decoded_reason_name(decoded_reason_code(reason)) == reason


def test_the_codes_are_a_bijection():
    wire = load_observation_wire_schema()
    for group in ("states", "decoded_reasons"):
        assert len(set(wire[group].values())) == len(wire[group]), group


@pytest.mark.parametrize("cell, match", [
    ({"s": 99, "d": 0, "raw_u32": 1}, "state"),
    ({"s": 1, "d": 99, "raw_u32": 1}, "decoded_reason"),
    ({"s": -1, "d": 0, "raw_u32": 1}, "state"),
    ({"s": "present", "d": 0, "raw_u32": 1}, "state"),
])
def test_an_out_of_range_code_fails_closed(cell, match):
    """An uncodeable cell must never round-trip as a default: a wrong `state` silently becoming
    `present` is exactly the silent loss this milestone exists to prevent."""
    with pytest.raises(WireSchemaError, match=match):
        _expand_compact(cell, _policy(), field="power_type", descriptors=_descriptors(),
                        row_schema=SPELL_SCHEMA_V4)


# --- a v4 cell expands to EXACTLY what its v3 twin expands to ---

@pytest.mark.parametrize("case", ["scalar", "join_absent", "join_resolved"])
def test_v4_expansion_equals_v3_expansion_for_every_cell_shape(case):
    policy, descriptors = _policy(), _descriptors()
    seen = 0
    for row in _v3_rows():
        for field, cell in row["raw"].items():
            shape = ("scalar" if "join_name" not in cell
                     else "join_absent" if "components" not in cell else "join_resolved")
            if shape != case:
                continue
            seen += 1
            v3 = _expand_compact(cell, policy, field=field, descriptors=descriptors,
                                 row_schema=SPELL_SCHEMA_V3)
            v4 = _expand_compact(compact_cell_v4(cell), policy, field=field, descriptors=descriptors,
                                 row_schema=SPELL_SCHEMA_V4)
            assert v4 == v3, field
    assert seen, f"the corpus exercises no {case} cell"


def test_the_committed_v4_corpus_expands_to_the_committed_v3_expansion():
    """Not a re-encode of the v3 corpus at test time: the BYTES on disk are what a v4 producer emits,
    so the encoding is pinned rather than re-derived by the same code that would be wrong."""
    policy, descriptors = _policy(), _descriptors()
    v3, v4 = _v3_rows(), _v4_rows()
    assert len(v4) == len(v3) > 0
    for a, b in zip(v3, v4):
        assert b["schema_version"] == SPELL_SCHEMA_V4
        assert a["spell_id"] == b["spell_id"]
        assert set(a["raw"]) == set(b["raw"])
        for field in a["raw"]:
            assert (_expand_compact(b["raw"][field], policy, field=field, descriptors=descriptors,
                                    row_schema=SPELL_SCHEMA_V4)
                    == _expand_compact(a["raw"][field], policy, field=field, descriptors=descriptors,
                                       row_schema=SPELL_SCHEMA_V3)), field


def test_a_v4_cell_carries_no_hoisted_key():
    for row in _v4_rows():
        for field, cell in row["raw"].items():
            assert set(cell) <= {"s", "d", "raw_u32", "raw_offset", "resolved", "components"}, field
            for part in (cell.get("components") or {}).values():
                assert set(part) <= {"s", "d", "raw_u32", "raw_offset", "resolved"}


# --- within v4 the dual-encoding tolerance is gone ---

@pytest.mark.parametrize("extra", ["policy_ref", "join_name", "state", "decoded_reason"])
def test_a_v4_cell_that_repeats_a_hoisted_key_is_rejected(extra):
    """T6.1 tolerated both encodings so the tree could stay green across the migration. Inside v4 that
    tolerance is a hole: a cell could claim a policy_ref the descriptor disagrees with."""
    cell = {"s": observation_state_code("present"), "d": decoded_reason_code("decoded"), "raw_u32": 3,
            extra: "smuggled"}
    with pytest.raises((WireSchemaError, ShapeError, ValueError), match=extra):
        _expand_compact(cell, _policy(), field="power_type", descriptors=_descriptors(),
                        row_schema=SPELL_SCHEMA_V4)


def test_a_v3_row_still_expands_because_e0r_v1_is_still_supported():
    policy, descriptors = _policy(), _descriptors()
    for row in _v3_rows():
        for field, cell in row["raw"].items():
            assert _expand_compact(cell, policy, field=field, descriptors=descriptors,
                                   row_schema=SPELL_SCHEMA_V3)


# --- the vocabulary comes from the trusted copy, never from the generation ---

def test_a_staged_wire_schema_that_differs_from_the_trusted_copy_is_rejected():
    staged = copy.deepcopy(load_observation_wire_schema())
    staged["states"]["present"] = 7
    with pytest.raises(WireSchemaError, match="states"):
        require_observation_wire(staged)


def test_the_honest_staged_wire_schema_is_accepted():
    require_observation_wire(copy.deepcopy(load_observation_wire_schema()))


def test_expansion_does_not_read_the_staged_vocabulary_at_all():
    """The staged child exists so a consumer HOLDING ONLY THE GENERATION can decode it. It is never the
    authority: each language decodes with its own trusted copy, and the staged one is checked against
    that copy rather than consulted."""
    import inspect

    from coa_client_extract import spell_record

    src = inspect.getsource(spell_record._expand_compact) + inspect.getsource(
        spell_record._expand_scalar_cell)
    assert "staged" not in src


# --- the shapes ---

def test_v4_and_v3_row_shapes_are_both_registered():
    assert {"full_spell_row_v3", "full_spell_row_v4"} <= set(SHAPES)
    assert {"spell_field_descriptors_v1", "observation_wire_v1"} <= set(SHAPES)


def test_the_v4_shape_rejects_a_v3_row_and_vice_versa():
    v3, v4 = _v3_rows()[0], _v4_rows()[0]
    with pytest.raises(ShapeError):
        SHAPES["full_spell_row_v4"](copy.deepcopy(v3))
    with pytest.raises(ShapeError):
        SHAPES["full_spell_row_v3"](copy.deepcopy(v4))


def test_the_v4_shape_accepts_every_committed_v4_row():
    for row in _v4_rows():
        SHAPES["full_spell_row_v4"](copy.deepcopy(row))


def test_the_new_document_shapes_accept_what_the_producer_stages():
    SHAPES["spell_field_descriptors_v1"](_descriptors())
    SHAPES["observation_wire_v1"](copy.deepcopy(load_observation_wire_schema()))


# --- the contract revision is NEW, and the old one is untouched ---

def test_the_registry_moved_current_to_e0r_v2_and_kept_e0r_v1():
    registry = load_contract_registry()
    assert registry["current"] == "e0r-v2"
    assert {"e0r-v1", "e0r-v2"} <= set(registry["supported"]), "an older generation must stay resolvable"


def test_e0r_v1_was_not_edited():
    """Revision files are immutable: editing one changes the digest every published generation pins."""
    from coa_client_extract.contracts import CONTRACTS_DIR, generation_contract_sha256

    registry = load_contract_registry()
    doc = json.loads((CONTRACTS_DIR / "e0r-v1.json").read_text(encoding="utf-8"))
    assert generation_contract_sha256(doc) == registry["supported"]["e0r-v1"]["sha256"]
    assert doc["children"]["coa_client_spell.jsonl"]["child_schema_version"] == SPELL_SCHEMA_V3


def test_e0r_v2_declares_the_v4_child_and_the_two_new_documents():
    from coa_client_extract.contracts import load_current_contract

    revision, contract = load_current_contract()
    assert revision == "e0r-v2"
    children = contract["children"]
    assert children["coa_client_spell.jsonl"]["child_schema_version"] == SPELL_SCHEMA_V4
    assert children["coa_client_spell.jsonl"]["shape"] == "full_spell_row_v4"
    for name, shape in ((FIELD_DESCRIPTORS_CHILD, "spell_field_descriptors_v1"),
                        (WIRE_SCHEMA_CHILD, "observation_wire_v1")):
        assert children[name]["shape"] == shape
        assert children[name]["optional"] is False
        assert children[name]["cardinality"] == {"rule": "single_document"}
    assert GENERATION_CONTRACT_CHILD in children


# --- and it is actually smaller ---

def test_the_v4_encoding_is_materially_smaller_than_v3():
    """The whole point. Measured over the same rows, on the committed bytes."""
    def payload(path):
        return sum(len(json.dumps({k: v for k, v in json.loads(line).items()
                                   if k not in ("case", "golden_accept")}, separators=(",", ":")))
                   for line in path.read_text(encoding="utf-8").splitlines()
                   if line.strip() and json.loads(line)["case"] == "valid_full")

    v3_bytes = payload(CORPUS_V3 / "full_rows.jsonl")
    v4_bytes = payload(CORPUS_V4 / "full_rows.jsonl")
    assert v4_bytes < v3_bytes * 0.65, f"v3 {v3_bytes} -> v4 {v4_bytes}"


# --- the real producer emits v4 and stages both new children ---

def test_the_real_generation_is_v4_and_carries_both_new_children():
    from tests.golden import _generation

    gen = _generation()
    manifest = json.loads((gen / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["children"]["coa_client_spell.jsonl"]["schema_version"] == SPELL_SCHEMA_V4
    for name in (FIELD_DESCRIPTORS_CHILD, WIRE_SCHEMA_CHILD):
        assert name in manifest["children"], name
        assert (gen / name).is_file()
    first = json.loads((gen / "coa_client_spell.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first["schema_version"] == SPELL_SCHEMA_V4
    assert set(next(iter(first["raw"].values()))) <= {"s", "d", "raw_u32", "raw_offset", "resolved",
                                                      "components"}


def test_the_staged_descriptor_child_is_the_policy_derived_one():
    from coa_client_extract.spell_record import require_field_descriptors
    from tests.golden import _generation

    gen = _generation()
    staged = json.loads((gen / FIELD_DESCRIPTORS_CHILD).read_text(encoding="utf-8"))
    policy_doc = json.loads((gen / "spell_layout_v2.json").read_text(encoding="utf-8"))
    require_field_descriptors(staged, policy_doc)


# --- and the generation-level gate: a staged decoder must equal the derived one ---

def test_a_generation_whose_staged_descriptor_differs_from_its_policy_is_rejected(tmp_path):
    """Not a shape question — a shape has no policy. The validator re-derives the descriptors from the
    staged (already trust-chained) policy and requires equality, so a generation cannot redefine what
    its own cells observe while staying internally consistent."""
    from coa_client_extract.publish import ResolveError
    from tests._e0r2_fixtures import stage_candidate, validate_staged

    gen = stage_candidate(tmp_path, forge_descriptors=lambda d: d["fields"]["power_type"].__setitem__(
        "policy_ref", "/tables/Spell/fields/school_mask"))
    with pytest.raises(ResolveError, match="power_type"):
        validate_staged(gen)


def test_a_generation_whose_staged_wire_schema_renumbers_a_code_is_rejected(tmp_path):
    """The sharpest version of the same rule: renumbering `present` would change what EVERY cell in the
    artifact says, at once, with every hash still valid."""
    from coa_client_extract.publish import ResolveError
    from tests._e0r2_fixtures import stage_candidate, validate_staged

    gen = stage_candidate(tmp_path, forge_wire=lambda w: w["states"].__setitem__("present", 7))
    with pytest.raises(ResolveError, match="states"):
        validate_staged(gen)


def test_the_honest_generation_validates(tmp_path):
    from tests._e0r2_fixtures import stage_candidate, validate_staged

    validate_staged(stage_candidate(tmp_path))
