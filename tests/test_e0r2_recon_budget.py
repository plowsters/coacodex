"""E0R.2 T3.3: recon measures a recon.

`record_count * record_size` is the raw DBC byte count of the source table — it is not, and cannot be,
the size of the artifact a later `regenerate` will serialize. On the real client it read ~187 MB against
a real generation of ~523 MB: off by 2.8x, in the optimistic direction, and gated as if it meant
something. A forecast from a serialized sample is an explicit NON-GOAL here: a wrong forecast is worse
than none, and publication (T2.4) measures the real thing exactly, per child and whole-generation.

So recon gates the two things it actually measures — its own peak RSS and its own elapsed — against the
REVIEWED policy ceilings, and makes no size claim at all.
"""
import pytest

import coa_client_extract.spell_mechanics as sm


def _ceilings(**over):
    base = {"max_serialized_bytes_per_child": 1 << 30, "max_whole_generation_bytes": 1 << 31,
            "python_peak_rss_mb": 4096, "python_elapsed_s": 900,
            "node_peak_rss_mb": 4096, "node_elapsed_s": 900}
    base.update(over)
    return base


# --- the retired API is GONE, not merely unused ---

def test_the_hard_coded_default_budget_no_longer_exists():
    # A module-level DEFAULT_BUDGET is how unreviewed ceilings kept re-entering the pipeline: any caller
    # that omitted a budget silently got 512 MB / 4 GB / 600 s that no review ever agreed to.
    assert not hasattr(sm, "DEFAULT_BUDGET")


def test_the_three_part_budget_no_longer_exists():
    assert not hasattr(sm, "three_part_budget")


# --- what recon_budget reports ---

def test_recon_budget_makes_no_size_claim():
    report = sm.recon_budget(peak_rss_mb=100.0, elapsed_s=12.5, ceilings=_ceilings())
    assert report["within_budget"] is True and report["breach"] == []
    assert not any("size" in k or "bytes" in k or "serialized" in k for k in report)
    assert set(report) == {"peak_rss_mb", "elapsed_s", "ceilings", "within_budget", "breach"}


def test_recon_budget_breaches_on_peak_rss():
    report = sm.recon_budget(peak_rss_mb=9000.0, elapsed_s=1.0, ceilings=_ceilings())
    assert report["within_budget"] is False
    assert any("python_peak_rss_mb" in b for b in report["breach"])


def test_recon_budget_breaches_on_elapsed():
    report = sm.recon_budget(peak_rss_mb=1.0, elapsed_s=5000.0, ceilings=_ceilings())
    assert report["within_budget"] is False
    assert any("python_elapsed_s" in b for b in report["breach"])


def test_recon_budget_reports_every_breach_not_just_the_first():
    report = sm.recon_budget(peak_rss_mb=9000.0, elapsed_s=5000.0, ceilings=_ceilings())
    assert len(report["breach"]) == 2


def test_recon_budget_gates_the_python_ceilings_not_the_node_ones():
    """A recon runs no Node. Gating a Python measurement against a Node ceiling would pass or fail for
    reasons that have nothing to do with what ran."""
    report = sm.recon_budget(peak_rss_mb=3000.0, elapsed_s=1.0,
                             ceilings=_ceilings(python_peak_rss_mb=4096, node_peak_rss_mb=1))
    assert report["within_budget"] is True


def test_recon_budget_refuses_ceilings_it_cannot_read():
    with pytest.raises(KeyError):
        sm.recon_budget(peak_rss_mb=1.0, elapsed_s=1.0, ceilings={"artifact_size_mb": 512})


# --- recon reads its ceilings from the REVIEWED policy ---

def test_recon_takes_its_ceilings_from_the_policy_budget_block():
    from tests._e0r2_recon_fixtures import recon_client

    report = recon_client().run()
    assert report["budget"]["ceilings"] == recon_client().policy_budget
    assert "serialized_mb" not in report["budget"]


def test_a_recon_over_its_reviewed_rss_ceiling_blocks():
    from tests._e0r2_recon_fixtures import recon_client

    report = recon_client(budget={"python_peak_rss_mb": 1, "python_elapsed_s": 900,
                                  "node_peak_rss_mb": 1, "node_elapsed_s": 900,
                                  "max_serialized_bytes_per_child": 1 << 30,
                                  "max_whole_generation_bytes": 1 << 31}).run()
    assert report["status"] == "blocked"
    assert any(f.get("reason") == "over_budget" for f in report["blocking_findings"])


def test_a_recon_against_a_policy_with_no_reviewed_budget_is_refused():
    """The same escape hatch T2.4 closed on the publish path: falling back to hard-coded ceilings when
    the reviewed policy declares none substitutes unreviewed limits exactly where review is missing."""
    from coa_client_extract.publish import PublishError
    from tests._e0r2_recon_fixtures import recon_client

    with pytest.raises(PublishError, match="declares no budget block"):
        recon_client(budget=None).run()


def test_the_committed_policy_declares_the_ceilings_recon_needs():
    from coa_client_extract.spell_layout import load_default_policy

    budget = load_default_policy().doc["budget"]
    for key in ("python_peak_rss_mb", "python_elapsed_s"):
        assert isinstance(budget.get(key), int) and budget[key] > 0, key
