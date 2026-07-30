# tests/test_e0r1_clean_env_collect.py
"""E0R.1 T6.1 — the suites must COLLECT and PASS in a clean environment, invoked exactly the way CI
invokes them. `python -m pytest` silently puts the CWD on sys.path; bare `pytest` does not, and CI runs
bare `pytest` — so a suite that only ever ran under `python -m pytest` can (and did) fail collection in
CI with `ModuleNotFoundError: No module named 'tests'`. This test runs the real bare-`pytest` collection
in a subprocess with the CWD-on-sys.path crutch removed, and pins the CI workflow to the branch/PR
triggers plus the probe suites."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CI = REPO / ".github" / "workflows" / "ci.yml"


def test_tests_are_an_importable_package():
    # `tests.<module>` cross-imports (shared DBC fixtures, the CLI helpers) only resolve when tests is a
    # real package — the rootdir then lands on sys.path under pytest's prepend import mode.
    assert (REPO / "tests" / "__init__.py").exists(), "tests/ must be a package for `tests.x` imports"
    assert (REPO / "tests" / "helpers" / "__init__.py").exists()


def test_bare_pytest_collects_the_whole_suite_in_a_clean_environment():
    # PYTHONPATH is stripped so nothing but the INSTALLED package + pytest's own rootdir handling can
    # satisfy the imports — the same conditions as a fresh CI checkout.
    # `-P` (safe path) drops the implicit CWD entry, so this subprocess sees exactly what bare `pytest`
    # sees: only the installed package plus whatever pytest's own rootdir handling contributes.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run([sys.executable, "-P", "-m", "pytest", "--collect-only", "-q",
                             "-p", "no:cacheprovider"],
                            cwd=REPO, env=env, capture_output=True, text=True)
    assert "error" not in result.stdout.lower() or result.returncode == 0, result.stdout[-4000:]
    assert result.returncode == 0, f"collection failed:\n{result.stdout[-4000:]}\n{result.stderr[-2000:]}"


@pytest.mark.parametrize("trigger", ["push:", "pull_request:"])
def test_ci_runs_on_branch_pushes_and_pull_requests(trigger):
    text = CI.read_text(encoding="utf-8")
    assert trigger in text
    # a branch-scoped push filter that only names main would never exercise a feature branch
    assert "branches: [main]" not in text, "CI must run on every branch push, not only main"


def test_ci_runs_both_suites_and_the_probe_tests():
    text = CI.read_text(encoding="utf-8")
    assert "pytest -q" in text, "CI must run the Python suite the same bare way this probe verifies"
    assert "npm --prefix coa_scraper" in text
    # the E0R.1 contract probes are the point of the milestone: name them so a silent skip is visible
    assert "tests/test_e0r1_" in text


def test_the_node_python_round_trip_does_not_depend_on_ambient_pythonpath():
    # `npm run unit-test` is CI's Node command and must work standalone: the cross-language round-trip
    # tests point the child interpreter at the repo root instead of assuming the package is installed
    # for whichever python3 is on PATH.
    for name in ("mechanics-v2.test.mjs", "e0r1-power-type-not-backfilled.test.mjs"):
        text = (REPO / "coa_scraper" / "tests" / name).read_text(encoding="utf-8")
        assert "PYTHONPATH" in text, f"{name} shells out to python3 without pinning PYTHONPATH"
        assert "env: PY_ENV" in text
