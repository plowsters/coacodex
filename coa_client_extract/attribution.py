# coa_client_extract/attribution.py
from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict

# class-kind -> participation mode. An unrecognized kind is deliberately absent:
# `.get(kind)` returns None so an out-of-band class contributes NO mode (never a
# silent "stock" default, which would mislabel unknowns as legal stock content).
_KIND_TO_MODE = {"coa_class": "coa", "coa_system": "coa", "reborn": "reborn",
                 "stock": "stock", "meta": "stock"}

@dataclass(frozen=True)
class AttributionResult:
    is_coa: bool
    modes: tuple[str, ...]
    exclusive_mode: str | None
    confidence: str


@dataclass
class SpellAttribution:
    result: AttributionResult
    memberships: list[dict] = field(default_factory=list)


def derive_coa_skill_lines(skill_line_ability_rows, coa_spell_ids):
    """PROVE the CoA SkillLine set empirically: the set of SkillLines that already carry at least one
    spell the registry attributed `coa`. Discovery showed CoA advancement spells attach to per-SPEC
    skill lines (Venomancer -> Stalking/Rot), not just the class-band lines 475-495, so a hard-coded
    range would miss most of them. Rows are positional dicts from `parse_positional(SkillLineAbility)`:
    col 1 = SkillLine FK, col 2 = Spell FK."""
    coa_spells = set(coa_spell_ids)
    return {row.get(1) for row in skill_line_ability_rows
            if row.get(2) in coa_spells and row.get(1)}


def build_skill_line_index(skill_line_ability_rows, coa_line_ids):
    """Map spell_id -> "coa" for abilities whose SkillLine is in the PROVEN CoA skill-line set
    (`derive_coa_skill_lines`). This is the medium-confidence fallback for spells absent from
    CharacterAdvancement.dbc — a graph-absent spell sharing a proven CoA line is likely CoA. The
    caller passes the derived set; there is no hard-coded skill-line range."""
    coa_lines = set(coa_line_ids)
    index: dict[int, str] = {}
    for row in skill_line_ability_rows:
        skill_line, spell_id = row.get(1), row.get(2)
        if skill_line in coa_lines and spell_id:
            index[spell_id] = "coa"
    return index


def attribute(nodes, class_types, skill_line_index=None) -> dict[int, SpellAttribution]:
    by_spell: dict[int, list] = defaultdict(list)
    for n in nodes:
        if n.spell_id:
            by_spell[n.spell_id].append(n)

    out: dict[int, SpellAttribution] = {}
    for spell_id, spell_nodes in by_spell.items():
        modes, memberships = [], []
        for n in spell_nodes:
            mode = _KIND_TO_MODE.get(n.class_kind)   # None for an unknown kind
            if mode and mode not in modes:
                modes.append(mode)
            memberships.append({
                "mode": mode or "unknown", "class_type_id": n.class_type_id,
                "class_internal": n.class_internal, "class_display": n.class_display,
                "tab_type_id": n.tab_type_id, "tab_name": n.tab_name,
                "node_id": n.node_id, "entry_type": n.entry_type,
            })
        modes = tuple(sorted(modes))
        is_coa = "coa" in modes
        # A graph-present spell with at least one recognized mode is high confidence;
        # if every node was an unknown kind, no mode is claimed -> low confidence.
        confidence = "high" if modes else "low"
        out[spell_id] = SpellAttribution(
            AttributionResult(is_coa, modes,
                              modes[0] if len(modes) == 1 else None, confidence),
            memberships,
        )

    # Skill-line fallback for spells absent from the graph (medium confidence, coa only).
    for spell_id, mode in (skill_line_index or {}).items():
        if spell_id not in out and mode == "coa":
            out[spell_id] = SpellAttribution(
                AttributionResult(True, ("coa",), "coa", "medium"), [])
    return out
