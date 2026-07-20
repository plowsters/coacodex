from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .contracts import BOUND_HEADER_FIELDS, BOUND_SOURCE_FIELDS
from .spell_proof import PROOF_STATES

SCHEMA = "coa-spell-layout-v2"
_KINDS = ("int32", "uint32", "float", "string")
_PROMOTIONS = ("normalized", "raw_only")
_DATA_DIR = Path(__file__).resolve().parent / "data"


class SpellPolicyError(ValueError):
    """A spell-layout policy failed schema/identity/hash validation. A ValueError because an
    invalid policy is an authoring bug, not client drift."""


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(obj) -> str:
    return hashlib.sha256(_canon(obj)).hexdigest()


@dataclass(frozen=True)
class FieldPolicy:
    """Per-value adjudication. `cell` is None until the value's column is proven (recon fills the
    proposed delta; a human authors it here). `promotion` makes raw-only status EXPLICIT rather than
    inferred from facets, so a deliberately raw-only field (e.g. description: interpretation reference)
    is distinguishable from an un-adjudicated one."""
    cell: int | None
    kind: str
    layout: str
    interpretation: str
    promotion: str
    evidence: str


@dataclass(frozen=True)
class JoinPolicy:
    index_field: str      # a Spell column holding the FK into the side table
    side_table: str       # e.g. "SpellCastTimes"
    side_value_field: str # the side-table column carrying the resolved value (e.g. "base_ms")
    promotion: str        # "normalized" | "raw_only" — whether the emitted join value is authorized


@dataclass(frozen=True)
class SpellPolicy:
    schema_version: str
    reviewed: bool
    bound: dict | None
    sha256: str
    tables: dict[str, dict]        # table -> {"expected_field_count": int, "fields": {name: FieldPolicy}}
    joins: dict[str, JoinPolicy]   # emitted_value -> JoinPolicy
    required_tables: tuple[str, ...]
    expected_absent: tuple[str, ...]
    anchor_set: dict
    _enum: dict

    # -- recon-facing views (spell_mechanics.recon_spell_mechanics consumes these) --
    @property
    def columns(self) -> dict[str, int]:
        return {n: fp.cell for n, fp in self.tables["Spell"]["fields"].items() if fp.cell is not None}

    @property
    def index_fields(self) -> dict[str, str]:
        # index_field -> side_table, ONLY for joins whose index cell is adjudicated (non-null).
        # An un-adjudicated join (null cell) is documented in the schema but not re-checked by
        # recon: a plain FK-validity scan cannot uniquely resolve these columns (empirically dozens
        # of small-int columns coincidentally fall in a side table's id range), so their promotion
        # awaits value-anchor disambiguation. range_min/max share range_index -> SpellRange; dedups.
        out: dict[str, str] = {}
        for j in self.joins.values():
            if self.tables["Spell"]["fields"][j.index_field].cell is not None:
                out[j.index_field] = j.side_table
        return out

    @property
    def enum_policy(self) -> dict:
        return {"power_types": frozenset(self._enum["power_types"]),
                "school_bits": frozenset(self._enum["school_bits"])}

    @property
    def anchors(self) -> list[dict]:
        return list(self.anchor_set["spells"])

    @property
    def anchor_sha256(self) -> str | None:
        return self.anchor_set.get("sha256")

    @property
    def enum_sha256(self) -> str:
        return compute_policy_sha256(self._enum)


