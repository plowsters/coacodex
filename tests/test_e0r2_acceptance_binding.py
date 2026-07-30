"""E0R.2 T4.3: the record must prove the measurements and the generation are the SAME run.

At 02e0b7c a recon document containing only `{"status": "verified"}` was accepted — the acceptance record
bound its hash and committed its bytes, but nothing tied it to the client the generation was extracted
from. A recon of a different capture, a different policy, or a client that had started shipping a table
the policy declares absent would all have been accepted verbatim. Equally, the pointer was read once at
the start: a publish landing between the resolve and the build would have combined two generations'
measurements into one attestation.

Two hashes with two different jobs:

  recon_binding_sha256   the canonical identity a recon and a generation must AGREE on. Computed from
                         both sides by the same function, so a key on one side and not the other moves it.
  recon_report_sha256    the exact normalized report bytes that were validated and embedded. What the
                         record ATTESTS to — the scan metrics, budget and proposed delta live only here.

And the mechanics side is checked against the artifacts, not the build's own claims: the emitted JSONL is
hashed and counted HERE, and its count must equal the number of unique Builder spell ids. `record_count
> 0` would accept a build that silently dropped 3,000 of 3,600 spells, which is the exact class of
silent loss this milestone exists to catch.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from coa_client_extract.cli import AcceptanceError, run_acceptance
from tests._e0r2_acceptance_fixtures import (BUILDER_UNIQUE_SPELL_IDS, acceptance_env,
                                             builder_entries_sha256, published_manifest)


# --- the recon must be bound to this generation, not merely present ---

def test_a_bare_status_only_recon_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="source_pins"):
        run_acceptance(**acceptance_env(tmp_path, recon={"status": "verified"}))


def test_a_recon_bound_to_a_different_policy_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="recon binding digest"):
        run_acceptance(**acceptance_env(tmp_path, recon_policy_sha256="0" * 64))


def test_a_recon_bound_to_a_different_client_capture_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="recon binding digest"):
        run_acceptance(**acceptance_env(tmp_path, recon_table_sha256={"Spell": "f" * 64}))


def test_a_recon_with_blocking_findings_cannot_match_the_digest(tmp_path):
    """status and blocking_findings are INSIDE the digest, so a doctored status alone cannot pass: the
    generation side contributes the REQUIRED values (verified, no findings), never the report's own."""
    with pytest.raises(AcceptanceError, match="recon binding digest"):
        run_acceptance(**acceptance_env(tmp_path, recon_blocking=[{"field": "x", "reason": "y"}]))


def test_a_client_that_started_shipping_an_expected_absent_table_is_refused(tmp_path):
    """expected_absent state is part of the substrate identity, not a detail: a client that ships
    SpellEffect is a different substrate, and its recon must not bind to this generation."""
    with pytest.raises(AcceptanceError, match="recon binding digest"):
        run_acceptance(**acceptance_env(tmp_path, recon_expected_absent_ok=False))


def test_a_recon_under_another_schema_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="recon binding digest"):
        run_acceptance(**acceptance_env(tmp_path, recon_schema_version="coa-spell-mechanics-recon-v0"))


# --- the pointer must not move under the build ---

def test_a_pointer_that_moved_during_the_build_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="pointer moved"):
        run_acceptance(**acceptance_env(tmp_path, republish_during_build=True))


def test_a_pointer_whose_manifest_hash_changed_is_refused(tmp_path):
    """Same generation_id, rewritten manifest — id equality alone would have missed it."""
    with pytest.raises(AcceptanceError, match="manifest_sha256"):
        run_acceptance(**acceptance_env(tmp_path, rewrite_manifest_during_build=True))


# --- the mechanics artifacts, checked rather than believed ---

def test_a_mechanics_manifest_claiming_a_hash_the_jsonl_does_not_have_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="mechanics jsonl sha256"):
        run_acceptance(**acceptance_env(tmp_path, forge_mechanics_output_hash=True))


def test_a_mechanics_manifest_claiming_a_count_the_jsonl_does_not_have_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="mechanics jsonl record count"):
        run_acceptance(**acceptance_env(tmp_path, forge_mechanics_record_count=99))


def test_a_mechanics_build_bound_to_another_generation_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="input_generation_id"):
        run_acceptance(**acceptance_env(
            tmp_path, forge_mechanics_binding={"input_generation_id": "deadbeef"}))


@pytest.mark.parametrize("key", ["pointer_manifest_sha256", "policy_sha256",
                                 "projection_child_sha256", "builder_entries_sha256"])
def test_every_mechanics_input_identity_is_checked(tmp_path, key):
    """Each one names a different way the build could have read something other than this generation."""
    with pytest.raises(AcceptanceError, match=key):
        run_acceptance(**acceptance_env(tmp_path, forge_mechanics_binding={key: "0" * 64}))


def test_an_incomplete_mechanics_build_is_refused(tmp_path):
    """record_count > 0 would accept a build that dropped 3,000 of 3,600 spells."""
    with pytest.raises(AcceptanceError, match="record_count .* builder spell"):
        run_acceptance(**acceptance_env(tmp_path, drop_mechanics_rows=1))


# --- coverage fails closed instead of quietly becoming {} ---

