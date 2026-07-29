"""E0R.2 T7.1: a tracked artifact is a published artifact.

Machine-local absolute paths leak the author's filesystem layout and make records non-reproducible
across machines: two people running the identical pipeline against the identical client produce records
that differ in a field neither of them chose. The client root is out of tree by design, so it is
referenced by the SYMBOLIC label `$COA_CLIENT_ROOT` — never by its expansion, and never by a hash of its
expansion, which would make otherwise identical runs machine-dependent while looking canonical.

The CI half is the same idea one level up: `npm test` is `unit-test && validate`, so running
`run unit-test` meant `validate-normalized.mjs` had never been a merge gate at all.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from coa_client_extract.artifacts import portable_path

REPO = Path(__file__).resolve().parents[1]
# Any `/home/<user>/` prefix, not just this author's — the point is that NO machine's layout belongs in
# a published record.
HOME_PATH = re.compile(r"/home/[a-z][a-z0-9_-]*/")
TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".py", ".mjs", ".js", ".yml", ".yaml", ".toml", ".txt",
                 ".sh", ".cfg", ".ini"}


def _tracked_text() -> list[Path]:
    out = subprocess.check_output(["git", "ls-files"], cwd=REPO, text=True)
    return [REPO / line for line in out.splitlines()
            if line and Path(line).suffix in TEXT_SUFFIXES]


def test_no_tracked_text_artifact_carries_a_machine_local_path():
    offenders = []
    for path in _tracked_text():
        if path.name == Path(__file__).name:
            continue                                   # this file names the pattern it forbids
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if HOME_PATH.search(line):
                offenders.append(f"{path.relative_to(REPO)}:{lineno}")
    assert offenders == [], f"machine-local paths in tracked text: {offenders}"


def test_the_scan_actually_reaches_the_tracked_corpus():
    """A hygiene scan that silently matched nothing would pass forever. Both halves are asserted: the
    file list is real, and the pattern fires on the string it is meant to catch."""
    tracked = _tracked_text()
    assert len(tracked) > 100 and all(p.is_absolute() for p in tracked)
    assert HOME_PATH.search("/home/someuser/projects/coacodex")
    assert not HOME_PATH.search("$COA_CLIENT_ROOT/Data/patch-T.MPQ")


# --- the producer, not just the artifact ---

def test_an_in_repo_path_is_recorded_repo_relative():
    assert portable_path(REPO / "reports/client_extract/coa_client_extract.pointer.json") == \
        "reports/client_extract/coa_client_extract.pointer.json"


def test_a_client_path_is_recorded_as_the_symbolic_label():
    """A LABEL, never a hash of the expansion: hashing would look canonical while still making two
    identical runs on two machines differ."""
    root = "/opt/some-launcher/resources/ascension-live"
    assert portable_path(f"{root}/Data/patch-T.MPQ", client_root=root) == \
        "$COA_CLIENT_ROOT/Data/patch-T.MPQ"
    assert HOME_PATH.search(portable_path("/home/someone/client/Data/patch-T.MPQ",
                                          client_root="/home/someone/client")) is None


def test_an_absolute_path_under_neither_root_degrades_to_its_name():
    """Archive names and content hashes carry the identity; the directory it sat in is the machine."""
    assert portable_path("/somewhere/else/patch-T.MPQ") == "patch-T.MPQ"


def test_a_relative_path_is_left_exactly_as_it_is():
    for value in ("dist/coa_entries.jsonl", "--out", "node", "./scripts/network-trap.mjs"):
        assert portable_path(value) == value


def test_the_recon_source_pins_name_archives_the_way_topology_does():
    """The recon report stated the same fact twice — `source_pins.effective_archive` absolute and
    `topology.tables[*].effective_archive` logical. The policy loader refuses an absolute one outright
    (`spell_layout`), so the logical name is the form the rest of the system already agrees on."""
    source = (REPO / "coa_client_extract/spell_mechanics.py").read_text(encoding="utf-8")
    assert '"effective_archive": member.effective_archive.name' in source
    assert '"patch_chain": [p.name for p in member.patch_chain]' in source
    assert "str(member.effective_archive)" not in source


def _absolute_strings(node, trail="") -> list[str]:
    """Every string in a record that reads as an absolute POSIX path. `$COA_CLIENT_ROOT/...` is the
    symbolic form and is deliberately not one."""
    if isinstance(node, dict):
        return [hit for k, v in node.items() for hit in _absolute_strings(v, f"{trail}.{k}")]
    if isinstance(node, list):
        return [hit for i, v in enumerate(node) for hit in _absolute_strings(v, f"{trail}[{i}]")]
    return [f"{trail} = {node}"] if isinstance(node, str) and node.startswith("/") else []


def test_the_acceptance_record_writer_emits_no_absolute_path(tmp_path):
    """The gate where it belongs — on the PRODUCER, driven end-to-end. The tracked artifact is only
    ever as clean as the writer that made it, and this run's inputs all live under an absolute tmp
    directory, so every path the record states had an absolute form available to leak."""
    from coa_client_extract.cli import run_acceptance
    from tests._e0r2_acceptance_fixtures import acceptance_env

    record = run_acceptance(**acceptance_env(tmp_path))
    assert _absolute_strings(record) == []


def _ci_commands() -> list[str]:
    """The workflow's actual `run:` commands. Scanning the whole file would match a comment explaining
    the very mistake being forbidden."""
    ci = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8").splitlines()
    return [line.split("run:", 1)[1].strip() for line in ci if line.strip().startswith("run:")]


def test_ci_runs_the_full_node_suite():
    commands = _ci_commands()
    assert "npm --prefix coa_scraper test" in commands
    # `npm test` is `unit-test && validate`; running unit-test alone skipped validate-normalized.mjs.
    assert not any("unit-test" in c for c in commands)


def test_ci_checks_out_full_history():
    """actions/checkout@v4 defaults to fetch-depth 1, which leaves the contract-immutability
    merge-base check (T1.1) unable to run at all — it needs the base commit to diff against."""
    ci = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in ci
