# coa_client_extract/contracts.py
"""The frozen design-lock contracts for M1.14E0R.

The single authority the rest of E0R imports: policy-reference helpers, the closed readiness/reason-code
and icon-asset enumerations, the manifest trust-key sets, the named cross-child consistency checks, and
the structured `bound` shape. Nothing here has behavior beyond pure lookups so it can be imported by every
producer/validator without cycles.
"""
from __future__ import annotations

import hashlib
import json
import re
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


# === the GENERATION CONTRACT registry (E0R.2 T1.1) ===
# A generation's child set is a CONTRACT, not a name list: a name list cannot express cardinality, row
# schema, or shape, which is how a complete-but-EMPTY generation passed both validators at 02e0b7c.
#
# Revisions are IMMUTABLE files. A revision is written once and never edited; a change means a NEW file
# and a new registry entry. That is what keeps a generation published under an older revision
# independently resolvable after a later revision moves `current` — including the predecessor the
# publish transaction chains to, and any generation an operator would roll back to.
GENERATION_CONTRACT_SCHEMA = "coa-generation-contract-v1"
CONTRACT_INDEX_SCHEMA = "coa-generation-contract-index-v1"
GENERATION_CONTRACT_CHILD = "generation_contract.json"
CONTRACTS_DIR = Path(__file__).resolve().parent / "data" / "generation_contracts"

_TOP_LEVEL_KEYS = {"schema_version", "revision", "note", "observation_wire_schema", "children"}
_CHILD_KEYS = {"kind", "child_schema_version", "row_schema_version", "optional", "cardinality", "shape"}
# rule -> the EXACT key set its cardinality object must carry. Exact, not merely "no unknown keys":
# `single_document` carrying a `min` or a `source_table` is a contradiction a permissive check would
# wave through, leaving a rule that reads as bound but is evaluated against nothing.
_CARDINALITY_KEYS_BY_RULE = {
    "reviewed_bound_record_count": {"rule", "source_table"},
    "derived_from_source_topology": {"rule", "source_table"},
    "declared_derivation": {"rule", "source_table"},
    "declared_content_derivation": {"rule"},
    "equals_full_spell_records": {"rule"},
    "equals_is_coa_full_records": {"rule"},
    "single_document": {"rule"},
    "min": {"rule", "min"},
}
_SAFE_CHILD_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SAFE_REVISION_PATH = re.compile(r"^[a-z0-9][a-z0-9.-]*\.json$")

_REGISTRY_CACHE: dict | None = None
_CONTRACT_CACHE: dict[str, dict] = {}


class ContractError(Exception):
    """The generation contract (or its registry) is itself malformed, unsupported, or tampered with.
    A broken gate that loads is worse than no gate, so every path here fails closed."""


def canonical_sha256(doc: dict) -> str:
    """Canonical digest: sorted keys, no whitespace variance — key order and indentation must not change
    the hash, because a contract is staged (re-serialized) as a generation child and both languages
    re-derive this digest independently from the parsed document."""
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


# The contract digest IS the canonical digest; the alias names the intent at each call site.
generation_contract_sha256 = canonical_sha256


def validate_generation_contract(doc: dict) -> dict:
    """Self-validate a contract document. Returns it on success; raises ContractError otherwise."""
    if not isinstance(doc, dict):
        raise ContractError("contract must be an object")
    if doc.get("schema_version") != GENERATION_CONTRACT_SCHEMA:
        raise ContractError(f"contract schema_version {doc.get('schema_version')!r}")
    extra_top = set(doc) - _TOP_LEVEL_KEYS
    if extra_top:
        raise ContractError(f"contract has unexpected top-level key(s) {sorted(extra_top)}")
    if not isinstance(doc.get("revision"), str) or not doc["revision"]:
        raise ContractError("contract revision must be a non-empty string")
    wire = doc.get("observation_wire_schema")
    if not isinstance(wire, dict) or len(str(wire.get("sha256", ""))) != 64 \
            or not wire.get("schema_version"):
        raise ContractError("contract must pin the observation wire schema by schema_version + sha256")
    children = doc.get("children")
    if not isinstance(children, dict) or not children:
        raise ContractError("contract declares no children")
    seen_shapes: set[str] = set()
    for name, spec in children.items():
        if not _SAFE_CHILD_NAME.match(name):
            raise ContractError(f"unsafe child name {name!r}: plain filenames only, no path separators")
        if not isinstance(spec, dict):
            raise ContractError(f"child {name!r} spec must be an object")
        extra = set(spec) - _CHILD_KEYS
        if extra:
            raise ContractError(f"child {name!r} has unexpected_key(s) {sorted(extra)}")
        missing = _CHILD_KEYS - set(spec)
        if missing:
            raise ContractError(f"child {name!r} missing {sorted(missing)}")
        if spec["kind"] not in ("jsonl", "json"):
            raise ContractError(f"child {name!r} kind {spec['kind']!r}")
        if not isinstance(spec["child_schema_version"], str) or not spec["child_schema_version"]:
            raise ContractError(f"child {name!r} child_schema_version must be a non-empty string")
        if spec["kind"] == "jsonl":
            if not isinstance(spec["row_schema_version"], str) or not spec["row_schema_version"]:
                raise ContractError(f"child {name!r} jsonl child needs a row_schema_version")
        elif spec["row_schema_version"] is not None:
            raise ContractError(f"child {name!r} json child must have row_schema_version null")
        if not isinstance(spec["optional"], bool):
            raise ContractError(f"child {name!r} optional must be a boolean")
        if not isinstance(spec["shape"], str) or not spec["shape"]:
            raise ContractError(f"child {name!r} shape must name a validator")
        if spec["shape"] in seen_shapes:
            raise ContractError(f"shape {spec['shape']!r} is reused; each child needs its own shape")
        seen_shapes.add(spec["shape"])
        _validate_cardinality(name, spec["cardinality"])
    return doc


