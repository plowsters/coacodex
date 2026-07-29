"""E0R.2 T6.4: the compatibility matrix — the registry, exercised rather than described.

Three revisions are `supported` and they differ in what they actually contain: `e0r-v1` carries v3 spell
rows with inline pointers and the flat v1 icon catalog; `e0r-v2` carries v4 hoisted+interned rows and the
two decoder children; `e0r-v3` adds the normalized icon pair. Until something STAGES each one and puts it
through the validator, "older revisions stay resolvable" is a promise the code makes to itself — the
existing coverage proves only that a CLONE of `current` under another name resolves, which exercises
membership but not one byte of the older encodings.

That distinction is what rollback and the publish transaction's predecessor read depend on: both must
work against a generation produced before the revision the working tree happens to ship.

The parametrization is DERIVED from the registry, so a fourth revision cannot be added without landing
in this matrix.
"""
from __future__ import annotations

import json
import re

import pytest

from coa_client_extract.contracts import load_contract_registry, load_current_contract
from coa_client_extract.publish import (ResolveError, resolve_active_generation)
from coa_client_extract.spell_icons import ASSET_CHILD as ICON_ASSET_CHILD
from coa_client_extract.spell_layout import load_spell_policy
from coa_client_extract.spell_record import (FIELD_DESCRIPTORS_CHILD, WIRE_SCHEMA_CHILD,
                                             build_field_descriptors)
from tests._e0r2_fixtures import (CORPUS, CORPUS_V4, bind_policy_doc, clean_budget, corpus_policy_doc,
                                  corpus_rows, stage_candidate, staged_writer, supported_contract,
                                  validate_staged)

SUPPORTED = tuple(sorted(load_contract_registry()["supported"]))
CURRENT = load_current_contract()[0]


def _publish(root, revision):
    """A PUBLISHED generation under `revision`, pointer and all — the artifact `resolve_active_generation`
    reads, which is the path rollback actually takes."""
    gw, candidate, ceilings = staged_writer(root, contract=supported_contract(revision))
    gw.finalize_and_publish(candidate_manifest=candidate, validation={"python": True, "node": True},
                            budget=clean_budget(ceilings))
    return gw.root


# --- the matrix is over the real registry ---

def test_the_matrix_covers_every_supported_revision():
    assert set(SUPPORTED) == set(load_contract_registry()["supported"])
    assert SUPPORTED != (CURRENT,), "a matrix over `current` alone proves nothing about older revisions"


@pytest.mark.parametrize("revision", SUPPORTED)
def test_a_candidate_of_every_supported_revision_validates(tmp_path, revision):
    gen = stage_candidate(tmp_path, contract=supported_contract(revision))
    resolved = validate_staged(gen)
    assert resolved["manifest"]["binding"]["generation_contract"]["revision"] == revision


@pytest.mark.parametrize("revision", SUPPORTED)
def test_a_published_generation_of_every_supported_revision_resolves(tmp_path, revision):
    """Not the same check twice: the candidate path validates by directory, the resolver arrives through
    the POINTER and re-derives the required-child set from the generation's own staged contract."""
    resolved = resolve_active_generation(_publish(tmp_path, revision))
    _, doc = supported_contract(revision)
    assert resolved["manifest"]["binding"]["generation_contract"]["revision"] == revision
    assert set(resolved["children"]) == set(doc["children"])


# --- a child belongs to a revision, not to the working tree ---

@pytest.mark.parametrize("revision, foreign", [
    ("e0r-v1", FIELD_DESCRIPTORS_CHILD),          # e0r-v2 introduced it
    ("e0r-v1", WIRE_SCHEMA_CHILD),                # e0r-v2 introduced it
    ("e0r-v1", ICON_ASSET_CHILD),                 # e0r-v3 introduced it
    ("e0r-v2", ICON_ASSET_CHILD),
])
def test_a_generation_carrying_a_child_from_a_later_revision_is_rejected(tmp_path, revision, foreign):
    """The contract is a whitelist per REVISION. A consumer that globs the directory would otherwise
    read a child the generation's own contract does not describe."""
    gen = stage_candidate(tmp_path, contract=supported_contract(revision),
                          extra_child=(foreign, b"{}\n"))
    with pytest.raises(ResolveError, match="unregistered child"):
        validate_staged(gen)


