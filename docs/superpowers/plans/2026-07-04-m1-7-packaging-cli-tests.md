# M1.7 Packaging, CLI, and Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Phase 1 report path runnable through `python -m coa_meta meta ...` with package metadata, thin CLI routing, package-data loading, and release-path tests.

**Architecture:** Keep the CLI as an adapter around M1.6 `MetaReportRunner` and `write_report_outputs`. Add minimal packaging metadata for the existing package layout, include built-in JSON profile data, and add smoke coverage that exercises the release command path without browser automation.

**Tech Stack:** Python 3.11+ standard library, argparse, setuptools via `pyproject.toml`, existing `coa_meta` package, `python -m pytest`.

---

## File Structure

- Create `coa_meta/cli.py`: argument parsing, `meta` command dispatch, and process exit codes.
- Create `coa_meta/__main__.py`: `python -m coa_meta` entry point.
- Create `pyproject.toml`: package metadata, setuptools config, console script, package data.
- Create `tests/test_cli.py`: CLI parser and dispatch tests with monkeypatched runner/writer.
- Create `tests/test_package_metadata.py`: package data loading and version checks.
- Create `tests/test_phase1_smoke.py`: release-path smoke test against current captured artifacts.
- Modify `docs/README.md`: package and CLI usage.
- Modify `docs/MODULES.md`: CLI/package module notes.
- Modify `docs/ROADMAP.md`: mark M1.7 release path expectations when complete.

## Prerequisite

Complete and verify M1.6 first. This plan expects:

- `coa_meta.reporting.MetaRunConfig`
- `coa_meta.reporting.MetaReportRunner`
- `coa_meta.reporting.write_report_outputs`
- `coa_meta.report_assets.AssetResolver`

Do not reimplement report logic in the CLI.

## Task 1: Thin CLI Adapter

**Files:**
- Create: `coa_meta/cli.py`
- Create: `coa_meta/__main__.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli.py`:

```python
from __future__ import annotations

from pathlib import Path

from coa_meta import cli


class DummyReport:
    def to_dict(self):
        return {"schema_version": "coa-meta-report-v1"}


class DummyRunner:
    last_config = None

    def __init__(self, config):
        DummyRunner.last_config = config

    def run(self):
        return DummyReport()


def test_meta_cli_dispatches_to_runner_and_writers(monkeypatch, tmp_path):
    written = {}

    def fake_write_outputs(report, out_dir, formats, asset_resolver=None):
        written["report"] = report
        written["out_dir"] = Path(out_dir)
        written["formats"] = formats
        written["asset_resolver"] = asset_resolver
        return (Path(out_dir) / "meta-report.json",)

    monkeypatch.setattr(cli, "MetaReportRunner", DummyRunner)
    monkeypatch.setattr(cli, "write_report_outputs", fake_write_outputs)

    exit_code = cli.main(
        [
            "meta",
            "--entries",
            "coa_scraper/dist/coa_entries.jsonl",
            "--classes",
            "coa_scraper/dist/coa_classes.json",
            "--class",
            "Venomancer",
            "--spec",
            "Stalker",
            "--level",
            "60",
            "--top",
            "2",
            "--beam-width",
            "4",
            "--branch-width",
            "8",
            "--require-budget-fraction",
            "0.5",
            "--format",
            "json",
            "--format",
            "html",
            "--out",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert DummyRunner.last_config is not None
    assert DummyRunner.last_config.class_names == ("Venomancer",)
    assert DummyRunner.last_config.spec_names_or_ids == ("Stalker",)
    assert DummyRunner.last_config.top == 2
    assert DummyRunner.last_config.beam_width == 4
    assert DummyRunner.last_config.branch_width == 8
    assert DummyRunner.last_config.require_budget_fraction == 0.5
    assert written["formats"] == ("json", "html")
    assert written["out_dir"] == tmp_path


def test_cli_returns_nonzero_for_unknown_command(capsys):
    exit_code = cli.main(["unknown"])

    assert exit_code == 2
    assert "usage:" in capsys.readouterr().err
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_cli.py -q
```

Expected: FAIL with `ImportError: cannot import name 'cli' from 'coa_meta'`.

- [ ] **Step 3: Implement CLI module**

