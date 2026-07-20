# coa_client_extract/contracts.py
"""The frozen design-lock contracts for M1.14E0R.

The single authority the rest of E0R imports: policy-reference helpers, the closed readiness/reason-code
and icon-asset enumerations, the manifest trust-key sets, the named cross-child consistency checks, and
the structured `bound` shape. Nothing here has behavior beyond pure lookups so it can be imported by every
producer/validator without cycles.
"""
from __future__ import annotations

READINESS_STATUSES = frozenset({"available", "unavailable", "not_applicable", "ambiguous", "verified_empty"})
READINESS_REASON_CODES = frozenset({
    "pending_e1_operand", "join_ambiguous", "unknown_symbol", "side_row_missing",
    "index_zero", "no_static_anchor", "not_extracted", "proven_empty",
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
READINESS_INVARIANTS = {
    "available": (False, False, False), "verified_empty": (False, False, True),
    "not_applicable": (True, False, False), "unavailable": (True, True, False),
    "ambiguous": (True, True, False),
}
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
