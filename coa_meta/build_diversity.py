from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Sequence

from .apl import APLDocument
from .domain import TalentNode


@dataclass(frozen=True)
class PlaystyleFingerprint:
    schema_version: str
    label: str
    primary_tags: tuple[str, ...]
    active_ability_names: tuple[str, ...]
    passive_ratio: float
    active_count: int
    cooldown_count: int
    dot_count: int
    summon_count: int
    heal_count: int
    defensive_count: int
    support_count: int
    melee_score: float
    ranged_score: float
    caster_score: float
    schools: dict[str, int]
    resources: dict[str, int]
    apl_categories: dict[str, int]
    selected_node_ids: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "label": self.label,
            "primary_tags": list(self.primary_tags),
            "active_ability_names": list(self.active_ability_names),
            "passive_ratio": self.passive_ratio,
            "active_count": self.active_count,
            "cooldown_count": self.cooldown_count,
            "dot_count": self.dot_count,
            "summon_count": self.summon_count,
            "heal_count": self.heal_count,
            "defensive_count": self.defensive_count,
            "support_count": self.support_count,
            "melee_score": self.melee_score,
            "ranged_score": self.ranged_score,
            "caster_score": self.caster_score,
            "schools": dict(self.schools),
            "resources": dict(self.resources),
            "apl_categories": dict(self.apl_categories),
            "selected_node_ids": list(self.selected_node_ids),
        }


def build_playstyle_fingerprint(
    *,
    nodes: Sequence[TalentNode],
    apl: APLDocument | None,
    role: str,
) -> PlaystyleFingerprint:
    tag_counts: Counter[str] = Counter()
    school_counts: Counter[str] = Counter()
    resource_counts: Counter[str] = Counter()
    apl_categories: Counter[str] = Counter()
    active_names: list[str] = []
    active_count = 0
    passive_count = 0

    for node in nodes:
        normalized_tags = {_normalize(value) for value in node.tags}
        text = _node_text(node)
        tag_counts.update(tag for tag in normalized_tags if tag)
        school_counts.update(_normalize(value) for value in node.damage_schools if value)
        resource_counts.update(_normalize(value) for value in node.resources if value)
        if node.is_passive:
            passive_count += 1
        else:
            active_count += 1
            active_names.append(node.name)
        _add_text_tags(tag_counts, text)

    if apl is not None:
        for action in apl.actions:
            apl_categories[_normalize(action.category)] += 1
            if action.node_id is not None and action.action_name not in active_names:
                active_names.append(action.action_name)

    total_nodes = max(1, len(nodes))
    primary_tags = tuple(tag for tag, _count in tag_counts.most_common(6))
    dot_count = tag_counts["dot"] + _count_names(active_names, ("poison", "venom"))
    summon_count = tag_counts["summon"] + tag_counts["pet"]
    heal_count = tag_counts["heal"] + tag_counts["healing"]
    defensive_count = tag_counts["tank"] + tag_counts["defensive"] + tag_counts["mitigation"]
    support_count = tag_counts["support"] + tag_counts["utility"] + tag_counts["aura"] + tag_counts["buff"]
    cooldown_count = tag_counts["cooldown"] + apl_categories["cooldown"]
    melee_score = float(tag_counts["melee"] + (1 if role == "melee_dps" else 0))
    ranged_score = float(tag_counts["ranged"] + (1 if "ranged" in role else 0))
    caster_score = float(tag_counts["caster"] + tag_counts["spell"] + (1 if role == "caster_dps" else 0))

    return PlaystyleFingerprint(
        schema_version="coa-build-playstyle-v1",
        label=_label_from_features(tag_counts, apl_categories, role),
        primary_tags=primary_tags,
        active_ability_names=tuple(active_names[:8]),
        passive_ratio=round(passive_count / total_nodes, 4),
        active_count=active_count,
        cooldown_count=cooldown_count,
        dot_count=dot_count,
        summon_count=summon_count,
        heal_count=heal_count,
        defensive_count=defensive_count,
        support_count=support_count,
        melee_score=melee_score,
        ranged_score=ranged_score,
        caster_score=caster_score,
        schools=dict(sorted(school_counts.items())),
        resources=dict(sorted(resource_counts.items())),
        apl_categories=dict(sorted(apl_categories.items())),
        selected_node_ids=tuple(sorted(node.entry_id for node in nodes)),
    )


