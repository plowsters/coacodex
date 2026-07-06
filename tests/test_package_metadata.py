from __future__ import annotations

import importlib.metadata
import json
import tomllib
from pathlib import Path

from coa_meta import __version__
from coa_meta.apl_profiles import load_builtin_apl_profile
from coa_meta.profiles import load_builtin_profile


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
    package_data = data["tool"]["setuptools"]["package-data"]["coa_meta"]
    assert "data/scoring_profiles/*.json" in package_data
    assert "data/apl_profiles/*.json" in package_data
    assert "data/role_overrides.json" in package_data


def test_root_package_json_delegates_scraper_pipeline_commands():
    path = Path("package.json")

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    scripts = data["scripts"]
    assert scripts["pipeline:m1.8"] == "npm --prefix coa_scraper run pipeline:m1.8"


def test_root_package_json_exposes_tree_layout_capture_from_repo_root():
    path = Path("package.json")

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    scripts = data["scripts"]
    assert scripts["capture:tree-layout"] == "node coa_scraper/scripts/capture-builder-tree-layout.mjs"
