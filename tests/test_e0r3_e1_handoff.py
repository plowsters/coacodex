# tests/test_e0r3_e1_handoff.py
"""E0R.3 P2: the E1 handoff must inherit the recon result that actually happened.

The E0R design was written expecting all four value-anchor joins to be adjudicated, and says so twice:
"E0R pulls **all four join adjudications** ... forward, so E1a shrinks: E1 no longer carries join
discovery", and "(This materially reduces E1a, which no longer carries join adjudication.)". The
realized run promoted exactly one — `spell_icon_id`, cell 133 — while `casting_time_index`,
`duration_index`, and `range_index` came back `reviewed_ambiguous` with committed evidence.

E0R behaved correctly: the ambiguity is measured, recorded, and fail-closed. The defect is the handoff.
An E1 implementer reading "no longer carries join discovery" would start by assuming cast time,
duration, and range are available, and would find nothing that says otherwise until a readiness gate
refused them.

So this reads the COMMITTED acceptance record rather than a list frozen here. If a later recon promotes
one of the three, this test fails and forces the handoff to be corrected in that direction too — the
docs cannot drift away from the record either way.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RECORD = REPO / "reports/client_extract/coa_e0r_acceptance_summary.json"
E0R_DESIGN = REPO / "docs/superpowers/specs/2026-07-19-m1-14-e0r-correctness-sunset-remediation-design.md"
E_DESIGN = REPO / "docs/superpowers/specs/2026-07-18-m1-14-e-mechanics-extraction-completion-design.md"
ROADMAP = REPO / "docs/ROADMAP.md"

# The milestone that owns the three unresolved joins. Not E1, and not "later": a named owner, because
# "deferred" with no owner is how a gap becomes permanent.
OWNER = "M1.14G"

# Claims the realized recon falsified. Matched literally: these exact sentences are the defect, and a
# rewrite that preserves the meaning would have to keep the words.
FALSIFIED_CLAIMS = (
    "E1 no longer carries join discovery",
    "no longer carries join adjudication",
)

UNAVAILABLE = ("unresolved", "unavailable", "reviewed_ambiguous", "ambiguous")


def _joins() -> tuple[list[str], list[str]]:
    """(ambiguous, resolved) join fields, from the published generation's own recon report."""
    report = json.loads(RECORD.read_text(encoding="utf-8"))["recon_report"]
    pairs = report["join_pairs"]
    required = report["required_joins"]
    ambiguous = sorted(f for f in required
                       if pairs.get(f, {}).get("adjudication") == "reviewed_ambiguous")
    return ambiguous, sorted(f for f in required if f not in ambiguous)


def _section(path: Path, heading: str) -> str:
    """A heading's body, up to the next heading of the same or higher level."""
    text = path.read_text(encoding="utf-8")
    level = len(heading) - len(heading.lstrip("#"))
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = re.search(rf"^#{{1,{level}}} ", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def test_the_record_and_the_docs_agree_on_which_joins_resolved():
    """Precondition for every assertion below: the record must actually distinguish the two groups.
    A record with nothing ambiguous, or nothing resolved, means the recon changed and this whole handoff
    needs rewriting rather than patching."""
    ambiguous, resolved = _joins()
    assert ambiguous and resolved, f"ambiguous={ambiguous} resolved={resolved}"


@pytest.mark.parametrize("claim", FALSIFIED_CLAIMS)
def test_no_design_still_claims_e1_inherits_adjudicated_joins(claim):
    for path in (E0R_DESIGN, E_DESIGN, ROADMAP):
        assert claim not in path.read_text(encoding="utf-8"), path.name


def test_the_e0r_design_hands_off_each_unresolved_join_by_name():
    section = _section(E0R_DESIGN, "## Impact on M1.14E1")
    ambiguous, resolved = _joins()
    for field in ambiguous:
        assert field in section, f"{field} is reviewed_ambiguous but the E1 handoff never names it"
    for field in resolved:
        assert field in section, f"{field} resolved but the E1 handoff never says so"
    assert any(word in section for word in UNAVAILABLE)
    assert OWNER in section, "the unresolved joins need a named owning milestone, not a deferral"


def test_the_e_umbrella_marks_e1_as_inheriting_them_unavailable():
    """The E umbrella is the doc an E1 implementer reads to learn what E1 is, so the inheritance has to
    be visible there and not only in E0R's retrospective."""
    text = E_DESIGN.read_text(encoding="utf-8")
    ambiguous, _ = _joins()
    for field in ambiguous:
        assert field in text, f"{field} is unresolved but the E umbrella never mentions it"
    assert OWNER in text


def test_the_roadmap_gives_the_unresolved_joins_a_named_owner():
    ambiguous, _ = _joins()
    owner_entry = _section(ROADMAP, "## Phase 1: Theorycrafting Meta Release")
    assert OWNER in owner_entry
    for field in ambiguous:
        assert field in owner_entry, f"{field} has no owner in the roadmap"


def test_the_evidence_bar_forbids_rerunning_the_same_scan():
    """The reviewer's constraint, kept where the next implementer will look: a second FK-validity scan
    over the same client is the same evidence, not new evidence. The recon report already records what
    that scan yields (30 / 34 / 14 candidate columns), so re-running it is a reproduction, and promoting
    a cell on the strength of it would be the exact unproven promotion E0R exists to prevent."""
    section = _section(E0R_DESIGN, "## Impact on M1.14E1")
    assert "FK-validity scan" in section
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    for field, spec in record["recon_report"]["join_pairs"].items():
        if spec.get("adjudication") != "reviewed_ambiguous":
            continue
        # Each ambiguous join's committed evidence must already state the candidate count, so the
        # "same scan" is a documented, reproducible quantity rather than a memory.
        assert "candidate columns" in spec["evidence"], field
