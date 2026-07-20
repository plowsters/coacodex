# tests/test_contracts.py
import pytest
from coa_client_extract.contracts import (
    policy_ref, policy_ref_component, resolve_policy_ref,
    READINESS_STATUSES, READINESS_REASON_CODES, ICON_ASSET_STATUSES,
    TRUST_CRITICAL_MANIFEST_KEYS, CROSS_CHILD_CHECKS, BOUND_HEADER_FIELDS,
)


def test_policy_ref_and_component_resolve_to_table_fields():
    assert policy_ref("Spell", "power_type") == "/tables/Spell/fields/power_type"
    jspec = {"index_field": "casting_time_index", "side_table": "SpellCastTimes", "side_value_field": "base_ms"}
    assert policy_ref_component(jspec, "side_value") == "/tables/SpellCastTimes/fields/base_ms"
    assert policy_ref_component(jspec, "index") == "/tables/Spell/fields/casting_time_index"
    assert policy_ref_component(jspec, "side_id") == "/tables/SpellCastTimes/fields/id"
    with pytest.raises(ValueError):
        policy_ref_component(jspec, "bogus")


def test_resolve_policy_ref_walks_the_document():
    doc = {"tables": {"Spell": {"fields": {"power_type": {"cell": 41, "kind": "int32"}}}}}
    assert resolve_policy_ref(doc, "/tables/Spell/fields/power_type")["cell"] == 41


def test_enums_are_closed_frozensets():
    assert isinstance(READINESS_STATUSES, frozenset)
    assert {"available", "unavailable", "not_applicable", "ambiguous", "verified_empty"} == READINESS_STATUSES
    assert "pending_e1_operand" in READINESS_REASON_CODES
    assert ICON_ASSET_STATUSES == frozenset({"converted", "source_only", "missing", "placeholder"})


def test_trust_critical_excludes_validation_and_budget():
    assert "validation" not in TRUST_CRITICAL_MANIFEST_KEYS
    assert "budget" not in TRUST_CRITICAL_MANIFEST_KEYS
    assert {"children", "binding", "generation_id", "schema_version"} <= TRUST_CRITICAL_MANIFEST_KEYS


def test_named_cross_child_checks_and_header_fields():
    assert "projection_is_coa_subset" in CROSS_CHILD_CHECKS
    assert "compact_raw_expands_to_envelope" in CROSS_CHILD_CHECKS
    assert BOUND_HEADER_FIELDS == ("magic", "record_count", "field_count", "record_size", "string_block_size")
