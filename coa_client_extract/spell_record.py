from __future__ import annotations

import struct

from .archive_plan import family_of
from .contracts import policy_ref, policy_ref_component, resolve_policy_ref
from .recordview import DbcView
from .spell_layout import FieldPolicy, SpellPolicy
from .spell_proof import (
    FieldProof, absent_envelope, compose_proof, make_domain_gated_envelope, make_envelope, make_join,
    make_string_observation, refine_enum, refine_mask, semantic_promotion_eligible,
)

SCHEMA = "coa-client-spell-v2"
SCHEMA_V3 = "coa-client-spell-v3"
_CUSTOM_ID_FLOOR = 100_000


def _proof(fp: FieldPolicy) -> FieldProof:
    # integrity is a runtime property: the view opened cleanly (open_view/require_dense already
    # enforced structural integrity), so integrity is verified; layout+interpretation come from
    # the human-authored, hash-bound policy.
    return FieldProof("verified", fp.layout, fp.interpretation)


def _decode_scalar(raw: int, kind: str):
    if kind == "int32":
        return struct.unpack("<i", struct.pack("<I", raw))[0]
    if kind == "float":
        return struct.unpack("<f", struct.pack("<I", raw))[0]
    return raw  # uint32


def _bits(mask: int):
    return [1 << b for b in range(32) if (mask >> b) & 1]


def _emit_gated(rec, fp: FieldPolicy, key, obs, refine, sink):
    """Emit a per-value domain-gated scalar enum (power_type). Returns the normalized value (or None)
    and records the observation in `obs`. An out-of-domain value keeps its raw, withholds normalized,
    and appends the unknown symbol to `sink` for the extract-level inventory."""
    if fp.cell is None:
        obs[key] = absent_envelope(proof=_proof(fp), evidence_ref=fp.evidence, state="unresolved").to_dict()
        return None
    raw = rec.u32(fp.cell)
    env = make_domain_gated_envelope(raw, kind=fp.kind, proof=_proof(fp), evidence_ref=fp.evidence, refine=refine)
    obs[key] = env.to_dict()
    if env.decoded is not None:
        return env.decoded["value"]
    if env.decoded_reason == "value_out_of_domain":
        sink.append(_decode_scalar(raw, fp.kind))
    return None


def _emit_join(rec, jname, join, spell_fields, policy, side_views, side_id_maps):
    idx_fp: FieldPolicy = spell_fields[join.index_field]
    if idx_fp.cell is None:
        # Un-adjudicated join: the index column is unproven, so there is nothing to resolve. Emit an
        # honest unresolved marker (raw retained is impossible — no cell), normalized stays null.
        env = absent_envelope(proof=_proof(idx_fp), state="unresolved",
                              evidence_ref=f"join {jname}: {idx_fp.evidence}")
        return None, env.to_dict()

    side_fields = policy.tables[join.side_table]["fields"]
    id_fp: FieldPolicy = side_fields["id"]
    val_fp: FieldPolicy = side_fields[join.side_value_field]
    fk = rec.u32(idx_fp.cell)
    idx_env = make_envelope(fk, kind=idx_fp.kind, proof=_proof(idx_fp), evidence_ref=idx_fp.evidence)

    if fk == 0:
        jo = make_join({"index": idx_env}, resolution="index_zero", decode=lambda c: None)
        return None, jo.to_dict()
    side_rec = side_id_maps.get(join.side_table, {}).get(fk)
    if side_rec is None:
        jo = make_join({"index": idx_env}, resolution="side_row_missing", decode=lambda c: None)
        return None, jo.to_dict()

    side_id_env = make_envelope(side_rec.u32(id_fp.cell), kind=id_fp.kind,
                                proof=_proof(id_fp), evidence_ref=id_fp.evidence)
    val_env = make_envelope(side_rec.u32(val_fp.cell), kind=val_fp.kind,
                            proof=_proof(val_fp), evidence_ref=val_fp.evidence)
    components = {"index": idx_env, "side_id": side_id_env, "side_value": val_env}
    jo = make_join(components, resolution="resolved",
                   decode=lambda c: c["side_value"].decoded["value"] if c["side_value"].decoded else None)
    return jo.decoded, jo.to_dict()