def test_the_same_child_is_required_by_one_revision_and_refused_by_another(tmp_path):
    """`coa_client_icon_assets.jsonl` is required under `e0r-v3` and unregistered under `e0r-v1`. The
    requirement is read from the generation's own revision — deriving it from `current` instead is what
    would make every older generation unresolvable the moment a revision ships."""
    dropped = stage_candidate(tmp_path / "v3", contract=supported_contract("e0r-v3"),
                              drop_children=(ICON_ASSET_CHILD,))
    with pytest.raises(ResolveError, match=f"required child {ICON_ASSET_CHILD!r} missing"):
        validate_staged(dropped)
    validate_staged(stage_candidate(tmp_path / "v1", contract=supported_contract("e0r-v1")))


# --- each revision pins exactly one encoding ---

@pytest.mark.parametrize("revision, child, foreign_rows", [
    ("e0r-v1", "coa_client_spell.jsonl", ("full", CORPUS_V4)),        # interned cells in a v3 generation
    ("e0r-v3", "coa_client_spell.jsonl", ("full", CORPUS)),           # inline pointers in a v4 generation
    ("e0r-v2", "coa_client_spell_icons.jsonl", ("icons", CORPUS_V4)),  # associations without an asset child
    ("e0r-v3", "coa_client_spell_icons.jsonl", ("icons", CORPUS)),     # the flat catalog after normalizing
])
def test_a_generation_using_another_revisions_encoding_is_rejected(tmp_path, revision, child,
                                                                   foreign_rows):
    """A revision names one SHAPE per child, and every shape pins the row `schema_version` it accepts.
    Mixing encodings is therefore refused at the row, not merely discouraged in a note."""
    kind, corpus = foreign_rows
    rows = corpus_rows("full_rows.jsonl" if kind == "full" else "icons.jsonl",
                       "valid_full" if kind == "full" else "valid_icon", corpus=corpus)
    gen = stage_candidate(tmp_path, contract=supported_contract(revision), **{kind: rows})
    with pytest.raises(ResolveError, match=re.escape(f"shape: child {child!r}")):
        validate_staged(gen)


def test_the_two_encodings_expand_to_the_same_envelope():
    """v3 (inline pointers) and v4 (hoisted + interned) are two ENCODINGS of one observation. If they
    ever expanded differently, a spell's meaning would depend on which revision published it — the exact
    thing a versioned registry exists to prevent. This is also what guards the concrete regression the
    v4 migration invited: quietly deleting the v3 branch of `_expand_compact`."""
    from coa_client_extract.publish import _expand_full_raw

    policy = load_spell_policy(bind_policy_doc(corpus_policy_doc(), spell_records=3))
    # The v4 half needs descriptors because that is where its pointers went; the v3 half must NOT, since
    # it carries them inline. Handing both the same descriptors is what proves the pointer moved rather
    # than changed.
    descriptors = build_field_descriptors(policy.doc)
    v3 = corpus_rows("full_rows.jsonl", "valid_full", corpus=CORPUS)
    v4 = corpus_rows("full_rows.jsonl", "valid_full", corpus=CORPUS_V4)
    assert len(v3) == len(v4) == 3
    for older, newer in zip(v3, v4):
        assert older["spell_id"] == newer["spell_id"]
        assert older["raw"] != newer["raw"], "the corpora must differ in ENCODING or this proves nothing"
        assert (_expand_full_raw(older["spell_id"], older["raw"], policy,
                                 row_schema=older["schema_version"]) ==
                _expand_full_raw(newer["spell_id"], newer["raw"], policy, descriptors=descriptors,
                                 row_schema=newer["schema_version"]))


# --- the declared child_schema_version is load-bearing ---

@pytest.mark.parametrize("revision", SUPPORTED)
def test_the_manifest_registers_the_schema_version_its_revision_declares(tmp_path, revision):
    _, doc = supported_contract(revision)
    gen = stage_candidate(tmp_path, contract=(revision, doc))
    children = json.loads((gen / "manifest.json").read_text(encoding="utf-8"))["children"]
    for name, spec in doc["children"].items():
        assert children[name]["schema_version"] == spec["child_schema_version"], name


def test_a_child_registered_under_another_revisions_schema_version_is_rejected(tmp_path):
    """Every revision DECLARES a `child_schema_version` per child. If nothing checks it the field is
    decorative, and a consumer that dispatches on the manifest-registered version can be handed v4 rows
    labelled v3 — with every hash, byte count and record count perfectly valid."""
    gen = stage_candidate(tmp_path,
                          forge_child_schema=("coa_client_spell.jsonl", "coa-client-spell-v3"))
    with pytest.raises(ResolveError, match="schema_version"):
        validate_staged(gen)
