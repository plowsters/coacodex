"""E0R.2 T6.1: field descriptors, derived from the policy and cross-checked by both trust boundaries.

The real generation is 523,026,495 of 536,870,912 bytes — 97.42% of ceiling. The measured attribution
says the dominant redundancy is not descriptions (mostly unique, ~8 MB dedupable) but per-cell CONSTANT
metadata: `policy_ref` is 23.6% of the payload (88.6 MB) with exactly one distinct value per field, and
`join_name` another 5.9% (22.3 MB) with the same property. Both are hoistable into a single per-field
descriptor.

This is the EXPAND half. Descriptors exist, both languages derive them independently from the policy and
reject a staged one that disagrees, and both expanders accept a cell WITH or WITHOUT its inline
`policy_ref`/`join_name`. Nothing is hoisted out of a row yet — T6.2 migrates and contracts atomically,
which is what keeps every commit green.

The correction that shapes the whole design: a single `policy_ref` per field CANNOT reconstruct a
resolved join. `_compact_join` emits `components.{index,side_id,side_value}`, each with its own ref
resolved through the join mapping (there is no synthetic `/joins/...` policy node). Descriptors are
therefore kind-aware, and a scalar-only descriptor would silently lose two thirds of a join cell.
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess

import pytest

from coa_client_extract.contracts import policy_ref, policy_ref_component
from coa_client_extract.spell_layout import load_spell_policy
from coa_client_extract.spell_record import (FIELD_DESCRIPTORS_SCHEMA, DescriptorError,
                                             _expand_compact, build_field_descriptors,
                                             require_field_descriptors)
from tests._e0r2_fixtures import corpus_policy_doc, corpus_rows

REPO = __import__("pathlib").Path(__file__).resolve().parent.parent


def _policy():
    return load_spell_policy(payload=corpus_policy_doc())


def _descriptors():
    return build_field_descriptors(corpus_policy_doc())


def _full_rows():
    return corpus_rows("full_rows.jsonl", "valid_full")


def _strip(cell: dict) -> dict:
    """The same cell with everything a descriptor supplies removed — the T6.2 encoding, expanded here."""
    out = {k: v for k, v in cell.items() if k not in ("policy_ref", "join_name")}
    if "components" in cell:
        out["components"] = {k: {kk: vv for kk, vv in c.items() if kk != "policy_ref"}
                             for k, c in cell["components"].items()}
    return out


# --- the descriptor is derived from the policy, and it is kind-aware ---

def test_the_descriptor_document_covers_every_scalar_field_and_every_join():
    doc = corpus_policy_doc()
    d = build_field_descriptors(doc)
    assert d["schema_version"] == FIELD_DESCRIPTORS_SCHEMA
    assert d["policy_sha256"] == doc["sha256"], "a descriptor is only meaningful against ONE policy"
    assert set(d["fields"]) == set(doc["tables"]["Spell"]["fields"]) | set(doc["joins"])


def test_a_scalar_descriptor_carries_the_field_pointer():
    d = _descriptors()["fields"]["power_type"]
    assert d == {"kind": "scalar", "policy_ref": policy_ref("Spell", "power_type")}


def test_a_join_descriptor_carries_the_index_pointer_and_all_three_component_pointers():
    """The round-2 correction, pinned: one `policy_ref` cannot reconstruct a resolved join.
    `index_policy_ref` serves the ABSENT form (null index cell), `components` the RESOLVED form."""
    doc = corpus_policy_doc()
    spec = {"index_field": "casting_time_index", "side_table": "SpellCastTimes",
            "side_value_field": "base_ms"}
    assert _descriptors()["fields"]["cast_time_ms"] == {
        "kind": "join", "join_name": "cast_time_ms",
        "index_policy_ref": policy_ref("Spell", "casting_time_index"),
        "components": {part: {"policy_ref": policy_ref_component(spec, part)}
                       for part in ("index", "side_id", "side_value")},
    }
    assert doc["joins"]["cast_time_ms"]["side_table"] == "SpellCastTimes"


def test_component_pointers_resolve_through_the_join_mapping_not_a_joins_node():
    d = _descriptors()["fields"]["duration_ms"]["components"]
    assert d["index"]["policy_ref"] == "/tables/Spell/fields/duration_index"
    assert d["side_id"]["policy_ref"] == "/tables/SpellDuration/fields/id"
    assert d["side_value"]["policy_ref"] == "/tables/SpellDuration/fields/base_ms"
    assert not any("/joins/" in c["policy_ref"] for c in d.values())


# --- the golden corpus exercises all three cell shapes ---

def test_the_corpus_covers_scalar_absent_join_and_resolved_join():
    """Every cell in all 208,447 real rows is scalar or join-absent today, so the resolved-join path is
    unexercised by real data — and reachable the moment E1 adopts a join. The corpus must carry one."""
    shapes = set()
    for row in _full_rows():
        for cell in row["raw"].values():
            if "join_name" not in cell:
                shapes.add("scalar")
            elif "components" not in cell:
                shapes.add("join_absent")
            else:
                shapes.add("join_resolved")
                assert set(cell["components"]) == {"index", "side_id", "side_value"}
    assert shapes == {"scalar", "join_absent", "join_resolved"}


# --- expansion is identical with or without the inline metadata ---

@pytest.mark.parametrize("case", ["scalar", "join_absent", "join_resolved"])
def test_a_hoisted_cell_expands_to_exactly_what_the_fat_cell_expands_to(case):
    policy, descriptors = _policy(), _descriptors()
    seen = 0
    for row in _full_rows():
        for field, cell in row["raw"].items():
            shape = ("scalar" if "join_name" not in cell
                     else "join_absent" if "components" not in cell else "join_resolved")
            if shape != case:
                continue
            seen += 1
            fat = _expand_compact(cell, policy, field=field, descriptors=descriptors)
            thin = _expand_compact(_strip(cell), policy, field=field, descriptors=descriptors)
            assert thin == fat, field
            # and the expansion still CARRIES what was hoisted — the rich dialect is unchanged
            if shape == "scalar":
                assert thin["policy_ref"] == descriptors["fields"][field]["policy_ref"]
            else:
                assert thin["join_name"] == field
    assert seen, f"the corpus exercises no {case} cell"


def test_both_encodings_are_accepted_at_this_step():
    """T6.1 EXPANDS: a fat cell must still expand with no descriptors at all, or the tree could not stay
    green between here and T6.2's migration."""
    policy = _policy()
    for row in _full_rows():
        for field, cell in row["raw"].items():
            assert _expand_compact(cell, policy) == _expand_compact(
                cell, policy, field=field, descriptors=_descriptors())


