from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from typing import Iterable

from .action_catalog import ActionCatalog, CatalogAction
from .apl import APLAction, APLDocument


@dataclass(frozen=True)
class RotationCandidateConfig:
    max_candidates: int = 48
    max_actions: int = 12
    threshold_variants: tuple[float, ...] = (0.75, 1.0, 1.25)
    include_opener_variants: bool = True
    include_cooldown_policy_variants: bool = True


@dataclass(frozen=True)
class RotationCandidate:
    candidate_id: str
    fingerprint: str
    mutation: str
    apl: APLDocument
    mutation_notes: tuple[str, ...] = tuple()
    warnings: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "fingerprint": self.fingerprint,
            "mutation": self.mutation,
            "apl": self.apl.to_dict(),
            "mutation_notes": list(self.mutation_notes),
            "warnings": list(self.warnings),
        }


_THRESHOLD_RE = re.compile(r"\b([a-z0-9_]+)>=(\d+(?:\.\d+)?)\b")
_REORDERABLE_CATEGORIES = {
    "builder",
    "spender",
    "filler",
    "maintenance",
    "execute",
    "aoe",
    "cooldown",
    "utility",
}
_ROLE_REQUIRED = {
    "healer": ({"healing"}, {"heal"}),
    "tank": ({"defensive"}, {"mitigation"}),
    "support": ({"support"}, {"support"}),
}


def generate_rotation_candidates(
    apl: APLDocument,
    action_catalog: ActionCatalog,
    *,
    role: str,
    config: RotationCandidateConfig | None = None,
) -> tuple[RotationCandidate, ...]:
    config = config or RotationCandidateConfig()
    base_actions, trim_warnings = _trim_actions(apl.actions, action_catalog, role, config.max_actions)
    if not _candidate_is_valid(base_actions, action_catalog, role, config):
        return tuple()

    base_apl = replace(apl, actions=base_actions)
    candidates: list[RotationCandidate] = []
    seen: set[str] = set()

    _append_candidate(
        candidates,
        seen,
        mutation="base",
        apl=base_apl,
        notes=("Generated APL unchanged.",),
        warnings=trim_warnings,
    )

    for variant_apl, notes in _threshold_variants(base_apl, config):
        if len(candidates) >= config.max_candidates:
            break
        if _candidate_is_valid(variant_apl.actions, action_catalog, role, config):
            _append_candidate(
                candidates,
                seen,
                mutation=notes[0],
                apl=variant_apl,
                notes=notes,
                warnings=trim_warnings,
            )

    for variant_apl, notes in _reorder_variants(base_apl, config):
        if len(candidates) >= config.max_candidates:
            break
        if _candidate_is_valid(variant_apl.actions, action_catalog, role, config):
            _append_candidate(
                candidates,
                seen,
                mutation=notes[0],
                apl=variant_apl,
                notes=notes,
                warnings=trim_warnings,
            )

    return tuple(candidates[: config.max_candidates])


def _threshold_variants(
    apl: APLDocument,
    config: RotationCandidateConfig,
) -> Iterable[tuple[APLDocument, tuple[str, ...]]]:
    for index, action in enumerate(apl.actions):
        match = _THRESHOLD_RE.search(action.condition)
        if not match:
            continue
        resource, raw_value = match.groups()
        base_value = float(raw_value)
        for multiplier in config.threshold_variants:
            new_value = _bounded_threshold(base_value * multiplier)
            if new_value == _format_threshold(base_value):
                continue
            condition = _THRESHOLD_RE.sub(f"{resource}>={new_value}", action.condition, count=1)
            actions = list(apl.actions)
            actions[index] = replace(action, condition=condition)
            yield (
                replace(apl, actions=tuple(actions)),
                (f"threshold:{action.action_key}:{resource}:{new_value}",),
            )


def _reorder_variants(
    apl: APLDocument,
    config: RotationCandidateConfig,
) -> Iterable[tuple[APLDocument, tuple[str, ...]]]:
    if not config.include_opener_variants:
        return

    actions = tuple(apl.actions)
    by_category: dict[str, list[int]] = {}
    for index, action in enumerate(actions):
        if action.category in _REORDERABLE_CATEGORIES:
            by_category.setdefault(action.category, []).append(index)

    for category in sorted(by_category):
        indices = by_category[category]
        if len(indices) < 2:
            continue
        group = [actions[index] for index in indices]
        yield (
            replace(apl, actions=_replace_group(actions, indices, tuple(reversed(group)))),
            (f"reorder_group:{category}", f"Reverse {category} priority order."),
        )
        if len(group) > 2:
            rotated = tuple((*group[1:], group[0]))
            yield (
                replace(apl, actions=_replace_group(actions, indices, rotated)),
                (f"reorder_group:{category}", f"Rotate {category} priority order."),
            )


