from __future__ import annotations

from coa_meta.domain import TalentNode
from coa_meta.leveling_path import (
    LEVELING_PATH_SCHEMA_VERSION,
    LevelingPathStep,
    automatic_passive_steps,
    essence_awards_for_levels,
    essence_kind_for_level,
)


def test_level_10_through_60_alternates_ae_then_te():
    awards = essence_awards_for_levels(10, 60)

    assert LEVELING_PATH_SCHEMA_VERSION == "coa-leveling-path-v1"
    assert awards[0].level == 10
    assert awards[0].essence_kind == "ability"
    assert awards[1].level == 11
    assert awards[1].essence_kind == "talent"
    assert essence_kind_for_level(60) == "ability"
    assert sum(1 for award in awards if award.essence_kind == "ability") == 26
    assert sum(1 for award in awards if award.essence_kind == "talent") == 25


def _node(
    entry_id: int,
    name: str,
    *,
    level: int,
    ae: int = 0,
    te: int = 0,
    passive: bool = True,
    tab_name: str = "Damage",
    required_ids: tuple[int, ...] = tuple(),
    required_tab_ae: int = 0,
    required_tab_te: int = 0,
    tags: tuple[str, ...] = ("damage",),
) -> TalentNode:
    return TalentNode(
        entry_id=entry_id,
        spell_id=entry_id + 1000,
        name=name,
        class_id=1,
        class_name="Testclass",
        tab_id=10 if tab_name == "Class" else 11,
        tab_name=tab_name,
        entry_type="Talent",
        essence_kind="talent" if te else "ability",
        ae_cost=ae,
        te_cost=te,
        required_tab_ae=required_tab_ae,
        required_tab_te=required_tab_te,
        required_level=level,
        max_rank=1,
        row=0,
        col=10,
        node_type="SpendCircle",
        is_passive=passive,
        is_starting_node=False,
        required_ids=required_ids,
        connected_node_ids=tuple(),
        tags=tags,
        damage_schools=tuple(),
        resources=tuple(),
        description_text="Level passive.",
        availability={"effective_required_level": level, "level_confidence": "high"},
    )


def test_automatic_passives_unlock_without_spending_essence():
    passive = _node(401, "Level 20 Passive", level=20)

    steps = automatic_passive_steps((passive,), selected_ids={401}, level=20, already_unlocked=set())

    assert steps == (
        LevelingPathStep(
            level=20,
            event_type="automatic_passive",
            node_id=401,
            spell_id=1401,
            name="Level 20 Passive",
            essence_kind="free",
            reason="Unlocks automatically at level 20.",
            ae_spent=0,
            te_spent=0,
            warnings=tuple(),
        ),
    )