def build_spell_v2_records(spell_view: DbcView, side_views: dict, *, policy: SpellPolicy,
                           provenance: dict) -> tuple[list[dict], dict]:
    """Build coa-client-spell-v2 records straight from RecordView cells under a hash-bound policy.

    Every DBC-derived value carries a `field_observations` entry (Envelope / StringObservation /
    JoinObservation) with raw + proof; the normalized `mechanics`/`name` values are copied FROM those
    observations so a populated normalized value always has a matching eligible observation. power_type
    and school_mask are per-value domain-gated; an unseen enum/bit withholds the normalized value
    (raw retained) and is tallied in the returned unknown_symbol_inventory."""
    sf = policy.tables["Spell"]["fields"]
    allowed_pt = policy.enum_policy["power_types"]
    allowed_bits = policy.enum_policy["school_bits"]
    inv_pt: list[int] = []
    inv_bits: list[int] = []

    effective = provenance.get("effective_archive", "")
    archive_family = family_of(effective) if effective else "unknown"

    side_id_maps: dict[str, dict] = {}
    for name, view in side_views.items():
        if view is None:
            continue
        m: dict[int, object] = {}
        for r in view.records():
            m.setdefault(r.u32(0), r)
        side_id_maps[name] = m

    records: list[dict] = []
    for rec in spell_view.records():
        obs: dict = {}
        mech: dict = {}
        id_fp = sf["id"]
        spell_id = rec.u32(id_fp.cell)
        obs["spell_id"] = make_envelope(spell_id, kind=id_fp.kind, proof=_proof(id_fp),
                                        evidence_ref=id_fp.evidence).to_dict()

        name_fp = sf["name"]
        name_val = None
        if name_fp.cell is not None:
            off = rec.u32(name_fp.cell)
            resolved = spell_view.read_string(off)   # strict: name is a proven string field
            sob = make_string_observation(off, resolved, proof=_proof(name_fp), evidence_ref=name_fp.evidence)
            obs["name"] = sob.to_dict()
            name_val = sob.resolved

        mech["power_type"] = _emit_gated(rec, sf["power_type"], "power_type", obs,
                                         lambda v: refine_enum(v, allowed_pt), inv_pt)
        mech["school_mask"] = _emit_school(rec, sf["school_mask"], obs, allowed_bits, inv_bits)

        desc_fp = sf.get("description")
        if desc_fp is not None and desc_fp.cell is not None:
            off = rec.u32(desc_fp.cell)
            resolved = spell_view.read_string(off)
            obs["description"] = make_string_observation(
                off, resolved, proof=_proof(desc_fp), evidence_ref=desc_fp.evidence).to_dict()

        for jname, join in policy.joins.items():
            mech[jname], obs[jname] = _emit_join(rec, jname, join, sf, policy, side_views, side_id_maps)

        records.append({
            "schema_version": SCHEMA,
            "spell_id": spell_id,
            "name": name_val,
            "mechanics": mech,
            "field_observations": obs,
            "provenance": {**provenance, "policy_sha256": policy.sha256},
            "coa_attribution": {
                "status": "unknown",
                "archive_family": archive_family,
                "id_range": "high" if spell_id >= _CUSTOM_ID_FLOOR else "base",
            },
        })

    inventory = {"power_type": sorted(set(inv_pt)), "school_bits": sorted(set(inv_bits))}
    return records, inventory


def _emit_school(rec, fp: FieldPolicy, obs, allowed_bits, sink):
    if fp.cell is None:
        obs["school_mask"] = absent_envelope(proof=_proof(fp), evidence_ref=fp.evidence,
                                             state="unresolved").to_dict()
        return None
    raw = rec.u32(fp.cell)
    env = make_domain_gated_envelope(raw, kind=fp.kind, proof=_proof(fp), evidence_ref=fp.evidence,
                                     refine=lambda v: refine_mask(v, allowed_bits))
    obs["school_mask"] = env.to_dict()
    if env.decoded is not None:
        return env.decoded["value"]
    if env.decoded_reason == "value_out_of_domain":
        sink.extend(b for b in _bits(raw) if b not in allowed_bits)
    return None


# --- E0R streaming compact-raw v3 producer ---------------------------------------------------------
#
# iter_spell_records STREAMS coa-client-spell-v3 rows: identity + normalized `mechanics` + a compact
# `raw` block (enough to reconstruct eligibility, plus a policy_ref, but NO per-row evidence text — Node
# re-derives proof/promotion from the pinned policy via policy_ref). A normalized value is emitted only
# when its full promotion predicate holds; the compact raw is retained regardless.


def _join_spec(join) -> dict:
    return {"index_field": join.index_field, "side_table": join.side_table,
            "side_value_field": join.side_value_field}


