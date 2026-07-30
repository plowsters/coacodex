# tests/test_e0r1_acceptance_binding.py
"""E0R.1 T6.2 — the acceptance summary is BINDING, not a caller's self-report. It must:

  * commit the NORMALIZED recon report itself (not merely its hash) and bind that report's sha256;
  * assert the recon `status == "verified"` — a `review_required`/`blocked` recon can never be accepted;
  * read strict-V3 / published / validation / budget from the RESOLVED manifest, rejecting any
    caller-supplied publication status or manifest;
  * record real icon / readiness / source COVERAGE counts;
  * derive `pointer_only` and the network-trap result from EXECUTED commands, never caller booleans.

E0R.2 T4.2 folded the executor INSIDE the record-writer (`write_acceptance_summary` -> `run_acceptance`),
so these tests let the writer call it rather than handing in a measurement. T4.3 then bound the recon to
the generation, so the fixture stages a fully BOUND generation and a recon that matches it — the staging
lives in tests/_e0r2_acceptance_fixtures.py, shared with tests/test_e0r2_acceptance_executes.py, so the
two suites cannot drift apart.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import coa_client_extract.cli as cli
from coa_client_extract.cli import AcceptanceError, run_acceptance
# Captured at import, before any test substitutes the module attribute: the last test in this file
# exercises the REAL executor directly.
from coa_client_extract.cli import run_measured_build_mechanics as _REAL_EXECUTOR

from tests._e0r2_acceptance_fixtures import acceptance_env, measured, published_manifest


def _set_executor(monkeypatch, **over):
    monkeypatch.setattr(cli, "run_measured_build_mechanics", lambda *a, **k: measured(**over))


def test_summary_commits_the_normalized_recon_report_and_binds_its_hash(tmp_path):
    env = acceptance_env(tmp_path)
    report = json.loads(Path(env["recon_report_path"]).read_text(encoding="utf-8"))

    summary = run_acceptance(**env)

    assert summary["recon_report"] == report, "the report itself must be committed, not just a hash"
    normalized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    assert summary["recon_report_sha256"] == hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    assert summary["recon_status"] == "verified"


def test_a_non_verified_recon_can_never_be_accepted(tmp_path):
    for status in ("review_required", "blocked", "unknown"):
        with pytest.raises(AcceptanceError, match="recon"):
            run_acceptance(**acceptance_env(tmp_path, recon_status=status))


def test_publication_facts_come_from_the_resolved_manifest_not_the_caller(tmp_path):
    env = acceptance_env(tmp_path)
    summary = run_acceptance(**env)

    assert summary["manifest_schema_version"] == "coa-client-extract-manifest-v3"
    assert summary["publication_state"] == "published"
    assert summary["validation"] == {"python": True, "node": True}
    assert summary["budget"]["within_budget"] is True
    assert summary["policy_sha256"] == published_manifest(env["dist"])["binding"]["policy_sha256"]
    # every REQUIRED child is pinned with its measured digest/size/record count
    assert summary["children"]["coa_client_spell.jsonl"]["sha256"]
    assert set(summary["children"]) >= {"coa_client_spell.jsonl", "coa_client_spell_coa.jsonl"}


def test_an_unpublished_or_missing_generation_is_refused(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(AcceptanceError):
        run_acceptance(**{**acceptance_env(tmp_path), "dist": empty})


def test_the_writer_refuses_a_caller_supplied_publication_status(tmp_path):
    # A caller cannot smuggle in its own verdict: there is no status/pointer_only parameter to pass.
    import inspect

    params = set(inspect.signature(run_acceptance).parameters)
    assert not params & {"manifest", "recon_status", "pointer_only", "publication_state", "validation"}


def test_coverage_counts_are_recorded(tmp_path):
    """E0R.2 T4.3 correction: `readiness` and `source` are MECHANICS-manifest facts. They were read from
    the generation manifest, which has never carried them — so both were `{}` in every record ever
    written, including the real one at 2846990. They now come from the executed build's own manifest."""
    summary = run_acceptance(**acceptance_env(tmp_path, base_manifest={
        "icon_coverage": {"spells": 10, "resolved_paths": 7, "placeholder": 3}}))

    assert summary["coverage"]["icon"]["resolved_paths"] == 7
    assert summary["coverage"]["observation"]["cells"] > 0
    assert summary["coverage"]["readiness"]["fields_considered"] > 0
    assert summary["coverage"]["source"]["name"]


def test_build_mechanics_must_be_an_executed_measurement(tmp_path, monkeypatch):
    # an executor that did not actually run is exactly what T6.2 removes — and T4.2 removed the
    # parameter through which a caller could claim it had.
    _set_executor(monkeypatch, executed=False)
    with pytest.raises(AcceptanceError, match="executed"):
        run_acceptance(**acceptance_env(tmp_path))
    # a failed build cannot be accepted
    _set_executor(monkeypatch, exit_code=1)
    with pytest.raises(AcceptanceError, match="build-mechanics"):
        run_acceptance(**acceptance_env(tmp_path))
    # neither can one that reached the network under the trap
    _set_executor(monkeypatch, network_attempts=2)
    with pytest.raises(AcceptanceError, match="network"):
        run_acceptance(**acceptance_env(tmp_path))
    # nor one that was not pointer-only
    _set_executor(monkeypatch, pointer_only=False)
    with pytest.raises(AcceptanceError, match="pointer"):
        run_acceptance(**acceptance_env(tmp_path))


def test_summary_round_trips_to_disk(tmp_path):
    out = tmp_path / "acceptance.json"
    summary = run_acceptance(**acceptance_env(tmp_path, out=out))
    assert json.loads(out.read_text(encoding="utf-8")) == summary
    assert summary["schema_version"] == "coa-e0r-acceptance-summary-v3"


def test_the_measured_build_runs_in_the_scraper_dir_with_an_absolute_pointer(tmp_path, monkeypatch):
    """T6.3 regression: `run_measured_build_mechanics` spawns the build with cwd=<scraper dir>, so a
    pointer path that was relative to the CALLER's cwd (e.g. `reports/client_extract/...`) resolved
    against the wrong directory and the canonical build exited 2 — the acceptance run failed for a
    path-resolution reason, not a contract one."""
    captured = {}

    class _Proc:
        returncode, stdout, stderr = 0, "", ""

    def fake_run(cmd, cwd=None, env=None, capture_output=None, text=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return _Proc()

    monkeypatch.setattr("subprocess.run", fake_run)
    scraper = tmp_path / "coa_scraper"
    scraper.mkdir()
    monkeypatch.chdir(tmp_path)
    pointer = tmp_path / "reports" / "client_extract" / "coa_client_extract.pointer.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text("{}", encoding="utf-8")

    _REAL_EXECUTOR(Path("coa_scraper"),
                   Path("reports/client_extract/coa_client_extract.pointer.json"),
                   builder_entries=Path("dist/coa_entries.jsonl"), out_dir=Path("dist"))

    flag = captured["cmd"].index("--client-extract-pointer")
    assert Path(captured["cmd"][flag + 1]).is_absolute(), captured["cmd"][flag + 1]
    assert Path(captured["cmd"][flag + 1]) == pointer.resolve()
    # the scraper-relative inputs stay relative — they are resolved against the subprocess cwd
    assert "dist/coa_entries.jsonl" in captured["cmd"]
