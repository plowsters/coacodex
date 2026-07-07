from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from .builds import BuildConfig, BuildRules
from .domain import BuildState, SelectedRank
from .domain import TalentNode
from .repository import TalentRepository

LEVELING_PATH_SCHEMA_VERSION = "coa-leveling-path-v1"


@dataclass(frozen=True)
class EssenceAward:
    level: int
    essence_kind: str
    amount: int = 1

    def to_dict(self) -> dict[str, int | str]:
        return {"level": self.level, "essence_kind": self.essence_kind, "amount": self.amount}


def essence_kind_for_level(level: int) -> str:
    if level < 10 or level > 60:
        raise ValueError("CoA leveling essence awards are defined for levels 10 through 60")
    return "ability" if level % 2 == 0 else "talent"


def essence_awards_for_levels(start_level: int = 10, max_level: int = 60) -> tuple[EssenceAward, ...]:
    if start_level < 10 or max_level > 60 or start_level > max_level:
        raise ValueError("Expected a level range within 10..60")
    return tuple(
        EssenceAward(level=level, essence_kind=essence_kind_for_level(level))
        for level in range(start_level, max_level + 1)
    )


@dataclass(frozen=True)
class LevelingPathStep:
    level: int
    event_type: str
    node_id: int | None
    spell_id: int | None
    name: str
    essence_kind: str
    reason: str
    ae_spent: int
    te_spent: int
    warnings: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "event_type": self.event_type,
            "node_id": self.node_id,
            "spell_id": self.spell_id,
            "name": self.name,
            "essence_kind": self.essence_kind,
            "reason": self.reason,
            "ae_spent": self.ae_spent,
            "te_spent": self.te_spent,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class LevelingPath:
    schema_version: str
    class_name: str
    spec_name: str
    build_id: str
    max_level: int
    steps: tuple[LevelingPathStep, ...]
    warnings: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "class_name": self.class_name,
            "spec_name": self.spec_name,
            "build_id": self.build_id,
            "max_level": self.max_level,
            "steps": [step.to_dict() for step in self.steps],
            "warnings": list(self.warnings),
        }


def effective_level(node: TalentNode) -> int:
    availability = node.availability or node.raw.get("availability") or {}
    level = availability.get("effective_required_level")
    if availability.get("level_confidence") in {"high", "medium"} and type(level) is int:
        return int(level)
    return int(node.required_level)


def automatic_passive_steps(
    nodes: Iterable[TalentNode],
    *,
    selected_ids: set[int],
    level: int,
    already_unlocked: set[int],
) -> tuple[LevelingPathStep, ...]:
    steps: list[LevelingPathStep] = []
    for node in sorted(nodes, key=lambda item: (effective_level(item), item.row, item.col, item.name)):
        if node.entry_id not in selected_ids or node.entry_id in already_unlocked:
            continue
        if node.ae_cost or node.te_cost:
            continue
        if effective_level(node) != level:
            continue
        already_unlocked.add(node.entry_id)
        steps.append(
            LevelingPathStep(
                level=level,
                event_type="automatic_passive",
                node_id=node.entry_id,
                spell_id=node.spell_id,
                name=node.name,
                essence_kind="free",
                reason=f"Unlocks automatically at level {level}.",
                ae_spent=0,
                te_spent=0,
            )
        )
    return tuple(steps)


