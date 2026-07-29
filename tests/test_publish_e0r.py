# tests/test_publish_e0r.py
import pytest
from pathlib import Path
from coa_client_extract.publish import (
    GenerationWriter, candidate_trust_sha256, validate_candidate_generation, ResolveError,
)
from tests._spell_fixtures import v2_policy
from tests._e0r2_fixtures import stage_candidate, validate_staged


def _full(sid, **extra):
    # the COMPACT full-child dialect: carries `raw`, never `field_observations`
    return {"schema_version": "coa-client-spell-v3", "spell_id": sid, "coa_attribution": {"is_coa": True},
            "name": None, "mechanics": {}, "raw": {}, **extra}


def _proj(sid, **extra):
    # the RICH projection dialect: carries `field_observations`, never `raw`
    return {"schema_version": "coa-client-spell-projection-v3", "spell_id": sid,
            "coa_attribution": {"is_coa": True}, "name": None, "mechanics": {},
            "field_observations": {}, **extra}


def _stage(root: Path, *, full=None, proj=None, icons=None):
    """Stage ALL required children so per-child hashes match; inconsistencies are injected at stage-time
    via full/proj/icons (NEVER by mutating a file after its hash is registered). Icons default to one row
    per full spell so a projection-gap test is not masked by the icon-coverage check.

    E0R.2 T2.1: the shared fixture sizes the staged policy's reviewed `bound` to the rows staged here, so
    these cross-child cases still reach the merge-join instead of failing the cardinality gate first."""
    full = full if full is not None else [_full(1)]
    proj = proj if proj is not None else [_proj(1)]
    if icons is None:
        icons = [{"schema_version": "coa-client-spell-icons-v1", "spell_id": r["spell_id"],
                  "asset_status": "source_only",
                  "client_path": f"Interface/Icons/S{r['spell_id']}.blp"} for r in full]
    return stage_candidate(root, full=full, proj=proj, icons=icons, policy_doc=v2_policy().doc)


def test_trust_digest_ignores_only_validation_and_budget():
    base = {"schema_version": "coa-client-extract-manifest-v3", "generation_id": "g", "children": {},
            "binding": {}, "outputs": {}, "unknown_symbol_inventory": {}, "predecessor_generation_id": None}
    d1 = candidate_trust_sha256({**base, "publication_state": "candidate", "validation": {"ok": True}, "budget": {"a": 1}})
    d2 = candidate_trust_sha256({**base, "publication_state": "published", "validation": {"ok": False}, "budget": {"a": 2}})
    assert d1 == d2                                            # only publication_state/validation/budget move
    assert candidate_trust_sha256({**base, "binding": {"x": 1}}) != d1
    assert candidate_trust_sha256({**base, "a_new_field": 1}) != d1   # a NEW top-level field is not ignored


def test_cross_child_rejects_is_coa_row_absent_from_projection(tmp_path):
    gen = _stage(tmp_path, full=[_full(1), _full(2)],
                 proj=[_proj(1)])   # spell 2 is_coa but not projected
    with pytest.raises(ResolveError, match="projection_is_coa_subset"):
        validate_staged(gen)


def test_cross_child_rejects_identity_mismatch(tmp_path):
    gen = _stage(tmp_path, full=[_full(1, name="Fireball")],
                 proj=[_proj(1, name="Frostbolt")])  # same id, different name
    with pytest.raises(ResolveError, match="identity_agrees"):
        validate_staged(gen)


def test_cross_child_rejects_compact_raw_without_raw(tmp_path):
    bad = _full(1, name="Fireball",
                raw={"power_type": {"state": "present", "policy_ref": "/tables/Spell/fields/power_type"}})  # no raw_u32/decoded_reason
    gen = _stage(tmp_path, full=[bad], proj=[_proj(1, name="Fireball")])
    with pytest.raises(ResolveError, match="compact_raw_expands_to_envelope"):
        validate_staged(gen)


def test_cross_child_rejects_projection_carrying_raw(tmp_path):
    # a projection row in the OLD compact dialect (carries raw) must be rejected — no two v3 dialects.
    bad_proj = _proj(1)
    bad_proj["raw"] = {}
    gen = _stage(tmp_path, full=[_full(1)], proj=[bad_proj])
    with pytest.raises(ResolveError, match="projection_is_rich"):
        validate_staged(gen)


def test_cross_child_rejects_tampered_field_observation(tmp_path):
    # the projection's field_observations must EQUAL the expansion of the full child's raw.
    full = _full(1, name="Fireball",
                 raw={"power_type": {"state": "present", "decoded_reason": "decoded",
                                     "policy_ref": "/tables/Spell/fields/power_type", "raw_u32": 3}})
    tampered = _proj(1, name="Fireball",
                     field_observations={"power_type": {"state": "present", "decoded_reason": "decoded",
                                                        "policy_ref": "/tables/Spell/fields/power_type",
                                                        "raw_u32": 3, "decoded": {"kind": "int32", "value": 99},
                                                        "proof": {"integrity": "verified", "layout": "verified",
                                                                  "interpretation": "verified"},
                                                        "promotion": "normalized"}})
    gen = _stage(tmp_path, full=[full], proj=[tampered])
    with pytest.raises(ResolveError, match="compact_raw_expands_to_envelope"):
        validate_staged(gen)


def test_valid_candidate_passes_cross_child(tmp_path):
    gen = _stage(tmp_path)
    active = validate_staged(gen)
    assert "coa_client_spell.jsonl" in active["children"]


def test_icon_bundle_required_when_any_converted(tmp_path):
    gen = _stage(tmp_path, icons=[{"schema_version": "coa-client-spell-icons-v1", "spell_id": 1,
                                  "asset_status": "converted", "converted_ref": "icons.tar#a.png",
                                  "client_path": "Interface/Icons/S1.blp"}])
    with pytest.raises(ResolveError, match="icon bundle required"):
        validate_staged(gen)


def test_candidate_manifest_is_not_pointer_resolvable(tmp_path):
    from coa_client_extract.publish import resolve_active_generation
    gen = _stage(tmp_path)          # publish_candidate does NOT write the pointer
    with pytest.raises(ResolveError):
        resolve_active_generation(tmp_path)
