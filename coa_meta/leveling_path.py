from __future__ import annotations

from dataclasses import dataclass

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