def _validate_field(table: str, name: str, spec: dict, field_count: int) -> FieldPolicy:
    for key in ("cell", "kind", "layout", "interpretation", "promotion", "evidence"):
        if key not in spec:
            raise SpellPolicyError(f"{table}.{name}: missing {key!r}")
    cell = spec["cell"]
    if cell is not None:
        if type(cell) is not int or isinstance(cell, bool) or not (0 <= cell < field_count):
            raise SpellPolicyError(f"{table}.{name}: cell {cell!r} out of [0,{field_count})")
    if spec["kind"] not in _KINDS:
        raise SpellPolicyError(f"{table}.{name}: kind {spec['kind']!r} not in {_KINDS}")
    for facet in ("layout", "interpretation"):
        if spec[facet] not in PROOF_STATES:
            raise SpellPolicyError(f"{table}.{name}: {facet} {spec[facet]!r} not a proof state")
    if spec["promotion"] not in _PROMOTIONS:
        raise SpellPolicyError(f"{table}.{name}: promotion {spec['promotion']!r} not in {_PROMOTIONS}")
    if not isinstance(spec["evidence"], str) or not spec["evidence"].strip():
        raise SpellPolicyError(f"{table}.{name}: evidence must be a non-empty string")
    # A normalized field MUST be fully proven; raw-only may keep reference/unproven facets.
    if spec["promotion"] == "normalized":
        if spec["layout"] != "verified" or spec["interpretation"] != "verified":
            raise SpellPolicyError(f"{table}.{name}: promotion 'normalized' requires verified layout+interpretation")
        if cell is None:
            raise SpellPolicyError(f"{table}.{name}: promotion 'normalized' requires a proven cell")
    return FieldPolicy(cell, spec["kind"], spec["layout"], spec["interpretation"],
                       spec["promotion"], spec["evidence"])


def _validate_bound(bound: dict) -> dict:
    """The structured A2 bound: per-table sha256 + full 5-field header + logical source (member,
    effective_archive, patch_chain). Rejects the flat E0 shape so a stale flat bound cannot slip through."""
    if "source_dbc_sha256" in bound:
        raise SpellPolicyError("bound uses the flat source_dbc_sha256 shape; E0R requires bound.tables{}")
    if not isinstance(bound.get("client_build"), str):
        raise SpellPolicyError("bound.client_build must be a string")
    tables = bound.get("tables")
    if not isinstance(tables, dict) or not tables:
        raise SpellPolicyError("bound.tables must be a non-empty dict")
    for tname, spec in tables.items():
        if not isinstance(spec.get("sha256"), str) or len(spec["sha256"]) != 64:
            raise SpellPolicyError(f"bound.tables.{tname}.sha256 must be a 64-char hex digest")
        header = spec.get("header", {})
        for h in BOUND_HEADER_FIELDS:
            if h not in header:
                raise SpellPolicyError(f"bound.tables.{tname}.header missing {h!r}")
        source = spec.get("source", {})
        for s in BOUND_SOURCE_FIELDS:
            if s not in source:
                raise SpellPolicyError(f"bound.tables.{tname}.source missing {s!r}")
        if os.path.isabs(str(source["effective_archive"])):
            raise SpellPolicyError(f"bound.tables.{tname}.source.effective_archive must be a logical name")
    return bound