def build_leveling_path(
    *,
    repository: TalentRepository,
    state: BuildState,
    class_name: str,
    spec_name: str,
    build_id: str,
    config: BuildConfig,
    role: str,
    apl=None,
    rotation_guide: dict | None = None,
) -> LevelingPath:
    del apl
    target_ids = set(state.selected_ids)
    target_nodes = tuple(
        repository.node_by_id(node_id)
        for node_id in sorted(_target_and_dependency_ids(repository, target_ids))
        if repository.get_node(node_id) is not None
    )
    selected: set[int] = set(state.free_node_ids)
    unlocked_passives: set[int] = set(state.free_node_ids)
    paid_ranks: list[SelectedRank] = []
    steps: list[LevelingPathStep] = []
    warnings: list[str] = []
    ae_budget = 0
    te_budget = 0
    ae_spent = 0
    te_spent = 0

    for award in essence_awards_for_levels(10, min(config.level, 60)):
        for passive_step in automatic_passive_steps(
            target_nodes,
            selected_ids=target_ids,
            level=award.level,
            already_unlocked=unlocked_passives,
        ):
            steps.append(replace(passive_step, ae_spent=ae_spent, te_spent=te_spent))
            if passive_step.node_id is not None:
                selected.add(passive_step.node_id)

        if award.essence_kind == "ability":
            ae_budget += award.amount
        else:
            te_budget += award.amount

        candidate, candidate_state = _best_legal_candidate(
            repository=repository,
            base_config=config,
            class_name=class_name,
            level=award.level,
            ae_budget=ae_budget,
            te_budget=te_budget,
            target_nodes=target_nodes,
            selected=selected,
            paid_ranks=paid_ranks,
            essence_kind=award.essence_kind,
            role=role,
            rotation_guide=rotation_guide or {},
        )
        if candidate is None or candidate_state is None:
            steps.append(
                LevelingPathStep(
                    level=award.level,
                    event_type="deferred",
                    node_id=None,
                    spell_id=None,
                    name="No legal target choice",
                    essence_kind=award.essence_kind,
                    reason=f"No selected {award.essence_kind} node is legal yet.",
                    ae_spent=ae_spent,
                    te_spent=te_spent,
                    warnings=("leveling_path_deferred_essence",),
                )
            )
            continue

        selected.add(candidate.entry_id)
        paid_ranks.append(SelectedRank(node_id=candidate.entry_id, rank=1))
        ae_spent = candidate_state.ae_spent
        te_spent = candidate_state.te_spent
        steps.append(
            LevelingPathStep(
                level=award.level,
                event_type="choose_ability" if award.essence_kind == "ability" else "choose_talent",
                node_id=candidate.entry_id,
                spell_id=candidate.spell_id,
                name=candidate.name,
                essence_kind=award.essence_kind,
                reason=_choice_reason(candidate, role, rotation_guide or {}),
                ae_spent=ae_spent,
                te_spent=te_spent,
            )
        )

    final_ids = {rank.node_id for rank in paid_ranks} | set(state.free_node_ids) | unlocked_passives
    missing = sorted(node_id for node_id in target_ids - final_ids if _is_paid_or_passive_target(repository, node_id))
    if missing:
        warnings.append("leveling_path_reconstruction_mismatch")
    return LevelingPath(
        schema_version=LEVELING_PATH_SCHEMA_VERSION,
        class_name=class_name,
        spec_name=spec_name,
        build_id=build_id,
        max_level=config.level,
        steps=tuple(steps),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _target_and_dependency_ids(repository: TalentRepository, target_ids: set[int]) -> set[int]:
    out = set(target_ids)
    changed = True
    while changed:
        changed = False
        for node_id in tuple(out):
            node = repository.get_node(node_id)
            if node is None:
                continue
            for required_id in node.required_ids:
                required = repository.get_node(required_id)
                if required and required.paid and required_id not in out:
                    out.add(required_id)
                    changed = True
    return out


def _best_legal_candidate(
    *,
    repository: TalentRepository,
    base_config: BuildConfig,
    class_name: str,
    level: int,
    ae_budget: int,
    te_budget: int,
    target_nodes: tuple[TalentNode, ...],
    selected: set[int],
    paid_ranks: list[SelectedRank],
    essence_kind: str,
    role: str,
    rotation_guide: dict,
) -> tuple[TalentNode | None, BuildState | None]:
    rules = BuildRules(
        repository,
        BuildConfig(
            class_name=class_name,
            level=level,
            max_ae=min(base_config.max_ae, ae_budget),
            max_te=min(base_config.max_te, te_budget),
            allowed_node_ids=base_config.allowed_node_ids,
        ),
    )
    scored: list[tuple[float, int, int, str, int, TalentNode, BuildState]] = []
    for node in target_nodes:
        if node.entry_id in selected or not node.paid:
            continue
        if essence_kind == "ability" and node.ae_cost <= 0:
            continue
        if essence_kind == "talent" and node.te_cost <= 0:
            continue
        result = rules.validate([*paid_ranks, SelectedRank(node.entry_id, 1)])
        if not result.valid or result.state is None:
            continue
        scored.append(
            (
                _marginal_value(node, role=role, rotation_guide=rotation_guide, selected=selected),
                -effective_level(node),
                -(node.required_tab_ae + node.required_tab_te),
                node.name,
                -node.entry_id,
                node,
                result.state,
            )
        )
    if not scored:
        return None, None
    scored.sort(reverse=True)
    _value, _level, _gate, _name, _entry_id, node, result_state = scored[0]
    return node, result_state


def _marginal_value(
    node: TalentNode,
    *,
    role: str,
    rotation_guide: dict,
    selected: set[int],
) -> float:
    value = 100.0
    rotation_names = _rotation_ability_names(rotation_guide)
    if node.name in rotation_names["core"]:
        value += 60.0
    if node.name in rotation_names["priority"]:
        value += 40.0
    if node.name in rotation_names["cooldown"]:
        value += 35.0
    if node.name in rotation_names["role"]:
        value += 35.0
    tags = {tag.casefold() for tag in node.tags}
    if role.endswith("_dps") and tags & {"damage", "melee", "ranged", "caster", "dot", "spender", "builder"}:
        value += 20.0
    if role == "tank" and tags & {"tank", "defensive", "mitigation"}:
        value += 20.0
    if role == "healer" and tags & {"heal", "healing"}:
        value += 20.0
    if role == "support" and tags & {"support", "utility", "aura", "buff"}:
        value += 20.0
    if any(required_id not in selected for required_id in node.required_ids):
        value -= 10.0
    value += max(0.0, 10.0 - effective_level(node) / 10.0)
    return value


def _rotation_ability_names(rotation_guide: dict) -> dict[str, set[str]]:
    if not rotation_guide:
        return {"core": set(), "priority": set(), "cooldown": set(), "role": set()}

    def names(*sections: str) -> set[str]:
        return {
            str(rule.get("ability_name"))
            for section in sections
            for rule in rotation_guide.get(section, []) or []
            if isinstance(rule, dict) and rule.get("ability_name")
        }

    return {
        "core": names("core_loop"),
        "priority": names("priority_rules"),
        "cooldown": names("cooldown_rules"),
        "role": names("defensive_rules", "healing_rules", "support_rules"),
    }


def _choice_reason(node: TalentNode, role: str, rotation_guide: dict) -> str:
    rotation_names = _rotation_ability_names(rotation_guide)
    if node.name in rotation_names["core"]:
        return "Take this early because it is part of the build's repeatable core loop."
    if node.name in rotation_names["priority"]:
        return "Take this early because it supports the build's main priority loop."
    if node.name in rotation_names["cooldown"]:
        return "Take this because it is one of the build's main cooldown tools."
    if node.name in rotation_names["role"]:
        return f"Take this because it supports the build's {role.replace('_', ' ')} role tools."
    if node.required_ids:
        return "Take this because it advances the selected talent tree path."
    return ""


def _is_paid_or_passive_target(repository: TalentRepository, node_id: int) -> bool:
    node = repository.get_node(node_id)
    if node is None:
        return False
    return node.paid or (node.ae_cost == 0 and node.te_cost == 0 and effective_level(node) > 0)
