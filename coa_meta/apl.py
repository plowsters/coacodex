from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

APL_SCHEMA_VERSION = "coa-apl-v1"


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