def _compact(obs_dict: dict, *, policy_ref_str: str) -> dict:
    """A compact raw cell: retain enough raw to reconstruct eligibility + a policy_ref, and DROP the
    per-row proof/evidence text. A string observation keeps raw_offset + resolved (a string cannot be
    re-decoded from an offset); a numeric cell keeps raw_u32."""
    out = {"state": obs_dict["state"], "decoded_reason": obs_dict["decoded_reason"],
           "policy_ref": policy_ref_str}
    if "raw_offset" in obs_dict:                       # StringObservation
        out["raw_offset"] = obs_dict["raw_offset"]
        out["resolved"] = obs_dict.get("resolved")
    else:                                              # numeric Envelope
        out["raw_u32"] = obs_dict.get("raw_u32")
    return out


def _join_normalized(join, idx_fp, id_fp, val_fp, jo) -> bool:
    """The exact four-part predicate (design A1): the join AND every contributing component are
    normalized, the composed proof is promotion-eligible, and the join resolved."""
    return (jo is not None and join.promotion == "normalized"
            and idx_fp.promotion == "normalized" and id_fp.promotion == "normalized"
            and val_fp.promotion == "normalized"
            and semantic_promotion_eligible(jo.composed_proof) and jo.state == "resolved")


def _resolve_join(rec, join, sf, policy, side_id_maps):
    """Resolve a numeric join to (value, jo_dict, jo). A null index cell yields an absent marker; fk==0 is
    index_zero (not_applicable); a missing side row is side_row_missing; otherwise resolved with
    index/side_id/side_value components."""
    idx_fp = sf[join.index_field]
    if idx_fp.cell is None:
        env = absent_envelope(proof=_proof(idx_fp), state="unresolved",
                              evidence_ref=policy_ref("Spell", join.index_field))
        return None, {"absent": env.to_dict()}, None
    side_fields = policy.tables[join.side_table]["fields"]
    id_fp, val_fp = side_fields["id"], side_fields[join.side_value_field]
    fk = rec.u32(idx_fp.cell)
    idx_env = make_envelope(fk, kind=idx_fp.kind, proof=_proof(idx_fp),
                            evidence_ref=policy_ref("Spell", join.index_field))
    if fk == 0:
        jo = make_join({"index": idx_env}, resolution="index_zero", decode=lambda c: None)
        return None, jo.to_dict(), jo
    side_rec = side_id_maps.get(join.side_table, {}).get(fk)
    if side_rec is None:
        jo = make_join({"index": idx_env}, resolution="side_row_missing", decode=lambda c: None)
        return None, jo.to_dict(), jo
    spec = _join_spec(join)
    side_id_env = make_envelope(side_rec.u32(id_fp.cell), kind=id_fp.kind, proof=_proof(id_fp),
                                evidence_ref=policy_ref_component(spec, "side_id"))
    val_env = make_envelope(side_rec.u32(val_fp.cell), kind=val_fp.kind, proof=_proof(val_fp),
                            evidence_ref=policy_ref_component(spec, "side_value"))
    components = {"index": idx_env, "side_id": side_id_env, "side_value": val_env}
    jo = make_join(components, resolution="resolved",
                   decode=lambda c: c["side_value"].decoded["value"] if c["side_value"].decoded else None)
    return jo.decoded, jo.to_dict(), jo


def _compact_join(jname, join, jo_dict) -> dict:
    if "absent" in jo_dict:
        a = jo_dict["absent"]
        return {"join_name": jname, "state": a["state"], "decoded_reason": a["decoded_reason"],
                "policy_ref": policy_ref("Spell", join.index_field)}
    spec = _join_spec(join)
    return {"join_name": jname, "state": jo_dict["state"], "decoded_reason": jo_dict["decoded_reason"],
            "components": {k: _compact(v, policy_ref_str=policy_ref_component(spec, k))
                           for k, v in jo_dict["components"].items()}}


PROJECTION_SCHEMA_V3 = "coa-client-spell-projection-v3"


