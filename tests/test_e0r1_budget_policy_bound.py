# tests/test_e0r1_budget_policy_bound.py
"""E0R.1 T4.3 — every ceiling is POLICY-BOUND and unambiguous. The reviewed policy declares a `budget`
block (per-child bytes, whole-generation bytes, python/node peak-RSS and elapsed ceilings, optional
per-child overrides); the loader validates it; a single child over its per-child ceiling FAILS even when
the whole generation is under; whole-generation over FAILS; and the authoritative manifest records a
reproducible `benchmark_env`. The python_elapsed_s ceiling is the reviewed answer to the real-client
breach found at T3.3 (~700s against the old hard-coded 600s DEFAULT_BUDGET)."""
import json

import pytest

from coa_client_extract.spell_layout import (
    SpellPolicyError, compute_policy_sha256, load_default_policy, load_spell_policy,
)
from coa_client_extract.spell_mechanics import benchmark_env, policy_budget_report

REQUIRED_CEILINGS = ("max_serialized_bytes_per_child", "max_whole_generation_bytes",
                     "python_peak_rss_mb", "python_elapsed_s", "node_peak_rss_mb", "node_elapsed_s")


def test_committed_policy_declares_every_ceiling():
    budget = load_default_policy().doc.get("budget")
    assert isinstance(budget, dict), "committed policy must carry a reviewed budget block"
    for key in REQUIRED_CEILINGS:
        assert isinstance(budget.get(key), int) and budget[key] > 0, key
    # The reviewed elapsed ceiling accommodates the MEASURED real regenerate (~700s incl. dual-language
    # full-domain verification) — the T3.3 breach is resolved by review, not by deleting the gate.
    assert budget["python_elapsed_s"] > 700


def test_loader_rejects_malformed_budget():
    doc = json.loads(json.dumps(load_default_policy().doc))
    doc["budget"]["python_elapsed_s"] = -5
    doc["sha256"] = compute_policy_sha256(doc)
    with pytest.raises(SpellPolicyError, match="budget"):
        load_spell_policy(doc)
    doc = json.loads(json.dumps(load_default_policy().doc))
    doc["budget"]["per_child_overrides"] = {"../evil": 1}
    doc["sha256"] = compute_policy_sha256(doc)
    with pytest.raises(SpellPolicyError, match="budget"):
        load_spell_policy(doc)


def _budget(**overrides):
    base = {"max_serialized_bytes_per_child": 100, "max_whole_generation_bytes": 250,
            "python_peak_rss_mb": 4096, "python_elapsed_s": 1200,
            "node_peak_rss_mb": 4096, "node_elapsed_s": 1200}
    base.update(overrides)
    return base


def _measured(**overrides):
    base = {"python_peak_rss_mb": 100.0, "python_elapsed_s": 10.0,
            "node_peak_rss_mb": 100.0, "node_elapsed_s": 5.0}
    base.update(overrides)
    return base


def test_single_child_over_its_ceiling_fails_even_when_whole_is_under():
    children = {"a.jsonl": {"byte_length": 150}, "b.jsonl": {"byte_length": 50}}   # whole=200 < 250
    report = policy_budget_report(children=children, measured=_measured(), budget=_budget())
    assert report["within_budget"] is False
    assert any("a.jsonl" in b for b in report["breach"])


def test_per_child_override_takes_precedence():
    children = {"a.jsonl": {"byte_length": 150}, "b.jsonl": {"byte_length": 50}}
    report = policy_budget_report(children=children, measured=_measured(),
                                  budget=_budget(per_child_overrides={"a.jsonl": 200}))
    assert report["within_budget"] is True


def test_whole_generation_over_fails():
    children = {"a.jsonl": {"byte_length": 90}, "b.jsonl": {"byte_length": 90}, "c.jsonl": {"byte_length": 90}}
    report = policy_budget_report(children=children, measured=_measured(), budget=_budget())
    assert report["within_budget"] is False
    assert any("whole_generation" in b for b in report["breach"])


def test_runtime_ceilings_enforced_per_language():
    children = {"a.jsonl": {"byte_length": 10}}
    ok = policy_budget_report(children=children, measured=_measured(), budget=_budget())
    assert ok["within_budget"] is True
    bad = policy_budget_report(children=children, measured=_measured(node_elapsed_s=5000), budget=_budget())
    assert bad["within_budget"] is False and any("node_elapsed_s" in b for b in bad["breach"])


def test_benchmark_env_is_reproducible_and_complete():
    env = benchmark_env()
    for key in ("python_version", "platform", "machine", "cpu_count"):
        assert env.get(key), key
    assert env == benchmark_env()                      # deterministic within a session
