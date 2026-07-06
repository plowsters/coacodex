from __future__ import annotations

from dataclasses import dataclass
from typing import Any

BACKEND_TRUST_SCHEMA_VERSION = "coa-backend-trust-v1"


@dataclass(frozen=True)
class TrustComponent:
    component_id: str
    score: float
    weight: float
    notes: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "score": round(self.score, 4),
            "weight": round(self.weight, 4),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class TrustResult:
    schema_version: str
    subject_id: str
    trust_label: str
    score: float
    components: tuple[TrustComponent, ...]
    watchlist_matches: tuple[str, ...] = tuple()
    warnings: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "subject_id": self.subject_id,
            "trust_label": self.trust_label,
            "score": round(self.score, 4),
            "components": [component.to_dict() for component in self.components],
            "watchlist_matches": list(self.watchlist_matches),
            "warnings": list(self.warnings),
        }


def trust_label_from_score(score: float) -> str:
    if score >= 0.80:
        return "high"
    if score >= 0.50:
        return "medium"
    return "low"
