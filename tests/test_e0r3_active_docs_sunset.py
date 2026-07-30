# tests/test_e0r3_active_docs_sunset.py
"""E0R.3 P2: the runtime sunset was enforced; the OPERATOR DOCUMENTATION still resurrected it.

E0R/E0R.1 deleted the AscensionDB enrichment runtime and proved it deleted — a network trap, a
no-ascensiondb suite, a negative-dependency gate. None of that reads the docs, so the docs went on
telling users and future contributors to run functionality that no longer exists:
`--db-tooltips` (removed from the CLI), `npm run pipeline:m1.8` (removed from both package.json
files), `coa_db_spell_tooltips.jsonl` (no producer), AscensionDB hotlinks (icons are client-native),
and a `db_enrichment` normalized field (absent from every script). `docs/README.md` is also the
distribution's `readme`, so it shipped in the package metadata.

The rule these tests encode is the reviewer's own: active documentation describes the system as it is,
while historical designs, decisions, and fixtures may keep AscensionDB references **when clearly marked
historical or superseded**. So the gate is not "the string never appears" — that would force lying about
the project's history — it is "an occurrence in an active doc is marked, at its line or by its section".

`docs/superpowers/**` is excluded by construction: every file there is a dated design, plan, or
execution tracker, historical the moment it is written. Deleting AscensionDB from those would destroy
the record of why it was removed.
"""
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Every way an active doc can point at the retired pipeline: the host and product name, plus the
# artifacts and record field it produced, none of which has a writer any more.
MENTION = re.compile(
    r"ascensiondb|db\.ascension\.gg|coa_db_spell_tooltips|coa_db_enrichment_summary|db_enrichment",
    re.I,
)

# Marking vocabulary. Deliberately tight: each token, read in a sentence about AscensionDB, can only
# mean the reference is to something no longer in force. Loose words ("never", "optional") are excluded
# because they also occur in sentences asserting a live capability.
MARKERS = (
    "retired", "removed", "superseded", "historical", "history", "no longer", "opt-in", "sunset",
    "deleted", "previously", "hard-cut", "corrected by",
)

# Deleted INVOCATIONS — a removed CLI flag and two removed npm scripts. These get no marker exemption
# anywhere in an active doc: a command reads as runnable regardless of the prose around it, and a reader
# who copies it gets an error, not a history lesson. Removed artifact and field NAMES are deliberately
# not on this list — a schema doc naming `db_enrichment` in order to say it is gone is doing its job —
# so they ride the marker rule above instead.
# `test_the_forbidden_commands_really_are_gone_from_the_runtime` keeps this list honest: if one is ever
# legitimately reintroduced, that test fails first and says so.
FORBIDDEN_COMMANDS = ("--db-tooltips", "pipeline:m1.8", "pipeline:m1.9")

LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")


def _active_docs() -> list[Path]:
    """Top-level docs plus the data-contract docs. NOT `docs/superpowers/**`.

    Git pathspecs are not shell globs — `*` crosses `/` — so `git ls-files "docs/*.md"` returns the
    dated designs and plans too. The exclusion has to be explicit."""
    listed = subprocess.run(["git", "ls-files", "docs"], capture_output=True, text=True, check=True,
                            cwd=REPO)
    paths = [REPO / line for line in listed.stdout.split()
             if line.endswith(".md") and Path(line).parent.as_posix() in ("docs", "docs/data")]
    assert paths, "no active docs found — the pathspec or the working directory is wrong"
    return paths


def _blocks(lines: list[str]) -> list[tuple[int, int]]:
    """Half-open line ranges of the prose blocks a marker can scope over: a paragraph, or a single list
    item including its wrapped continuation lines.

    Markdown wraps sentences, so line-level matching would miss a marker that landed one line after the
    mention it qualifies. Blocks are also cut at each list item, so a marked bullet does not silently
    exempt the unmarked bullet beside it."""
    ranges = []
    start = None
    for i, line in enumerate(lines):
        if not line.strip():
            if start is not None:
                ranges.append((start, i))
                start = None
            continue
        if start is not None and (LIST_ITEM.match(line) or line.startswith("#")):
            ranges.append((start, i))
            start = i
        elif start is None:
            start = i
    if start is not None:
        ranges.append((start, len(lines)))
    return ranges


def _section_context(lines: list[str], heading: int) -> list[str]:
    """A heading plus the first block under it. This repo marks status exactly there — see
    `docs/ROADMAP.md`'s M1.8 entry, whose heading is followed by
    `Status: ... **Superseded by M1.14E0R.1 (AscensionDB sunset).**` — so a section marked once need not
    repeat the marker on every line beneath it."""
    i = heading + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    paragraph = []
    while i < len(lines) and lines[i].strip() and not lines[i].startswith("#"):
        paragraph.append(lines[i])
        i += 1
    return [lines[heading]] + paragraph


def _unmarked_mentions(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    block_of = {i: (start, stop) for start, stop in _blocks(lines) for i in range(start, stop)}
    context: list[str] = []
    unmarked = []
    for index, line in enumerate(lines):
        if line.startswith("#"):
            context = _section_context(lines, index)
        if MENTION.search(line):
            start, stop = block_of.get(index, (index, index + 1))
            blob = " ".join(context + lines[start:stop]).lower()
            if not any(marker in blob for marker in MARKERS):
                unmarked.append(f"{path.relative_to(REPO)}:{index + 1}: {line.strip()}")
    return unmarked


def test_active_docs_mention_ascensiondb_only_as_retired():
    """Every AscensionDB reference in an active doc is marked — on its own line, or by the section it
    sits in. An unmarked one reads as a live data source, which is what a future contributor would then
    build against."""
    unmarked = [hit for path in _active_docs() for hit in _unmarked_mentions(path)]
    assert unmarked == []


@pytest.mark.parametrize("invocation", FORBIDDEN_COMMANDS)
def test_no_active_doc_invokes_retired_functionality(invocation):
    hits = [f"{path.relative_to(REPO)}:{number}"
            for path in _active_docs()
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
            if invocation in line]
    assert hits == []


@pytest.mark.parametrize("invocation", FORBIDDEN_COMMANDS)
def test_the_forbidden_commands_really_are_gone_from_the_runtime(invocation):
    """The blacklist must track the code, not outlive it. Forbidding a flag in the docs while the CLI
    still accepts it would be its own documentation defect — the opposite one — so each entry is
    checked against the runtime that would have to provide it."""
    searched = ["coa_meta", "coa_client_extract", "coa_scraper/scripts", "package.json",
                "coa_scraper/package.json"]
    found = subprocess.run(["git", "grep", "-l", "-F", invocation, "--"] + searched,
                           capture_output=True, text=True, cwd=REPO)
    assert found.stdout.split() == [], f"{invocation} still exists in the runtime"
