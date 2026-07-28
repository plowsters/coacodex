# tests/test_e0r1_sunset_complete.py
"""E0R.1 T5.1 — the AscensionDB sunset is COMPLETE, encoded as the plan's probe verbatim: no runtime
(non-test, non-downloader) file imports `ascensiondb` or contains `db.ascension.gg`; `guide_tooltips`
emits neither an `ascension_db` source nor a DB URL; no CLI exposes a DB input; the opt-in icon
downloader refuses to run without `--authorize` and only writes under a `diagnostic/` dir (behavioral
downloader gates live in coa_scraper/tests/no-ascensiondb.test.mjs)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "coa_scraper" / "scripts"
DOWNLOADER = SCRIPTS / "download-spell-icons.mjs"
DB_HOST = "db.ascension.gg"

# git rm'd by T5.1 — the DB parser/cache runtime, the DB-derived item builder, and their tests.
DELETED = (
    "coa_scraper/scripts/lib/ascensiondb.mjs",
    "coa_scraper/scripts/lib/ascensiondb-cache.mjs",
    "coa_scraper/scripts/build-item-artifacts.mjs",
    "coa_scraper/tests/ascensiondb-parser.test.mjs",
    "coa_scraper/tests/ascensiondb-cache.test.mjs",
)

_MJS_IMPORT_RE = re.compile(r"""(?:from|import)\s*\(?\s*["'][^"']*ascensiondb""")


def _runtime_files():
    roots = ((REPO / "coa_meta", "**/*.py"), (REPO / "coa_client_extract", "**/*.py"),
             (SCRIPTS, "**/*.mjs"))
    for base, pattern in roots:
        for path in sorted(base.glob(pattern)):
            if {"__pycache__", "node_modules", "dist", "reports"} & set(path.parts):
                continue
            if path == DOWNLOADER:
                continue
            yield path


def test_deleted_ascensiondb_files_are_gone():
    survivors = [rel for rel in DELETED if (REPO / rel).exists()]
    assert survivors == [], f"AscensionDB runtime files survive the sunset: {survivors}"


def test_no_runtime_file_imports_ascensiondb_or_contains_the_db_host():
    offenders = []
    for path in _runtime_files():
        text = path.read_text(encoding="utf-8")
        if DB_HOST in text:
            offenders.append(f"{path.relative_to(REPO)}: contains {DB_HOST}")
        if path.suffix == ".mjs" and _MJS_IMPORT_RE.search(text):
            offenders.append(f"{path.relative_to(REPO)}: imports ascensiondb")
    assert offenders == [], "\n".join(offenders)


def test_db_host_survives_only_in_the_opt_in_downloader():
    # The downloader is the ONLY non-test file that may carry the hostname, and it must be gated:
    # explicit --authorize plus a diagnostic/-only output dir.
    text = DOWNLOADER.read_text(encoding="utf-8")
    assert DB_HOST in text
    assert "--authorize" in text
    assert "diagnostic" in text


def test_no_runtime_script_imports_the_downloader():
    # Canonical guide generation must never be able to reach the downloader.
    offenders = [str(p.relative_to(REPO)) for p in _runtime_files()
                 if "download-spell-icons" in p.read_text(encoding="utf-8")
                 and p.name != "README-regeneration.md"]
    assert offenders == [], offenders


def test_guide_tooltips_is_client_native():
    import coa_meta.guide_tooltips as gt

    assert not hasattr(gt, "load_db_tooltip_rows"), "the DB tooltip loader must be removed"
    assert not hasattr(gt, "ascension_spell_url"), "the DB URL helper must be removed"
    source = Path(gt.__file__).read_text(encoding="utf-8")
    assert "ascension_db" not in source and DB_HOST not in source

    from coa_meta.repository import TalentRepository

    repo = TalentRepository.from_entries(REPO / "tests" / "fixtures" / "meta_report_fixture.jsonl")
    # Node 201 previously PREFERRED the scraped DB tooltip; client-native it is always `normalized`.
    tooltip = gt.build_node_tooltip(repo.node_by_id(201))
    assert tooltip.source == "normalized"
    assert tooltip.db_url is None
    assert tooltip.text  # normalized from the client/Builder description, never empty


def test_no_cli_exposes_a_db_input():
    from coa_meta.cli import build_parser

    assert "--db-tooltips" not in (REPO / "coa_meta" / "cli.py").read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        build_parser().parse_args(["meta", "--db-tooltips", "x.jsonl"])


def test_regeneration_readme_is_pointer_only_client_native():
    text = (SCRIPTS / "README-regeneration.md").read_text(encoding="utf-8")
    for stale in ("--db-spells", DB_HOST, "coa_db_spell_tooltips", "pipeline:m1.9"):
        assert stale not in text, f"stale DB-era regeneration instruction survives: {stale}"
    assert "--client-extract-pointer" in text


def test_artifact_manifest_writer_no_longer_tracks_deleted_db_files():
    writer = (SCRIPTS / "write-artifact-manifest.mjs").read_text(encoding="utf-8")
    committed = (REPO / "coa_scraper" / "reports" / "coa_artifact_manifest.json").read_text(encoding="utf-8")
    for text, where in ((writer, "writer"), (committed, "committed manifest")):
        for stale in ("ascensiondb", "build-item-artifacts", "coa_items.jsonl"):
            assert stale not in text, f"{where} still tracks {stale}"