def _replace_group(
    actions: tuple[APLAction, ...],
    indices: list[int],
    replacement_group: tuple[APLAction, ...],
) -> tuple[APLAction, ...]:
    updated = list(actions)
    priorities = [actions[index].priority for index in indices]
    for index, action, priority in zip(indices, replacement_group, priorities, strict=True):
        updated[index] = replace(action, priority=priority)
    return tuple(updated)


def _trim_actions(
    actions: tuple[APLAction, ...],
    action_catalog: ActionCatalog,
    role: str,
    max_actions: int,
) -> tuple[tuple[APLAction, ...], tuple[str, ...]]:
    if max_actions <= 0:
        return tuple(), ("rotation_candidate_max_actions_zero",)
    if len(actions) <= max_actions:
        return actions, tuple()

    mandatory_keys = _mandatory_action_keys(actions, action_catalog, role)
    ranked_indices = sorted(
        range(len(actions)),
        key=lambda index: (
            0 if actions[index].action_key in mandatory_keys else 1,
            actions[index].priority,
            actions[index].action_key,
        ),
    )
    selected_indices = set(ranked_indices[:max_actions])
    trimmed = tuple(action for index, action in enumerate(actions) if index in selected_indices)
    warnings = (f"rotation_candidate_trimmed_actions:{len(actions) - len(trimmed)}",)
    return trimmed, warnings


def _candidate_is_valid(
    actions: tuple[APLAction, ...],
    action_catalog: ActionCatalog,
    role: str,
    config: RotationCandidateConfig,
) -> bool:
    if not actions or len(actions) > config.max_actions:
        return False

    executable = [action for action in actions if action.action_key in action_catalog.actions_by_key]
    if not executable:
        return False

    executable_categories = {action.category for action in executable}
    if executable_categories and executable_categories <= {"cooldown"} and "filler" not in executable_categories:
        return False

    required_categories, required_classifications = _required_for_role(role)
    if required_categories or required_classifications:
        for action in executable:
            catalog_action = action_catalog.actions_by_key.get(action.action_key)
            if action.category in required_categories:
                return True
            if catalog_action and catalog_action.role_classification in required_classifications:
                return True
        return False

    return True


def _mandatory_action_keys(
    actions: tuple[APLAction, ...],
    action_catalog: ActionCatalog,
    role: str,
) -> set[str]:
    required_categories, required_classifications = _required_for_role(role)
    mandatory: set[str] = set()
    for action in actions:
        catalog_action = action_catalog.actions_by_key.get(action.action_key)
        if action.category in required_categories:
            mandatory.add(action.action_key)
        elif catalog_action and catalog_action.role_classification in required_classifications:
            mandatory.add(action.action_key)
    return mandatory


def _required_for_role(role: str) -> tuple[set[str], set[str]]:
    normalized = role.casefold()
    if normalized in _ROLE_REQUIRED:
        categories, classifications = _ROLE_REQUIRED[normalized]
        return set(categories), set(classifications)
    return set(), set()


def _append_candidate(
    candidates: list[RotationCandidate],
    seen: set[str],
    *,
    mutation: str,
    apl: APLDocument,
    notes: tuple[str, ...],
    warnings: tuple[str, ...],
) -> None:
    fingerprint = _fingerprint(apl.actions)
    if fingerprint in seen:
        return
    seen.add(fingerprint)
    candidates.append(
        RotationCandidate(
            candidate_id=f"{mutation}:{fingerprint[:12]}",
            fingerprint=fingerprint,
            mutation=mutation,
            apl=apl,
            mutation_notes=notes,
            warnings=warnings,
        )
    )


def _fingerprint(actions: tuple[APLAction, ...]) -> str:
    payload = [
        {
            "action_key": action.action_key,
            "category": action.category,
            "condition": action.condition,
            "priority": action.priority,
        }
        for action in actions
    ]
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(data.encode("utf-8")).hexdigest()


def _bounded_threshold(value: float) -> str:
    return _format_threshold(min(max(value, 0.0), 1000.0))


def _format_threshold(value: float) -> str:
    rounded = round(value, 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")
