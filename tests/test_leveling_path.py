from __future__ import annotations

from coa_meta.leveling_path import (
    LEVELING_PATH_SCHEMA_VERSION,
    essence_awards_for_levels,
    essence_kind_for_level,
)


def test_level_10_through_60_alternates_ae_then_te():
    awards = essence_awards_for_levels(10, 60)

    assert LEVELING_PATH_SCHEMA_VERSION == "coa-leveling-path-v1"
    assert awards[0].level == 10
    assert awards[0].essence_kind == "ability"
    assert awards[1].level == 11
    assert awards[1].essence_kind == "talent"
    assert essence_kind_for_level(60) == "ability"
    assert sum(1 for award in awards if award.essence_kind == "ability") == 26
    assert sum(1 for award in awards if award.essence_kind == "talent") == 25
