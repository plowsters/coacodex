# tests/test_publish_e0r.py
from coa_client_extract.contracts import decoded_reason_code, observation_state_code
import pytest
from pathlib import Path
from coa_client_extract.publish import (
    GenerationWriter, candidate_trust_sha256, validate_candidate_generation, ResolveError,
)
from tests._spell_fixtures import v2_policy
from tests._e0r2_fixtures import stage_candidate, validate_staged


# E0R.2 T2.2: a row must now satisfy its contracted SHAPE, so the minimal row carries real observation
# cells instead of an empty substrate — a row with no observations is not lossless. The projection's
# expansion is computed with the same `_expand_compact` the validator uses, so these cross-child tests
# stay about cross-child semantics rather than about the fixture.
#
# E0R.2 T2.3: "minimal" now means the FULL observation domain the fixture policy declares, not one cell.
# A row may leave every mechanics value null, but every declared field must have an envelope and every
# mechanics key must be present — so the fixture derives both from `policy.artifact_contract` rather than
# hard-coding a list that would silently fall behind the policy.
def _cell(sid):
    return {"state": "present", "decoded_reason": "decoded",
            "policy_ref": "/tables/Spell/fields/id", "raw_u32": sid}


def _domain_raw(sid):
    """One envelope per declared observation: numeric cells present/decoded, the string cell resolved,
    and the join UNRESOLVED (index_zero) — which is still an observation, not an absence."""
    policy = v2_policy()
    joins = set(policy.doc.get("joins", {}))
    unresolved, present = observation_state_code("unresolved"), observation_state_code("present")
    raw = {}
    # E0R.2 T6.2 (v4): the pointer and the join name come from the descriptors, the vocabulary is
    # interned. What each cell MEANS is unchanged — only what it repeats.
    for field in policy.artifact_contract["required_raw_observations"]:
        if field in joins:
            raw[field] = {"s": unresolved, "d": decoded_reason_code("index_zero")}
        elif policy.doc["tables"]["Spell"]["fields"][field]["kind"] == "string":
            raw[field] = {"s": unresolved, "d": decoded_reason_code("not_present"),
                          "raw_offset": 0, "resolved": None}
        else:
            raw[field] = {"s": present, "d": decoded_reason_code("decoded"), "raw_u32": sid}
    return raw


def _domain_mechanics():
    # Present-but-null: a null is a recorded observation, an absent key is loss.
    return {k: None for k in v2_policy().artifact_contract["required_mechanics_keys"]}


def _full(sid, **extra):
    # the COMPACT full-child dialect: carries `raw`, never `field_observations`
    return {"schema_version": "coa-client-spell-v4", "spell_id": sid, "coa_attribution": {"is_coa": True},
            "name": None, "mechanics": _domain_mechanics(), "raw": _domain_raw(sid), **extra}


def _proj(sid, **extra):
    # the RICH projection dialect: carries `field_observations`, never `raw`
    from coa_client_extract.spell_record import _expand_compact, build_field_descriptors
    policy = v2_policy()
    descriptors = build_field_descriptors(policy.doc)
    return {"schema_version": "coa-client-spell-projection-v3", "spell_id": sid,
            "coa_attribution": {"is_coa": True}, "name": None, "mechanics": _domain_mechanics(),
            "field_observations": {f: _expand_compact(cell, policy, field=f, descriptors=descriptors,
                                                      row_schema="coa-client-spell-v4")
                                   for f, cell in _domain_raw(sid).items()}, **extra}


def _icon_path(sid):
    return f"Interface/Icons/S{sid}.blp"


def _icon(sid, **extra):
    """A v2 ASSOCIATION row (E0R.2 T6.3): a reference plus the codes that explain a null one."""
    from coa_client_extract.spell_icons import icon_asset_id

    return {"schema_version": "coa-client-spell-icons-v2", "spell_id": sid, "spell_icon_id": sid,
            "asset_ref": icon_asset_id(_icon_path(sid)), "s": observation_state_code("resolved"),
            "d": decoded_reason_code("decoded"), "readiness": "available", **extra}


def _icon_asset(sid, **extra):
    from coa_client_extract.spell_icons import canonical_icon_path, icon_asset_id

    return {"schema_version": "coa-client-icon-assets-v1", "asset_id": icon_asset_id(_icon_path(sid)),
            "client_path": canonical_icon_path(_icon_path(sid)), "availability": "source_only",
            "source_asset_sha256": "a" * 64, "source_archive": "patch-T.MPQ", **extra}


