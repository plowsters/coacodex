# tests/test_mechanics_v2.py
import pytest
from coa_meta.mechanics import mechanic_from_raw, MechanicsLoadError, MECHANICS_SCHEMA_VERSION


def _rec(**over):
    # E0R.1 T5.2: every null load-bearing field carries an explicit readiness entry; each test then
    # varies exactly one field/readiness pair.
    base = {"schema_version": "coa-mechanics-v2", "spell_id": 5, "name": "X", "kind": "ability",
            "field_readiness": {f: {"status": "unavailable", "reason_code": "pending_e1_operand"}
                                for f in ("costs", "cooldown_ms", "gcd_ms")}}
    fr = dict(base["field_readiness"])
    fr.update(over.pop("field_readiness", {}))
    base.update(over)
    base["field_readiness"] = fr
    return base


def test_schema_version_is_v2():
    assert MECHANICS_SCHEMA_VERSION == "coa-mechanics-v2"


def test_unknown_costs_is_none_not_empty_dict():
    r = mechanic_from_raw(_rec(costs=None, field_readiness={"costs": {"status": "unavailable",
                          "reason_code": "pending_e1_operand"}}))
    assert r.costs is None                                     # unknown != free {}
    assert r.field_readiness["costs"]["status"] == "unavailable"
    # missing != default: costs serializes as an explicit null, never dropped
    assert "costs" in r.to_dict() and r.to_dict()["costs"] is None


def test_verified_empty_costs_survives():
    r = mechanic_from_raw(_rec(costs={}, field_readiness={"costs": {"status": "verified_empty",
                          "reason_code": "proven_empty"}}))
    assert r.costs == {} and r.field_readiness["costs"]["status"] == "verified_empty"


def test_contradictory_readiness_is_rejected():
    # verified_empty must carry an EMPTY set-valued value; costs=None contradicts it.
    with pytest.raises(MechanicsLoadError, match="readiness invariant"):
        mechanic_from_raw(_rec(costs=None, field_readiness={"costs": {"status": "verified_empty",
                          "reason_code": "proven_empty"}}))


def test_bad_status_or_reason_code_is_rejected():
    with pytest.raises(MechanicsLoadError, match="status"):
        mechanic_from_raw(_rec(field_readiness={"costs": {"status": "made_up", "reason_code": "not_extracted"}}))
    with pytest.raises(MechanicsLoadError, match="reason_code"):
        mechanic_from_raw(_rec(field_readiness={"costs": {"status": "unavailable", "reason_code": "made_up"}}))


def test_field_readiness_is_required_only_for_null_load_bearing_fields():
    # E0R.1 T5.2: a record may omit field_readiness entirely ONLY when no load-bearing field is null;
    # a null costs/cooldown_ms/gcd_ms must explain itself.
    r = mechanic_from_raw({"schema_version": "coa-mechanics-v2", "spell_id": 5, "name": "X",
                           "kind": "ability", "costs": {"mana": 30}, "cooldown_ms": 0, "gcd_ms": 1500})
    assert r.field_readiness == {} and r.costs == {"mana": 30}
    with pytest.raises(MechanicsLoadError, match="requires a readiness"):
        mechanic_from_raw({"schema_version": "coa-mechanics-v2", "spell_id": 5, "name": "X",
                           "kind": "ability"})


def test_v1_is_rejected():
    with pytest.raises(MechanicsLoadError, match="coa-mechanics-v2"):
        mechanic_from_raw({"schema_version": "coa-mechanics-v1", "spell_id": 1, "name": "n", "kind": "k"})
