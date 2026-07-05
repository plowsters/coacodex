from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CombatEvent:
    time_ms: int
    event_type: str
    spell_id: int | None = None
    source: str = "player"
    target: str = "target"
    amount: float = 0.0
    school: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_ms": self.time_ms,
            "event_type": self.event_type,
            "spell_id": self.spell_id,
            "source": self.source,
            "target": self.target,
            "amount": self.amount,
            "school": self.school,
            "details": self.details,
        }
