from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

PROOF_STATES = ("verified", "reference", "unproven", "contradicted")
_KINDS = ("int32", "uint32", "float")            # numeric envelope kinds; strings use StringObservation
_STATES = ("present", "not_applicable", "unresolved")
_TOKEN = object()
_ORDER = {"verified": 3, "reference": 2, "unproven": 1, "contradicted": 0}
_INV = {v: k for k, v in _ORDER.items()}


@dataclass(frozen=True)
class FieldProof:
    integrity: str
    layout: str
    interpretation: str

    def __post_init__(self):
        for v in (self.integrity, self.layout, self.interpretation):
            if v not in PROOF_STATES:
                raise ValueError(f"proof state {v!r} not in {PROOF_STATES}")

    def to_dict(self):
        return {"integrity": self.integrity, "layout": self.layout, "interpretation": self.interpretation}


def raw_decode_eligible(p: FieldProof) -> bool:
    return p.integrity == "verified" and p.layout == "verified"


def semantic_promotion_eligible(p: FieldProof) -> bool:
    return raw_decode_eligible(p) and p.interpretation == "verified"


def compose_proof(*proofs: FieldProof) -> FieldProof:
    """Composed proof for a joined value = the WEAKEST facet across all contributing parts, so a join
    is never stronger than its weakest component or file integrity."""
    if not proofs:
        raise ValueError("compose_proof requires at least one proof")
    keys = ("integrity", "layout", "interpretation")
    return FieldProof(*[_INV[min(_ORDER[getattr(p, k)] for p in proofs)] for k in keys])


def _decode(raw_u32: int, kind: str):
    if kind == "uint32":
        return {"kind": "uint32", "value": raw_u32}
    if kind == "int32":
        return {"kind": "int32", "value": struct.unpack("<i", struct.pack("<I", raw_u32))[0]}
    (v,) = struct.unpack("<f", struct.pack("<I", raw_u32))
    return None if not math.isfinite(v) else {"kind": "float", "value": v}


@dataclass(frozen=True)
class Envelope:
    state: str
    raw_u32: int | None
    decoded: dict | None
    decoded_reason: str
    proof: FieldProof
    evidence_ref: str
    _token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self._token is not _TOKEN:
            raise TypeError("construct Envelope via make_envelope()/absent_envelope()/make_domain_gated_envelope()")

    def to_dict(self):
        return {"state": self.state, "raw_u32": self.raw_u32, "decoded": self.decoded,
                "decoded_reason": self.decoded_reason, "proof": self.proof.to_dict(),
                "evidence_ref": self.evidence_ref}


def _validate(kind: str, evidence_ref: str) -> None:
    if kind not in _KINDS:
        raise ValueError(f"unknown kind {kind!r} (expected one of {_KINDS})")
    if not evidence_ref:
        raise ValueError("evidence_ref must be non-empty")


def make_envelope(raw_u32, *, kind, proof, evidence_ref) -> Envelope:
    _validate(kind, evidence_ref)
    if type(raw_u32) is not int or not (0 <= raw_u32 < 2**32):   # rejects bool + out-of-domain
        raise ValueError(f"raw_u32 {raw_u32!r} outside the 32-bit cell domain")
    if semantic_promotion_eligible(proof):
        decoded = _decode(raw_u32, kind)
        reason = "decoded" if decoded is not None else "non_finite"
    else:
        decoded, reason = None, "proof_withheld"
    return Envelope("present", raw_u32, decoded, reason, proof, evidence_ref, _TOKEN)


def absent_envelope(*, proof, evidence_ref, state) -> Envelope:
    _validate("uint32", evidence_ref)
    if state not in ("not_applicable", "unresolved"):
        raise ValueError("absent_envelope requires a non-present state")
    return Envelope(state, None, None, "not_present", proof, evidence_ref, _TOKEN)


def make_domain_gated_envelope(raw_u32, *, kind, proof, evidence_ref, refine) -> Envelope:
    """Build the envelope, then withhold the decoded value IN-BAND (decoded_reason='value_out_of_domain')
    when `refine(value) -> (normalized, in_domain)` reports an unseen enum/bit — so a consumer tells an
    unknown symbol apart from ordinary absence. Raw is retained."""
    env = make_envelope(raw_u32, kind=kind, proof=proof, evidence_ref=evidence_ref)
    if env.decoded is None or refine(env.decoded["value"])[1]:
        return env
    return Envelope("present", env.raw_u32, None, "value_out_of_domain", proof, evidence_ref, _TOKEN)