def _expand_scalar_cell(cell: dict, policy: SpellPolicy) -> dict:
    """Expand ONE compact scalar cell into a canonical rich observation: re-derive `decoded` from the raw
    substrate + the policy kind, and attach the policy field's proof/promotion (CLAIMS a consumer
    re-verifies, never trusts). The exact inverse of `_compact`, so the compact child expands losslessly."""
    fp = resolve_policy_ref(policy.doc, cell["policy_ref"])
    proof = {"integrity": "verified", "layout": fp["layout"], "interpretation": fp["interpretation"]}
    out = {"state": cell["state"], "decoded_reason": cell["decoded_reason"],
           "proof": proof, "promotion": fp["promotion"], "policy_ref": cell["policy_ref"]}
    if "raw_offset" in cell:                                   # StringObservation substrate
        out["raw_offset"] = cell["raw_offset"]
        out["resolved"] = cell.get("resolved")
    else:                                                      # numeric Envelope substrate
        raw_u32 = cell.get("raw_u32")
        out["raw_u32"] = raw_u32
        out["decoded"] = ({"kind": fp["kind"], "value": _redecode(raw_u32, fp["kind"])}
                          if cell["decoded_reason"] == "decoded" and raw_u32 is not None else None)
    return out


def _expand_compact(cell: dict, policy: SpellPolicy) -> dict:
    """Expand a compact raw cell (scalar OR join) into its canonical rich field observation. This is the
    contract-critical inverse of the compact producer: `_expand_compact(full.raw[f], policy)` MUST equal
    the projection's `field_observations[f]`, so the compact full child is provably lossless."""
    if "join_name" not in cell:
        return _expand_scalar_cell(cell, policy)
    if "components" not in cell:                              # absent join (null index cell)
        fp = resolve_policy_ref(policy.doc, cell["policy_ref"])
        return {"join_name": cell["join_name"], "state": cell["state"],
                "decoded_reason": cell["decoded_reason"], "policy_ref": cell["policy_ref"],
                "proof": {"integrity": "verified", "layout": fp["layout"],
                          "interpretation": fp["interpretation"]}, "promotion": fp["promotion"]}
    components = {k: _expand_scalar_cell(v, policy) for k, v in cell["components"].items()}
    composed = compose_proof(*(FieldProof(c["proof"]["integrity"], c["proof"]["layout"],
                                          c["proof"]["interpretation"]) for c in components.values()))
    join = policy.joins.get(cell["join_name"])
    decoded = None
    if cell["decoded_reason"] == "decoded" and "side_value" in components:
        sv = components["side_value"]
        decoded = sv["decoded"]["value"] if sv.get("decoded") else sv.get("resolved")
    return {"join_name": cell["join_name"], "state": cell["state"],
            "decoded_reason": cell["decoded_reason"], "components": components,
            "composed_proof": composed.to_dict(), "decoded": decoded,
            "promotion": join.promotion if join is not None else "raw_only"}


def project_v3_row(compact_row: dict, policy: SpellPolicy) -> dict:
    """Build a coa-client-spell-projection-v3 row from a compact full child row: identity + normalized
    mechanics + attribution, and the compact `raw` EXPANDED into rich `field_observations`. The projection
    carries NO compact `raw` (the two v3 dialects are deliberately disjoint — full=compact, projection=rich)."""
    return {"schema_version": PROJECTION_SCHEMA_V3,
            "spell_id": compact_row["spell_id"], "name": compact_row.get("name"),
            "mechanics": compact_row["mechanics"], "coa_attribution": compact_row["coa_attribution"],
            "field_observations": {f: _expand_compact(cell, policy)
                                   for f, cell in compact_row["raw"].items()}}


def _side_maps(side_views: dict) -> dict:
    out: dict[str, dict] = {}
    for name, view in side_views.items():
        if view is None:
            continue
        m: dict[int, object] = {}
        for r in view.records():
            m.setdefault(r.u32(0), r)
        out[name] = m
    return out


