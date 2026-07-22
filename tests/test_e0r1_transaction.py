# tests/test_e0r1_transaction.py
"""E0R.1 T3.4 — regenerate is a TRUE transaction under late failure and concurrency. A parity failure
aborts BEFORE the pointer flips (the previous generation stays live); the noncanonical fixed-path summary
can never fail a completed publication; and the publish lock is held from the predecessor read through the
pointer replace, with the predecessor REVALIDATED under the lock before the replace — so two concurrent
publishers serialize instead of last-writer-winning the generation chain."""
import json
import threading
from pathlib import Path

import pytest

from coa_client_extract.publish import (
    GenerationWriter, PublishError, ResolveError, resolve_active_generation,
)
from tests.test_client_extract_cli import (
    _bound_spell_policy, _client, _fake_backend, _synthetic_layouts,
)


def _regenerate(client_root, out, tmp_path, **kwargs):
    from coa_client_extract.cli import regenerate
    policy = _bound_spell_policy(_fake_backend(), client_root)
    lock = tmp_path / "spell_layout.lock.json"
    lock.write_text(json.dumps({"schema_version": "coa-spell-layout-lock-v1", "sha256": policy.sha256}))
    return regenerate(client_root, out, backend=_fake_backend(), layouts=_synthetic_layouts(),
                      spell_policy=policy, node_lock_path=lock, **kwargs)


# --- late failure: parity aborts BEFORE the flip; the summary can never fail a completed publication ---

def test_parity_failure_leaves_previous_pointer_untouched(tmp_path):
    client_root = _client(tmp_path)
    out = tmp_path / "out"
    _regenerate(client_root, out, tmp_path)
    gen1 = resolve_active_generation(out)["generation_id"]

    bad_entries = tmp_path / "coa_entries.jsonl"
    bad_entries.write_text("this is not json\n")
    with pytest.raises(ValueError):
        _regenerate(client_root, out, tmp_path, builder_entries_path=str(bad_entries))
    assert resolve_active_generation(out)["generation_id"] == gen1   # previous generation still live


def test_summary_write_failure_does_not_fail_publication(tmp_path):
    client_root = _client(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "coa_client_extract_manifest.json").mkdir()      # fixed-path summary target is unwritable
    manifest = _regenerate(client_root, out, tmp_path)      # must NOT raise: the summary is noncanonical
    assert manifest["publication_state"] == "published"
    assert "summary_write_error" in manifest                 # the failure is reported, not fatal
    resolved = resolve_active_generation(out)                # the generation itself IS published
    assert resolved["manifest"]["publication_state"] == "published"


# --- concurrency: predecessor read -> pointer replace under ONE lock, revalidated before the replace ---

def _stage_minimal(root):
    """Stage every REQUIRED_CHILD with a minimal body (the strict resolver checks the registry; the
    cross-child semantics are validated at the cli layer, not by finalize)."""
    gw = GenerationWriter(root)
    gw.add_jsonl("coa_client_spell.jsonl", [], schema_version="coa-client-spell-v3")
    gw.add_jsonl("coa_client_spell_coa.jsonl", [], schema_version="coa-client-spell-projection-v3")
    gw.add_json("coa_client_spell_projection.manifest.json",
                {"schema_version": "coa-client-spell-projection-manifest-v3"},
                schema_version="coa-client-spell-projection-manifest-v3")
    gw.add_jsonl("coa_client_spell_icons.jsonl", [], schema_version="coa-client-spell-icons-v1")
    for name in ("coa_client_content.jsonl", "coa_client_advancement.jsonl", "coa_client_class_types.jsonl",
                 "coa_client_tab_types.jsonl", "coa_client_essence.jsonl"):
        gw.add_jsonl(name, [], schema_version="coa-client-misc-v1")
    gw.add_json("coa_client_archive_plan.json", {"schema_version": "coa-client-archive-plan-v1"},
                schema_version="coa-client-archive-plan-v1")
    gw.add_json("spell_layout_v2.json", {"schema_version": "coa-spell-layout-v2"},
                schema_version="coa-spell-layout-v2")
    return gw


def _finalize(gw, candidate):
    return gw.finalize_and_publish(candidate_manifest=candidate,
                                   validation={"python": True, "node": True},
                                   budget={"within_budget": True})


def test_finalize_rejects_stale_predecessor(tmp_path):
    # A staged its candidate first and published; B's candidate still names A's predecessor (None) —
    # finalizing B must FAIL (no last-writer-win) and leave A live.
    gw_a = _stage_minimal(tmp_path)
    _finalize(gw_a, gw_a.publish_candidate(base_manifest={}, binding={}))

    gw_b = _stage_minimal(tmp_path)
    real_predecessor = gw_b._predecessor
    gw_b._predecessor = lambda: None                        # simulate a pre-A (stale) predecessor read
    candidate_b = gw_b.publish_candidate(base_manifest={}, binding={})
    gw_b._predecessor = real_predecessor                    # finalize revalidates against the REAL pointer
    with pytest.raises(PublishError, match="changed since the candidate was staged"):
        _finalize(gw_b, candidate_b)
    gw_b.abort_publication()
    assert resolve_active_generation(tmp_path)["generation_id"] == gw_a.generation_id


def test_concurrent_publishers_serialize_and_chain(tmp_path):
    # B's publish_candidate BLOCKS while A holds the publish lock; once A finalizes, B proceeds and its
    # candidate records A as predecessor — the chain never loses a generation.
    gw_a = _stage_minimal(tmp_path)
    candidate_a = gw_a.publish_candidate(base_manifest={}, binding={})   # lock now held by A

    staged = threading.Event()
    result = {}

    def publish_b():
        gw_b = _stage_minimal(tmp_path)
        result["candidate"] = gw_b.publish_candidate(base_manifest={}, binding={})
        result["writer"] = gw_b
        staged.set()

    t = threading.Thread(target=publish_b, daemon=True)
    t.start()
    assert not staged.wait(0.5), "B staged its candidate while A still held the publish lock"

    _finalize(gw_a, candidate_a)                            # releases the lock
    assert staged.wait(10), "B never acquired the publish lock after A finalized"
    assert result["candidate"]["predecessor_generation_id"] == gw_a.generation_id
    _finalize(result["writer"], result["candidate"])        # B publishes cleanly on top of A
    assert resolve_active_generation(tmp_path)["generation_id"] == result["writer"].generation_id


def test_abort_releases_the_publish_lock(tmp_path):
    # A failed AFTER staging its candidate (validation/budget/parity): abort_publication releases the lock
    # without touching the pointer, so the next publisher is not deadlocked.
    gw_a = _stage_minimal(tmp_path)
    gw_a.publish_candidate(base_manifest={}, binding={})
    gw_a.abort_publication()
    with pytest.raises(ResolveError):                       # nothing was ever published
        resolve_active_generation(tmp_path)

    gw_b = _stage_minimal(tmp_path)
    done = threading.Event()

    def publish_b():
        candidate = gw_b.publish_candidate(base_manifest={}, binding={})
        _finalize(gw_b, candidate)
        done.set()

    t = threading.Thread(target=publish_b, daemon=True)
    t.start()
    assert done.wait(10), "publish lock leaked by the aborted publisher"
    assert resolve_active_generation(tmp_path)["generation_id"] == gw_b.generation_id
