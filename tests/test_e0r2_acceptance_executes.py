"""E0R.2 T4.2: the acceptance record must describe a build the record-writer itself ran.

`write_acceptance_summary(dist, *, build_mechanics=...)` took the measurement as a PARAMETER. It checked
that measurement hard — executed, exit 0, zero network attempts, pointer-only — but every one of those
checks ran against a dict the caller handed in. The CLI happened to pass a real one; nothing in the
function required that, and a record whose central attestation is "whatever I was told" is not an
attestation. `run_acceptance` folds the executor inside, so there is no parameter to fabricate.
"""
import inspect
import json

import pytest

import coa_client_extract.cli as cli
from coa_client_extract.cli import AcceptanceError, run_acceptance
from tests._e0r2_acceptance_fixtures import measured, publish_generation, recon_report


def _args(tmp_path, dist, **over):
    base = dict(recon_report_path=recon_report(tmp_path), scraper_dir=tmp_path / "coa_scraper",
                builder_entries=tmp_path / "entries.jsonl", mechanics_out=tmp_path / "mech")
    base.update(over)
    return base


# --- the retired API is gone, and the new one has no seam to fabricate through ---

def test_the_v2_writer_no_longer_exists():
    assert not hasattr(cli, "write_acceptance_summary")


def test_run_acceptance_takes_no_build_mechanics_parameter():
    params = set(inspect.signature(run_acceptance).parameters)
    assert "build_mechanics" not in params
    # nor any other seam for a caller's own verdict
    assert not params & {"manifest", "recon_status", "pointer_only", "publication_state", "validation"}


def test_run_acceptance_takes_what_it_needs_to_execute_the_build():
    params = set(inspect.signature(run_acceptance).parameters)
    assert {"scraper_dir", "builder_entries", "mechanics_out", "node"} <= params


# --- the executor actually runs, and its verdict is the record's ---

def test_a_failing_build_is_refused_and_the_executor_was_really_called(tmp_path, monkeypatch):
    dist = publish_generation(tmp_path / "dist")
    calls = []

    def fake_exec(scraper_dir, pointer_path, **kw):
        calls.append({"scraper_dir": scraper_dir, "pointer": pointer_path, **kw})
        return measured(exit_code=1)

    monkeypatch.setattr(cli, "run_measured_build_mechanics", fake_exec)
    with pytest.raises(AcceptanceError, match="build-mechanics"):
        run_acceptance(dist, **_args(tmp_path, dist))
    assert len(calls) == 1, "the record-writer must execute the build, not be handed its result"
    assert calls[0]["pointer"] == dist / "coa_client_extract.pointer.json"


@pytest.mark.parametrize("bad, match", [
    ({"executed": False}, "executed"),
    ({"exit_code": 1}, "build-mechanics"),
    ({"network_attempts": 2}, "network"),
    ({"network_attempts": None}, "network"),
    ({"pointer_only": False}, "pointer"),
    ({"pointer_only": None}, "pointer"),
])
def test_every_unacceptable_measurement_is_refused(tmp_path, monkeypatch, bad, match):
    dist = publish_generation(tmp_path / "dist")
    monkeypatch.setattr(cli, "run_measured_build_mechanics", lambda *a, **k: measured(**bad))
    with pytest.raises(AcceptanceError, match=match):
        run_acceptance(dist, **_args(tmp_path, dist))


def test_the_recorded_measurement_is_the_executors_own_return(tmp_path, monkeypatch):
    dist = publish_generation(tmp_path / "dist")
    mine = measured(elapsed_s=99.5, peak_rss_mb=321.0)
    monkeypatch.setattr(cli, "run_measured_build_mechanics", lambda *a, **k: mine)
    summary = run_acceptance(dist, **_args(tmp_path, dist))
    assert summary["build_mechanics"]["elapsed_s"] == 99.5
    assert summary["build_mechanics"]["peak_rss_mb"] == 321.0


# --- an unacceptable run must not pay for a build it can never accept ---

def test_an_unresolvable_generation_is_refused_before_the_build_runs(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    calls = []
    monkeypatch.setattr(cli, "run_measured_build_mechanics",
                        lambda *a, **k: calls.append(1) or measured())
    with pytest.raises(AcceptanceError):
        run_acceptance(empty, **_args(tmp_path, empty))
    assert calls == [], "a generation that can never be accepted must not spend a canonical build first"


def test_a_non_verified_recon_is_refused_before_the_build_runs(tmp_path, monkeypatch):
    dist = publish_generation(tmp_path / "dist")
    calls = []
    monkeypatch.setattr(cli, "run_measured_build_mechanics",
                        lambda *a, **k: calls.append(1) or measured())
    path = recon_report(tmp_path, status="review_required", name="recon-rr.json")
    with pytest.raises(AcceptanceError, match="recon"):
        run_acceptance(dist, **_args(tmp_path, dist, recon_report_path=path))
    assert calls == []


# --- the record itself ---

def test_a_clean_run_produces_a_v3_record(tmp_path, monkeypatch):
    dist = publish_generation(tmp_path / "dist")
    monkeypatch.setattr(cli, "run_measured_build_mechanics", lambda *a, **k: measured())
    out = tmp_path / "acceptance.json"
    summary = run_acceptance(dist, **_args(tmp_path, dist), out=out)
    assert summary["schema_version"] == "coa-e0r-acceptance-summary-v3"
    assert summary["recon_status"] == "verified"
    assert summary["publication_state"] == "published"
    assert json.loads(out.read_text(encoding="utf-8")) == summary


def test_the_record_carries_observation_coverage_from_the_generation(tmp_path, monkeypatch):
    dist = publish_generation(tmp_path / "dist", base_manifest={
        "icon_coverage": {"spells": 3, "resolved_paths": 2},
        "observation_coverage": {"schema_version": "coa-client-observation-coverage-v1",
                                 "rows": 3, "cells": 12, "states": {"present": 12},
                                 "decoded_reasons": {"decoded": 12}, "fields": {}},
    })
    monkeypatch.setattr(cli, "run_measured_build_mechanics", lambda *a, **k: measured())
    summary = run_acceptance(dist, **_args(tmp_path, dist))
    assert summary["coverage"]["icon"]["spells"] == 3
    assert summary["coverage"]["observation"]["cells"] == 12
