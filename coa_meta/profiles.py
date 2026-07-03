from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROFILE_SCHEMA_VERSION = "coa-scoring-profile-v1"
SUPPORTED_ENCOUNTERS = {"single_target", "cleave_2", "aoe_5", "solo"}
PROFILE_DIR = Path(__file__).parent / "data" / "scoring_profiles"


class ProfileLoadError(ValueError):
    pass


@dataclass(frozen=True)
class ScoringProfile:
    profile_id: str
    class_name: str
    spec_key: str
    role: str
    encounter: str
    baseline_index: float
    weights: dict[str, dict[str, float]]
    named_boosts: dict[str, float]
    regex_boosts: tuple[dict[str, Any], ...]
    synergies: tuple[dict[str, Any], ...]
    anti_synergies: tuple[dict[str, Any], ...]
    confidence: dict[str, Any]
    assumptions: tuple[str, ...]


def _load_profile_json(profile_id: str) -> dict[str, Any]:
    path = PROFILE_DIR / f"{profile_id}.json"
    if not path.exists():
        raise ProfileLoadError(f"Unknown profile {profile_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ProfileLoadError(f"{profile_id} has invalid schema_version")
    return data


def load_builtin_profile(profile_id: str, encounter: str) -> ScoringProfile:
    if encounter not in SUPPORTED_ENCOUNTERS:
        raise ProfileLoadError(f"Unsupported encounter {encounter}")
    data = _load_profile_json(profile_id)
    if encounter not in data.get("supported_encounters", []):
        raise ProfileLoadError(f"{profile_id} does not support encounter {encounter}")
    merged = copy.deepcopy(data)
    overrides = merged.get("encounter_overrides", {}).get(encounter, {})
    if overrides:
        for group in ["tabs", "tags", "schools", "resources"]:
            merged.setdefault("weights", {}).setdefault(group, {}).update(overrides.get(group, {}))
        merged.setdefault("named_boosts", {}).update(overrides.get("named_boosts", {}))
    return ScoringProfile(
        profile_id=merged["profile_id"],
        class_name=merged["class_name"],
        spec_key=merged["spec_key"],
        role=merged["role"],
        encounter=encounter,
        baseline_index=float(merged.get("baseline_index", 100.0)),
        weights=merged.get("weights", {}),
        named_boosts={key: float(value) for key, value in merged.get("named_boosts", {}).items()},
        regex_boosts=tuple(merged.get("regex_boosts", [])),
        synergies=tuple(merged.get("synergies", [])),
        anti_synergies=tuple(merged.get("anti_synergies", [])),
        confidence=merged.get("confidence", {"base": "medium"}),
        assumptions=tuple(merged.get("assumptions", [])),
    )


def load_profile_by_role(class_name: str, spec_key: str, role: str, encounter: str) -> tuple[ScoringProfile, list[str]]:
    specific_id = f"{class_name.lower().replace(' ', '_')}_{spec_key}"
    warnings: list[str] = []
    try:
        return load_builtin_profile(specific_id, encounter), warnings
    except ProfileLoadError:
        warnings.append("specific_profile_missing")

    generic_id = {
        "dps": "generic_dps",
        "tank": "generic_tank",
        "healer_support": "generic_healer_support",
    }.get(role)
    if not generic_id:
        raise ProfileLoadError(f"Unsupported role {role}")
    return load_builtin_profile(generic_id, encounter), warnings
