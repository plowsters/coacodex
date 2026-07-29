"""E0R.2 T2.4: a generation that failed a trust boundary or its budget must never become the pointer's
target. Consumer-side strictness is a second line of defence, not the gate — the Node resolver refuses to
READ such a generation, but by then the pointer has already flipped and the failed generation is the live
one. The refusal has to happen before the flip, in the publisher.
"""
import pytest

from coa_client_extract.publish import POINTER_NAME, PublishError
from tests._e0r2_fixtures import clean_budget, staged_writer


def _publish(gw, candidate, *, validation, budget):
    return gw.finalize_and_publish(candidate_manifest=candidate, validation=validation, budget=budget)


@pytest.mark.parametrize("validation", [
    {"python": True, "node": False},
    {"python": True, "node": "yes"},       # truthy but not True
    {"python": True},                      # absent
    {"python": False, "node": True},       # the other boundary
    {},
])
def test_publishing_without_both_validations_is_refused(tmp_path, validation):
    gw, candidate, ceilings = staged_writer(tmp_path)
    with pytest.raises(PublishError, match="validation"):
        _publish(gw, candidate, validation=validation, budget=clean_budget(ceilings))
    assert not (tmp_path / POINTER_NAME).exists()


def test_a_non_dict_validation_is_refused(tmp_path):
    gw, candidate, ceilings = staged_writer(tmp_path)
    with pytest.raises(PublishError, match="validation"):
        _publish(gw, candidate, validation=True, budget=clean_budget(ceilings))
    assert not (tmp_path / POINTER_NAME).exists()


@pytest.mark.parametrize("mutate", [
    lambda b: b.update(within_budget=False, breach=["whole_generation bytes 1 > 0"]),
    lambda b: b.update(within_budget="ok"),                            # truthy but not True
    lambda b: b.update(breach=["a breach nobody acted on"]),           # says clean, lists a breach
    lambda b: b.pop("ceilings"),                                       # nothing to re-check against
])
def test_publishing_with_an_unclean_budget_is_refused(tmp_path, mutate):
    gw, candidate, ceilings = staged_writer(tmp_path)
    budget = clean_budget(ceilings)
    mutate(budget)
    with pytest.raises(PublishError, match="budget"):
        _publish(gw, candidate, validation={"python": True, "node": True}, budget=budget)
    assert not (tmp_path / POINTER_NAME).exists()


def test_the_budget_is_recomputed_from_staged_child_metadata(tmp_path):
    """A caller-supplied within_budget must not outrank the staged bytes. This is the case a report
    computed before the last child was staged would otherwise sail through."""
    gw, candidate, ceilings = staged_writer(tmp_path, oversized=True)
    with pytest.raises(PublishError, match="recomputed from the staged children"):
        _publish(gw, candidate, validation={"python": True, "node": True},
                 budget=clean_budget(ceilings))
    assert not (tmp_path / POINTER_NAME).exists()


def test_a_report_that_misstates_the_generation_size_is_refused(tmp_path):
    gw, candidate, ceilings = staged_writer(tmp_path)
    budget = clean_budget(ceilings)
    budget["whole_generation_bytes"] = 1                 # not what the staged children total
    with pytest.raises(PublishError, match="whole-generation bytes"):
        _publish(gw, candidate, validation={"python": True, "node": True}, budget=budget)
    assert not (tmp_path / POINTER_NAME).exists()


def test_a_refused_publication_releases_the_lock_and_leaves_no_pointer(tmp_path):
    """The refusal path runs inside the same try/finally the successful path does, so a failed publish
    does not strand the publish lock — otherwise one bad generation would wedge every later one."""
    gw, candidate, ceilings = staged_writer(tmp_path)
    with pytest.raises(PublishError):
        _publish(gw, candidate, validation={"python": True}, budget=clean_budget(ceilings))
    assert not (tmp_path / POINTER_NAME).exists()
    final = _publish(gw, candidate, validation={"python": True, "node": True},
                     budget=clean_budget(ceilings))     # the lock was released; a clean retry publishes
    assert final["publication_state"] == "published"


def test_a_fully_validated_within_budget_generation_publishes(tmp_path):
    gw, candidate, ceilings = staged_writer(tmp_path)
    final = _publish(gw, candidate, validation={"python": True, "node": True},
                     budget=clean_budget(ceilings))
    assert final["publication_state"] == "published"
    assert (tmp_path / POINTER_NAME).is_file()


def test_the_publish_path_refuses_a_policy_with_no_reviewed_budget(tmp_path):
    """The escape hatch T2.4 removed: `regenerate` used to fall back to hard-coded three-part ceilings
    whenever the policy declared no budget block, silently substituting unreviewed limits for reviewed
    ones. A policy with no budget now refuses to publish at all."""
    import copy
    import json

    from coa_client_extract.cli import regenerate
    from tests.test_client_extract_cli import (_bound_spell_policy, _client, _fake_backend,
                                               _synthetic_layouts)
    from coa_client_extract.spell_layout import compute_policy_sha256, load_spell_policy

    client_root = _client(tmp_path)
    policy = _bound_spell_policy(_fake_backend(), client_root)
    doc = copy.deepcopy(policy.doc)
    del doc["budget"]
    doc["sha256"] = compute_policy_sha256({k: v for k, v in doc.items() if k != "sha256"})
    unbudgeted = load_spell_policy(doc)

    lock = tmp_path / "spell_layout.lock.json"
    lock.write_text(json.dumps({"schema_version": "coa-spell-layout-lock-v1", "sha256": doc["sha256"]}))
    with pytest.raises(PublishError, match="declares no budget block"):
        regenerate(client_root, tmp_path / "out", backend=_fake_backend(),
                   layouts=_synthetic_layouts(), spell_policy=unbudgeted, node_lock_path=lock)
    assert not (tmp_path / "out" / POINTER_NAME).exists()
