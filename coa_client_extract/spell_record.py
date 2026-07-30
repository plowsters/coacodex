from __future__ import annotations

import struct

from .archive_plan import family_of
from .contracts import (WireSchemaError, decoded_reason_code, decoded_reason_name, policy_ref,
                        policy_ref_component, observation_state_code, observation_state_name,
                        resolve_policy_ref)
from .recordview import DbcView
from .spell_layout import FieldPolicy, SpellPolicy
from .spell_proof import (
    FieldProof, absent_envelope, compose_proof, make_domain_gated_envelope, make_envelope, make_join,
    make_string_observation, refine_enum, refine_mask, semantic_promotion_eligible,
)

SCHEMA = "coa-client-spell-v2"
SCHEMA_V3 = "coa-client-spell-v3"
# E0R.2 T6.2. v4 is v3 with the per-cell CONSTANTS removed: `policy_ref` (23.6% of the real payload,
# 88.6 MB, one distinct value per field) and `join_name` (5.9%, 22.3 MB) move to the staged field
# descriptors, and the two closed vocabularies (`state` 9.7%, `decoded_reason` 14.8%) become the integer
# codes `s`/`d`. The PROJECTION stays v3: `_expand_compact` absorbs the change, so
# `expand_compact(full.raw) == projection.field_observations` is still literally true.
SPELL_SCHEMA_V3 = SCHEMA_V3
SPELL_SCHEMA_V4 = "coa-client-spell-v4"
FIELD_DESCRIPTORS_CHILD = "coa_client_spell_fields.json"
WIRE_SCHEMA_CHILD = "observation_wire_schema.json"
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
# iter_spell_records STREAMS coa-client-spell-v4 rows: identity + normalized `mechanics` + a compact
# `raw` block (enough to reconstruct eligibility, plus a policy_ref, but NO per-row evidence text — Node
# re-derives proof/promotion from the pinned policy via policy_ref). A normalized value is emitted only
# when its full promotion predicate holds; the compact raw is retained regardless.


def _join_spec(join) -> dict:
    return {"index_field": join.index_field, "side_table": join.side_table,
            "side_value_field": join.side_value_field}


def _compact(obs_dict: dict, *, policy_ref_str: str = None) -> dict:
    """A compact raw cell (E0R.2 T6.2: v4). Retain only the SUBSTRATE plus the two interned vocabulary
    codes; the policy pointer and the join name come from the staged field descriptors, and the per-row
    proof/evidence text is dropped entirely (Node re-derives it from the policy).

    A string observation keeps raw_offset + resolved (a string cannot be re-decoded from an offset); a
    numeric cell keeps raw_u32. `policy_ref_str` is accepted and ignored — the call sites still name the
    pointer they mean, which is what makes the descriptor derivation checkable against them."""
    out = {"s": observation_state_code(obs_dict["state"]),
           "d": decoded_reason_code(obs_dict["decoded_reason"])}
    if "raw_offset" in obs_dict:                       # StringObservation
        out["raw_offset"] = obs_dict["raw_offset"]
        out["resolved"] = obs_dict.get("resolved")
    else:                                              # numeric Envelope
        out["raw_u32"] = obs_dict.get("raw_u32")
    return out


def compact_cell_v4(cell: dict) -> dict:
    """Re-encode a v3 compact cell as a v4 one. Used to migrate fixtures and to prove, cell by cell,
    that the two encodings expand to the same rich observation."""
    substrate = {k: v for k, v in cell.items()
                 if k in ("raw_u32", "raw_offset", "resolved")}
    out = {"s": observation_state_code(cell["state"]), "d": decoded_reason_code(cell["decoded_reason"]),
           **substrate}
    if "components" in cell:
        out["components"] = {k: compact_cell_v4(v) for k, v in cell["components"].items()}
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
    """v4: the join name and every component pointer come from the descriptor for this field, so a join
    cell is its two vocabulary codes plus (when resolved) three component substrates."""
    if "absent" in jo_dict:
        a = jo_dict["absent"]
        return {"s": observation_state_code(a["state"]),
                "d": decoded_reason_code(a["decoded_reason"])}
    spec = _join_spec(join)
    return {"s": observation_state_code(jo_dict["state"]),
            "d": decoded_reason_code(jo_dict["decoded_reason"]),
            "components": {k: _compact(v, policy_ref_str=policy_ref_component(spec, k))
                           for k, v in jo_dict["components"].items()}}


PROJECTION_SCHEMA_V3 = "coa-client-spell-projection-v3"
OBSERVATION_COVERAGE_SCHEMA = "coa-client-observation-coverage-v1"


