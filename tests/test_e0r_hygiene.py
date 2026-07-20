# tests/test_e0r_hygiene.py
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _iter_paths(doc):
    for group in ("scripts", "artifacts"):
        for entry in doc.get(group, []):
            if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                yield entry["path"]
    for key in ("dist_dir", "reports_dir"):
        if isinstance(doc.get(key), str):
            yield doc[key]


def test_no_absolute_home_paths_in_tracked_manifest():
    p = REPO / "coa_scraper/reports/coa_artifact_manifest.json"
    if p.exists():
        text = p.read_text()
        assert not re.search(r"/home/[a-z]", text), "machine-local absolute paths must be scrubbed"
        assert not re.search(r"/Users/[A-Za-z]", text), "machine-local absolute paths must be scrubbed"


def test_manifest_generator_emits_relative_paths(tmp_path):
    # Seed the two inputs the generator loads, then run it against a temp tree.
    (tmp_path / "coa_builder_payload.json").write_text(json.dumps({"id": 1, "slug": "s", "name": "n"}))
    (tmp_path / "coa_validation_summary.json").write_text(json.dumps({"status": "pass"}))
    out = tmp_path / "m.json"
    subprocess.run(
        ["node", str(REPO / "coa_scraper/scripts/write-artifact-manifest.mjs"),
         str(tmp_path), str(tmp_path), str(out)],
        cwd=str(REPO / "coa_scraper"), check=True,
    )
    doc = json.loads(out.read_text())
    for entry in _iter_paths(doc):
        assert not entry.startswith("/"), f"absolute path leaked: {entry}"
    # a missing-file note must carry only the repo-relative path, never a /home/... absolute leak.
    blob = json.dumps(doc)
    assert "/home/" not in blob and "\\Users\\" not in blob
