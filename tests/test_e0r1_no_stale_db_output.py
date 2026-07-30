# tests/test_e0r1_no_stale_db_output.py
"""E0R.1 T2.5 — the generated guide site and the scraped DB tooltip catalog carry db.ascension.gg hotlinks
and are build OUTPUTS, not authority. They must be UNTRACKED + gitignored; the generator, templates, and
source fonts stay committed under coa_meta/. Guards against a stale db.ascension.gg artifact re-entering git."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Generated outputs that previously carried db.ascension.gg hotlinks (untrack + ignore).
GENERATED = ["reports/meta", "coa_scraper/dist/coa_db_spell_tooltips.jsonl"]
# Generator + templates + source fonts that MUST remain the committed authority.
AUTHORITY = ["coa_meta/guide_writer.py", "coa_meta/guide_builder.py", "coa_meta/guide_rendering.py",
             "coa_meta/guide_assets.py", "coa_meta/assets/fonts/Barlow-400.woff2"]


def _tracked(path: str) -> list[str]:
    out = subprocess.run(["git", "ls-files", path], cwd=REPO, capture_output=True, text=True, check=True)
    return [l for l in out.stdout.splitlines() if l.strip()]


def _ignored(path: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO).returncode == 0


def test_generated_site_and_db_catalog_are_untracked():
    for path in GENERATED:
        assert _tracked(path) == [], f"{path} is a generated output and must not be tracked"


def test_generated_outputs_are_gitignored():
    assert _ignored("reports/meta/index.html")
    assert _ignored("coa_scraper/dist/coa_db_spell_tooltips.jsonl")


def test_no_tracked_file_under_generated_site_carries_db_hotlink():
    # The generated site is fully untracked, so a git grep scoped to it finds nothing (0 -> no matches).
    r = subprocess.run(["git", "grep", "-l", "db.ascension.gg", "--", "reports/meta/"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.stdout.strip() == "", f"tracked generated artifact still carries a hotlink: {r.stdout!r}"


def test_generator_templates_and_fonts_remain_committed():
    for path in AUTHORITY:
        assert _tracked(path) == [path], f"{path} is authority and must remain tracked"
