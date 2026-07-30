# tests/test_e0r1_description_raw.py
"""E0R.1 Task 2.1 — the client tooltip `description` (Spell.dbc cell 170) is a real extracted string. It is
raw_only (its $s1 macros are unresolved templates, so it is never a mechanic), but it MUST be emitted into
the v3 `raw` block with its offset + resolved text so the artifact is lossless and downstream guides can
show the client tooltip."""
from coa_client_extract.spell_layout import load_default_policy
from coa_client_extract.spell_record import build_field_descriptors, iter_spell_records
from tests._spell_fixtures import spell_dbc_desc, v2_desc_policy


def test_default_policy_carries_description_at_170_raw_only():
    fp = load_default_policy().tables["Spell"]["fields"]["description"]
    assert fp.cell == 170 and fp.kind == "string" and fp.promotion == "raw_only"


def test_description_emitted_into_raw_with_offset_and_resolved():
    policy = v2_desc_policy()
    row = list(iter_spell_records(spell_dbc_desc(), {}, policy=policy,
                                  provenance={"effective_archive": "patch-T.MPQ"}))[0]
    desc = row["raw"]["description"]
    assert desc["resolved"] == "Hurls a fiery ball that causes Fire damage."
    assert "raw_offset" in desc and desc["raw_offset"] > 0
    # E0R.2 T6.2: the pointer is hoisted into the field descriptors; the cell keeps its substrate
    assert build_field_descriptors(policy.doc)["fields"]["description"]["policy_ref"] \
        .endswith("/description")


def test_description_is_never_a_mechanic():
    row = list(iter_spell_records(spell_dbc_desc(), {}, policy=v2_desc_policy(),
                                  provenance={"effective_archive": "patch-T.MPQ"}))[0]
    assert "description" not in row["mechanics"]
