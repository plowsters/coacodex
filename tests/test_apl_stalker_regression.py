from __future__ import annotations

from pathlib import Path

from coa_meta.apl import generate_apl
from coa_meta.apl_profiles import load_builtin_apl_profile
from coa_meta.domain import BuildState, SelectedRank
from coa_meta.repository import TalentRepository

ENTRIES = Path("coa_scraper/dist/coa_entries.jsonl")
STALKER_NODE_IDS = {
    "Withering Venom": 7152,
    "Contagion": 7190,
    "Widowmaker": 12201,
    "Noxious Empowerment": 29577,
    "Nerubian Sting": 29580,
    "Facemelter": 30464,
}


def stalker_state() -> tuple[TalentRepository, BuildState]:
    repo = TalentRepository.from_entries(ENTRIES)
    selected = tuple(SelectedRank(node_id, 1) for node_id in sorted(STALKER_NODE_IDS.values()))
    state = BuildState(
        class_name="Venomancer",
        selected_ranks=selected,
        free_node_ids=tuple(),
        ae_spent=0,
        te_spent=len(selected),
        tab_ae=tuple(),
        tab_te=((77, len(selected)),),
    )
    return repo, state


def test_stalker_single_target_matches_old_apl_semantics():
    repo, state = stalker_state()
    profile = load_builtin_apl_profile("venomancer_stalker")

    document = generate_apl(state, repo, profile, encounter="single_target")
    by_name = {action.action_name: action for action in document.actions}
    categories = [action.category for action in document.actions]

    assert by_name["Withering Venom"].category == "maintenance"
    assert by_name["Nerubian Sting"].category == "maintenance"
    assert by_name["Facemelter"].category == "spender"
    assert by_name["Widowmaker"].category == "execute"
    assert by_name["Widowmaker"].condition == "target.health.pct<35"
    assert "aoe" not in categories
    assert categories.index("maintenance") < categories.index("spender")
    assert any("profile_rule:stalker_dot_maintenance" in action.evidence for action in document.actions)


def test_stalker_aoe_branch_contains_aoe_actions():
    repo, state = stalker_state()
    profile = load_builtin_apl_profile("venomancer_stalker")

    document = generate_apl(state, repo, profile, encounter="aoe_5")
    by_name = {action.action_name: action for action in document.actions}

    assert by_name["Contagion"].category == "aoe"
    assert by_name["Contagion"].condition == "active_enemies>=3"
    assert by_name["Facemelter"].category == "spender"