def iter_spell_records(spell_view, side_views, *, policy, provenance, coa_spell_ids=None):
    """Stream coa-client-spell-v3 rows. String joins (SpellIcon.path) are emitted by the icon catalog,
    not here, so `mechanics` stays numeric.

    `coa_attribution.is_coa` is AUTHORITATIVE: a spell is CoA iff its id is in `coa_spell_ids` — the set
    the M1.14B advancement-graph + skill-line attribution proves (built two-pass by the caller). It is NOT
    the `spell_id >= 100000` id floor, which is only the `id_range` PROVENANCE signal (marking ~139k
    enemy/NPC/aura/dev spells CoA distorts the projection, closure, and coverage). When `coa_spell_ids` is
    None (a caller with no attribution, e.g. a raw compact-raw unit test) is_coa fails closed to False."""
    coa_ids = coa_spell_ids if coa_spell_ids is not None else frozenset()
    sf = policy.tables["Spell"]["fields"]
    allowed_pt = policy.enum_policy["power_types"]
    allowed_bits = policy.enum_policy["school_bits"]
    side_id_maps = _side_maps(side_views)
    effective = provenance.get("effective_archive", "")
    archive_family = family_of(effective) if effective else "unknown"

    for rec in spell_view.records():
        spell_id = rec.u32(sf["id"].cell)
        raw: dict = {}
        mech: dict = {}

        id_env = make_envelope(spell_id, kind=sf["id"].kind, proof=_proof(sf["id"]),
                               evidence_ref=policy_ref("Spell", "id"))
        raw["id"] = _compact(id_env.to_dict(), policy_ref_str=policy_ref("Spell", "id"))

        name_val = None
        name_fp = sf.get("name")
        if name_fp is not None and name_fp.cell is not None:
            off = rec.u32(name_fp.cell)
            sob = make_string_observation(off, spell_view.read_string(off), proof=_proof(name_fp),
                                          evidence_ref=policy_ref("Spell", "name"))
            raw["name"] = _compact(sob.to_dict(), policy_ref_str=policy_ref("Spell", "name"))
            name_val = sob.resolved if name_fp.promotion == "normalized" else None

        # description (client tooltip @170): a real extracted string, but raw_only — its $s1 macros are
        # unresolved templates, so it is emitted into `raw` and NEVER into mechanics. The raw block is
        # LOSSLESS: unlike a numeric raw_u32, a string cannot be reconstructed from an offset, so the actual
        # tooltip TEXT is retained (the raw_only-ness is a promotion property, not a decode failure).
        desc_fp = sf.get("description")
        if desc_fp is not None and desc_fp.cell is not None:
            doff = rec.u32(desc_fp.cell)
            raw["description"] = _compact(
                {"state": "present", "raw_offset": doff, "resolved": spell_view.read_string(doff),
                 "decoded_reason": "decoded"},
                policy_ref_str=policy_ref("Spell", "description"))

        for nm, refine in (("power_type", lambda v: refine_enum(v, allowed_pt)),
                           ("school_mask", lambda v: refine_mask(v, allowed_bits))):
            fp = sf[nm]
            if fp.cell is None:
                env = absent_envelope(proof=_proof(fp), evidence_ref=policy_ref("Spell", nm), state="unresolved")
            else:
                env = make_domain_gated_envelope(rec.u32(fp.cell), kind=fp.kind, proof=_proof(fp),
                                                 evidence_ref=policy_ref("Spell", nm), refine=refine)
            raw[nm] = _compact(env.to_dict(), policy_ref_str=policy_ref("Spell", nm))
            mech[nm] = env.decoded["value"] if (fp.promotion == "normalized" and env.decoded is not None) else None

        for jname, join in policy.joins.items():
            val_fp = policy.tables[join.side_table]["fields"][join.side_value_field]
            if val_fp.kind == "string":
                continue                                # SpellIcon.path -> icon catalog, not spell mechanics
            value, jo_dict, jo = _resolve_join(rec, join, sf, policy, side_id_maps)
            idx_fp, id_fp = sf[join.index_field], policy.tables[join.side_table]["fields"]["id"]
            mech[jname] = value if _join_normalized(join, idx_fp, id_fp, val_fp, jo) else None
            raw[jname] = _compact_join(jname, join, jo_dict)

        yield {"schema_version": SCHEMA_V3, "spell_id": spell_id, "name": name_val,
               "mechanics": mech, "raw": raw,
               "coa_attribution": {"is_coa": spell_id in coa_ids, "status": "unknown",
                                   "archive_family": archive_family,
                                   "id_range": "high" if spell_id >= _CUSTOM_ID_FLOOR else "base",
                                   "policy_sha256": policy.sha256}}


def eligible_from_row(obs: dict, pol: dict, policy_doc: dict) -> bool:
    """Recompute a field's promotion eligibility from the SERIALIZED compact form (the exact shape Node
    consumes), so the golden fixtures pin producer and Node to one rule. A join is eligible iff its own
    `promotion` (looked up in policy_doc['joins']) is normalized, it resolved, and every component's
    policy is verified+normalized; a scalar iff its policy is fully verified+normalized and it decoded."""
    if obs.get("components"):
        join = policy_doc.get("joins", {}).get(obs.get("join_name"), {})
        if join.get("promotion") != "normalized" or obs.get("state") != "resolved":
            return False
        for _, c in obs["components"].items():
            cp = resolve_policy_ref(policy_doc, c["policy_ref"])
            if not (cp.get("promotion") == "normalized" and cp.get("layout") == "verified"
                    and cp.get("interpretation") == "verified"):
                return False
        return True
    return (pol.get("promotion") == "normalized" and pol.get("layout") == "verified"
            and pol.get("interpretation") == "verified"
            and obs.get("state") in ("present", "resolved") and obs.get("decoded_reason") == "decoded")