def load_spell_policy(payload: dict) -> SpellPolicy:
    if payload.get("schema_version") != SCHEMA:
        raise SpellPolicyError(f"schema_version must be {SCHEMA!r} (coa-spell-layout-v2)")
    if not isinstance(payload.get("reviewed"), bool):
        raise SpellPolicyError("reviewed must be a bool")

    raw_tables = payload.get("tables")
    if not isinstance(raw_tables, dict) or "Spell" not in raw_tables:
        raise SpellPolicyError("tables must be a dict including 'Spell'")
    tables: dict[str, dict] = {}
    for tname, tspec in raw_tables.items():
        fc = tspec.get("expected_field_count")
        if type(fc) is not int or fc <= 0:
            raise SpellPolicyError(f"{tname}: expected_field_count must be a positive int")
        key_cell = tspec.get("key_cell")
        if type(key_cell) is not int or isinstance(key_cell, bool) or not (0 <= key_cell < fc):
            raise SpellPolicyError(f"{tname}: key_cell {key_cell!r} out of [0,{fc})")
        unique = tspec.get("unique")
        if not isinstance(unique, bool):
            raise SpellPolicyError(f"{tname}: unique must be a bool")
        fields, seen_cells = {}, {}
        for fname, fspec in tspec.get("fields", {}).items():
            fp = _validate_field(tname, fname, fspec, fc)
            if fp.cell is not None:
                if fp.cell in seen_cells:
                    raise SpellPolicyError(f"{tname}: cell {fp.cell} reused by {seen_cells[fp.cell]!r} and {fname!r}")
                seen_cells[fp.cell] = fname
            fields[fname] = fp
        tables[tname] = {"expected_field_count": fc, "key_cell": key_cell, "unique": unique, "fields": fields}

    # joins reference real Spell index columns + real side tables/value columns
    joins: dict[str, JoinPolicy] = {}
    for jname, jspec in payload.get("joins", {}).items():
        idx, side, val = jspec.get("index_field"), jspec.get("side_table"), jspec.get("side_value_field")
        promo = jspec.get("promotion")
        if idx not in tables["Spell"]["fields"]:
            raise SpellPolicyError(f"join {jname}: index_field {idx!r} not a Spell field")
        if side not in tables:
            raise SpellPolicyError(f"join {jname}: side_table {side!r} not defined")
        if val not in tables[side]["fields"]:
            raise SpellPolicyError(f"join {jname}: side_value_field {val!r} not in {side}")
        if "id" not in tables[side]["fields"]:
            raise SpellPolicyError(f"join {jname}: side_table {side!r} has no 'id' field")
        if promo not in _PROMOTIONS:
            raise SpellPolicyError(f"join {jname}: promotion {promo!r} not in {_PROMOTIONS}")
        if promo == "normalized":
            # A normalized join emits only when every contributing component is itself normalized.
            for role, tbl, fname in (("index", "Spell", idx), ("side_id", side, "id"), ("side_value", side, val)):
                if tables[tbl]["fields"][fname].promotion != "normalized":
                    raise SpellPolicyError(f"join {jname}: normalized join has a raw_only component {fname}")
        joins[jname] = JoinPolicy(idx, side, val, promo)

    enum = payload.get("enum_policy", {})
    power_types, school_bits = enum.get("power_types"), enum.get("school_bits")
    if not isinstance(power_types, list) or not isinstance(school_bits, list):
        raise SpellPolicyError("enum_policy.power_types and school_bits must be lists")
    for b in school_bits:
        if type(b) is not int or isinstance(b, bool) or b <= 0 or b >= 2**32 or (b & (b - 1)) != 0:
            raise SpellPolicyError(f"enum_policy.school_bits {b!r} is not a distinct power of two < 2**32")
    if len(set(school_bits)) != len(school_bits):
        raise SpellPolicyError("enum_policy.school_bits must be distinct")
    if compute_policy_sha256(enum) != enum.get("sha256"):
        raise SpellPolicyError("enum_policy.sha256 mismatch")

    anchor_set = payload.get("anchor_set", {})
    if not isinstance(anchor_set.get("spells"), list) or not anchor_set["spells"]:
        raise SpellPolicyError("anchor_set.spells must be a non-empty list")
    if compute_policy_sha256(anchor_set) != anchor_set.get("sha256"):
        raise SpellPolicyError("anchor_set.sha256 mismatch")

    required_tables = tuple(payload.get("required_tables", []))
    expected_absent = tuple(payload.get("expected_absent", []))
    bound = payload.get("bound")
    if bound is not None:
        _validate_bound(bound)
        if set(bound["tables"]) != set(required_tables):
            raise SpellPolicyError("bound.tables must equal required_tables (every required table is bound)")
        if set(bound.get("expected_absent", [])) != set(expected_absent):
            raise SpellPolicyError("bound.expected_absent must equal the policy expected_absent set")

    declared = payload.get("sha256")
    recomputed = _sha({k: v for k, v in payload.items() if k != "sha256"})
    if declared != recomputed:
        raise SpellPolicyError("policy sha256 mismatch (document was edited without rehashing)")

    return SpellPolicy(
        schema_version=SCHEMA, reviewed=payload["reviewed"], bound=bound, sha256=recomputed,
        tables=tables, joins=joins,
        required_tables=required_tables,
        expected_absent=expected_absent,
        anchor_set=anchor_set, _enum={"power_types": power_types, "school_bits": school_bits},
    )


def compute_policy_sha256(payload: dict) -> str:
    """The canonical policy hash the authoring tool writes into the 'sha256' field."""
    return _sha({k: v for k, v in payload.items() if k != "sha256"})


def load_default_policy(*, root: Path | None = None) -> SpellPolicy:
    path = (root or _DATA_DIR) / "spell_layout_v2.json"
    return load_spell_policy(json.loads(path.read_text(encoding="utf-8")))
