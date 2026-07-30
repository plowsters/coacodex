"""E0R.2 T2.1: `min_records: 1` is not a domain gate — a one-spell generation passes it, and so does a
one-class-type generation, which is useless for a class guide.

The client topology records the exact source-domain count, so the contract DERIVES the expectation
instead of guessing a floor. The count must be rooted in something the validator trusts independently of
the candidate: deriving it from `manifest.binding.topology` is circular, because a malformed candidate
can set that count to 1, write one spell row, recompute `candidate_trust_sha256`, and satisfy the
equality. The REVIEWED POLICY states the count, and the policy is pinned by a lock both languages read.

The trust chain, in order, each step its own assertion:

  1. the staged `spell_layout_v2.json` child hashes to the LOCALLY SUPPORTED policy (the lock);
  2. `manifest.binding.policy_sha256` equals that same hash;
  3. `manifest.binding.topology` matches the staged policy's reviewed `bound` facet-for-facet;
  4. only then are child cardinalities resolved — against `policy.bound`, never against the manifest.
"""
from __future__ import annotations

import json

import pytest

from coa_client_extract.publish import ResolveError, validate_candidate_generation

from tests._e0r2_fixtures import stage_candidate

LOCK = "spell_layout.lock.json"


def _validate(gen_dir):
    """Validate against the lock the fixture wrote — the fixture's synthetic policy is what is 'locally
    supported' for these tests, exactly as production's committed lock is for the real policy."""
    return validate_candidate_generation(gen_dir, lock_path=gen_dir.parent / LOCK)


def test_a_wellformed_candidate_still_validates(tmp_path):
    """Every negative below is only meaningful if the honest case passes."""
    resolved = _validate(stage_candidate(tmp_path))
    assert resolved["manifest"]["children"]["coa_client_spell.jsonl"]["records"] == 3


# --- the trust chain ---

def test_a_staged_policy_that_is_not_the_locally_supported_policy_is_rejected(tmp_path):
    """Step 1: a candidate cannot bring its own policy and be believed. This is THE attack the
    manifest-rooted rule permitted — forge the source count in the policy the candidate ships."""
    gen = stage_candidate(tmp_path, forge_staged_policy_bound_record_count=1, truncate_full_to=1)
    with pytest.raises(ResolveError, match="staged policy .* not the supported policy"):
        _validate(gen)


def test_a_manifest_policy_hash_that_disagrees_with_the_staged_policy_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, forge_manifest_policy_sha256="0" * 64)
    with pytest.raises(ResolveError, match="binding.policy_sha256"):
        _validate(gen)


def test_a_candidate_that_rewrites_its_own_topology_to_match_a_truncation_is_rejected(tmp_path):
    """Step 3, and the reason the rule is policy-rooted: truncate to one spell, set the manifest topology
    to one, recompute candidate trust. The reviewed policy — not the candidate — states the count."""
    gen = stage_candidate(tmp_path, truncate_full_to=1, forge_manifest_topology_record_count=1)
    with pytest.raises(ResolveError, match="topology does not match the reviewed bound"):
        _validate(gen)


def test_a_candidate_whose_staged_policy_is_unbound_is_rejected(tmp_path):
    """`bound: None` means the policy was never proven against a client capture. A generation produced
    from one has no provable source domain, so the rules are REFUSED rather than skipped — skipping is
    how a hole opens."""
    gen = stage_candidate(tmp_path, unbind_staged_policy=True)
    with pytest.raises(ResolveError, match="unbound|not the supported policy"):
        _validate(gen)


# --- the relational rules ---

def test_a_truncated_full_child_is_rejected(tmp_path):
    """Three spells in the reviewed bound; stage two, honestly registered."""
    gen = stage_candidate(tmp_path, truncate_full_to=2)
    with pytest.raises(ResolveError, match="reviewed_bound_record_count"):
        _validate(gen)


def test_an_ancillary_child_truncated_to_one_row_is_rejected(tmp_path):
    """A floor of 1 admitted this: one class-type row is not a generation a class guide can use."""
    gen = stage_candidate(tmp_path, truncate_child=("coa_client_class_types.jsonl", 1))
    with pytest.raises(ResolveError, match="derived_from_source_topology"):
        _validate(gen)


@pytest.mark.parametrize("child", ["coa_client_tab_types.jsonl", "coa_client_essence.jsonl"])
def test_every_one_to_one_ancillary_child_is_gated(tmp_path, child):
    gen = stage_candidate(tmp_path, truncate_child=(child, 0))
    with pytest.raises(ResolveError, match="derived_from_source_topology"):
        _validate(gen)


