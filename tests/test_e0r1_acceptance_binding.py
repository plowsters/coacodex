# tests/test_e0r1_acceptance_binding.py
"""E0R.1 T6.2 — the acceptance summary is BINDING, not a caller's self-report. It must:

  * commit the NORMALIZED recon report itself (not merely its hash) and bind that report's sha256;
  * assert the recon `status == "verified"` — a `review_required`/`blocked` recon can never be accepted;
  * read strict-V3 / published / validation / budget from the RESOLVED manifest, rejecting any
    caller-supplied publication status or manifest;
  * record real icon / readiness / source COVERAGE counts;
  * derive `pointer_only` and the network-trap result from EXECUTED commands, never caller booleans.

E0R.2 T4.2 folded the executor INSIDE the record-writer (`write_acceptance_summary` -> `run_acceptance`),
so these tests substitute the executor and let the writer call it, rather than handing in a measurement.
The staging helpers moved to tests/_e0r2_acceptance_fixtures.py, shared with
tests/test_e0r2_acceptance_executes.py, so the two suites cannot drift apart.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import coa_client_extract.cli as cli
from coa_client_extract.cli import AcceptanceError, run_acceptance
# Captured at import, BEFORE the autouse fixture below substitutes the module attribute: the last
# test in this file exercises the REAL executor and must not get the stub.
from coa_client_extract.cli import run_measured_build_mechanics as _REAL_EXECUTOR

from tests._e0r2_acceptance_fixtures import VERIFIED_RECON, measured, publish


def _recon(tmp_path, payload=VERIFIED_RECON, name="recon.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _publish(root, *, base_manifest=None):
    return publish(root, base_manifest=base_manifest)


@pytest.fixture(autouse=True)
def _executor(monkeypatch):
    """T4.2: the writer executes the build itself, so every test here substitutes the executor. The
    default is a clean measurement; a test that cares overrides it with `_set_executor`."""
    monkeypatch.setattr(cli, "run_measured_build_mechanics", lambda *a, **k: measured())


def _set_executor(monkeypatch, **over):
    monkeypatch.setattr(cli, "run_measured_build_mechanics", lambda *a, **k: measured(**over))


def _accept(dist, tmp_path, *, recon_report_path=None, out=None):
    return run_acceptance(dist, recon_report_path=recon_report_path or _recon(tmp_path),
                          scraper_dir=tmp_path / "coa_scraper",
                          builder_entries=tmp_path / "entries.jsonl",
                          mechanics_out=tmp_path / "mech", out=out)


def test_summary_commits_the_normalized_recon_report_and_binds_its_hash(tmp_path):
    dist = tmp_path / "dist"
    _publish(dist)
    report_path = _recon(tmp_path)

    summary = _accept(dist, tmp_path, recon_report_path=report_path)

    assert summary["recon_report"] == VERIFIED_RECON, "the report itself must be committed, not just a hash"
    normalized = json.dumps(VERIFIED_RECON, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    assert summary["recon_report_sha256"] == hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    assert summary["recon_status"] == "verified"


def test_a_non_verified_recon_can_never_be_accepted(tmp_path):
    dist = tmp_path / "dist"
    _publish(dist)
    for status in ("review_required", "blocked", "unknown"):
        path = _recon(tmp_path, {**VERIFIED_RECON, "status": status}, name=f"recon-{status}.json")
        with pytest.raises(AcceptanceError, match="recon"):
            _accept(dist, tmp_path, recon_report_path=path)


def test_publication_facts_come_from_the_resolved_manifest_not_the_caller(tmp_path):
    dist = tmp_path / "dist"
    _publish(dist)
    summary = _accept(dist, tmp_path)

    assert summary["manifest_schema_version"] == "coa-client-extract-manifest-v3"
    assert summary["publication_state"] == "published"
    assert summary["validation"] == {"python": True, "node": True}
    assert summary["budget"]["within_budget"] is True
    assert summary["policy_sha256"] == "abc123"
    # every REQUIRED child is pinned with its measured digest/size/record count
    assert summary["children"]["coa_client_spell.jsonl"]["sha256"]
    assert set(summary["children"]) >= {"coa_client_spell.jsonl", "coa_client_spell_coa.jsonl"}


def test_an_unpublished_or_missing_generation_is_refused(tmp_path):
    dist = tmp_path / "empty"
    dist.mkdir()
    with pytest.raises(AcceptanceError):
        _accept(dist, tmp_path)


def test_the_writer_refuses_a_caller_supplied_publication_status(tmp_path):
    # A caller cannot smuggle in its own verdict: there is no status/pointer_only parameter to pass.
    import inspect

    params = set(inspect.signature(run_acceptance).parameters)
    assert not params & {"manifest", "recon_status", "pointer_only", "publication_state", "validation"}


def test_coverage_counts_are_recorded(tmp_path):
    dist = tmp_path / "dist"
    _publish(dist, base_manifest={
        "icon_coverage": {"total": 10, "resolved": 7, "placeholder": 3},
        "readiness_coverage": {"available": 4, "unavailable": 6},
        "source_coverage": {"client_dbc": 8, "verified_builder": 2},
    })
    summary = _accept(dist, tmp_path)

    assert summary["coverage"]["icon"]["resolved"] == 7
    assert summary["coverage"]["readiness"]["unavailable"] == 6
    assert summary["coverage"]["source"]["client_dbc"] == 8


def test_build_mechanics_must_be_an_executed_measurement(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    _publish(dist)
    report_path = _recon(tmp_path)

    # an executor that did not actually run is exactly what T6.2 removes — and T4.2 removed the
    # parameter through which a caller could claim it had.
    _set_executor(monkeypatch, executed=False)
    with pytest.raises(AcceptanceError, match="executed"):
        _accept(dist, tmp_path, recon_report_path=report_path)
    # a failed build cannot be accepted
    _set_executor(monkeypatch, exit_code=1)
    with pytest.raises(AcceptanceError, match="build-mechanics"):
        _accept(dist, tmp_path, recon_report_path=report_path)
    # neither can one that reached the network under the trap
    _set_executor(monkeypatch, network_attempts=2)
    with pytest.raises(AcceptanceError, match="network"):
        _accept(dist, tmp_path, recon_report_path=report_path)
    # nor one that was not pointer-only
    _set_executor(monkeypatch, pointer_only=False)
    with pytest.raises(AcceptanceError, match="pointer"):
        _accept(dist, tmp_path, recon_report_path=report_path)


def test_summary_round_trips_to_disk(tmp_path):
    dist = tmp_path / "dist"
    _publish(dist)
    out = tmp_path / "acceptance.json"
    summary = _accept(dist, tmp_path, out=out)
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