class _ObservationAccumulator:
    """Streaming state/reason tallies over full-row raw cells (E0R.2 T4.1).

    This is OBSERVATION coverage, not mechanics readiness — a distinction with two different
    denominators. Observation coverage counts every raw CELL of every full row; icon coverage counts
    every SPELL in the domain; mechanics readiness lives on the other side of the trust boundary
    entirely. Reporting one as the other yields a healthy-looking number about the wrong population.

    The denominator is exact by construction: each cell increments exactly one state bucket and exactly
    one reason bucket, at both the per-field and the overall level, so the parts always sum to `cells`.
    A coverage figure computed over "the cells we happened to emit" cannot tell complete extraction from
    silent loss — it reads 100% either way.

    A join's COMPONENTS are sub-observations of the one field cell and are deliberately not counted:
    they would inflate numerator and denominator with a different unit.

    Counters only — no row is retained. This folds into the streaming write loop over a 200k-row table
    (design A4), where holding rows would defeat the point.
    """

    __slots__ = ("rows", "cells", "states", "reasons", "fields")

    def __init__(self):
        self.rows = 0
        self.cells = 0
        self.states: dict[str, int] = {}
        self.reasons: dict[str, int] = {}
        self.fields: dict[str, dict] = {}

    def observe(self, row: dict) -> None:
        self.rows += 1
        for field, cell in (row.get("raw") or {}).items():
            entry = self.fields.get(field)
            if entry is None:
                entry = self.fields[field] = {"cells": 0, "states": {}, "decoded_reasons": {}}
            # E0R.2 T6.2: a v4 cell carries interned codes. Coverage is reported in the VOCABULARY
            # NAMES either way — a consumer reading `{"1": 12}` learns nothing about which state that is.
            state, reason = ((observation_state_name(cell["s"]), decoded_reason_name(cell["d"]))
                             if "s" in cell else (cell.get("state"), cell.get("decoded_reason")))
            self.cells += 1
            entry["cells"] += 1
            self.states[state] = self.states.get(state, 0) + 1
            self.reasons[reason] = self.reasons.get(reason, 0) + 1
            entry["states"][state] = entry["states"].get(state, 0) + 1
            entry["decoded_reasons"][reason] = entry["decoded_reasons"].get(reason, 0) + 1

    def result(self) -> dict:
        return {"schema_version": OBSERVATION_COVERAGE_SCHEMA, "rows": self.rows, "cells": self.cells,
                "states": dict(sorted(self.states.items())),
                "decoded_reasons": dict(sorted(self.reasons.items())),
                "fields": {f: {"cells": e["cells"],
                               "states": dict(sorted(e["states"].items())),
                               "decoded_reasons": dict(sorted(e["decoded_reasons"].items()))}
                           for f, e in sorted(self.fields.items())}}


def observation_accumulator() -> _ObservationAccumulator:
    return _ObservationAccumulator()


# === E0R.2 T6.1: kind-aware field descriptors =====================================================
FIELD_DESCRIPTORS_SCHEMA = "coa-client-spell-fields-v1"


class DescriptorError(ValueError):
    """A staged field-descriptor document disagrees with the policy it claims to describe, or a cell
    that relies on a descriptor was expanded without one."""


def build_field_descriptors(policy_doc: dict) -> dict:
    """The per-field constants every cell repeats today, hoisted into ONE document derived from the
    policy: `policy_ref` is 23.6% of the real payload (88.6 MB) with exactly one distinct value per
    field, `join_name` another 5.9% (22.3 MB).

    KIND-AWARE, because a single `policy_ref` per field cannot reconstruct a resolved join: a join cell
    carries `components.{index,side_id,side_value}`, each pointing at a DIFFERENT table-field through
    the join mapping. `index_policy_ref` serves the absent form (null index cell), `components` the
    resolved one. A scalar-only descriptor would silently lose two thirds of every join cell.

    Bound to `policy_sha256`, because a descriptor is meaningful against exactly one policy.
    """
    fields: dict[str, dict] = {}
    for name in policy_doc["tables"]["Spell"]["fields"]:
        fields[name] = {"kind": "scalar", "policy_ref": policy_ref("Spell", name)}
    for jname, join in (policy_doc.get("joins") or {}).items():
        spec = {"index_field": join["index_field"], "side_table": join["side_table"],
                "side_value_field": join["side_value_field"]}
        fields[jname] = {
            "kind": "join", "join_name": jname,
            "index_policy_ref": policy_ref("Spell", join["index_field"]),
            "components": {part: {"policy_ref": policy_ref_component(spec, part)}
                           for part in ("index", "side_id", "side_value")},
        }
    return {"schema_version": FIELD_DESCRIPTORS_SCHEMA, "policy_sha256": policy_doc.get("sha256"),
            "fields": fields}


