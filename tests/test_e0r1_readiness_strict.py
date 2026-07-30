# tests/test_e0r1_readiness_strict.py
"""E0R.1 T5.2 — the readiness state machine is a COMPLETE truth table, enforced at load:

  * `available` requires a present, non-null value (a null cannot be "available").
  * `verified_empty` is set-valued ONLY and requires an actually-EMPTY collection — a non-empty map
    claiming `verified_empty` is a contradiction, not a nuance.
  * `not_applicable` / `unavailable` / `ambiguous` require a null value.
  * every reason_code must be COMPATIBLE with its status (`proven_empty` ⇒ `verified_empty`;
    `not_extracted` ⇏ `verified_empty`; `proven_empty` ⇏ `unavailable`; `index_zero` ⇒
    `not_applicable`; `join_ambiguous` ⇒ `ambiguous`).
  * a required load-bearing field (costs / cooldown_ms / gcd_ms) whose value is null cannot SILENTLY
    omit readiness — the omission is exactly the ambiguity readiness exists to remove.
"""
import pytest

from coa_client_extract.contracts import (
    READINESS_INVARIANTS, READINESS_REASON_CODES, READINESS_REASON_COMPATIBILITY, READINESS_STATUSES,
)
from coa_meta.mechanics import MechanicsLoadError, mechanic_from_raw

LOAD_BEARING = ("costs", "cooldown_ms", "gcd_ms")


def _rec(**over):
    # A record whose load-bearing fields are all explained, so each test varies ONE thing.
    base = {"schema_version": "coa-mechanics-v2", "spell_id": 5, "name": "X", "kind": "ability",
            "field_readiness": {f: {"status": "unavailable", "reason_code": "pending_e1_operand"}
                                for f in LOAD_BEARING}}
    base.update(over)
    return base


def _readiness(field, status, reason, **values):
    fr = dict(_rec()["field_readiness"])
    fr[field] = {"status": status, "reason_code": reason}
    return _rec(field_readiness=fr, **values)


# --- the compatibility map itself is total and closed -------------------------------------------

def test_every_reason_code_declares_its_compatible_statuses():
    assert set(READINESS_REASON_COMPATIBILITY) == set(READINESS_REASON_CODES)
    for reason, statuses in READINESS_REASON_COMPATIBILITY.items():
        assert statuses, f"{reason} must be compatible with at least one status"
        assert statuses <= READINESS_STATUSES, f"{reason} names a status outside the closed enum"


def test_every_status_is_reachable_by_some_reason_code():
    reachable = set().union(*READINESS_REASON_COMPATIBILITY.values())
    assert reachable == set(READINESS_STATUSES), f"unreachable statuses: {set(READINESS_STATUSES) - reachable}"


# --- status x value ------------------------------------------------------------------------------

def test_available_requires_a_present_non_null_value():
    with pytest.raises(MechanicsLoadError, match="readiness invariant"):
        mechanic_from_raw(_readiness("cooldown_ms", "available", "extracted", cooldown_ms=None))
    ok = mechanic_from_raw(_readiness("cooldown_ms", "available", "extracted", cooldown_ms=0))
    assert ok.cooldown_ms == 0                       # a verified 0 is available, not "missing"


def test_verified_empty_requires_an_actually_empty_collection():
    ok = mechanic_from_raw(_readiness("costs", "verified_empty", "proven_empty", costs={}))
    assert ok.costs == {}
    with pytest.raises(MechanicsLoadError, match="readiness invariant"):
        mechanic_from_raw(_readiness("costs", "verified_empty", "proven_empty", costs={"mana": 30}))
    with pytest.raises(MechanicsLoadError, match="readiness invariant"):
        mechanic_from_raw(_readiness("costs", "verified_empty", "proven_empty", costs=None))


def test_verified_empty_is_set_valued_only():
    # a scalar field can never be verified_empty — emptiness is a property of collections
    with pytest.raises(MechanicsLoadError, match="readiness invariant"):
        mechanic_from_raw(_readiness("cooldown_ms", "verified_empty", "proven_empty", cooldown_ms=0))


@pytest.mark.parametrize("status,reason", [("not_applicable", "index_zero"),
                                           ("unavailable", "not_extracted"),
                                           ("ambiguous", "join_ambiguous")])
def test_null_required_statuses_reject_a_present_value(status, reason):
    with pytest.raises(MechanicsLoadError, match="readiness invariant"):
        mechanic_from_raw(_readiness("cooldown_ms", status, reason, cooldown_ms=1500))
    assert mechanic_from_raw(_readiness("cooldown_ms", status, reason, cooldown_ms=None)).cooldown_ms is None


# --- status x reason_code -------------------------------------------------------------------------

def test_proven_empty_implies_verified_empty():
    with pytest.raises(MechanicsLoadError, match="incompatible"):
        mechanic_from_raw(_readiness("costs", "unavailable", "proven_empty", costs=None))


def test_not_extracted_cannot_claim_verified_empty():
    with pytest.raises(MechanicsLoadError, match="incompatible"):
        mechanic_from_raw(_readiness("costs", "verified_empty", "not_extracted", costs={}))


def test_index_zero_implies_not_applicable_and_join_ambiguous_implies_ambiguous():
    with pytest.raises(MechanicsLoadError, match="incompatible"):
        mechanic_from_raw(_readiness("cooldown_ms", "unavailable", "index_zero", cooldown_ms=None))
    with pytest.raises(MechanicsLoadError, match="incompatible"):
        mechanic_from_raw(_readiness("cooldown_ms", "not_applicable", "join_ambiguous", cooldown_ms=None))


def test_every_declared_compatible_pair_actually_loads():
    # The map is not decoration: each declared pair must pass the loader on a value-compatible record.
    for reason, statuses in READINESS_REASON_COMPATIBILITY.items():
        for status in statuses:
            must_be_null, _blocking, set_valued_only = READINESS_INVARIANTS[status]
            if set_valued_only:
                record = _readiness("costs", status, reason, costs={})
            elif must_be_null:
                record = _readiness("costs", status, reason, costs=None)
            else:
                record = _readiness("costs", status, reason, costs={"mana": 30})
            mechanic_from_raw(record)                # must not raise


# --- omission ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("field", LOAD_BEARING)
def test_a_null_load_bearing_field_cannot_silently_omit_readiness(field):
    fr = {f: v for f, v in _rec()["field_readiness"].items() if f != field}
    with pytest.raises(MechanicsLoadError, match="requires a readiness"):
        mechanic_from_raw(_rec(field_readiness=fr, **{field: None}))


def test_a_populated_load_bearing_field_may_omit_readiness():
    # A present value is self-evidently available; only the null case is ambiguous.
    record = _rec(field_readiness={}, costs={"mana": 30}, cooldown_ms=1500, gcd_ms=1500)
    loaded = mechanic_from_raw(record)
    assert loaded.costs == {"mana": 30} and loaded.cooldown_ms == 1500