def _validate_cardinality(name: str, card) -> None:
    if not isinstance(card, dict):
        raise ContractError(f"child {name!r} cardinality must be an object")
    rule = card.get("rule")
    if rule not in _CARDINALITY_KEYS_BY_RULE:
        raise ContractError(f"child {name!r} cardinality rule {rule!r} is not a known rule")
    expected_keys = _CARDINALITY_KEYS_BY_RULE[rule]
    if set(card) != expected_keys:
        raise ContractError(
            f"child {name!r} cardinality for rule {rule!r} must have exactly {sorted(expected_keys)}, "
            f"got {sorted(card)}")
    if rule == "min":
        floor = card["min"]
        # `isinstance(True, int)` is True in Python — a boolean floor must not silently mean 1.
        if isinstance(floor, bool) or not isinstance(floor, int) or floor < 1:
            raise ContractError(f"child {name!r} min cardinality needs a positive integer floor")
    if "source_table" in expected_keys:
        if not isinstance(card["source_table"], str) or not card["source_table"]:
            raise ContractError(f"child {name!r} rule {rule!r} needs a non-empty source_table")


def validate_contract_registry(doc: dict) -> dict:
    """Self-validate the registry index. Returns it on success; raises ContractError otherwise."""
    if not isinstance(doc, dict):
        raise ContractError("contract registry must be an object")
    if doc.get("schema_version") != CONTRACT_INDEX_SCHEMA:
        raise ContractError(f"contract registry schema_version {doc.get('schema_version')!r}")
    extra = set(doc) - {"schema_version", "current", "supported", "note"}
    if extra:
        raise ContractError(f"contract registry has unexpected key(s) {sorted(extra)}")
    supported = doc.get("supported")
    if not isinstance(supported, dict) or not supported:
        raise ContractError("contract registry lists no supported revisions")
    for revision, entry in supported.items():
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise ContractError(
                f"registry entry {revision!r} must have exactly ['path', 'sha256'], got "
                f"{sorted(entry) if isinstance(entry, dict) else type(entry).__name__}")
        if not isinstance(entry["path"], str) or not _SAFE_REVISION_PATH.match(entry["path"]):
            raise ContractError(f"registry entry {revision!r} path {entry['path']!r} is unsafe")
        if not isinstance(entry["sha256"], str) or len(entry["sha256"]) != 64:
            raise ContractError(f"registry entry {revision!r} sha256 must be a 64-char digest")
    if doc.get("current") not in supported:
        raise ContractError(f"registry current {doc.get('current')!r} is not a supported revision")
    return doc


def load_contract_registry() -> dict:
    """The validated registry index. Cached: it is a frozen data file read per publish/resolve."""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is None:
        _REGISTRY_CACHE = validate_contract_registry(
            json.loads((CONTRACTS_DIR / "index.json").read_text(encoding="utf-8")))
    return _REGISTRY_CACHE


def load_supported_contract(revision: str, sha256: str) -> dict:
    """The trusted contract for `revision`, refused unless the registry supports it AND its canonical
    digest equals BOTH the caller's expectation and the registry's pin. Dispatching on the hash is what
    lets an older generation stay resolvable while `current` moves on."""
    registry = load_contract_registry()
    entry = registry["supported"].get(revision)
    if entry is None:
        raise ContractError(
            f"unsupported generation-contract revision {revision!r} "
            f"(supported: {sorted(registry['supported'])})")
    if revision not in _CONTRACT_CACHE:
        doc = validate_generation_contract(
            json.loads((CONTRACTS_DIR / entry["path"]).read_text(encoding="utf-8")))
        if doc["revision"] != revision:
            raise ContractError(f"contract file {entry['path']!r} declares revision {doc['revision']!r}")
        actual = generation_contract_sha256(doc)
        if actual != entry["sha256"]:
            raise ContractError(
                f"contract {revision!r} sha256 {actual[:16]} != registry pin {entry['sha256'][:16]}: the "
                "revision was edited in place; add a new revision instead")
        _CONTRACT_CACHE[revision] = doc
    if sha256 != entry["sha256"]:
        raise ContractError(
            f"contract {revision!r} sha256 {str(sha256)[:16]} != trusted {entry['sha256'][:16]}")
    return _CONTRACT_CACHE[revision]


def load_current_contract() -> tuple[str, dict]:
    """(revision, doc) for the revision the PRODUCER writes. Resolvers must NOT use this — see
    publish.required_children_for."""
    registry = load_contract_registry()
    revision = registry["current"]
    return revision, load_supported_contract(revision, registry["supported"][revision]["sha256"])


READINESS_STATUSES = frozenset({"available", "unavailable", "not_applicable", "ambiguous", "verified_empty"})
READINESS_REASON_CODES = frozenset({
    "pending_e1_operand", "join_ambiguous", "unknown_symbol", "side_row_missing",
    "index_zero", "no_static_anchor", "not_extracted", "proven_empty", "extracted",
})
# E0R.2 T2.5: `converted` (and its icon bundle) is PROHIBITED in this schema. It promised tar path
# containment, per-entry bundle-manifest verification, and per-asset content hashes checked against the
# catalog; E0R.1 shipped only an existence test for the bundle child, and no producer ever emitted the
# status. An unverifiable status with no producer is not a feature. Reintroducing it requires ALL THREE
# of those checks in the SAME change, plus a producer — until then no producer may emit it and no
# validator may accept it.
ICON_ASSET_STATUSES = frozenset({"source_only", "missing", "placeholder"})

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