def require_field_descriptors(staged: dict, policy_doc: dict) -> dict:
    """Re-derive the descriptors from the policy and require the staged document to equal them.

    Never trust a staged descriptor: it defines what every hoisted cell MEANS, so a tampered one could
    redefine a field's substrate while keeping compact->rich expansion perfectly self-consistent. The
    only defence is deriving the expectation independently — on BOTH sides of the trust boundary."""
    expected = build_field_descriptors(policy_doc)
    if not isinstance(staged, dict):
        raise DescriptorError(f"field descriptors must be an object, got {type(staged).__name__}")
    if staged.get("schema_version") != expected["schema_version"]:
        raise DescriptorError(f"field descriptors schema_version {staged.get('schema_version')!r} is not "
                              f"{expected['schema_version']!r}")
    if staged.get("policy_sha256") != expected["policy_sha256"]:
        raise DescriptorError(f"field descriptors policy_sha256 {staged.get('policy_sha256')!r} does not "
                              f"describe this policy ({expected['policy_sha256']!r})")
    got = staged.get("fields")
    if not isinstance(got, dict):
        raise DescriptorError("field descriptors carry no `fields` object")
    for name in sorted(set(got) ^ set(expected["fields"])):
        raise DescriptorError(f"field descriptor set differs from the policy at {name!r} "
                              f"({'staged only' if name in got else 'policy only'})")
    for name in sorted(expected["fields"]):
        if got[name] != expected["fields"][name]:
            raise DescriptorError(f"field descriptor {name!r} differs from the policy-derived one: "
                                  f"{got[name]!r} != {expected['fields'][name]!r}")
    return expected


def _descriptor_for(field, descriptors) -> dict:
    if descriptors is None or field is None:
        raise DescriptorError(
            f"cell {field!r} carries no inline policy_ref and no descriptors were supplied; refusing to "
            "guess which policy field it observes")
    entry = (descriptors.get("fields") or {}).get(field)
    if entry is None:
        raise DescriptorError(f"no field descriptor for {field!r}")
    return entry


def _cell_policy_ref(cell: dict, field, descriptors, *, part=None) -> str:
    """The pointer a cell observes: inline while both encodings are supported (T6.1), from the descriptor
    once T6.2 hoists it out of the row."""
    if "policy_ref" in cell:
        return cell["policy_ref"]
    entry = _descriptor_for(field, descriptors)
    if part is not None:
        return entry["components"][part]["policy_ref"]
    return entry["index_policy_ref"] if entry["kind"] == "join" else entry["policy_ref"]


_V4_HOISTED_KEYS = ("policy_ref", "join_name", "state", "decoded_reason")


def _vocabulary(cell: dict, row_schema) -> tuple[str, str]:
    """The cell's (state, decoded_reason), decoded from the trusted wire schema for a v4 cell and read
    verbatim from a v3 one. A v4 cell that ALSO repeats a hoisted key is refused rather than
    reconciled: it could claim a policy_ref the descriptor disagrees with, and there is no principled
    winner between them."""
    if row_schema == SPELL_SCHEMA_V4 or (row_schema is None and "s" in cell):
        for key in _V4_HOISTED_KEYS:
            if key in cell:
                raise WireSchemaError(
                    f"v4 cell repeats the hoisted key {key!r}; the descriptor and the wire schema are "
                    "the only sources for it")
        return observation_state_name(cell.get("s")), decoded_reason_name(cell.get("d"))
    return cell["state"], cell["decoded_reason"]


def _expand_scalar_cell(cell: dict, policy: SpellPolicy, *, field=None, descriptors=None,
                        part=None, row_schema=None) -> dict:
    """Expand ONE compact scalar cell into a canonical rich observation: re-derive `decoded` from the raw
    substrate + the policy kind, and attach the policy field's proof/promotion (CLAIMS a consumer
    re-verifies, never trusts). The exact inverse of `_compact`, so the compact child expands losslessly.

    E0R.2 T6.1/T6.2: the pointer comes from the cell (v3) or from the field descriptor (v4), and the
    vocabulary members are interned codes in v4. The rich observation is identical either way — the
    encoding changed, never the meaning."""
    state, reason = _vocabulary(cell, row_schema)
    ref = _cell_policy_ref(cell, field, descriptors, part=part)
    fp = resolve_policy_ref(policy.doc, ref)
    proof = {"integrity": "verified", "layout": fp["layout"], "interpretation": fp["interpretation"]}
    out = {"state": state, "decoded_reason": reason,
           "proof": proof, "promotion": fp["promotion"], "policy_ref": ref}
    if "raw_offset" in cell:                                   # StringObservation substrate
        out["raw_offset"] = cell["raw_offset"]
        out["resolved"] = cell.get("resolved")
    else:                                                      # numeric Envelope substrate
        raw_u32 = cell.get("raw_u32")
        out["raw_u32"] = raw_u32
        out["decoded"] = ({"kind": fp["kind"], "value": _redecode(raw_u32, fp["kind"])}
                          if reason == "decoded" and raw_u32 is not None else None)
    return out


