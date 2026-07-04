from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .apl_profiles import APLProfile, APLRuleProfile
from .domain import BuildState, TalentNode
from .repository import TalentRepository

APL_SCHEMA_VERSION = "coa-apl-v1"
CATEGORY_ORDER = {
    "precombat": 0,
    "maintenance": 10,
    "cooldown": 20,
    "execute": 30,
    "aoe": 40,
    "spender": 50,
    "builder": 60,
    "filler": 70,
    "utility": 80,
}


class APLGenerationError(ValueError):
    pass


@dataclass(frozen=True)
class APLAction:
    action_key: str
    action_name: str
    node_id: int | None
    spell_id: int | None
    category: str
    condition: str
    priority: float
    confidence: str
    notes: tuple[str, ...]
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_key": self.action_key,
            "action_name": self.action_name,
            "node_id": self.node_id,
            "spell_id": self.spell_id,
            "category": self.category,
            "condition": self.condition,
            "priority": self.priority,
            "confidence": self.confidence,
            "notes": list(self.notes),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class APLDocument:
    schema_version: str
    source: str
    profile_id: str
    class_name: str
    spec_key: str
    role: str
    encounter: str
    actions: tuple[APLAction, ...]
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    provenance: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "profile_id": self.profile_id,
            "class_name": self.class_name,
            "spec_key": self.spec_key,
            "role": self.role,
            "encounter": self.encounter,
            "actions": [action.to_dict() for action in self.actions],
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "provenance": dict(self.provenance),
        }


def slugify_action(name: str) -> str:
    normalized = name.lower().replace("'", "")
    return re.sub(r"[^a-z0-9_]+", "_", normalized).strip("_")


def apl_to_simc_lines(document: APLDocument) -> list[str]:
    lines: list[str] = []
    for action in document.actions:
        condition = f",if={action.condition}" if action.condition else ""
        note = f"  # {action.notes[0]}" if action.notes else ""
        lines.append(f"actions+=/{action.action_key}{condition}{note}")
    return lines


def generate_apl(
    state: BuildState,
    repository: TalentRepository,
    profile: APLProfile,
    encounter: str,
    profile_warnings: list[str] | None = None,
) -> APLDocument:
    if encounter not in profile.supported_encounters:
        raise APLGenerationError(f"{profile.profile_id} does not support encounter {encounter}")
    branch = next((item for item in profile.branches if item.encounter == encounter), None)
    if branch is None:
        raise APLGenerationError(f"{profile.profile_id} has no branch for encounter {encounter}")

    nodes = [repository.get_node(node_id) for node_id in state.selected_ids]
    selected_nodes = [node for node in nodes if node is not None]
    selected_ranks = {selected.node_id: selected.rank for selected in state.selected_ranks}
    actions: list[APLAction] = []
    warnings: list[str] = list(profile_warnings or [])

    for rule in profile.rules:
        if rule.category not in branch.include_categories:
            continue
        for node in selected_nodes:
            rank = selected_ranks.get(node.entry_id, state.rank_for(node.entry_id))
            if _node_matches_rule(node, rank, rule):
                actions.append(_action_from_match(node, rule, profile))
                if _uses_inferred_condition(node, rule):
                    warning = "condition inferred from normalized tooltip tags"
                    if warning not in warnings:
                        warnings.append(warning)

    deduped = _dedupe_actions(actions)
    categories = {action.category for action in deduped}
    for category in branch.include_categories:
        if category not in categories:
            warnings.append(f"no action matched category:{category}")
    if selected_nodes and "filler" not in categories:
        warnings.append("selected build has active nodes but no filler action")

    return APLDocument(
        schema_version=APL_SCHEMA_VERSION,
        source="theorycraft",
        profile_id=profile.profile_id,
        class_name=state.class_name,
        spec_key=profile.spec_key,
        role=profile.role,
        encounter=encounter,
        actions=tuple(sorted(deduped, key=_action_sort_key)),
        assumptions=profile.assumptions,
        warnings=tuple(warnings),
        provenance={
            "build_state_schema": "M1.3 BuildState",
            "profile_schema": "coa-apl-profile-v1",
            "normalized_schema": "coa-normalized-v1",
        },
    )


def _node_matches_rule(node: TalentNode, selected_rank: int, rule: APLRuleProfile) -> bool:
    match = rule.match
    if match.get("active_only") and node.is_passive:
        return False
    if match.get("passive_only") and not node.is_passive:
        return False
    if "selected_rank_at_least" in match and selected_rank < int(match["selected_rank_at_least"]):
        return False
    if "tags_any" in match and not set(match["tags_any"]) & set(node.tags):
        return False
    if "tags_all" in match and not set(match["tags_all"]).issubset(set(node.tags)):
        return False
    if "schools_any" in match and not set(match["schools_any"]) & set(node.damage_schools):
        return False
    if "resources_any" in match and not set(match["resources_any"]) & set(node.resources):
        return False
    if "name_contains_any" in match:
        lowered = node.name.lower()
        if not any(str(item).lower() in lowered for item in match["name_contains_any"]):
            return False
    if "description_matches_any" in match:
        if not any(
            re.search(str(pattern), node.description_text, re.IGNORECASE)
            for pattern in match["description_matches_any"]
        ):
            return False
    if "entry_type_in" in match and node.entry_type not in set(match["entry_type_in"]):
        return False
    if "essence_kind_in" in match and node.essence_kind not in set(match["essence_kind_in"]):
        return False
    return True


def _action_from_match(node: TalentNode, rule: APLRuleProfile, profile: APLProfile) -> APLAction:
    action_key = slugify_action(node.name)
    condition = _render_condition(rule.condition_template, action_key, profile)
    evidence = [f"profile_rule:{rule.id}"]
    for tag in node.tags:
        if tag in rule.match.get("tags_any", []) or tag in rule.match.get("tags_all", []):
            evidence.insert(0, f"tag:{tag}")
    return APLAction(
        action_key=action_key,
        action_name=node.name,
        node_id=node.entry_id,
        spell_id=node.spell_id,
        category=rule.category,
        condition=condition,
        priority=rule.priority,
        confidence=rule.confidence,
        notes=(rule.note,) if rule.note else tuple(),
        evidence=tuple(evidence),
    )


def _render_condition(template_name: str, action_key: str, profile: APLProfile) -> str:
    if not template_name:
        return ""
    template = profile.condition_templates.get(template_name, "")
    primary_resource = profile.resources[0].aliases[0] if profile.resources and profile.resources[0].aliases else "resource"
    values = {
        "action_key": action_key,
        "primary_resource": primary_resource,
        "spender_threshold": profile.thresholds.get("spender", 80),
        "execute_health_pct": profile.thresholds.get("execute_health_pct", 35),
        "aoe_min_enemies": profile.thresholds.get("aoe_min_enemies", 3),
    }
    return template.format(**values)


def _uses_inferred_condition(node: TalentNode, rule: APLRuleProfile) -> bool:
    return bool(node.tags or rule.match.get("description_matches_any"))


def _dedupe_actions(actions: list[APLAction]) -> list[APLAction]:
    seen: set[tuple[str, str, str]] = set()
    output: list[APLAction] = []
    for action in sorted(actions, key=_action_sort_key):
        key = (action.action_key, action.condition, action.category)
        if key in seen:
            continue
        seen.add(key)
        output.append(action)
    return output


def _action_sort_key(action: APLAction) -> tuple[float, int, str]:
    return (action.priority, CATEGORY_ORDER.get(action.category, 999), action.action_name)
