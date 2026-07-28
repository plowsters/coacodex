# coa_client_extract/contracts.py
"""The frozen design-lock contracts for M1.14E0R.

The single authority the rest of E0R imports: policy-reference helpers, the closed readiness/reason-code
and icon-asset enumerations, the manifest trust-key sets, the named cross-child consistency checks, and
the structured `bound` shape. Nothing here has behavior beyond pure lookups so it can be imported by every
producer/validator without cycles.
"""
from __future__ import annotations

import json
from pathlib import Path

# === the closed OBSERVATION vocabularies (E0R.2 T0.1) ===
# Distinct from READINESS_* below: an observation state/reason describes ONE decoded cell, a readiness
# status describes a consumer-facing field. Conflating them is how an earlier draft of this milestone
# proposed `unknown_symbol` (a readiness reason) as a decoded_reason while MISSING `not_applicable`,
# which spell_proof emits positionally for every index-zero join.
#
# The wire codes live in data/observation_wire_schema.json so BOTH languages read one trusted file
# rather than Python owning constants Node has to mirror. The file is IMMUTABLE: T6.2 serializes these
# integers, so a new vocabulary entry means a new coa-observation-wire-vN document referenced by a new
# generation-contract revision — never an edit, which would break the hash published contracts pin.
_WIRE_SCHEMA_PATH = Path(__file__).resolve().parent / "data" / "observation_wire_schema.json"
_WIRE_SCHEMA_CACHE: dict | None = None


def load_observation_wire_schema() -> dict:
    """The shared observation wire schema (vocabularies + integer codes). Cached: it is a frozen data
    file consulted per cell during compaction."""
    global _WIRE_SCHEMA_CACHE
    if _WIRE_SCHEMA_CACHE is None:
        doc = json.loads(_WIRE_SCHEMA_PATH.read_text(encoding="utf-8"))
        if doc.get("schema_version") != "coa-observation-wire-v1":
            raise ValueError(f"observation wire schema bad schema_version {doc.get('schema_version')!r}")
        _WIRE_SCHEMA_CACHE = doc
    return _WIRE_SCHEMA_CACHE


OBSERVATION_STATES = tuple(sorted(load_observation_wire_schema()["states"]))
DECODED_REASONS = tuple(sorted(load_observation_wire_schema()["decoded_reasons"]))


def observation_state_code(state: str) -> int:
    """Wire code for an observation state. KeyError (fails closed) for anything out of vocabulary —
    an uncodeable cell must never round-trip as a default."""
    return load_observation_wire_schema()["states"][state]


def decoded_reason_code(reason: str) -> int:
    return load_observation_wire_schema()["decoded_reasons"][reason]


READINESS_STATUSES = frozenset({"available", "unavailable", "not_applicable", "ambiguous", "verified_empty"})
READINESS_REASON_CODES = frozenset({
    "pending_e1_operand", "join_ambiguous", "unknown_symbol", "side_row_missing",
    "index_zero", "no_static_anchor", "not_extracted", "proven_empty", "extracted",
})
ICON_ASSET_STATUSES = frozenset({"converted", "source_only", "missing", "placeholder"})

# The manifest fields candidate_trust_sha256 covers: everything a consumer trusts EXCEPT the
# post-validation /validation and /budget results (which legitimately differ candidate->final).
TRUST_CRITICAL_MANIFEST_KEYS = frozenset({
    "schema_version", "generation_id", "predecessor_generation_id", "children",
    "binding", "unknown_symbol_inventory", "outputs",
})

# The named cross-child consistency checks a candidate validator MUST run (design A5).
CROSS_CHILD_CHECKS = (
    "projection_is_coa_subset", "projection_within_domain", "identity_agrees",
    "compact_raw_expands_to_envelope", "icons_agree", "sorted_unique_ids",
)

# The structured `bound` per-table shape (design A2).
BOUND_HEADER_FIELDS = ("magic", "record_count", "field_count", "record_size", "string_block_size")
BOUND_SOURCE_FIELDS = ("member", "effective_archive", "patch_chain")

# status -> (value must be null?, blocking?, set-valued-only?) — the readiness state machine (design B3).
# `available` additionally requires a PRESENT value and `verified_empty` an actually-EMPTY collection;
# both are enforced by the loader (E0R.1 T5.2) since neither is expressible as a null/set-valued flag.
READINESS_INVARIANTS = {
    "available": (False, False, False), "verified_empty": (False, False, True),
    "not_applicable": (True, False, False), "unavailable": (True, True, False),
    "ambiguous": (True, True, False),
}

# reason_code -> the statuses it may accompany (E0R.1 T5.2). A reason is a CLAIM about WHY a field sits
# in its status; an incompatible pair (`proven_empty` on an `unavailable` field, `not_extracted` on a
# `verified_empty` one) is a self-contradicting record, not a nuance, and fails closed at load.
READINESS_REASON_COMPATIBILITY = {
    "extracted": frozenset({"available"}),                 # the value was read from a proven source
    "proven_empty": frozenset({"verified_empty"}),         # emptiness itself is the proven fact
    "not_extracted": frozenset({"unavailable"}),           # never read — says nothing about emptiness
    "pending_e1_operand": frozenset({"unavailable"}),      # the operand model does not exist yet
    "no_static_anchor": frozenset({"unavailable"}),        # observed, but not statically authorized
    "side_row_missing": frozenset({"unavailable"}),        # nonzero FK with no side row (recoverable)
    "unknown_symbol": frozenset({"unavailable", "ambiguous"}),  # unreadable, or readable >1 way
    "join_ambiguous": frozenset({"ambiguous"}),            # >1 candidate join survives adjudication
    "index_zero": frozenset({"not_applicable"}),           # FK 0 == "no reference", not "missing"
}

# Fields whose null value MUST be explained by a readiness entry — a silent omission is exactly the
# ambiguity readiness exists to remove (design B5: the quantitative interlock reads these).
LOAD_BEARING_FIELDS = ("costs", "cooldown_ms", "gcd_ms")
# The ONLY manifest keys that may differ between the candidate and the final manifest.
CANDIDATE_MUTABLE_KEYS = frozenset({"publication_state", "validation", "budget"})


def policy_ref(table: str, field: str) -> str:
    """A JSON Pointer into coa-spell-layout-v2, e.g. '/tables/Spell/fields/power_type'. The ONLY thing a
    row carries to reference its policy; the policy supplies kind/proof/promotion/evidence."""
    if not table or not field:
        raise ValueError("policy_ref requires a table and a field")
    return f"/tables/{table}/fields/{field}"


def policy_ref_component(join_spec: dict, part: str) -> str:
    """Resolve a join component to its UNDERLYING table-field policy pointer via the join mapping — there
    is no synthetic /joins/... policy node. index -> Spell.<index_field>; side_id -> <side_table>.id;
    side_value -> <side_table>.<side_value_field>."""
    if part == "index":
        return policy_ref("Spell", join_spec["index_field"])
    if part == "side_id":
        return policy_ref(join_spec["side_table"], "id")
    if part == "side_value":
        return policy_ref(join_spec["side_table"], join_spec["side_value_field"])
    raise ValueError(f"join component {part!r} not in (index, side_id, side_value)")


def resolve_policy_ref(policy_doc: dict, ref: str) -> dict:
    """Resolve an RFC-6901 JSON Pointer against a policy document."""
    node = policy_doc
    for token in ref.split("/")[1:]:
        node = node[token.replace("~1", "/").replace("~0", "~")]
    return node