def fingerprint_distance(left: PlaystyleFingerprint, right: PlaystyleFingerprint) -> float:
    active_distance = _jaccard_distance(set(left.active_ability_names), set(right.active_ability_names))
    tag_distance = _jaccard_distance(set(left.primary_tags), set(right.primary_tags))
    apl_distance = _jaccard_distance(set(left.apl_categories), set(right.apl_categories))
    school_resource_distance = (
        _jaccard_distance(set(left.schools), set(right.schools))
        + _jaccard_distance(set(left.resources), set(right.resources))
    ) / 2
    numeric_distance = _bounded_delta(left.passive_ratio, right.passive_ratio)
    numeric_distance += _bounded_delta(left.cooldown_count, right.cooldown_count)
    numeric_distance += _bounded_delta(left.dot_count, right.dot_count)
    numeric_distance += _bounded_delta(left.summon_count, right.summon_count)
    numeric_distance = min(1.0, numeric_distance / 4)
    role_distance = min(
        1.0,
        (
            _bounded_delta(left.melee_score, right.melee_score)
            + _bounded_delta(left.ranged_score, right.ranged_score)
            + _bounded_delta(left.caster_score, right.caster_score)
            + _bounded_delta(left.heal_count + left.defensive_count + left.support_count, right.heal_count + right.defensive_count + right.support_count)
        )
        / 4,
    )
    distance = (
        active_distance * 0.30
        + tag_distance * 0.25
        + apl_distance * 0.15
        + school_resource_distance * 0.10
        + numeric_distance * 0.10
        + role_distance * 0.10
    )
    return round(min(1.0, max(0.0, distance)), 4)


def reliability_score(
    *,
    nodes: Sequence[TalentNode],
    apl: APLDocument | None,
    role: str,
    warnings: Sequence[str],
) -> float:
    score = 1.0
    selected_active_ids = {node.entry_id for node in nodes if not node.is_passive}
    apl_actions = tuple(apl.actions) if apl else tuple()
    if not apl_actions or not any(action.node_id in selected_active_ids for action in apl_actions):
        score -= 0.20
    categories = {_normalize(action.category) for action in apl_actions}
    if _missing_role_core(categories, role):
        score -= 0.15
    if apl_actions:
        low_confidence = sum(1 for action in apl_actions if action.confidence == "low")
        if low_confidence > len(apl_actions) / 2:
            score -= 0.10
    tags = {_normalize(tag) for node in nodes for tag in node.tags}
    if ("spender" in tags or "builder" in tags) and not ({"spender", "builder"} & categories):
        score -= 0.10
    warning_text = " ".join(warnings).lower()
    if any(token in warning_text for token in ("missing role", "missing_level", "tooltip")):
        score -= 0.10
    return round(min(1.0, max(0.0, score)), 4)


def reliability_label(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.50:
        return "medium"
    return "low"


def _label_from_features(tags: Counter[str], categories: Counter[str], role: str) -> str:
    if tags["poison"] or tags["venom"] or tags["dot"] or categories["maintenance"]:
        return "poison DoT loop" if tags["poison"] or tags["venom"] else "DoT upkeep loop"
    if tags["summon"] or tags["pet"]:
        return "pet setup window"
    if tags["cooldown"] or categories["cooldown"]:
        return "burst cooldown cycle"
    if role == "tank" or tags["tank"] or tags["defensive"]:
        return "defensive sustain"
    if role == "healer" or tags["heal"] or tags["healing"]:
        return "healing cadence"
    if role == "support" or tags["support"] or tags["aura"] or tags["utility"]:
        return "support uptime"
    if tags["builder"] or tags["spender"] or categories["builder"] or categories["spender"]:
        return "builder-spender loop"
    if tags:
        return f"{tags.most_common(1)[0][0]} build"
    return "generalist build"


def _node_text(node: TalentNode) -> str:
    return " ".join((node.name, node.description_text)).casefold()


def _add_text_tags(counter: Counter[str], text: str) -> None:
    markers = {
        "poison": ("poison", "venom"),
        "dot": ("damage over time", "periodic"),
        "cooldown": ("cooldown",),
        "heal": ("heal", "healing"),
        "summon": ("summon", "pet"),
        "defensive": ("armor", "shield", "mitigation", "defensive"),
    }
    for tag, needles in markers.items():
        if any(needle in text for needle in needles):
            counter[tag] += 1


def _count_names(names: Sequence[str], needles: Sequence[str]) -> int:
    return sum(1 for name in names if any(needle in name.casefold() for needle in needles))


def _jaccard_distance(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    return 1.0 - (len(left & right) / len(left | right))


def _bounded_delta(left: float, right: float) -> float:
    return min(1.0, abs(float(left) - float(right)))


def _missing_role_core(categories: set[str], role: str) -> bool:
    if role == "tank":
        return not (categories & {"defensive", "cooldown", "utility", "filler"})
    if role == "healer":
        return not (categories & {"heal", "maintenance", "cooldown", "utility"})
    if role == "support":
        return not (categories & {"support", "utility", "maintenance", "cooldown"})
    return not (categories & {"builder", "spender", "filler", "maintenance", "cooldown"})


def _normalize(value: str) -> str:
    return value.strip().casefold().replace(" ", "_")