def test_a_declared_derivation_whose_accounting_does_not_close_is_rejected(tmp_path):
    """kept + rejected must equal the REVIEWED source count; a silent drop breaks the identity."""
    gen = stage_candidate(tmp_path, advancement_source=3,
                          advancement_derivation={"source": "CharacterAdvancement",
                                                  "kept": 2, "rejected": 0})
    with pytest.raises(ResolveError, match="declared_derivation"):
        _validate(gen)


def test_a_declared_derivation_that_disagrees_with_the_emitted_child_is_rejected(tmp_path):
    """The other leg: the accounting closes, but the child does not carry `kept` rows."""
    gen = stage_candidate(tmp_path, advancement_kept=2, advancement_source=3,
                          advancement_derivation={"source": "CharacterAdvancement",
                                                  "kept": 3, "rejected": 0})
    with pytest.raises(ResolveError, match="declared_derivation"):
        _validate(gen)


def test_a_declared_derivation_naming_the_wrong_source_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, advancement_derivation={"source": "SomethingElse",
                                                            "kept": 2, "rejected": 1})
    with pytest.raises(ResolveError, match="source"):
        _validate(gen)


def test_a_missing_derivation_block_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, drop_derivations=True)
    with pytest.raises(ResolveError, match="derivation"):
        _validate(gen)


def test_a_content_derivation_that_disagrees_with_the_reviewed_source_entries_is_rejected(tmp_path):
    """The Content child has no WDBC source; its count is rooted in `content_sources`, not `bound`."""
    gen = stage_candidate(tmp_path, content_entries=2,
                          content_derivation={"source": "content_json", "source_entries": 99,
                                              "kept": 2, "rejected": 0})
    with pytest.raises(ResolveError, match="declared_content_derivation"):
        _validate(gen)


def test_a_content_child_shorter_than_its_declared_kept_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, truncate_child=("coa_client_content.jsonl", 1))
    with pytest.raises(ResolveError, match="declared_content_derivation"):
        _validate(gen)


def test_a_json_child_with_more_than_one_document_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, duplicate_json_document="coa_client_archive_plan.json")
    with pytest.raises(ResolveError, match="single_document"):
        _validate(gen)


# --- cross-child-derived counts (defense in depth, not new coverage) ---

def test_an_icon_catalog_shorter_than_the_full_domain_is_rejected(tmp_path):
    """The merge-join already enforces this exactly; the count check is a second, independently-derived
    number. Either message is a correct rejection."""
    gen = stage_candidate(tmp_path, truncate_icons_to=2)
    with pytest.raises(ResolveError, match="equals_full_spell_records|icons_agree"):
        _validate(gen)


def test_a_projection_missing_an_is_coa_row_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, drop_projection_rows=1)
    with pytest.raises(ResolveError, match="equals_is_coa_full_records|projection_is_coa_subset"):
        _validate(gen)


# --- the contract is a whitelist ---

def test_an_unregistered_child_is_rejected(tmp_path):
    """candidate_trust_sha256 AUTHENTICATES an added child; it does not reject one. The digest covers
    `children`, so a child added to the manifest AND the directory is perfectly self-consistent."""
    gen = stage_candidate(tmp_path, extra_child=("smuggled.jsonl", b'{"x":1}\n'))
    with pytest.raises(ResolveError, match="unregistered child"):
        _validate(gen)


def test_a_registered_but_uncontracted_child_is_rejected(tmp_path):
    """The stronger case: registered in the manifest, present on disk, hash-correct, trust digest
    recomputed — and still refused, because the contract is the whitelist."""
    gen = stage_candidate(tmp_path)
    body = b'{"x":1}\n'
    (gen / "smuggled.jsonl").write_bytes(body)
    manifest = json.loads((gen / "manifest.json").read_text())
    import hashlib

    from coa_client_extract.publish import candidate_trust_sha256
    manifest["children"]["smuggled.jsonl"] = {
        "sha256": hashlib.sha256(body).hexdigest(), "byte_length": len(body), "records": 1,
        "schema_version": "smuggled-v1"}
    manifest["candidate_trust_sha256"] = candidate_trust_sha256(manifest)
    (gen / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                                  sort_keys=True) + "\n")
    with pytest.raises(ResolveError, match="unregistered child"):
        _validate(gen)