def test_a_hoisted_cell_without_a_descriptor_is_refused_rather_than_guessed():
    policy = _policy()
    cell = _strip(_full_rows()[0]["raw"]["power_type"])
    with pytest.raises(DescriptorError, match="power_type"):
        _expand_compact(cell, policy, field="power_type")


# --- a staged descriptor must equal the policy-derived one ---

def _tamper(mutate):
    staged = _descriptors()
    mutate(staged)
    return staged


@pytest.mark.parametrize("mutate, match", [
    (lambda d: d["fields"]["power_type"].__setitem__("policy_ref", "/tables/Spell/fields/school_mask"),
     "power_type"),
    (lambda d: d["fields"].pop("school_mask"), "school_mask"),
    (lambda d: d["fields"].__setitem__("invented", {"kind": "scalar", "policy_ref": "/x"}), "invented"),
    (lambda d: d["fields"]["cast_time_ms"]["components"]["side_value"].__setitem__(
        "policy_ref", "/tables/SpellDuration/fields/base_ms"), "cast_time_ms"),
    (lambda d: d["fields"].__setitem__("cast_time_ms", {"kind": "scalar", "policy_ref": "/x"}),
     "cast_time_ms"),
    (lambda d: d.__setitem__("policy_sha256", "0" * 64), "policy_sha256"),
    (lambda d: d.__setitem__("schema_version", "coa-client-spell-fields-v0"), "schema_version"),
])
def test_a_staged_descriptor_that_differs_from_the_policy_is_rejected(mutate, match):
    """A tampered descriptor could redefine what every cell MEANS while keeping compact->rich expansion
    internally self-consistent. The only defence is deriving the expectation from the policy."""
    with pytest.raises(DescriptorError, match=match):
        require_field_descriptors(_tamper(mutate), corpus_policy_doc())


def test_the_honest_descriptor_is_accepted():
    require_field_descriptors(_descriptors(), corpus_policy_doc())


def test_a_descriptor_derived_from_a_different_policy_is_rejected():
    other = copy.deepcopy(corpus_policy_doc())
    other["joins"]["cast_time_ms"]["side_value_field"] = "id"
    with pytest.raises(DescriptorError):
        require_field_descriptors(build_field_descriptors(other), corpus_policy_doc())


# --- the two trust boundaries must derive the SAME descriptor ---

@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_node_derives_a_byte_identical_descriptor_document():
    """Two independent implementations, one canonical document. If they disagree, a hoisted row means
    two different things on the two sides of the boundary — which is the whole failure mode T6.2 would
    otherwise ship."""
    script = (
        'import { buildFieldDescriptors } from "./coa_scraper/scripts/lib/mechanics-projection.mjs";'
        'import fs from "node:fs";'
        'const doc = JSON.parse(fs.readFileSync("tests/golden/e0r1_corpus/policy.json", "utf8"));'
        'process.stdout.write(JSON.stringify(buildFieldDescriptors(doc)));'
    )
    out = subprocess.run(["node", "--input-type=module", "-e", script], cwd=REPO,
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == _descriptors()