@pytest.mark.parametrize("missing", ["observation_coverage", "icon_coverage"])
def test_absent_generation_coverage_fails_instead_of_becoming_an_empty_object(tmp_path, missing):
    with pytest.raises(AcceptanceError, match=missing):
        run_acceptance(**acceptance_env(tmp_path, drop_manifest_keys=[missing]))


@pytest.mark.parametrize("missing", ["field_readiness_coverage", "per_field_winner_counts_by_source"])
def test_absent_mechanics_coverage_fails(tmp_path, missing):
    with pytest.raises(AcceptanceError, match=missing):
        run_acceptance(**acceptance_env(tmp_path, drop_mechanics_keys=[missing]))


# --- the two hashes have different jobs ---

def test_a_non_binding_recon_edit_moves_the_report_hash_but_not_the_identity_digest(tmp_path):
    """Identity is what must MATCH the generation; the report hash is what the record ATTESTS to. Only
    recording the first would let candidate metrics, budget measurements or proposed_policy_delta change
    with the acceptance record unmoved."""
    base = run_acceptance(**acceptance_env(tmp_path))
    edited = run_acceptance(**acceptance_env(tmp_path, recon_candidate_distinct_ids=999))
    assert edited["recon_binding_sha256"] == base["recon_binding_sha256"]
    assert edited["recon_report_sha256"] != base["recon_report_sha256"]


def test_the_identity_digest_is_computed_from_both_sides_independently(tmp_path):
    """Not a field-by-field walk that silently skips a key it does not know about: one equality over one
    canonical object, built from the recon's source_pins+topology and from the manifest's binding."""
    from coa_client_extract.spell_mechanics import (generation_binding_facts, recon_binding_digest,
                                                    recon_binding_facts)

    env = acceptance_env(tmp_path)
    record = run_acceptance(**env)
    report = json.loads(Path(env["recon_report_path"]).read_text(encoding="utf-8"))
    binding = published_manifest(env["dist"])["binding"]

    from_recon = recon_binding_digest(**recon_binding_facts(report))
    from_manifest = recon_binding_digest(**generation_binding_facts(binding))
    assert from_recon == from_manifest == record["recon_binding_sha256"]


def test_a_table_the_generation_never_bound_moves_the_digest(tmp_path):
    """A key present on one side and absent on the other must change the digest — that is the point of
    hashing one canonical object rather than comparing the keys both sides happen to share."""
    from coa_client_extract.spell_mechanics import (generation_binding_facts, recon_binding_digest,
                                                    recon_binding_facts)

    env = acceptance_env(tmp_path)
    report = json.loads(Path(env["recon_report_path"]).read_text(encoding="utf-8"))
    extra = json.loads(json.dumps(report))
    # A COHERENT recon of a client with one more bound table: pinned and reported, exactly as a real
    # capture of it would be. The digest must still move, because the generation bound no such table.
    extra["topology"]["tables"]["SpellVisual"] = dict(report["topology"]["tables"]["Spell"])
    extra["source_pins"]["dbc"]["SpellVisual"] = dict(report["source_pins"]["dbc"]["Spell"])
    assert recon_binding_digest(**recon_binding_facts(extra)) != \
        recon_binding_digest(**recon_binding_facts(report))
    assert recon_binding_digest(**generation_binding_facts(
        published_manifest(env["dist"])["binding"])) == recon_binding_digest(**recon_binding_facts(report))


# --- the record itself ---

def test_the_record_binds_every_identity(tmp_path):
    env = acceptance_env(tmp_path)
    record = run_acceptance(**env)
    manifest = published_manifest(env["dist"])

    assert record["schema_version"] == "coa-e0r-acceptance-summary-v3"
    assert len(record["recon_binding_sha256"]) == 64
    assert len(record["recon_report_sha256"]) == 64
    assert record["recon_report"]["status"] == "verified"       # the bytes themselves are committed
    assert record["generation_contract"]["revision"] == manifest["binding"]["generation_contract"]["revision"]
    assert len(record["generation_contract"]["sha256"]) == 64
    assert len(record["mechanics"]["jsonl_sha256"]) == 64
    assert record["mechanics"]["record_count"] == record["mechanics"]["builder_unique_spell_ids"]
    assert record["mechanics"]["builder_unique_spell_ids"] == BUILDER_UNIQUE_SPELL_IDS
    assert record["mechanics"]["binding"]["builder_entries_sha256"] == builder_entries_sha256(env)
    assert record["coverage"]["observation"]["cells"] > 0
    assert record["coverage"]["icon"]["spells"] > 0
    assert record["coverage"]["readiness"]["fields_considered"] > 0
    assert record["coverage"]["source"]


def test_the_recorded_mechanics_hash_is_the_one_the_record_writer_computed(tmp_path):
    env = acceptance_env(tmp_path)
    record = run_acceptance(**env)
    emitted = Path(env["mechanics_out"]) / "coa_mechanics.jsonl"
    assert record["mechanics"]["jsonl_sha256"] == hashlib.sha256(emitted.read_bytes()).hexdigest()
    assert record["mechanics"]["record_count"] == len(
        [ln for ln in emitted.read_text(encoding="utf-8").splitlines() if ln.strip()])


def test_the_record_round_trips_to_disk(tmp_path):
    out = Path(tmp_path) / "acceptance.json"
    record = run_acceptance(**acceptance_env(tmp_path, out=out))
    assert json.loads(out.read_text(encoding="utf-8")) == record
