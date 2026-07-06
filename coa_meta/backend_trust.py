from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_TRUST_SCHEMA_VERSION = "coa-backend-trust-v1"
WATCHLIST_PATH = Path(__file__).parent / "data" / "live_sanity_watchlist.json"


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


@dataclass(frozen=True)
class LiveSanityWatchlistEntry:
    watchlist_id: str
    class_name: str
    source_spec_name: str
    guide_role: str
    concern: str
    direction: str
    severity: str
    evidence_type: str
    evidence: tuple[str, ...]
    confidence: str
    source: str
    status: str
    not_user_facing: bool
    expires_after: str


def load_live_sanity_watchlist(path: Path | str = WATCHLIST_PATH) -> tuple[LiveSanityWatchlistEntry, ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(
        LiveSanityWatchlistEntry(
            watchlist_id=str(item["watchlist_id"]),
            class_name=str(item["class_name"]),
            source_spec_name=str(item["source_spec_name"]),
            guide_role=str(item["guide_role"]),
            concern=str(item["concern"]),
            direction=str(item["direction"]),
            severity=str(item["severity"]),
            evidence_type=str(item["evidence_type"]),
            evidence=tuple(str(value) for value in item.get("evidence", [])),
            confidence=str(item["confidence"]),
            source=str(item["source"]),
            status=str(item["status"]),
            not_user_facing=bool(item["not_user_facing"]),
            expires_after=str(item["expires_after"]),
        )
        for item in raw
    )


def match_watchlist(
    entries: tuple[LiveSanityWatchlistEntry, ...],
    *,
    class_name: str,
    source_spec_name: str,
    guide_role: str,
) -> tuple[LiveSanityWatchlistEntry, ...]:
    return tuple(
        entry
        for entry in entries
        if _matches(entry.class_name, class_name)
        and _matches(entry.source_spec_name, source_spec_name)
        and _matches_role(entry.guide_role, guide_role)
    )


def _matches(pattern: str, value: str) -> bool:
    return pattern == "*" or pattern.casefold() == value.casefold()


def _matches_role(pattern: str, value: str) -> bool:
    if pattern == "*":
        return True
    if pattern == "*_dps":
        return value.endswith("_dps")
    return pattern == value