def _redecode(raw_u32: int, kind: str):
    b = struct.pack("<I", raw_u32 & 0xFFFFFFFF)
    if kind == "int32":
        return struct.unpack("<i", b)[0]
    if kind == "float":
        return struct.unpack("<f", b)[0]
    return struct.unpack("<I", b)[0]


def _verify_scalar_claims(spell_id, field, obs: dict, policy_doc: dict) -> None:
    """A rich field observation is self-describing but NEVER trusted: re-derive proof/promotion from the
    policy and re-decode the value from the raw substrate, then verify the observation's claims match."""
    pol = resolve_policy_ref(policy_doc, obs["policy_ref"])
    want_proof = {"integrity": "verified", "layout": pol["layout"], "interpretation": pol["interpretation"]}
    if obs.get("proof") != want_proof:
        raise ValueError(f"{spell_id}:{field} proof claim disagrees with policy")
    if obs.get("promotion") != pol.get("promotion"):
        raise ValueError(f"{spell_id}:{field} promotion claim disagrees with policy")
    if "raw_offset" in obs:                                    # string substrate: resolved is the value
        return
    raw_u32 = obs.get("raw_u32")
    want = ({"kind": pol["kind"], "value": _redecode(raw_u32, pol["kind"])}
            if obs.get("decoded_reason") == "decoded" and raw_u32 is not None else None)
    if obs.get("decoded") != want:
        raise ValueError(f"{spell_id}:{field} decoded claim disagrees with re-decode")


def verify_row_against_policy(row: dict, policy_doc: dict) -> None:
    """Independent Python mirror of Node's verifyRowAgainstPolicy over the RICH projection dialect: reject a
    row that carries compact `raw` or lacks `field_observations`; verify each observation's self-describing
    claims; then the biconditional (eligible iff populated) must hold and a populated value must agree with a
    re-decode of raw_u32 (numeric) or the resolved string. Raises ValueError on any mismatch. Exercised
    against the SAME golden fixtures as the Node verifier, so the two can never silently diverge."""
    mech = row.get("mechanics", {})
    if "raw" in row:
        raise ValueError(f"{row.get('spell_id')}: carries compact raw (v3 projection is rich field_observations)")
    fobs = row.get("field_observations")
    if not isinstance(fobs, dict):
        raise ValueError(f"{row.get('spell_id')}: missing field_observations")
    for field, obs in fobs.items():
        if obs.get("components"):
            for _, c in obs["components"].items():
                _verify_scalar_claims(row.get("spell_id"), field, c, policy_doc)
        else:
            _verify_scalar_claims(row.get("spell_id"), field, obs, policy_doc)
        # eligible_from_row only reads `pol` on the scalar branch; a join's eligibility comes from
        # policy_doc['joins'] + its components, so no side_value lookup happens here.
        scalar_pol = None if obs.get("components") else resolve_policy_ref(policy_doc, obs["policy_ref"])
        eligible = eligible_from_row(obs, scalar_pol, policy_doc)
        if field == "id":
            value = row.get("spell_id")
        elif field in mech:
            value = mech[field]
        elif field in row:
            value = row[field]
        else:
            value = None
        populated = value is not None
        if eligible != populated:
            raise ValueError(f"{row.get('spell_id')}:{field} eligible={eligible} populated={populated}")
        if not populated:
            continue
        # Resolve the value's policy node ONLY when populated: an unresolved join (index_zero/
        # side_row_missing) has no side_value component, and a resolved join always does (Node's guard).
        pol = (scalar_pol if scalar_pol is not None
               else resolve_policy_ref(policy_doc, obs["components"]["side_value"]["policy_ref"]))
        if pol.get("kind") == "string":
            resolved = obs["components"]["side_value"]["resolved"] if obs.get("components") else obs.get("resolved")
            if value != resolved:
                raise ValueError(f"{row.get('spell_id')}:{field} string != resolved")
        else:
            raw = obs["components"]["side_value"]["raw_u32"] if obs.get("components") else obs["raw_u32"]
            if _redecode(raw, pol.get("kind")) != value:
                raise ValueError(f"{row.get('spell_id')}:{field} re-decode disagrees")