def _is_join_cell(cell: dict, field, descriptors) -> bool:
    """A join cell says so inline (T6.1) or is named a join by its descriptor (T6.2). `components` alone
    is not the test: an ABSENT join carries none."""
    if "join_name" in cell:
        return True
    if "components" in cell:
        return True
    if descriptors is None or field is None:
        return False
    entry = (descriptors.get("fields") or {}).get(field)
    return bool(entry) and entry.get("kind") == "join"


def _expand_compact(cell: dict, policy: SpellPolicy, *, field=None, descriptors=None,
                    row_schema=None) -> dict:
    """Expand a compact raw cell (scalar OR join) into its canonical rich field observation. This is the
    contract-critical inverse of the compact producer: `_expand_compact(full.raw[f], policy)` MUST equal
    the projection's `field_observations[f]`, so the compact full child is provably lossless.

    Dispatches on the ROW's schema version, so both encodings stay readable: `e0r-v1` remains a
    supported contract revision, and a generation published under it must still expand years later.
    `row_schema=None` infers from the cell, which is what the pre-T6.2 call sites relied on."""
    if not _is_join_cell(cell, field, descriptors):
        return _expand_scalar_cell(cell, policy, field=field, descriptors=descriptors,
                                   row_schema=row_schema)
    state, reason = _vocabulary(cell, row_schema)
    join_name = cell.get("join_name") or _descriptor_for(field, descriptors)["join_name"]
    if "components" not in cell:                              # absent join (null index cell)
        ref = _cell_policy_ref(cell, field, descriptors)
        fp = resolve_policy_ref(policy.doc, ref)
        return {"join_name": join_name, "state": state,
                "decoded_reason": reason, "policy_ref": ref,
                "proof": {"integrity": "verified", "layout": fp["layout"],
                          "interpretation": fp["interpretation"]}, "promotion": fp["promotion"]}
    components = {k: _expand_scalar_cell(v, policy, field=field, descriptors=descriptors, part=k,
                                         row_schema=row_schema)
                  for k, v in cell["components"].items()}
    composed = compose_proof(*(FieldProof(c["proof"]["integrity"], c["proof"]["layout"],
                                          c["proof"]["interpretation"]) for c in components.values()))
    join = policy.joins.get(join_name)
    decoded = None
    if reason == "decoded" and "side_value" in components:
        sv = components["side_value"]
        decoded = sv["decoded"]["value"] if sv.get("decoded") else sv.get("resolved")
    return {"join_name": join_name, "state": state,
            "decoded_reason": reason, "components": components,
            "composed_proof": composed.to_dict(), "decoded": decoded,
            "promotion": join.promotion if join is not None else "raw_only"}


def project_v3_row(compact_row: dict, policy: SpellPolicy, descriptors: dict = None) -> dict:
    """Build a coa-client-spell-projection-v3 row from a compact full child row: identity + normalized
    mechanics + attribution, and the compact `raw` EXPANDED into rich `field_observations`. The projection
    carries NO compact `raw` (the two v3 dialects are deliberately disjoint — full=compact, projection=rich).

    E0R.2 T6.2: the projection schema does NOT move with the full child's. Expansion absorbs the v4
    encoding, so `expand_compact(full.raw) == projection.field_observations` stays literally true and the
    consumer's dialect is untouched."""
    descriptors = descriptors if descriptors is not None else build_field_descriptors(policy.doc)
    row_schema = compact_row.get("schema_version")
    return {"schema_version": PROJECTION_SCHEMA_V3,
            "spell_id": compact_row["spell_id"], "name": compact_row.get("name"),
            "mechanics": compact_row["mechanics"], "coa_attribution": compact_row["coa_attribution"],
            "field_observations": {f: _expand_compact(cell, policy, field=f, descriptors=descriptors,
                                                      row_schema=row_schema)
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
    """Stream coa-client-spell-v4 rows. String joins (SpellIcon.path) are emitted by the icon catalog,
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

        yield {"schema_version": SPELL_SCHEMA_V4, "spell_id": spell_id, "name": name_val,
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