@dataclass(frozen=True)
class StringObservation:
    state: str
    raw_offset: int | None
    resolved: str | None
    decoded_reason: str
    proof: FieldProof
    evidence_ref: str
    _token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self._token is not _TOKEN:
            raise TypeError("construct StringObservation via make_string_observation()")

    def to_dict(self):
        return {"state": self.state, "raw_offset": self.raw_offset, "resolved": self.resolved,
                "decoded_reason": self.decoded_reason, "proof": self.proof.to_dict(),
                "evidence_ref": self.evidence_ref}


def make_string_observation(raw_offset, resolved, *, proof, evidence_ref) -> StringObservation:
    """A string cell is a string-block OFFSET; the normalized value is text. Consumers match on
    `resolved` text, never a raw u32."""
    if type(raw_offset) is not int or not (0 <= raw_offset < 2**32):
        raise ValueError("raw_offset outside the 32-bit domain")
    if not evidence_ref:
        raise ValueError("evidence_ref must be non-empty")
    if semantic_promotion_eligible(proof):
        if not isinstance(resolved, str):
            raise ValueError("resolved must be a str when promotion-eligible")
        return StringObservation("present", raw_offset, resolved, "decoded", proof, evidence_ref, _TOKEN)
    return StringObservation("present", raw_offset, None, "proof_withheld", proof, evidence_ref, _TOKEN)


@dataclass(frozen=True)
class JoinObservation:
    state: str
    components: dict
    composed_proof: FieldProof
    decoded: object | None
    decoded_reason: str
    _token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self._token is not _TOKEN:
            raise TypeError("construct JoinObservation via make_join()")

    def to_dict(self):
        return {"state": self.state, "components": {k: v.to_dict() for k, v in self.components.items()},
                "composed_proof": self.composed_proof.to_dict(), "decoded": self.decoded,
                "decoded_reason": self.decoded_reason}


def make_join(components: dict, *, resolution, decode) -> JoinObservation:
    """resolution ∈ {resolved, index_zero, side_row_missing}. index_zero = no FK (not_applicable);
    side_row_missing = nonzero FK with no matching side row (recoverable -> unresolved). A structurally
    MALFORMED/impossible reference is caught by open_view/RecordView integrity and fails closed BEFORE
    make_join -- it is never turned into a publishable observation."""
    if not components:
        raise ValueError("join requires components")
    composed = compose_proof(*(e.proof for e in components.values()))
    if resolution == "index_zero":
        return JoinObservation("not_applicable", components, composed, None, "index_zero", _TOKEN)
    if resolution == "side_row_missing":
        return JoinObservation("unresolved", components, composed, None, "side_row_missing", _TOKEN)
    if resolution != "resolved":
        raise ValueError(f"invalid join resolution {resolution!r} (fail closed)")
    if not semantic_promotion_eligible(composed):
        return JoinObservation("resolved", components, composed, None, "proof_withheld", _TOKEN)
    value = decode(components)
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and \
        (not isinstance(value, float) or math.isfinite(value))
    return JoinObservation("resolved", components, composed, value if ok else None,
                           "decoded" if ok else "non_finite", _TOKEN)


def make_string_join(components: dict, *, resolution, side_key: str = "side_value") -> JoinObservation:
    """A join whose side value is a StringObservation (e.g. SpellIcon.path). Mirrors make_join's states,
    but the resolved value is the side observation's `resolved` text; a string cannot be re-decoded from
    an offset, so consumers verify equality against `resolved`. index_zero -> not_applicable,
    side_row_missing -> unresolved, and a withheld composed proof (or an unresolved side) withholds."""
    if not components:
        raise ValueError("string join requires components")
    composed = compose_proof(*(c.proof for c in components.values()))
    if resolution == "index_zero":
        return JoinObservation("not_applicable", components, composed, None, "index_zero", _TOKEN)
    if resolution == "side_row_missing":
        return JoinObservation("unresolved", components, composed, None, "side_row_missing", _TOKEN)
    if resolution != "resolved":
        raise ValueError(f"invalid string-join resolution {resolution!r} (fail closed)")
    side = components[side_key]
    if not semantic_promotion_eligible(composed) or side.resolved is None:
        return JoinObservation("resolved", components, composed, None, "proof_withheld", _TOKEN)
    return JoinObservation("resolved", components, composed, side.resolved, "decoded", _TOKEN)


def refine_enum(value, allowed):
    """Exact-membership gate for a scalar enum (e.g. power_type)."""
    return (value, True) if value in allowed else (None, False)


def refine_mask(value, allowed_bits):
    """Bitmask gate: every SET bit must be allowed; a valid combination like 20 (4|16) passes, zero
    passes, an unknown bit is withheld."""
    bad = [1 << b for b in range(32) if (value >> b) & 1 and (1 << b) not in allowed_bits]
    return (None, False) if bad else (value, True)