Create `coa_meta/cli.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .report_assets import AssetResolver
from .reporting import MetaReportRunner, MetaRunConfig, write_report_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coa_meta")
    subparsers = parser.add_subparsers(dest="command")

    meta = subparsers.add_parser("meta", help="Generate Phase 1 theorycraft meta reports")
    meta.add_argument("--entries", type=Path, default=Path("coa_scraper/dist/coa_entries.jsonl"))
    meta.add_argument("--classes", type=Path, default=Path("coa_scraper/dist/coa_classes.json"))
    meta.add_argument("--level", type=int, default=60)
    meta.add_argument("--class", dest="classes", action="append", default=[])
    meta.add_argument("--spec", dest="specs", action="append", default=[])
    meta.add_argument("--encounter-profile", dest="encounters", action="append", default=[])
    meta.add_argument("--top", type=int, default=3)
    meta.add_argument("--beam-width", type=int, default=5)
    meta.add_argument("--branch-width", type=int, default=10)
    meta.add_argument("--require-budget-fraction", type=float, default=0.7)
    meta.add_argument("--workers", type=int, default=1)
    meta.add_argument("--format", dest="formats", action="append", choices=("json", "md", "html"), default=[])
    meta.add_argument("--out", type=Path, default=Path("reports/meta"))
    meta.add_argument("--asset-root", type=Path, default=None)
    meta.set_defaults(handler=run_meta)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(args))


def run_meta(args: argparse.Namespace) -> int:
    config = MetaRunConfig(
        entries_path=args.entries,
        classes_path=args.classes,
        class_names=tuple(args.classes),
        spec_names_or_ids=tuple(args.specs),
        level=args.level,
        encounter_profile_ids=tuple(args.encounters) if args.encounters else ("baseline_single_target",),
        top=args.top,
        beam_width=args.beam_width,
        branch_width=args.branch_width,
        require_budget_fraction=args.require_budget_fraction,
    )
    report = MetaReportRunner(config).run()
    formats = tuple(args.formats) if args.formats else ("json", "md", "html")
    asset_resolver = AssetResolver(args.asset_root) if args.asset_root else None
    write_report_outputs(report, args.out, formats=formats, asset_resolver=asset_resolver)
    return 0
```

Create `coa_meta/__main__.py`:

```python
from __future__ import annotations

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
python -m pytest tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit CLI adapter**

```bash
git add coa_meta/cli.py coa_meta/__main__.py tests/test_cli.py
git commit -m "feat: add meta CLI entry point"
```

## Task 2: Packaging Metadata and Package Data

**Files:**
- Create: `pyproject.toml`
- Test: `tests/test_package_metadata.py`

- [ ] **Step 1: Write failing package tests**

Create `tests/test_package_metadata.py`:

```python
from __future__ import annotations

import importlib.metadata
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
```

- [ ] **Step 2: Run package tests before metadata**

Run:

```bash
python -m pytest tests/test_package_metadata.py -q
```

Expected: FAIL with `AssertionError` for missing `pyproject.toml`.

- [ ] **Step 3: Add minimal `pyproject.toml`**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "coa-meta-analyzer"
version = "0.1.0"
description = "Ascension Conquest of Azeroth Phase 1 theorycraft meta analyzer"
readme = "docs/README.md"
requires-python = ">=3.11"
authors = [
  {name = "CoA Meta Analyzer contributors"}
]
dependencies = []

[project.scripts]
coa-meta = "coa_meta.cli:main"

[tool.setuptools]
packages = ["coa_meta"]

[tool.setuptools.package-data]
coa_meta = [
  "data/scoring_profiles/*.json",
  "data/apl_profiles/*.json"
]
```

- [ ] **Step 4: Verify package metadata and source tests**

Run:

```bash
python -m pytest tests/test_package_metadata.py tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit packaging metadata**

```bash
git add pyproject.toml tests/test_package_metadata.py
git commit -m "build: add package metadata"
```

## Task 3: Release-Path Smoke Test

**Files:**
- Create: `tests/test_phase1_smoke.py`

- [ ] **Step 1: Write smoke test for `python -m coa_meta meta`**

Create `tests/test_phase1_smoke.py`:

```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_python_module_meta_command_generates_json_report(tmp_path):
    entries = Path("coa_scraper/dist/coa_entries.jsonl")
    classes = Path("coa_scraper/dist/coa_classes.json")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "coa_meta",
            "meta",
            "--entries",
            str(entries),
            "--classes",
            str(classes),
            "--class",
            "Venomancer",
            "--top",
            "1",
            "--beam-width",
            "2",
            "--branch-width",
            "4",
            "--require-budget-fraction",
            "0.0",
            "--format",
            "json",
            "--out",
            str(tmp_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    report_path = tmp_path / "meta-report.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "coa-meta-report-v1"
    assert data["spec_results"]
    assert all(result["class_name"] == "Venomancer" for result in data["spec_results"])
    assert "observed_dps" not in data
    assert "raw_dps" not in data
```

- [ ] **Step 2: Run smoke test**

Run:

```bash
python -m pytest tests/test_phase1_smoke.py -q
```

Expected: PASS and create only temporary report files under pytest's temporary directory.

- [ ] **Step 3: Run CLI and package tests together**

Run:

```bash
python -m pytest tests/test_cli.py tests/test_package_metadata.py tests/test_phase1_smoke.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit smoke test**

```bash
git add tests/test_phase1_smoke.py
git commit -m "test: add phase1 CLI smoke test"
```

## Task 4: User-Facing CLI Documentation

**Files:**
- Modify: `docs/README.md`
- Modify: `docs/MODULES.md`
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Update docs README with release command**

Append to `docs/README.md`:

````markdown

## Phase 1 Meta Report Command

After installing the package or running from the repository root, generate a theorycraft meta report with:

```bash
python -m coa_meta meta \
  --entries coa_scraper/dist/coa_entries.jsonl \
  --classes coa_scraper/dist/coa_classes.json \
  --out reports/meta \
  --format json --format md --format html
```

Useful bounded runs:

```bash
python -m coa_meta meta --class Venomancer --top 1 --format json --out reports/meta-smoke
python -m coa_meta meta --class "Sun Cleric" --spec Blessings --level 60 --out reports/sun-cleric-blessings
```

The report emits projected theorycraft indexes. It does not emit observed DPS, simulated DPS, or empirical rankings.
````

- [ ] **Step 2: Update module docs**

Append to `docs/MODULES.md`:

```markdown

## CLI and Packaging

- `coa_meta.cli`: thin argparse command adapter. It constructs `MetaRunConfig`, calls `MetaReportRunner`, and writes requested report formats.
- `coa_meta.__main__`: enables `python -m coa_meta`.
- `pyproject.toml`: package metadata and package-data inclusion for built-in scoring/APL profiles.
```

- [ ] **Step 3: Update roadmap status language**

In `docs/ROADMAP.md`, under M1.7 exit criteria, keep the existing criteria and add this implementation note:

```markdown

Implementation note:

- The release path is `python -m coa_meta meta ...`.
- Browser capture remains part of `coa_scraper/` and is not required for package tests.
```

- [ ] **Step 4: Run full verification**

Run:

```bash
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit documentation**

```bash
git add docs/README.md docs/MODULES.md docs/ROADMAP.md
git commit -m "docs: document meta CLI release path"
```

## Task 5: Final Packaging Verification

**Files:**
- No new source files.

- [ ] **Step 1: Run full test suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 2: Run direct module help command**

Run:

```bash
python -m coa_meta --help
```

Expected: exit code 0 and output containing `meta`.

- [ ] **Step 3: Run bounded release command manually**

Run:

```bash
python -m coa_meta meta \
  --entries coa_scraper/dist/coa_entries.jsonl \
  --classes coa_scraper/dist/coa_classes.json \
  --class Venomancer \
  --top 1 \
  --beam-width 2 \
  --branch-width 4 \
  --require-budget-fraction 0.0 \
  --format json \
  --out /tmp/coa-meta-smoke
```

Expected: exit code 0 and `/tmp/coa-meta-smoke/meta-report.json` exists with `schema_version` equal to `coa-meta-report-v1`.

- [ ] **Step 4: Commit final verification marker if docs changed**

If no files changed in Step 1 through Step 3, do not create an empty commit. If verification exposed documentation corrections, commit only those corrections:

```bash
git add docs/README.md docs/MODULES.md docs/ROADMAP.md
git commit -m "docs: clarify meta CLI verification"
```

## M1.7 Completion Gate

Run:

```bash
python -m pytest -q
python -m coa_meta --help
```

Expected: tests pass and help output includes the `meta` command.

M1.7 is complete when `python -m coa_meta meta ...` is the documented release path, package metadata includes built-in profile data, and report tests do not require browser automation.
