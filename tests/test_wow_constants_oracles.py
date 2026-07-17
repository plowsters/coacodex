import struct

from coa_client_extract.wow_constants import load_authored_input, load_axis_policy, map_table_entries
from coa_client_extract.wdbc import parse_gametable
from coa_meta.wow_constants import WowConstantsRepository


def _implicit(values):
    return struct.pack("<4sIIII", b"WDBC", len(values), 1, 4, 0) + b"".join(
        struct.pack("<f", v) for v in values)


def test_rating_to_percent_reference_formula_at_60_and_80():
    doc = {"schema_version": "coa-wow-constants-v1", "client_build": "t",
           "class_axis": {"observed_client_ids": [8], "default_power_type_by_wow_class_id": {}},
           "enum_maps": {"rating_enum": {"supported": {"10": "crit_spell"}}, "power_type": {"map": {}}},
           "game_tables": {
               "combat_ratings": {"axes": ["rating_id", "level"], "class_indexed": False,
                   "entries": [{"rating_id": 10, "level": 60, "value": 14.0},
                               {"rating_id": 10, "level": 80, "value": 45.9}]},
               "class_combat_rating_scalar": {"axes": ["wow_class_id", "rating_id"], "class_indexed": True,
                   "entries": [{"wow_class_id": 8, "rating_id": 10, "value": 1.0}]}},
           "rules": {}}
    repo = WowConstantsRepository.from_dict(doc)
    scalar = repo.class_combat_rating_scalar(wow_class_id=8, rating_id=10)  # test-only division
    assert abs(scalar / repo.combat_rating_ratio(10, 60) - 1 / 14.0) < 1e-6
    assert abs(scalar / repo.combat_rating_ratio(10, 80) - 1 / 45.9) < 1e-6


def test_raw_divisor_nondecreasing_within_rating_id_with_plateaus():
    layouts, ls, rs = load_axis_policy(load_authored_input("gt_axis_policy").payload)
    values = [0.0] * 3200
    for level in range(1, 101):
        values[10 * 100 + (level - 1)] = float(level // 2)  # nondecreasing with plateaus
    table = parse_gametable(_implicit(values), physical_form="implicit_row",
                            expected_field_count=1, expected_record_size=4)
    entries, _ = map_table_entries(layouts["combat_ratings"], table, class_roster=[],
                                   level_stride=ls, rating_stride=rs)
    r10 = sorted((e["level"], e["value"]) for e in entries if e["rating_id"] == 10)
    assert all(b >= a for (_, a), (_, b) in zip(r10, r10[1:]))
