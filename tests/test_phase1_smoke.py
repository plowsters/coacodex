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
