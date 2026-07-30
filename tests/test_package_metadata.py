from __future__ import annotations

import glob
import importlib.metadata
import json
import subprocess
import tomllib
from pathlib import Path

import pytest

from coa_meta import __version__
from coa_meta.apl_profiles import load_builtin_apl_profile
from coa_meta.profiles import load_builtin_profile

REPO = Path(__file__).resolve().parents[1]


def test_builtin_profiles_load_from_package_data():
    scoring = load_builtin_profile("generic_dps", encounter="single_target")
    apl = load_builtin_apl_profile("generic_dps")

    assert scoring.profile_id == "generic_dps"
    assert apl.profile_id == "generic_dps"


def test_package_version_matches_import_metadata_when_installed():
    try:
        installed_version = importlib.metadata.version("coa-meta-analyzer")
    except importlib.metadata.PackageNotFoundError:
        installed_version = __version__

    assert installed_version == __version__


def test_pyproject_declares_package_data_and_console_script():
    path = Path("pyproject.toml")

    assert path.exists()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data["project"]["name"] == "coa-meta-analyzer"
    assert data["project"]["scripts"]["coa-meta"] == "coa_meta.cli:main"
    # Both distributed packages must declare package-data at all; WHICH files each pattern has to reach
    # is `test_every_tracked_data_file_is_declared_as_package_data`'s job, stated over the tracked tree
    # rather than as a list of glob strings a nested directory can slip past.
    package_data = data["tool"]["setuptools"]["package-data"]
    assert package_data["coa_meta"] and package_data["coa_client_extract"]


def _setuptools_config() -> dict:
    return tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]


def _tracked_data_files(package: str) -> set[str]:
    """Package-relative paths of every TRACKED file under `<package>/data/`. Tracked, not merely
    present: a committed data file is one the package promises to carry, while a stray local file is
    not, and only the committed set is what a build from a clean checkout can even see."""
    listed = subprocess.run(["git", "ls-files", "-z", f"{package}/data"],
                            capture_output=True, text=True, check=True, cwd=REPO)
    return {path[len(package) + 1:] for path in listed.stdout.split("\0") if path}


def _declared_data_files(package: str, patterns: list[str]) -> set[str]:
    """What the build will actually ship: each declared `package-data` glob expanded the way setuptools
    expands it — rooted at the package directory, `recursive=True` so `**` spans directories."""
    shipped: set[str] = set()
    for pattern in patterns:
        shipped |= set(glob.glob(pattern, root_dir=REPO / package, recursive=True))
    return shipped


@pytest.mark.parametrize("package", ["coa_meta", "coa_client_extract"])
def test_every_tracked_data_file_is_declared_as_package_data(package):
    """E0R.3 P1: `coa_client_extract = ["data/*.json"]` matched `data/*.json` and nothing below it, so
    `data/generation_contracts/` — the hash-pinned generation-contract registry that
    `coa_client_extract.contracts` reads by absolute package path — was absent from the built wheel.
    An editable install masks that completely (the whole source tree is on the path); a real install
    raises `FileNotFoundError` on the registry index before the publication layer can load.
    `coa_meta/data/live_sanity_watchlist.json`, read by `coa_meta.backend_trust`, was omitted the same
    way and by the same mechanism.

    Naming the two offenders would fix today's defect and leave the next nested data directory free to
    reintroduce it, so the invariant is stated over the tracked tree instead: whatever is committed
    under `<package>/data/` is exactly what the wheel carries. A file that genuinely must not ship has
    to be excluded on purpose, in the open, rather than by a glob that quietly cannot see it."""
    patterns = _setuptools_config()["package-data"][package]
    assert _tracked_data_files(package) == _declared_data_files(package, patterns)


def test_ci_gates_the_installed_wheel_and_not_only_the_source_tree():
    """A pattern-level check cannot prove setuptools honored the patterns, and the `test` job's
    `pip install -e .` can never fail this way — it exposes every file in the checkout whether the
    wheel carries it or not. Only building the wheel, installing it clean, and importing from a
    directory outside the checkout closes that gap."""
    ci = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "python -m build --wheel" in ci
    assert "install dist/*.whl" in ci
    # A clean interpreter, not the job's own: `-e` or a plain `pip install .` alongside the checkout
    # would leave the source tree reachable and the gate unable to fail.
    assert "python -m venv" in ci
    # Outside the checkout: `${{ runner.temp }}` is not under `github.workspace`, so an omitted data
    # file cannot be found via the source tree.
    assert "working-directory: ${{ runner.temp }}" in ci
    assert "scripts/wheel_smoke.py" in ci


def test_root_package_json_delegates_scraper_pipeline_commands():
    path = Path("package.json")

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    scripts = data["scripts"]
    # The M1.8/M1.9 AscensionDB pipelines were retired in M1.14E0R; the surviving delegation is the
    # normalization pipeline (no db.ascension.gg step).
    assert scripts["pipeline"] == "npm --prefix coa_scraper run pipeline"
    assert "pipeline:m1.8" not in scripts and "pipeline:m1.9" not in scripts


def test_root_package_json_exposes_tree_layout_capture_from_repo_root():
    path = Path("package.json")

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    scripts = data["scripts"]
    assert scripts["capture:tree-layout"] == "node coa_scraper/scripts/capture-builder-tree-layout.mjs"