def _stage(root: Path, *, full=None, proj=None, icons=None, icon_assets=None):
    """Stage ALL required children so per-child hashes match; inconsistencies are injected at stage-time
    via full/proj/icons (NEVER by mutating a file after its hash is registered). Icons default to one row
    per full spell so a projection-gap test is not masked by the icon-coverage check.

    E0R.2 T2.1: the shared fixture sizes the staged policy's reviewed `bound` to the rows staged here, so
    these cross-child cases still reach the merge-join instead of failing the cardinality gate first."""
    full = full if full is not None else [_full(1)]
    proj = proj if proj is not None else [_proj(1)]
    if icons is None:
        icons = [_icon(r["spell_id"]) for r in full]
    # The asset child is derived from the associations staged here, so the honest case is mutually
    # determined and a knob breaks exactly one relation (E0R.2 T6.3).
    if icon_assets is None:
        icon_assets = [_icon_asset(r["spell_id"]) for r in full]
    return stage_candidate(root, full=full, proj=proj, icons=icons, icon_assets=icon_assets,
                           policy_doc=v2_policy().doc)


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
    # T2.2 rejects the malformed envelope at the SHAPE gate, which runs first; the cross-child
    # expansion check remains behind it. Either is a correct rejection.
    with pytest.raises(ResolveError, match="compact_raw_expands_to_envelope|shape"):
        validate_staged(gen)


def test_cross_child_rejects_projection_carrying_raw(tmp_path):
    # a projection row in the OLD compact dialect (carries raw) must be rejected — no two v3 dialects.
    bad_proj = _proj(1)
    bad_proj["raw"] = {}
    gen = _stage(tmp_path, full=[_full(1)], proj=[bad_proj])
    # The disjoint v3 dialects are now a SHAPE fact (a projection row has no `raw` key at all), caught
    # before the cross-child dialect check.
    with pytest.raises(ResolveError, match="projection_is_rich|unknown key"):
        validate_staged(gen)


def test_cross_child_rejects_tampered_field_observation(tmp_path):
    # the projection's field_observations must EQUAL the expansion of the full child's raw. The tamper is
    # ADDITIVE to the full declared domain (T2.3), so this stays a cross-child equality test rather than
    # tripping the observation-domain gate on a hand-narrowed raw block.
    full = _full(1, name="Fireball")
    tampered = _proj(1, name="Fireball")
    tampered["field_observations"]["power_type"]["decoded"] = {"kind": "int32", "value": 99}
    gen = _stage(tmp_path, full=[full], proj=[tampered])
    with pytest.raises(ResolveError, match="compact_raw_expands_to_envelope"):
        validate_staged(gen)


def test_valid_candidate_passes_cross_child(tmp_path):
    gen = _stage(tmp_path)
    active = validate_staged(gen)
    assert "coa_client_spell.jsonl" in active["children"]


def test_a_dangling_asset_ref_is_rejected(tmp_path):
    """E0R.2 T6.3. This test used to be about `converted`, which T2.5 prohibited outright and T6.3's
    dialect no longer has a key for. The relational failure it is replaced by is the one normalizing
    actually introduces: a reference to an asset row that is not there."""
    gen = _stage(tmp_path, icons=[_icon(1, asset_ref="0" * 32)])
    with pytest.raises(ResolveError, match="dangling asset_ref"):
        validate_staged(gen)


def test_an_orphan_asset_row_is_rejected(tmp_path):
    """The other direction. Without it the two children are consistent one way only, and an asset table
    could accumulate rows nothing will ever reference."""
    gen = _stage(tmp_path, icon_assets=[_icon_asset(1), _icon_asset(2)])
    with pytest.raises(ResolveError, match="referenced by no spell"):
        validate_staged(gen)


def test_a_readiness_that_disagrees_with_its_asset_is_rejected(tmp_path):
    gen = _stage(tmp_path, icons=[_icon(1, readiness="unavailable")])
    with pytest.raises(ResolveError, match="readiness"):
        validate_staged(gen)


def test_a_reference_whose_reason_is_not_decoded_is_rejected(tmp_path):
    gen = _stage(tmp_path, icons=[_icon(1, d=decoded_reason_code("side_row_missing"))])
    with pytest.raises(ResolveError, match="only a decoded join yields a path"):
        validate_staged(gen)


def test_an_unsorted_asset_child_is_rejected(tmp_path):
    """Sorted-unique by asset_id is what makes identical inputs produce identical bytes."""
    gen = _stage(tmp_path, full=[_full(1), _full(2)], proj=[_proj(1), _proj(2)],
                 icon_assets=[_icon_asset(2), _icon_asset(1)])
    with pytest.raises(ResolveError, match="out of order"):
        validate_staged(gen)


def test_candidate_manifest_is_not_pointer_resolvable(tmp_path):
    from coa_client_extract.publish import resolve_active_generation
    gen = _stage(tmp_path)          # publish_candidate does NOT write the pointer
    with pytest.raises(ResolveError):
        resolve_active_generation(tmp_path)
